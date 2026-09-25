from pathlib import Path

from steph.config import Config
from steph.llm import _build_args, _build_env


def test_build_args_defaults_omit_flash_attn_and_cache_type():
    args = _build_args(Config(), "/opt/llama/llama-server")
    assert "-fa" not in args
    assert "-ctk" not in args
    assert "-ctv" not in args
    assert args[:3] == ["/opt/llama/llama-server", "-m", Config().model]


def test_build_args_includes_flash_attn_and_cache_type_when_set():
    cfg = Config()
    cfg.llm_flash_attn = "on"
    cfg.llm_cache_type = "q8_0"
    args = _build_args(cfg, "/opt/llama/llama-server")
    assert args[args.index("-fa") + 1] == "on"
    assert args[args.index("-ctk") + 1] == "q8_0"
    assert args[args.index("-ctv") + 1] == "q8_0"


def test_build_args_uses_parallel_batch_ubatch_from_config():
    cfg = Config()
    cfg.llm_parallel = 4
    cfg.llm_batch = 1024
    cfg.llm_ubatch = 256
    args = _build_args(cfg, "/opt/llama/llama-server")
    assert args[args.index("--parallel") + 1] == "4"
    assert args[args.index("-b") + 1] == "1024"
    assert args[args.index("-ub") + 1] == "256"


def test_build_args_extra_args_come_last():
    cfg = Config()
    cfg.llm_extra_args = ["--foo", "bar"]
    args = _build_args(cfg, "/opt/llama/llama-server")
    assert args[-2:] == ["--foo", "bar"]


def test_build_env_merges_llm_env():
    cfg = Config()
    cfg.llm_env = {"GGML_VK_VISIBLE_DEVICES": "0"}
    env = _build_env(cfg, Path("/opt/llama-b1234/llama-server"))
    assert env["GGML_VK_VISIBLE_DEVICES"] == "0"


def test_build_env_sets_library_path_next_to_llama_binary():
    env = _build_env(Config(), Path("/opt/llama-b1234/llama-server"))
    assert env["LD_LIBRARY_PATH"].startswith("/opt/llama-b1234")
    assert env["DYLD_LIBRARY_PATH"].startswith("/opt/llama-b1234")
