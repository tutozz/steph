"""P14a : latence du chemin complet de steph (fin de commande -> premier son -> premier
fait utile) sur les 36 cas historiques du banc, avec un vrai LLM (llama-server local) et
un vrai Speaker (Piper). Rejoue chaque cas dans le vrai `Narrator._finish`/`_llm_say` de
`src/steph/narrator.py`, sans modifier aucun fichier du dépôt.

Écart volontaire face à la production : en production `narrator` construit les messages
via `prompts.summary_messages` (SUMMARY_SYSTEM, prompt long avec exemples) alors que le
modèle affiné actuel a appris TRAIN_SYSTEM (prompt court de `bench/matrix/finetune/label.py`,
sujet de P18/B3). Pour cette mesure de latence, `prompts.summary_messages` est monkeypatché
EN MÉMOIRE (aucun fichier touché) pour renvoyer TRAIN_SYSTEM comme message système, avec le
même tour utilisateur (digest + statut + durée) que la production. Toute la mécanique réelle
de `_finish`/`_llm_say` (verbatim court, digest.resolve, digest+LLM, masquage P9, garde-fou
d'ancrage P13, TTS Piper) tourne sans modification.

Deux temps mesurés par cas, depuis l'instant où le harnais appelle `_finish` (= fin de
commande simulée) :
  - premier_son_s   : premier octet audio réellement écrit vers le lecteur (paplay), quelle
                       que soit sa source (préfixe de statut P9, préfixe de durée, ou phrase
                       de digest.resolve) ;
  - premier_fait_utile_s : premier octet audio portant du contenu du modèle ou de resolve()
                       (donc après le tampon d'ancrage P13 et après tout préfixe synthétique).

Usage :
    PYTHONPATH=<dossier contenant steph/> \
    <venv-piper>/bin/python3 p14a_harness.py \
        --model /root/stephbench-ft/models/granite-soup-Q4_K_M.gguf \
        --llama-server /root/stephbench-g2/bin/llama-b11205/llama-server \
        --voice /root/stephbench-ft/voices/fr_FR-siwis-medium.onnx \
        --fixtures-dir /root/p14a-work/fixtures \
        --out /root/p14a-work/out/p14a-latency.json \
        --pulse-server unix:/run/user/1000/pulse/native
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time


def build_fixture_table(fixtures_dir: str) -> list[dict]:
    fx = json.load(open(os.path.join(fixtures_dir, "fixtures.json"), encoding="utf-8"))
    fx += json.load(open(os.path.join(fixtures_dir, "extra_fixtures.json"), encoding="utf-8"))
    byid = {}
    for i, f in enumerate(fx):
        cid = f.get("id") or f"fx{i:02d}"
        byid[cid] = f
    df = open(os.path.join(fixtures_dir, "df_proxmox.txt"), encoding="utf-8").read()
    ipa = open(os.path.join(fixtures_dir, "ip_a_proxmox.txt"), encoding="utf-8").read()
    byid["df_proxmox"] = {"cmd": "df -h", "exit": 0, "duration": 0.1, "output": df}
    byid["ip_a_proxmox"] = {"cmd": "ip a", "exit": 0, "duration": 0.1, "output": ipa}
    ids = [f"fx{i:02d}" for i in range(31)] + ["df_proxmox", "ip_a_proxmox"]
    return [{"id": cid, **byid[cid]} for cid in ids]


def percentile(values: list[float], p: float) -> float:
    """Interpolation linéaire, méthode habituelle (numpy 'linear')."""
    if not values:
        return float("nan")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--llama-server", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--fixtures-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--speech-log", default="")
    ap.add_argument("--pulse-server", default="")
    ap.add_argument("--port", type=int, default=8971)
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--case-timeout", type=float, default=60.0)
    ap.add_argument("--steph-src", default="", help="dossier contenant le paquet steph/ (sinon PYTHONPATH déjà positionné)")
    args = ap.parse_args()

    if args.steph_src:
        sys.path.insert(0, args.steph_src)
    if args.pulse_server:
        os.environ["PULSE_SERVER"] = args.pulse_server

    from steph.config import Config
    from steph.session import Session
    from steph.llm import LLM
    from steph.tts import Speaker, SENTENCE_END
    from steph.narrator import Narrator, fmt_duration
    from steph.strings import t as _t
    import steph.audio as audio_mod
    import steph.prompts as prompts_mod
    import steph.digest as digest_mod

    # ---------------------------------------------------------------- TRAIN_SYSTEM
    # Copié tel quel depuis bench/matrix/finetune/label.py (source de vérité de
    # l'entraînement) : jamais réécrit ici.
    TRAIN_SYSTEM = (
        "Tu lis la sortie d'une commande de terminal et tu dis à voix haute l'essentiel, en français. "
        "Réponds par une seule ligne courte, 15 mots au plus : d'abord le résultat, puis un détail utile. "
        "Recopie les noms et les nombres exactement comme dans la sortie. Si une information n'est pas "
        "écrite dans la sortie, ne la donne pas : n'invente jamais."
    )

    _orig_summary_messages = prompts_mod.summary_messages

    def _train_summary_messages(cmd, exit_code, duration, output, nlines, cwd="", language="fr"):
        msgs = _orig_summary_messages(cmd, exit_code, duration, output, nlines, cwd, language=language)
        msgs[0] = {"role": "system", "content": TRAIN_SYSTEM}
        return msgs

    prompts_mod.summary_messages = _train_summary_messages  # narrator.py lit prompts.summary_messages à l'appel

    # ---------------------------------------------------------------- instrumentation audio
    # Horodate le premier octet PCM réellement écrit vers paplay, pour chaque phrase TTS
    # (une Popen par phrase, dans l'ordre où `tts.Speaker._run` les joue).
    writes: list[float] = []
    write_lock = threading.Lock()
    _orig_popen_quiet = audio_mod.popen_quiet

    class _TimestampedStdin:
        def __init__(self, real, cb):
            self._real, self._cb, self._fired = real, cb, False

        def write(self, data):
            if not self._fired:
                self._fired = True
                self._cb()
            return self._real.write(data)

        def flush(self):
            return self._real.flush()

        def close(self):
            return self._real.close()

    def _popen_quiet_patched(cmd, stdin=None):
        proc = _orig_popen_quiet(cmd, stdin=stdin)
        if proc.stdin is not None:
            def cb():
                with write_lock:
                    writes.append(time.time())
            proc.stdin = _TimestampedStdin(proc.stdin, cb)
        return proc

    audio_mod.popen_quiet = _popen_quiet_patched

    # ---------------------------------------------------------------- config réelle
    cfg = Config()
    cfg.model = args.model
    cfg.llama_server = args.llama_server
    cfg.llm_port = args.port
    cfg.llm_ctx = args.ctx
    cfg.llm_extra_args = ["-t", str(args.threads)]
    cfg.voice = args.voice
    cfg.tts_enabled = True
    cfg.speech_log = args.speech_log

    session = Session()
    llm = LLM(cfg)
    print(f"lancement de llama-server sur le port {args.port}…", file=sys.stderr)
    if not llm.ensure_server(90):
        print("llama-server n'a pas démarré, voir", llm.logfile, file=sys.stderr)
        return 1
    print("llama-server prêt.", file=sys.stderr)

    speaker = Speaker(cfg)  # charge la voix Piper (warm_up() inclus)
    narrator = Narrator(cfg, session, speaker, llm)

    # spy sur _llm_say (instance seulement) : capture le préfixe P9 réellement utilisé,
    # sans changer son comportement (délègue à la vraie méthode liée).
    captured: dict = {}
    _orig_llm_say = narrator._llm_say

    def _spy_llm_say(msgs, fallback, prefix="", max_tokens=90, on_done=None, interrupt=True, tag="", strip_status=False):
        captured["prefix"] = prefix
        captured["msgs"] = msgs
        return _orig_llm_say(msgs, fallback, prefix=prefix, max_tokens=max_tokens, on_done=on_done,
                              interrupt=interrupt, tag=tag, strip_status=strip_status)

    narrator._llm_say = _spy_llm_say

    # ---------------------------------------------------------------- amorçage (non mesuré)
    t_warm = time.time()
    narrator.warm_system_prompts()  # cache slot 0 : préfixe système (patché en TRAIN_SYSTEM)
    narrator._llm_ok()  # marque llm_ready, hors mesure
    warm_llm_s = time.time() - t_warm

    writes.clear()
    done_evt = threading.Event()
    speaker.say("Test d'amorçage, un deux trois.", on_done=lambda t: done_evt.set())
    done_evt.wait(30)
    while speaker.speaking.is_set() or not speaker._q.empty():
        time.sleep(0.01)
    warm_tts_first_audio_s = (writes[0] - t_warm) if writes else None
    writes.clear()

    # ---------------------------------------------------------------- cas
    fixtures = build_fixture_table(args.fixtures_dir)
    log_offset = 0
    if cfg.speech_log and os.path.exists(cfg.speech_log):
        log_offset = os.path.getsize(cfg.speech_log)

    results = []
    for idx, fx in enumerate(fixtures, start=1):
        cmd, exit_code, duration, raw = fx["cmd"], fx["exit"], fx["duration"], fx["output"]
        raw_fed = raw if raw.endswith("\n") else raw + "\n"

        c = session.start(cmd)
        now = time.time()
        c.start = now - duration
        c.enter_at = c.start
        c.exit = exit_code
        c.feed(raw_fed.encode("utf-8"))
        c.end = time.time()

        # classification (réplique la logique de _finish, avec les vraies fonctions)
        lines = [l for l in c.all_lines() if l.strip() and l.strip() not in ("^C", "^Z", "^\\")]
        text = "\n".join(lines).strip()
        words = len(text.split())
        verbatim = words <= cfg.read_verbatim_max_words and len(lines) <= 3
        said = None if verbatim else digest_mod.resolve(cmd, exit_code, "\n".join(c.all_lines()), cfg.language)
        bucket = "verbatim" if verbatim else ("resolve" if said else "llm")
        active = c.end - max(c.start, c.enter_at)
        long_cmd = active >= cfg.first_update_after
        if long_cmd:
            if exit_code == 0:
                prefix_text = _t(cfg.language, "finished_in").format(dur=fmt_duration(active, cfg.language))
            elif exit_code == 130:
                prefix_text = _t(cfg.language, "interrupted_after").format(dur=fmt_duration(c.duration, cfg.language))
            else:
                prefix_text = _t(cfg.language, "failed_after").format(dur=fmt_duration(c.duration, cfg.language))
        else:
            prefix_text = ""

        writes.clear()
        captured.clear()
        t0 = time.time()
        narrator._finish(c, "", "")

        deadline = time.time() + args.case_timeout
        while (speaker.speaking.is_set() or not speaker._q.empty()) and time.time() < deadline:
            time.sleep(0.005)
        time.sleep(0.02)  # marge : on_done() tourne juste après speaking.clear()
        timed_out = time.time() >= deadline

        if bucket == "llm":
            n_prefix_sentences = len(list(SENTENCE_END.finditer(captured.get("prefix", ""))))
            llm_prefix_used = captured.get("prefix", "")
        else:
            n_prefix_sentences = len(list(SENTENCE_END.finditer(prefix_text)))
            llm_prefix_used = prefix_text

        writes_rel = [round(w - t0, 4) for w in writes]
        premier_son_s = writes_rel[0] if writes_rel else None
        if writes_rel:
            j = n_prefix_sentences if n_prefix_sentences < len(writes_rel) else len(writes_rel) - 1
            premier_fait_utile_s = writes_rel[j]
        else:
            premier_fait_utile_s = None

        # texte réellement dit, lu dans le journal (pas de dépendance à on_done, pas de
        # concurrence possible : self._journal(s) est synchrone, avant chaque synthèse)
        spoken_sentences = []
        if cfg.speech_log and os.path.exists(cfg.speech_log):
            with open(cfg.speech_log, encoding="utf-8") as f:
                f.seek(log_offset)
                new = f.read()
                log_offset += len(new.encode("utf-8"))
            for line in new.splitlines():
                if "\t" in line:
                    ts, txt = line.split("\t", 1)
                    spoken_sentences.append({"t_rel": round(float(ts) - t0, 4), "text": txt})

        results.append({
            "id": fx["id"], "cmd": cmd, "exit": exit_code, "duration_fixture_s": duration,
            "bucket": bucket, "long_cmd": long_cmd, "resolve_said": said,
            "n_prefix_sentences": n_prefix_sentences, "prefix_used": llm_prefix_used,
            "n_sentences_spoken": len(writes_rel), "timed_out": timed_out,
            "premier_son_s": premier_son_s, "premier_fait_utile_s": premier_fait_utile_s,
            "spoken_text": " ".join(s["text"] for s in spoken_sentences),
            "spoken_sentences": spoken_sentences,
        })
        print(f"[{idx:02d}/{len(fixtures)}] {fx['id']:14s} bucket={bucket:8s} "
              f"son={premier_son_s} fait_utile={premier_fait_utile_s}"
              f"{'  TIMEOUT' if timed_out else ''}", file=sys.stderr)

    def stats(vals):
        v = [x for x in vals if x is not None]
        if not v:
            return {"n": 0}
        return {"n": len(v), "median": round(statistics.median(v), 4),
                "p90": round(percentile(v, 0.9), 4), "max": round(max(v), 4)}

    code_cases = [r for r in results if r["bucket"] in ("verbatim", "resolve")]
    llm_cases = [r for r in results if r["bucket"] == "llm"]

    summary = {
        "warmup_llm_s": round(warm_llm_s, 3),
        "warmup_tts_first_audio_s": round(warm_tts_first_audio_s, 3) if warm_tts_first_audio_s else None,
        "n_cases": len(results), "n_code": len(code_cases), "n_model": len(llm_cases),
        "premier_son": {
            "code": stats([r["premier_son_s"] for r in code_cases]),
            "model": stats([r["premier_son_s"] for r in llm_cases]),
            "all": stats([r["premier_son_s"] for r in results]),
        },
        "premier_fait_utile": {
            "code": stats([r["premier_fait_utile_s"] for r in code_cases]),
            "model": stats([r["premier_fait_utile_s"] for r in llm_cases]),
            "all": stats([r["premier_fait_utile_s"] for r in results]),
        },
    }

    out = {"model": args.model, "voice": args.voice, "llm_ctx": args.ctx, "llm_threads": args.threads,
           "summary": summary, "results": results}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    llm.stop_server()
    speaker.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
