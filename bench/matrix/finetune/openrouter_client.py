"""T9 : client OpenRouter minimal avec garde-fou de dépense, bibliothèque standard seulement.

    from openrouter_client import Ledger, OpenRouter, read_key, load_prices
    ledger = Ledger(Path("spend-bench.jsonl"), cap_usd=1.5)
    api = OpenRouter(read_key(), ledger, load_prices(models_json))
    api.check_key(global_cap=4.8)          # avant chaque lot
    text, rec = api.chat(model, messages, max_tokens=64)

Chaque appel réserve d'abord une borne haute de son coût (entrée estimée à 2 caractères par jeton,
sortie au plafond max_tokens) et refuse de partir si dépense + réservations + borne dépasse le
plafond. Le coût réel se lit dans `usage.cost`, sinon dans /api/v1/generation, sinon prix × jetons.
Un délai dépassé compte la borne comme dépensée : la génération a pu être facturée.
Le journal (une ligne JSON par appel) ne contient ni la clé ni aucun texte, seulement des comptes.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://openrouter.ai/api/v1"
KEY_PATH = Path.home() / ".config" / "steph" / "openrouter.key"
CHARS_PER_TOKEN_FLOOR = 2.0  # borne basse : le français et les sorties de terminal font 3 à 4 car./jeton
TOKENS_PER_MESSAGE = 8
PRICE_MARGIN = 1.5  # le fournisseur servi peut facturer plus que le prix affiché du modèle


class BudgetExceeded(RuntimeError):
    pass


class HTTPFailure(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def read_key(path: Path = KEY_PATH) -> str:
    return Path(path).read_text().strip()


def load_prices(models: list[dict]) -> dict[str, tuple[float, float]]:
    """Prix par jeton (entrée, sortie) depuis la liste de /api/v1/models."""
    return {m["id"]: (float(m["pricing"]["prompt"]), float(m["pricing"]["completion"])) for m in models}


def urllib_transport(method: str, url: str, headers: dict, body: dict | None, timeout: float) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data, {**headers, "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise HTTPFailure(e.code, e.read().decode(errors="replace")) from None


class Ledger:
    """Dépense cumulée d'une phase, persistée en jsonl ; réservations en mémoire (un seul processus)."""

    def __init__(self, path: Path, cap_usd: float):
        self.path = Path(path)
        self.cap = cap_usd
        self.lock = threading.Lock()
        self.reserved = 0.0
        self.spent = 0.0
        self.calls = 0
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self.spent += json.loads(line)["cost"]
                    self.calls += 1

    def reserve(self, amount: float) -> None:
        with self.lock:
            if self.spent + self.reserved + amount > self.cap:
                raise BudgetExceeded(f"plafond {self.cap:.4f} $ : dépensé {self.spent:.6f}, réservé "
                                     f"{self.reserved:.6f}, appel jusqu'à {amount:.6f}")
            self.reserved += amount

    def settle(self, reserved: float, record: dict | None) -> None:
        with self.lock:
            self.reserved = max(0.0, self.reserved - reserved)
            if record is None:
                return
            self.spent += record["cost"]
            self.calls += 1
            with open(self.path, "a") as f:
                f.write(json.dumps(record) + "\n")


class OpenRouter:
    def __init__(self, key: str, ledger: Ledger, prices: dict[str, tuple[float, float]], transport=urllib_transport,
                 timeout: float = 120.0):
        self._key = key
        self.ledger = ledger
        self.prices = prices
        self.transport = transport
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key}"}

    def estimate(self, model: str, messages: list[dict], max_tokens: int) -> float:
        if model not in self.prices:
            raise BudgetExceeded(f"prix inconnu pour {model} : appel refusé")
        pin, pout = self.prices[model]
        chars = sum(len(m["content"]) for m in messages)
        tokens_in = math.ceil(chars / CHARS_PER_TOKEN_FLOOR) + TOKENS_PER_MESSAGE * len(messages)
        return (tokens_in * pin + max_tokens * pout) * PRICE_MARGIN

    def check_key(self, global_cap: float) -> float:
        """Dépense du compte vue par OpenRouter ; refuse le lot si elle atteint le plafond global."""
        usage = float(self.transport("GET", f"{BASE}/key", self._headers(), None, 30)["data"]["usage"])
        if usage >= global_cap:
            raise BudgetExceeded(f"compte OpenRouter : {usage:.4f} $ dépensés, plafond global {global_cap} $")
        return usage

    def _real_cost(self, model: str, resp: dict) -> tuple[float, str]:
        usage = resp.get("usage") or {}
        if usage.get("cost") is not None:
            return float(usage["cost"]), "usage.cost"
        if resp.get("id"):
            try:
                gen = self.transport("GET", f"{BASE}/generation?id={resp['id']}", self._headers(), None, 30)
                return float(gen["data"]["total_cost"]), "generation"
            except (HTTPFailure, KeyError, TypeError, ValueError, OSError):
                pass
        pin, pout = self.prices[model]
        return usage.get("prompt_tokens", 0) * pin + usage.get("completion_tokens", 0) * pout, "price"

    def chat(self, model: str, messages: list[dict], max_tokens: int, **params) -> tuple[str, dict]:
        est = self.estimate(model, messages, max_tokens)
        self.ledger.reserve(est)
        pin, pout = self.prices[model]
        # sans ce plafond, le tri par prix d'entrée choisit un fournisseur dont la sortie coûte 8 fois le prix
        # affiché (mesuré : Relace sur deepseek-v4-flash) et la borne réservée n'en est plus une
        provider = {**params.pop("provider", {}),
                    "max_price": {"prompt": pin * 1e6 * PRICE_MARGIN, "completion": pout * 1e6 * PRICE_MARGIN}}
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "usage": {"include": True},
                "provider": provider, **params}
        t0 = time.time()
        try:
            resp = self.transport("POST", f"{BASE}/chat/completions", self._headers(), body, self.timeout)
        except HTTPFailure:
            self.ledger.settle(est, None)
            raise
        except Exception:
            self.ledger.settle(est, {"ts": round(t0), "model": model, "cost": est, "source": "estimate-timeout",
                                     "prompt_tokens": None, "completion_tokens": None})
            raise
        cost, source = self._real_cost(model, resp)
        usage = resp.get("usage") or {}
        record = {"ts": round(t0), "model": model, "cost": cost, "source": source,
                  "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                  "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                  "provider": resp.get("provider"), "wall_s": round(time.time() - t0, 2)}
        self.ledger.settle(est, record)
        if "error" in resp and not resp.get("choices"):
            raise HTTPFailure(int(resp["error"].get("code") or 0), str(resp["error"].get("message")))
        content = resp["choices"][0]["message"].get("content") or ""
        return content, record
