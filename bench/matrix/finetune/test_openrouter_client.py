"""Tests du garde-fou de dépense OpenRouter (T9) : aucun réseau, transport simulé."""

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import openrouter_client as oc  # noqa: E402

KEY = "sk-or-v1-secret-test-key"
PRICES = {"m/cheap": (1e-7, 4e-7)}  # USD par jeton : entrée, sortie


class FakeTransport:
    """Répond comme OpenRouter ; `calls` garde (méthode, url) pour vérifier ce qui est parti."""

    def __init__(self, usage=None, key_usage=0.0, generation_cost=None, fail=None):
        self.usage = usage if usage is not None else {"prompt_tokens": 1000, "completion_tokens": 30, "cost": 0.00012}
        self.key_usage = key_usage
        self.generation_cost = generation_cost
        self.fail = fail
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url))
        assert headers["Authorization"] == f"Bearer {KEY}"
        if url.endswith("/key"):
            return {"data": {"usage": self.key_usage, "limit": None}}
        if "/generation" in url:
            if self.generation_cost is None:
                raise oc.HTTPFailure(404, "not found")
            return {"data": {"total_cost": self.generation_cost}}
        if self.fail:
            raise self.fail
        return {"id": "gen-1", "choices": [{"message": {"content": "Succès. 3 fichiers."}}], "usage": dict(self.usage)}


def client(tmp_path, cap=1.0, **kw):
    ledger = oc.Ledger(tmp_path / "ledger.jsonl", cap)
    return oc.OpenRouter(KEY, ledger, PRICES, transport=FakeTransport(**kw))


MSGS = [{"role": "system", "content": "s" * 400}, {"role": "user", "content": "u" * 2000}]


def test_cost_comes_from_usage_cost(tmp_path):
    c = client(tmp_path)
    text, rec = c.chat("m/cheap", MSGS, max_tokens=64)
    assert text == "Succès. 3 fichiers."
    assert rec["cost"] == pytest.approx(0.00012)
    assert rec["source"] == "usage.cost"
    assert c.ledger.spent == pytest.approx(0.00012)


def test_cost_falls_back_to_generation_endpoint(tmp_path):
    c = client(tmp_path, usage={"prompt_tokens": 1000, "completion_tokens": 30}, generation_cost=0.0005)
    _, rec = c.chat("m/cheap", MSGS, max_tokens=64)
    assert rec["cost"] == pytest.approx(0.0005)
    assert rec["source"] == "generation"


def test_cost_falls_back_to_price_times_tokens(tmp_path):
    c = client(tmp_path, usage={"prompt_tokens": 1000, "completion_tokens": 30})
    _, rec = c.chat("m/cheap", MSGS, max_tokens=64)
    assert rec["cost"] == pytest.approx(1000 * 1e-7 + 30 * 4e-7)
    assert rec["source"] == "price"


def test_refuses_call_that_would_exceed_cap_without_sending(tmp_path):
    c = client(tmp_path, cap=0.0001)  # estimation > 1e-4 : 2400 car. d'entrée + 64 jetons de sortie
    with pytest.raises(oc.BudgetExceeded):
        c.chat("m/cheap", MSGS, max_tokens=64)
    assert not [u for _, u in c.transport.calls if u.endswith("/chat/completions")]
    assert c.ledger.spent == 0


def test_estimate_is_an_upper_bound_of_the_real_price(tmp_path):
    c = client(tmp_path)
    est = c.estimate("m/cheap", MSGS, 64)
    assert est >= (2400 / 4) * 1e-7 + 64 * 4e-7


def test_unknown_model_price_is_refused(tmp_path):
    c = client(tmp_path)
    with pytest.raises(oc.BudgetExceeded):
        c.chat("m/unknown", MSGS, max_tokens=64)


def test_spent_survives_restart(tmp_path):
    c = client(tmp_path)
    c.chat("m/cheap", MSGS, max_tokens=64)
    c.chat("m/cheap", MSGS, max_tokens=64)
    again = oc.Ledger(tmp_path / "ledger.jsonl", 1.0)
    assert again.spent == pytest.approx(0.00024)
    assert again.calls == 2


def test_cap_counts_spending_of_previous_runs(tmp_path):
    c = client(tmp_path, cap=0.0003, usage={"prompt_tokens": 10, "completion_tokens": 1, "cost": 0.00029})
    c.chat("m/cheap", MSGS[1:], max_tokens=4)
    c2 = oc.OpenRouter(KEY, oc.Ledger(tmp_path / "ledger.jsonl", 0.0003), PRICES, transport=c.transport)
    with pytest.raises(oc.BudgetExceeded):
        c2.chat("m/cheap", MSGS[1:], max_tokens=4)


def test_reservations_block_concurrent_overshoot(tmp_path):
    ledger = oc.Ledger(tmp_path / "ledger.jsonl", 1.0)
    ledger.reserve(0.6)
    with pytest.raises(oc.BudgetExceeded):
        ledger.reserve(0.5)


def test_http_error_releases_reservation(tmp_path):
    c = client(tmp_path, fail=oc.HTTPFailure(400, "bad request"))
    with pytest.raises(oc.HTTPFailure):
        c.chat("m/cheap", MSGS, max_tokens=64)
    assert c.ledger.spent == 0
    assert c.ledger.reserved == 0


def test_timeout_counts_the_estimate_as_spent(tmp_path):
    c = client(tmp_path, fail=TimeoutError("read timeout"))
    est = c.estimate("m/cheap", MSGS, 64)
    with pytest.raises(TimeoutError):
        c.chat("m/cheap", MSGS, max_tokens=64)
    assert c.ledger.spent == pytest.approx(est)
    assert c.ledger.reserved == 0


def test_check_key_refuses_when_account_usage_reaches_global_cap(tmp_path):
    c = client(tmp_path, key_usage=4.81)
    with pytest.raises(oc.BudgetExceeded):
        c.check_key(global_cap=4.8)


def test_check_key_returns_usage_under_cap(tmp_path):
    c = client(tmp_path, key_usage=1.2)
    assert c.check_key(global_cap=4.8) == pytest.approx(1.2)


def test_ledger_never_holds_the_key_nor_text(tmp_path):
    c = client(tmp_path)
    c.chat("m/cheap", MSGS, max_tokens=64)
    raw = (tmp_path / "ledger.jsonl").read_text()
    assert KEY not in raw
    assert "Succès" not in raw and "uuuu" not in raw
    rec = json.loads(raw.splitlines()[0])
    assert rec["model"] == "m/cheap" and rec["prompt_tokens"] == 1000


def test_threads_never_exceed_cap(tmp_path):
    # chaque appel coûte au plus son estimation : sous plafond serré, 20 fils ne dépassent jamais
    usage = {"prompt_tokens": 1000, "completion_tokens": 30, "cost": 0.0001}
    c = client(tmp_path, cap=0.002, usage=usage)
    errors = []

    def go():
        try:
            c.chat("m/cheap", MSGS, max_tokens=64)
        except oc.BudgetExceeded:
            errors.append(1)

    ts = [threading.Thread(target=go) for _ in range(20)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errors
    assert c.ledger.spent <= 0.002


def test_read_key_strips_and_never_logs(tmp_path):
    p = tmp_path / "k"
    p.write_text(KEY + "\n")
    assert oc.read_key(p) == KEY


def test_request_caps_provider_price_to_the_estimate_margin(tmp_path):
    # un fournisseur au prix d'entrée bas mais à la sortie chère (Relace : x8) ne doit pas être choisi :
    # max_price garde le coût réel sous la borne réservée
    bodies = []
    t = FakeTransport()
    orig = t.__call__

    def spy(method, url, headers, body, timeout):
        if body is not None:
            bodies.append(body)
        return orig(method, url, headers, body, timeout)

    c = oc.OpenRouter(KEY, oc.Ledger(tmp_path / "l.jsonl", 1.0), PRICES, transport=spy)
    c.chat("m/cheap", MSGS, max_tokens=64, provider={"sort": "price"})
    mp = bodies[0]["provider"]["max_price"]
    assert mp["prompt"] == pytest.approx(0.1 * oc.PRICE_MARGIN)
    assert mp["completion"] == pytest.approx(0.4 * oc.PRICE_MARGIN)
    assert bodies[0]["provider"]["sort"] == "price"
