<!--
Draft section for README.md. Every number below comes from docs/readme-charts/data.json.
Numbers tagged "placeholder" in data.json are followed by a "ph: <key>" HTML comment and must be
updated after the fine-tuned model is benchmarked; then run python3 docs/readme-charts/build.py.
-->

## A voice model small enough for any laptop

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/hero.en.dark.png">
  <img src="assets/charts/hero.en.light.png" alt="steph's small model: nearly the quality of a 9B model, the size of a 270M model" width="100%">
</picture>

steph turns a wall of terminal output into one spoken sentence. Until now, a good sentence took a big model: Qwen3.5 9B gets 100 % of the expected facts on our bench of 36 real terminal outputs. That model weighs 5,681 MB. On an old laptop without a GPU, it is out of reach.

Raw small models fit, but they miss the point. Under one billion parameters, they get between 13.3 % and 46.7 % on the same bench, and the best of them, with a tuned prompt, still tops out at 68.3 % on the control set.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/quality.en.dark.png">
  <img src="assets/charts/quality.en.light.png" alt="Bench quality: Qwen3.5 9B 100 %, Gemma 4 E2B 97.5 %, steph fine-tuned (provisional), raw small models between 13.3 % and 46.7 %" width="100%">
</picture>

So we trained our own. steph's small model learned from the 9B, on real terminal sessions, to say what the 9B would say, in a file small enough for any laptop.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/example.en.dark.png">
  <img src="assets/charts/example.en.light.png" alt="Before and after on rm /etc/hostname: the raw small model talks about Header.tsx, a file that is not in the output; steph says the deletion failed for lack of permission" width="100%">
</picture>

The target is an Intel Core i5-7200U laptop from 2017<!-- ph: laptop.year -->: 2 cores, no GPU. There, steph speaks its first word within 1.5 s<!-- ph: ttft_p90_i5.steph --> nine times out of ten, where a 2B model takes 13.3 s.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/speed.en.dark.png">
  <img src="assets/charts/speed.en.light.png" alt="First word on an i5-7200U without GPU: steph 1.5 s (provisional), Qwen3.5 0.8B 5.7 s, Qwen3.5 2B 13.3 s, SmolLM3 3B 22.4 s, Ministral 3 3B 27.0 s" width="100%">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/charts/size.en.dark.png">
  <img src="assets/charts/size.en.light.png" alt="Size on disk: steph 292 MB (provisional), Gemma 4 E2B 3,350 MB, Qwen3.5 9B 5,681 MB" width="100%">
</picture>

**How we built it.** Real terminal outputs collected on 7<!-- ph: corpus.machines --> lab machines, anonymized and audited before any use; each one labeled by Qwen3.5 9B (distillation); a LoRA fine-tune of a small base model; exported to GGUF for llama.cpp. The full method, thresholds and bench files: the internal mission log (not published)).
