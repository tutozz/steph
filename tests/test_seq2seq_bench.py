"""Tests de la partie pure de train_seq2seq.py et bench_t5.py (piste encodeur-décodeur)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "matrix" / "finetune"))
sys.path.insert(0, str(ROOT / "bench" / "matrix"))

from bench_t5 import completion_cmd, parse_perf  # noqa: E402
from train_seq2seq import to_pair  # noqa: E402

SYSTEM = {"role": "system", "content": "Tu lis la sortie d'une commande."}
USER = {"role": "user", "content": "Commande : df -h\nStatut : succès (code 0)\nSortie :\n/dev/sda1 50G"}


class TestToPair:
    def test_source_is_user_message_and_target_is_label(self):
        messages = [SYSTEM, USER, {"role": "assistant", "content": "Racine 50G."}]
        assert to_pair(messages) == (USER["content"], "Racine 50G.")

    def test_system_prompt_is_dropped(self):
        source, _ = to_pair([SYSTEM, USER, {"role": "assistant", "content": "x"}])
        assert "Tu lis" not in source

    def test_case_without_answer_gives_empty_target(self):
        assert to_pair([SYSTEM, USER]) == (USER["content"], "")

    def test_missing_user_message_is_an_error(self):
        with pytest.raises(ValueError):
            to_pair([SYSTEM])


PERF_LOG = """
llama_perf_sampler_print:    sampling time =       1.20 ms /    14 runs   (    0.09 ms per token, 11666.67 tokens per second)
llama_perf_context_print:        load time =     153.44 ms
llama_perf_context_print: prompt eval time =     210.51 ms /   147 tokens (    1.43 ms per token,   698.30 tokens per second)
llama_perf_context_print:        eval time =      95.02 ms /    13 runs   (    7.31 ms per token,   136.81 tokens per second)
llama_perf_context_print:       total time =     320.77 ms /   160 tokens
"""


class TestParsePerf:
    def test_reads_load_prompt_and_generation(self):
        assert parse_perf(PERF_LOG) == {
            "load_ms": 153.44, "prompt_ms": 210.51, "prompt_n": 147,
            "eval_ms": 95.02, "gen_n": 13, "gen_tok_s": 136.81,
        }

    def test_reads_decimal_commas_of_a_french_locale(self):
        perf = parse_perf(PERF_LOG.replace("153.44", "153,44").replace("136.81", "136,81"))
        assert perf["load_ms"] == 153.44
        assert perf["gen_tok_s"] == 136.81

    def test_missing_lines_give_empty_dict(self):
        assert parse_perf("nothing here") == {}


class TestCompletionCmd:
    def test_command_disables_chat_template_and_prompt_echo(self):
        cmd = completion_cmd("llama-completion", "m.gguf", "p.txt", n_predict=80, threads=4, ctx=4096,
                             seed=42, repeat_penalty=1.1, temperature=0.2)
        assert cmd[:5] == ["llama-completion", "-m", "m.gguf", "-f", "p.txt"]
        for flag in ("-no-cnv", "--no-display-prompt"):
            assert flag in cmd
        assert cmd[cmd.index("-t") + 1] == "4"
        assert cmd[cmd.index("-n") + 1] == "80"
        assert cmd[cmd.index("--repeat-penalty") + 1] == "1.1"
        assert cmd[cmd.index("-ngl") + 1] == "0"

    def test_encoder_reads_the_whole_prompt_in_one_micro_batch(self):
        cmd = completion_cmd("llama-completion", "m.gguf", "p.txt", n_predict=80, threads=4, ctx=4096,
                             seed=42, repeat_penalty=1.1, temperature=0.2)
        for flag in ("-c", "-b", "-ub"):
            assert cmd[cmd.index(flag) + 1] == "4096"
