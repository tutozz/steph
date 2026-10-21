"""P19 : même protocole que P14a (`p14a_harness.py` : 33 cas, vrai Narrator, vrai Speaker
Piper, llama-server local, TRAIN_SYSTEM patché en mémoire), plus ce que le temps d'écriture
ne voit pas :

  - premier_son_s          : premier octet PCM écrit vers le lecteur (mesure P14a, inchangée) ;
  - premier_son_audible_s  : premier bloc de 10 ms non silencieux (RMS > 300) capté sur le
                             moniteur de la sortie PulseAudio/PipeWire (parec). Voit le silence
                             de tête de Piper et le démarrage du lecteur, que l'écriture ignore ;
  - premier_fait_utile_s   : écriture du premier segment qui n'appartient pas au préfixe de
                             statut ou de durée (mesure P14a) ;
  - premier_fait_utile_audible_s : instant où ce segment devient audible, par modèle de file :
                             début_k = max(écriture_k + L, fin_{k-1}), audible = début_j + tête_j,
                             L calé par cas sur le premier son capté ;
  - coupure_s              : somme des attentes entre segments d'une même annonce (lecteur à vide).

Le moniteur tient la sortie éveillée : la reprise d'une sortie suspendue n'est pas mesurée.
Le même harnais mesure l'ancien code (un lecteur par phrase) et le nouveau (un lecteur par
annonce, une écriture par segment) : il reconnaît le nouveau à `Speaker._play_pipelined`.

Usage : comme p14a_harness.py, plus --monitor <source moniteur> (défaut : moniteur de la
sortie par défaut).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import struct
import subprocess
import sys
import threading
import time

SILENT_RMS = 300
MON_RATE = 16000
MON_BLOCK = MON_RATE // 100  # 10 ms


def block_rms(b: bytes) -> float:
    n = len(b) // 2
    if not n:
        return 0.0
    v = struct.unpack(f"<{n}h", b[: 2 * n])
    return (sum(x * x for x in v) / n) ** 0.5


def lead_seconds(pcm: bytes, rate: int) -> float:
    """Silence de tête d'un segment, avec le même critère que le moniteur (RMS 10 ms)."""
    step = 2 * (rate // 100)
    for i in range(0, len(pcm), step):
        if block_rms(pcm[i:i + step]) > SILENT_RMS:
            return i / 2 / rate
    return len(pcm) / 2 / rate


class Monitor:
    """Capture le moniteur de la sortie son, horodate chaque bloc de 10 ms."""

    def __init__(self, source: str):
        self.p = subprocess.Popen(["parec", "--raw", "--format=s16le", f"--rate={MON_RATE}", "--channels=1",
                                   "--latency-msec=5", "-d", source],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.blocks: list[tuple[float, float]] = []
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            b = self.p.stdout.read(2 * MON_BLOCK)
            if not b:
                return
            self.blocks.append((time.time(), block_rms(b)))

    def onset(self, t0: float, t1: float) -> float | None:
        for t, rms in self.blocks:
            if t0 <= t <= t1 and rms > SILENT_RMS:
                return t - t0
        return None

    def close(self):
        self.p.kill()


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
    ap.add_argument("--monitor", default="@DEFAULT_MONITOR@")
    ap.add_argument("--steph-src", default="", help="dossier contenant le paquet steph/ (sinon PYTHONPATH déjà positionné)")
    args = ap.parse_args()

    if args.steph_src:
        sys.path.insert(0, args.steph_src)
    if args.pulse_server:
        os.environ["PULSE_SERVER"] = args.pulse_server

    from steph.config import Config
    from steph.session import Session
    from steph.llm import LLM
    from steph.tts import Speaker
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
    chunks: list[tuple[float, int, bytes]] = []  # (t, n° de lecteur, octets) de chaque écriture
    write_lock = threading.Lock()
    _orig_popen_quiet = audio_mod.popen_quiet
    n_players = [0]

    class _TimestampedStdin:
        def __init__(self, real, idx):
            self._real, self._idx, self._fired = real, idx, False

        def write(self, data):
            now = time.time()
            with write_lock:
                if not self._fired:
                    self._fired = True
                    writes.append(now)
                chunks.append((now, self._idx, bytes(data)))
            return self._real.write(data)

        def flush(self):
            return self._real.flush()

        def close(self):
            return self._real.close()

    def _popen_quiet_patched(cmd, stdin=None):
        proc = _orig_popen_quiet(cmd, stdin=stdin)
        if proc.stdin is not None:
            n_players[0] += 1
            proc.stdin = _TimestampedStdin(proc.stdin, n_players[0])
        return proc

    audio_mod.popen_quiet = _popen_quiet_patched

    # ---------------------------------------------------------------- config réelle
    cfg = Config()
    # Q3 : profil affiné (B3/B3b), pour que _finish() envoie les prompts TRAIN_* réels
    # (finetuned_summary_messages, plafond 587 car.) et que llm.py applique Q2c
    # (contexte 8192, --cache-ram 0) - sinon --ctx et le monkeypatch TRAIN_SYSTEM
    # ci-dessus ne reproduisent que partiellement le chemin de production.
    cfg.llm_profile = "finetuned"
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

    def _spy_llm_say(msgs, fallback, prefix="", max_tokens=90, on_done=None, interrupt=True, tag="",
                      strip_status=False, suffix=""):
        captured["prefix"] = prefix
        captured["msgs"] = msgs
        return _orig_llm_say(msgs, fallback, prefix=prefix, max_tokens=max_tokens, on_done=on_done,
                              interrupt=interrupt, tag=tag, strip_status=strip_status, suffix=suffix)

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
    pipelined = hasattr(Speaker, "_play_pipelined")
    player_lats: list[float] = []
    monitor = Monitor(args.monitor)
    time.sleep(1.0)
    with write_lock:
        chunks.clear()
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
        with write_lock:
            chunks.clear()
        captured.clear()
        t0 = time.time()
        narrator._finish(c, "", "")

        deadline = time.time() + args.case_timeout
        while (speaker.speaking.is_set() or not speaker._q.empty()) and time.time() < deadline:
            time.sleep(0.005)
        time.sleep(0.02)  # marge : on_done() tourne juste après speaking.clear()
        timed_out = time.time() >= deadline

        llm_prefix_used = captured.get("prefix", "") if bucket == "llm" else prefix_text

        # texte réellement dit, lu dans le journal (un segment par ligne)
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

        # segments joués : une écriture par segment (nouveau code), un lecteur par phrase (ancien)
        with write_lock:
            case_chunks = list(chunks)
            chunks.clear()
        if pipelined:
            segs = [(t, b) for t, _, b in case_chunks]
        else:
            by_player: dict[int, list] = {}
            for t, i, b in case_chunks:
                by_player.setdefault(i, [t, b""])[1] += b
            segs = [(v[0], v[1]) for v in by_player.values()]
        rate = speaker.rate
        leads = [lead_seconds(b, rate) for _, b in segs]
        durs = [len(b) / 2 / rate for _, b in segs]

        # segments du préfixe (statut, durée, nombre de lignes) : ceux dont le texte cumulé
        # reste un début du préfixe réellement envoyé
        pref, acc, j = llm_prefix_used.strip(), "", 0
        for sent in spoken_sentences:
            cand = (acc + " " + sent["text"]).strip()
            if pref and pref.startswith(cand):
                acc, j = cand, j + 1
            else:
                break
        j = min(j, len(segs) - 1) if segs else 0

        onset = monitor.onset(t0, time.time())
        premier_son_s = round(segs[0][0] - t0, 4) if segs else None
        premier_fait_utile_s = round(segs[j][0] - t0, 4) if segs else None
        player_lat = None
        if segs and onset is not None:
            player_lat = onset - (segs[0][0] - t0) - leads[0]
            player_lats.append(player_lat)
        lat = player_lat if player_lat is not None else (statistics.median(player_lats) if player_lats else 0.03)
        audible, prev_end, gap = [], None, 0.0
        for k, (t, _) in enumerate(segs):
            ready = t - t0 + lat
            start = ready if prev_end is None else max(ready, prev_end)
            if prev_end is not None:
                gap += max(0.0, ready - prev_end)
            audible.append(start + leads[k])
            prev_end = start + durs[k]
        fait_audible = round(audible[j], 4) if segs else None

        results.append({
            "id": fx["id"], "cmd": cmd, "exit": exit_code, "duration_fixture_s": duration,
            "bucket": bucket, "long_cmd": long_cmd, "resolve_said": said,
            "n_prefix_segments": j, "prefix_used": llm_prefix_used,
            "n_segments": len(segs), "n_journal": len(spoken_sentences), "timed_out": timed_out,
            "premier_son_s": premier_son_s, "premier_fait_utile_s": premier_fait_utile_s,
            "premier_son_audible_s": round(onset, 4) if onset is not None else None,
            "premier_fait_utile_audible_s": fait_audible,
            "lecteur_latence_s": round(player_lat, 4) if player_lat is not None else None,
            "tete_silence_s": [round(x, 3) for x in leads],
            "coupure_s": round(gap, 4),
            "spoken_text": " ".join(s["text"] for s in spoken_sentences),
            "spoken_sentences": spoken_sentences,
        })
        print(f"[{idx:02d}/{len(fixtures)}] {fx['id']:14s} bucket={bucket:8s} "
              f"son={premier_son_s} audible={results[-1]['premier_son_audible_s']} "
              f"fait_utile={premier_fait_utile_s} audible={fait_audible} coupure={round(gap, 3)}"
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
        "premier_son_audible": {
            "code": stats([r["premier_son_audible_s"] for r in code_cases]),
            "model": stats([r["premier_son_audible_s"] for r in llm_cases]),
            "all": stats([r["premier_son_audible_s"] for r in results]),
        },
        "premier_fait_utile_audible": {
            "code": stats([r["premier_fait_utile_audible_s"] for r in code_cases]),
            "model": stats([r["premier_fait_utile_audible_s"] for r in llm_cases]),
            "all": stats([r["premier_fait_utile_audible_s"] for r in results]),
        },
        "coupure": stats([r["coupure_s"] for r in results]),
        "lecteur_latence": stats([r["lecteur_latence_s"] for r in results]),
        "pipelined": pipelined,
    }

    out = {"model": args.model, "voice": args.voice, "llm_ctx": args.ctx, "llm_threads": args.threads,
           "summary": summary, "results": results}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))

    monitor.close()
    llm.stop_server()
    speaker.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
