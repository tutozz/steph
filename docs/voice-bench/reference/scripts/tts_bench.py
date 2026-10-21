"""Banc TTS : chargement, temps jusqu'au premier son, facteur temps réel, RAM crête.

Usage : tts_bench.py <moteur> <modèle> <threads> <label> <sortie.json> [echantillon.wav]
moteur : piper (modèle = chemin .onnx) | kokoro (modèle = chemin .onnx, voix ff_siwis)
"""
import json
import os
import resource
import statistics
import sys
import time
import wave

engine, model, threads, label, out = sys.argv[1:6]
sample = sys.argv[6] if len(sys.argv) > 6 else None
threads = int(threads)
os.environ["OMP_NUM_THREADS"] = str(threads)

SENTENCES = [
    "Erreur 1 : cat: /nope : aucun fichier ou dossier de ce nom.",
    "Erreur TypeScript : la propriété titel n'existe pas, utilisez title.",
    "En cours : mise à jour des paquets. 35 pour cent, décompression de vim-common. "
    "Terminé en 1 minute 24. 12 paquets mis à jour.",
    "Question : il est nécessaire de prendre 24 Mo. Souhaitez-vous continuer ? Oui ou non, oui par défaut.",
    "OK.",
    "Commande introuvable.",
]
SAMPLE_TEXT = SENTENCES[1]

t0 = time.time()
if engine == "piper":
    from piper import PiperVoice

    voice = PiperVoice.load(model)
    rate = voice.config.sample_rate

    def stream(text):
        for chunk in voice.synthesize(text):
            yield chunk.audio_int16_bytes
else:
    import numpy as np
    import onnxruntime as ort
    from kokoro_onnx import Kokoro

    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    sess = ort.InferenceSession(model, so, providers=["CPUExecutionProvider"])
    kok = Kokoro.from_session(sess, os.path.join(os.path.dirname(model), "voices-v1.0.bin"))
    rate = 24000

    def stream(text):
        samples, _ = kok.create(text, voice="ff_siwis", speed=1.0, lang="fr-fr")
        yield (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()

load = time.time() - t0
list(stream("Bonjour."))  # chauffe

rows = []
for s in SENTENCES:
    t = time.time()
    first = None
    nbytes = 0
    for pcm in stream(s):
        if first is None:
            first = time.time() - t
        nbytes += len(pcm)
    synth = time.time() - t
    dur = nbytes / 2 / rate
    rows.append({"text": s, "first_audio": round(first, 3), "synth": round(synth, 3),
                 "audio_s": round(dur, 2), "rtf": round(synth / dur, 3) if dur else None})

if sample:
    pcm = b"".join(stream(SAMPLE_TEXT))
    with wave.open(sample, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)

longest = max(rows, key=lambda r: len(r["text"]))
res = {
    "label": label, "engine": engine, "model": os.path.basename(model), "threads": threads,
    "load_s": round(load, 2),
    "first_audio_longest": longest["first_audio"],
    "first_audio_median": statistics.median(r["first_audio"] for r in rows),
    "rtf_median": statistics.median(r["rtf"] for r in rows if r["rtf"]),
    "rtf_max": max(r["rtf"] for r in rows if r["rtf"]),
    "ram_peak_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    "rows": rows,
}
json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
print(f"{label}: load {res['load_s']}s first {res['first_audio_longest']}s rtf {res['rtf_median']} ram {res['ram_peak_mb']}Mo")
