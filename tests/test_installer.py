"""B8b : scripts d'installation. `scripts/install.sh` (source, fonctions pures) et
`site/public/install` (exécuté avec des outils factices, HOME temporaire)."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL = REPO / "scripts" / "install.sh"
PUBLIC = REPO / "site" / "public" / "install"


def bash(snippet: str, env=None) -> subprocess.CompletedProcess:
    full_env = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], **(env or {})}
    return subprocess.run(["bash", "-c", f'source "{INSTALL}"; {snippet}'], capture_output=True, text=True,
                          env=full_env, timeout=20)


# ------------------------------------------------------------ install.sh : binaire llama.cpp selon la machine


@pytest.mark.parametrize("os_name, arch, gpu, flavor", [
    ("Darwin", "arm64", "none", "macos-arm64"),
    ("Darwin", "x86_64", "none", "macos-x64"),
    ("Linux", "x86_64", "nvidia", "ubuntu-cuda-12.8-x64"),
    ("Linux", "x86_64", "vulkan", "ubuntu-vulkan-x64"),
    ("Linux", "x86_64", "none", "ubuntu-x64"),
    ("Linux", "aarch64", "none", "ubuntu-arm64"),
    ("Linux", "arm64", "vulkan", "ubuntu-vulkan-arm64"),
    ("Linux", "aarch64", "nvidia", "ubuntu-cuda-13.4-arm64"),
])
def test_llama_flavor(os_name, arch, gpu, flavor):
    r = bash(f"llama_flavor {os_name} {arch} {gpu}")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == flavor


def test_unsupported_architecture_is_refused():
    r = bash("llama_flavor Linux armv7l none")
    assert r.returncode != 0
    assert r.stdout.strip() == ""


def test_messages_follow_the_locale():
    assert bash('msg "bonjour" "hello"', {"LANG": "fr_FR.UTF-8"}).stdout == "bonjour\n"
    assert bash('msg "bonjour" "hello"', {"LANG": "en_US.UTF-8"}).stdout == "hello\n"
    assert bash('msg "bonjour" "hello"', {"LANG": "C", "LC_ALL": "fr_CA.UTF-8"}).stdout == "bonjour\n"


def test_announced_size_matches_measures():
    assert "3,6 Go" in bash("plan_size gemma ''", {"LANG": "fr_FR.UTF-8"}).stdout
    assert "4,4 Go" in bash("plan_size gemma 1", {"LANG": "fr_FR.UTF-8"}).stdout
    assert "3.6 GB" in bash("plan_size gemma ''", {"LANG": "en_US.UTF-8"}).stdout


def test_finish_gives_absolute_path_and_shell_line_when_steph_is_not_on_path(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "steph").write_text("#!/bin/sh\n")
    (bindir / "steph").chmod(0o755)
    r = bash(f'PATH=/usr/bin:/bin; SHELL=/bin/zsh; path_advice "{bindir}"', {"LANG": "fr_FR.UTF-8"})
    assert str(bindir / "steph") in r.stdout
    assert f'export PATH="{bindir}:$PATH"' in r.stdout
    assert ".zshrc" in r.stdout


def test_finish_checks_the_users_path_not_the_installers(tmp_path):
    """Le script public ajoute ~/.local/bin à son propre PATH : le terminal de la personne, lui, ne l'a pas."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "steph").write_text("#!/bin/sh\n")
    (bindir / "steph").chmod(0o755)
    r = bash(f'PATH="{bindir}:/usr/bin:/bin"; STEPH_USER_PATH=/usr/bin:/bin; path_advice "{bindir}"',
             {"LANG": "fr_FR.UTF-8"})
    assert f'export PATH="{bindir}:$PATH"' in r.stdout


def test_public_script_hands_the_original_path_to_the_installer():
    assert 'STEPH_USER_PATH="${STEPH_USER_PATH:-$PATH}"' in PUBLIC.read_text()


def test_finish_is_silent_about_path_when_steph_is_found(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "steph").write_text("#!/bin/sh\n")
    (bindir / "steph").chmod(0o755)
    r = bash(f'PATH="{bindir}:/usr/bin:/bin"; path_advice "{bindir}"', {"LANG": "fr_FR.UTF-8"})
    assert r.returncode == 0
    assert "export PATH" not in r.stdout


def test_install_script_has_no_fixed_tmp_paths_and_no_curl_progress_bar():
    text = INSTALL.read_text()
    assert "/tmp/llama.tgz" not in text and "/tmp/cudart" not in text
    assert "FLAVOR=ubuntu-x64" not in text


# ------------------------------------------------------------ B7 : steph setup à la fin de l'installation


def test_maybe_run_setup_calls_steph_setup_and_never_fails(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "log"
    (bindir / "uv").write_text(f'#!/bin/sh\necho "$@" >> "{log}"\nexit 7\n')
    (bindir / "uv").chmod(0o755)
    env = {"PATH": f"{bindir}:{os.environ['PATH']}"}
    r = bash("set -e; maybe_run_setup", env)
    assert r.returncode == 0, r.stderr  # || true : un setup refusé n'interrompt pas l'installation
    assert log.read_text().strip() == "run -q steph setup"


def test_setup_only_runs_at_the_end_of_a_fresh_install():
    """--update et --check ne doivent jamais relancer steph setup à la fin (script complet)."""
    text = INSTALL.read_text()
    assert '[ "$MODE" = install ] && maybe_run_setup' in text


def test_install_script_no_longer_needs_a_hardcoded_model_choice_once_a_terminal_offers_the_catalog():
    """B7 : le téléchargement du modèle de démarrage reste (justifié, voir l'en-tête du script :
    le modèle universel du catalogue B4 n'est pas encore publié), mais steph setup (catalogue B4/B6)
    reprend la main juste après quand un terminal est disponible."""
    text = INSTALL.read_text()
    model_step = text.index("--- 4. modèle")
    call_site = text.index('[ "$MODE" = install ] && maybe_run_setup')
    assert model_step < call_site


# ------------------------------------------------------------ site/public/install : prérequis avant toute modification


REAL = ("sh", "mkdir", "dirname", "cat", "rm", "grep", "sed", "awk", "head", "tr", "env", "ls", "chmod", "mv", "cp",
        "basename", "readlink", "id", "printf")


def _tools(tmp_path, missing=(), arch="x86_64", os_name="Linux"):
    bindir = tmp_path / "tools"
    bindir.mkdir()
    for name in REAL:
        path = shutil.which(name)
        if path:
            (bindir / name).symlink_to(path)
    for name in ("git", "curl", "tar"):
        if name not in missing and shutil.which(name):
            (bindir / name).symlink_to(shutil.which(name))
    stubs = {
        "uname": f'#!/bin/sh\ncase "$1" in -m) echo {arch};; *) echo {os_name};; esac\n',
        "df": "#!/bin/sh\necho 'Filesystem 1024-blocks Used Available Capacity Mounted'\n"
              "echo '/dev/x 100000000 1 90000000 1% /'\n",
        "uv": "#!/bin/sh\necho uv-stub \"$@\"\n",
    }
    for name, body in stubs.items():
        (bindir / name).write_text(body)
        (bindir / name).chmod(0o755)
    return bindir


def run_public(tmp_path, tools, lang="fr_FR.UTF-8", extra=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"PATH": str(tools), "HOME": str(home), "LANG": lang, "GIT_CONFIG_NOSYSTEM": "1", **(extra or {})}
    r = subprocess.run(["/bin/sh", str(PUBLIC)], capture_output=True, text=True, env=env, timeout=60)
    return r, home


@pytest.mark.parametrize("missing", ["git", "curl", "tar"])
def test_public_script_stops_on_missing_tool_before_touching_home(tmp_path, missing):
    r, home = run_public(tmp_path, _tools(tmp_path, missing=(missing,)))
    assert r.returncode != 0
    assert missing in r.stderr
    assert list(home.iterdir()) == []


def test_public_script_speaks_english_with_an_english_locale(tmp_path):
    r, _ = run_public(tmp_path, _tools(tmp_path, missing=("git",)), lang="en_US.UTF-8")
    assert "required" in r.stderr and "requis" not in r.stderr


def test_public_script_refuses_unknown_architecture(tmp_path):
    r, home = run_public(tmp_path, _tools(tmp_path, arch="armv7l"))
    assert r.returncode != 0 and "armv7l" in r.stderr
    assert list(home.iterdir()) == []


def test_public_script_explains_an_unreachable_repository(tmp_path):
    r, home = run_public(tmp_path, _tools(tmp_path), extra={"STEPH_REPO": str(tmp_path / "absent.git")})
    assert r.returncode != 0
    assert "dépôt" in r.stderr
    assert "Username" not in r.stderr and "fatal" not in r.stderr
    assert list(home.iterdir()) == []  # ni uv, ni .bashrc, ni .profile


def test_public_script_clones_then_runs_the_installer(tmp_path):
    src = tmp_path / "fixture"
    (src / "scripts").mkdir(parents=True)
    (src / "scripts" / "install.sh").write_text("#!/bin/sh\necho INSTALL-RAN\n")
    (src / "scripts" / "install.sh").chmod(0o755)
    git = ["git", "-C", str(src), "-c", "user.name=t", "-c", "user.email=t@example.org"]
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-qm", "init"], check=True)
    r, home = run_public(tmp_path, _tools(tmp_path), extra={"STEPH_REPO": str(src)})
    assert r.returncode == 0, r.stderr
    assert "INSTALL-RAN" in r.stdout
    assert (home / ".local" / "share" / "steph" / "src" / ".git").is_dir()
    assert not (home / ".bashrc").exists() and not (home / ".profile").exists()


# ------------------------------------------------------------ M5 : charte dans les installeurs

TRUECOLOR = {"TERM": "xterm-256color", "COLORTERM": "truecolor", "LANG": "fr_FR.UTF-8"}


def _in_pty(argv, env, timeout=20) -> str:
    """Sortie brute (stdout et stderr) d'une commande dont le terminal est un pty."""
    import pty
    import select
    import time

    pid, fd = pty.fork()
    if pid == 0:
        os.execve(argv[0], argv, env)
    out, end = b"", time.time() + timeout
    while time.time() < end:
        if select.select([fd], [], [], 0.1)[0]:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    os.waitpid(pid, 0)
    return out.decode(errors="replace")


@pytest.mark.parametrize("role, expected", [
    ("strong", "\x1b[1mx\x1b[0m\n"),
    ("accent", "\x1b[38;2;11;11;11;48;2;226;255;59mx\x1b[0m\n"),
    ("muted", "\x1b[38;2;138;138;133;48;2;11;11;11mx\x1b[0m\n"),
])
def test_install_styled_roles_use_the_charter(role, expected):
    r = bash(f"STEPH_STYLE=truecolor styled {role} x")
    assert r.returncode == 0, r.stderr
    assert r.stdout == expected


def test_install_logo_is_one_line_word_and_lemon_chevron():
    r = bash("STEPH_STYLE=truecolor styled logo", env={"LANG": "fr_FR.UTF-8", "TERM": "xterm-256color"})
    assert r.stdout == "\x1b[38;2;11;11;11;48;2;226;255;59m steph › \x1b[0m\n"


def test_install_without_style_prints_plain_text_and_no_logo():
    r = bash("STEPH_STYLE=none styled strong x; styled logo; styled accent y")
    assert r.stdout == "x\ny\n"


def test_install_style_is_none_when_output_is_not_a_terminal():
    r = bash('use_style_of 1; printf %s "$STEPH_STYLE" >&2', env=TRUECOLOR)
    assert r.stderr == "none"


def test_install_style_follows_no_color_and_dumb_on_a_real_terminal():
    base = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], **TRUECOLOR}
    probe = f'source "{INSTALL}"; use_style_of 1; printf "[%s]" "$STEPH_STYLE"'
    assert "[truecolor]" in _in_pty(["/bin/bash", "-c", probe], base)
    assert "[none]" in _in_pty(["/bin/bash", "-c", probe], {**base, "NO_COLOR": "1"})
    assert "[none]" in _in_pty(["/bin/bash", "-c", probe], {**base, "TERM": "dumb"})


def _stubbed_install(tmp_path, extra=None) -> str:
    """Vrai install.sh (copie) sur un pty, uv/curl/tar factices : rien n'est téléchargé."""
    tree = tmp_path / "tree"
    (tree / "scripts").mkdir(parents=True)
    (tree / "src" / "steph" / "shell").mkdir(parents=True)
    shutil.copy(INSTALL, tree / "scripts" / "install.sh")
    shutil.copy(REPO / "src" / "steph" / "shell" / "style.sh", tree / "src" / "steph" / "shell" / "style.sh")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    uv = '#!/bin/sh\ncase "$*" in *"python -c"*) echo b9999 ;; "tool dir --bin") echo "$HOME/bin" ;; esac\n'
    for name, body in {"uv": uv, "curl": "#!/bin/sh\n", "tar": "#!/bin/sh\n"}.items():
        (stubs / name).write_text(body)
        (stubs / name).chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {"PATH": f"{stubs}:/usr/bin:/bin", "HOME": str(home), "XDG_DATA_HOME": str(home / "data"),
           **TRUECOLOR, **(extra or {})}
    return _in_pty(["/bin/bash", str(tree / "scripts" / "install.sh")], env)


def test_real_install_run_on_a_terminal_shows_logo_steps_and_lemon_success(tmp_path):
    out = _stubbed_install(tmp_path)
    assert out.startswith("\x1b[38;2;11;11;11;48;2;226;255;59m steph › \x1b[0m\r\n")
    assert "\x1b[1mVoix : installation (environ 230 Mo).\x1b[0m" in out
    assert "\x1b[38;2;11;11;11;48;2;226;255;59msteph est installé.\x1b[0m" in out


@pytest.mark.parametrize("extra", [{"NO_COLOR": "1"}, {"TERM": "dumb"}])
def test_real_install_run_without_color_has_no_sequence_and_no_logo(tmp_path, extra):
    out = _stubbed_install(tmp_path, extra)
    assert "steph est installé." in out
    assert "\x1b" not in out
    assert out.startswith("steph : environ")  # pas de ligne de logo sans couleur


def test_public_script_error_is_bold_on_a_terminal_and_plain_when_piped(tmp_path):
    tools = _tools(tmp_path, missing=("git",))
    home = tmp_path / "home"
    home.mkdir()
    env = {"PATH": str(tools), "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1", **TRUECOLOR}
    out = _in_pty(["/bin/sh", str(PUBLIC)], env)
    assert "\x1b[1msteph : git est requis." in out
    assert "\x1b" not in _in_pty(["/bin/sh", str(PUBLIC)], {**env, "NO_COLOR": "1"})
    r, _ = run_public(tmp_path, tools)
    assert "\x1b" not in r.stderr


def test_public_script_color_depth_is_a_verbatim_copy_of_style_sh():
    def body(text: str) -> str:
        start = text.index("__steph_color_depth() {")
        return text[start:text.index("\n}\n", start)]

    style_sh = (REPO / "src" / "steph" / "shell" / "style.sh").read_text()
    assert body(PUBLIC.read_text()) == body(style_sh)


# ------------------------------------------------------------ Z1/B9b : modèle téléchargé par défaut


def fake_uv(tmp_path, stdout: str) -> dict:
    """`uv` factice : répond `stdout` à la question du catalogue ; env à passer à bash()."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir(exist_ok=True)
    uv = bindir / "uv"
    uv.write_text(f"#!/bin/sh\nprintf '%s' '{stdout}'\n")
    uv.chmod(0o755)
    return {"PATH": f"{bindir}:{os.environ['PATH']}"}


def pick(tmp_path, catalog_answer: str, mode="install", model_env=None):
    env = {**fake_uv(tmp_path, catalog_answer), **({"STEPH_MODEL": model_env} if model_env else {})}
    r = bash(f'MODE={mode}; resolve_model; echo "$MODEL_CHOICE|${{REPO:-}}|${{FILE:-}}|${{SHA:-}}"', env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip().split("|")


def test_default_model_is_the_one_the_catalog_recommends(tmp_path):
    assert pick(tmp_path, "tutozz/r-GGUF s-v2.gguf abc123") == ["steph", "tutozz/r-GGUF", "s-v2.gguf", "abc123"]


def test_raw_gemma_only_on_explicit_choice(tmp_path):
    assert pick(tmp_path, "tutozz/r-GGUF s-v2.gguf", model_env="gemma") == \
        ["gemma", "google/gemma-4-E2B-it-qat-q4_0-gguf", "gemma-4-E2B_q4_0-it.gguf", ""]


def test_qwen_still_available_on_explicit_choice(tmp_path):
    assert pick(tmp_path, "x y", model_env="qwen")[0] == "qwen"


def test_gemma_is_the_fallback_when_catalog_has_nothing_published(tmp_path):
    assert pick(tmp_path, "")[0] == "gemma"


def test_update_keeps_the_installed_model(tmp_path):
    assert pick(tmp_path, "keep", mode="update")[0] == "keep"


def test_announced_size_for_the_steph_model_is_small():
    out = bash("plan_size steph ''", {"LANG": "fr_FR.UTF-8"}).stdout
    assert "0,6 Go" in out and "3,6 Go" not in out
    assert "1,4 Go" in bash("plan_size steph 1", {"LANG": "fr_FR.UTF-8"}).stdout
    assert "0.6 GB" in bash("plan_size steph ''", {"LANG": "en_US.UTF-8"}).stdout


def test_installer_no_longer_hardcodes_gemma_as_default():
    text = INSTALL.read_text()
    assert 'MODEL_CHOICE=$([ "${STEPH_MODEL:-gemma}"' not in text


def test_model_download_checks_the_catalog_sha256():
    src = (REPO / "scripts" / "install.sh").read_text()
    line = next(l for l in src.splitlines() if 'fetch "$(msg Modèle Model)"' in l)
    nxt = src.splitlines()[src.splitlines().index(line) + 1]
    assert "--sha256" in line + nxt
