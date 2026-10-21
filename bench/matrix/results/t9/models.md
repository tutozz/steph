# T9 : candidats OpenRouter

Instantané de `/api/v1/models` du 2026-10-01 (464 modèles). Prix affichés en $ par million de jetons ; le fournisseur servi peut facturer moins (tri par prix) ou plus (plafonné par `max_price` à 1,5 fois le prix affiché depuis le correctif du client).

Tailles mesurées : DEV complet au prompt générique de production (SUMMARY_SYSTEM, bloc de faits L5 ; QA_SYSTEM et historique) = 2 054 258 caractères, 858 évaluations ; 3,0 à 3,2 caractères par jeton mesurés sur les réponses d'OpenRouter, soit **663 k jetons d'entrée** et ~17 k de sortie (20 jetons par réponse mesurés). Réétiquetage : 4 027 requêtes distinctes (2 461 résumés FR, 533 EN, 113 questions, 151 progression et flux, 769 détails), 7 165 430 caractères, soit **2,31 M jetons d'entrée** et ~130 k de sortie.

Capacité FR/EN : l'API ne la déclare pas ; elle est mesurée par les colonnes FR et EN du banc (`T9.md`).

## Testés au sous-échantillon DEV (152 évaluations)

| Modèle | Entrée | Sortie | Contexte | DEV complet, prix affiché ($) | Réétiquetage, prix affiché ($) |
|---|---:|---:|---:|---:|---:|
| `deepseek/deepseek-v4-flash` | 0.079 | 0.157 | 1048 k | 0.055 | 0.20 |
| `openai/gpt-oss-120b` | 0.037 | 0.170 | 131 k | 0.027 | 0.11 |
| `qwen/qwen3-235b-a22b-2507` | 0.087 | 0.350 | 262 k | 0.064 | 0.25 |
| `google/gemma-4-31b-it` | 0.090 | 0.340 | 262 k | 0.065 | 0.25 |
| `meta-llama/llama-3.3-70b-instruct` | 0.100 | 0.320 | 131 k | 0.072 | 0.27 |
| `google/gemini-2.5-flash-lite` | 0.100 | 0.400 | 1048 k | 0.073 | 0.28 |
| `qwen/qwen3.8-flash` | 0.150 | 0.470 | 1000 k | 0.107 | 0.41 |
| `mistralai/mistral-small-2603` | 0.150 | 0.600 | 262 k | 0.110 | 0.42 |
| `google/gemini-3.1-flash-lite` | 0.250 | 1.500 | 1048 k | 0.191 | 0.77 |
| `qwen/qwen3.8-27b` | 0.420 | 3.000 | 1000 k | 0.329 | 1.36 |
| `mistralai/mistral-large-2512` | 0.500 | 1.500 | 262 k | 0.357 | 1.35 |
| `deepseek/deepseek-v4-pro` | 0.783 | 1.566 | 1048 k | 0.546 | 2.01 |

## Non testés, pour mémoire

| Modèle | Entrée | Sortie | Contexte | DEV complet ($) | Réétiquetage ($) |
|---|---:|---:|---:|---:|---:|
| `qwen/qwen3.8-27b:free` | 0.000 | 0.000 | 262 k | 0.000 | 0.00 |
| `google/gemma-4-31b-it:free` | 0.000 | 0.000 | 262 k | 0.000 | 0.00 |
| `nvidia/nemotron-3-super-120b-a12b` | 0.080 | 0.450 | 262 k | 0.061 | 0.24 |
| `openai/gpt-5-nano` | 0.050 | 0.400 | 400 k | 0.040 | 0.17 |
| `google/gemini-3.8-flash` | 0.750 | 3.750 | 1048 k | 0.561 | 2.22 |
| `openai/gpt-5.4-mini` | 0.750 | 4.500 | 400 k | 0.574 | 2.32 |
| `anthropic/claude-haiku-4.5` | 1.000 | 5.000 | 200 k | 0.748 | 2.96 |
| `moonshotai/kimi-k2.6` | 0.650 | 3.410 | 262 k | 0.489 | 1.94 |
| `z-ai/glm-5.3-flash` | 0.150 | 0.500 | 1048 k | 0.108 | 0.41 |
| `mistralai/mistral-medium-3.1` | 0.400 | 2.000 | 131 k | 0.299 | 1.18 |

Les variantes `:free` (0 $) sont limitées à 1 000 requêtes par jour pour cette clé : 4 027 requêtes de réétiquetage prendraient 5 jours, avec des limites de débit ; écartées pour tenir la tâche dans la session.
Les variantes `:batch` ne sont pas servies en appel synchrone ; écartées.
