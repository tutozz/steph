"""Tests for the second, independent PII pass (bench/matrix/finetune/audit_pii_second_pass.py).

Deliberately different patterns from tests/test_audit_pii.py: this script exists to catch
what the first scanner structurally cannot (unknown proper nouns, prompt-embedded
hostnames, vendor key shapes), so its tests exercise those, not the first scanner's rules.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

from audit_pii_second_pass import scan_text  # noqa: E402


def test_unknown_capitalized_name_is_caught():
    text = "connexion établie pour Aurélien Dupont sur le serveur\n"
    assert "unknown_proper_noun" in scan_text(text, known_names=set())


def test_common_tech_vocabulary_is_not_flagged_as_a_proper_noun():
    text = "paquet installé via Docker puis vérifié avec Python et Git\n"
    assert "unknown_proper_noun" not in scan_text(text, known_names=set())


def test_a_name_already_in_the_known_list_is_not_reflagged():
    text = "session ouverte par Marie Curie ce matin\n"
    assert "unknown_proper_noun" not in scan_text(text, known_names={"Marie", "Curie"})


def test_shell_prompt_hostname_is_caught():
    text = "steph@lab-w7:~$ ls\n"
    assert "shell_prompt_host" in scan_text(text, known_names=set())


def test_localhost_prompt_is_not_flagged():
    text = "user@localhost:~$ ls\nroot@machine:~# whoami\n"
    assert scan_text(text, known_names=set()) == []


def test_hostnamectl_static_hostname_is_caught():
    text = "   Static hostname: workstation-9\n"
    assert "hostname" in scan_text(text, known_names=set())


def test_obfuscated_email_is_caught():
    text = "contact: john [at] example [dot] com pour toute question\n"
    assert "email_obfuscated" in scan_text(text, known_names=set())


def test_vendor_key_shapes_are_each_caught():
    samples = {
        "github_token": "ghp_" + "a" * 36,
        "aws_access_key": "AKIA" + "Q" * 16,
        "slack_token": "xoxb-" + "1" * 12,
        "openai_key": "sk-" + "b" * 20,
        "npm_token": "npm_" + "c" * 36,
        "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ_abc123",
        "ssh_public_key": "ssh-ed25519 " + "A" * 60,
    }
    for kind, token in samples.items():
        found = scan_text(f"voici la valeur : {token} fin\n", known_names=set())
        assert kind in found, f"{kind} not detected in {token!r}"


def test_serial_field_is_caught_but_not_a_placeholder():
    assert "serial_number" in scan_text("Serial Number: XK3-9910AB\n", known_names=set())
    assert "serial_number" not in scan_text("Serial Number: 0000000000\n", known_names=set())


def test_imei_like_number_is_caught_but_not_a_placeholder_run():
    assert "imei_like" in scan_text("IMEI: 490154203237518\n", known_names=set())
    assert "imei_like" not in scan_text("padding: 000000000000000\n", known_names=set())


def test_broad_home_path_is_caught_but_the_lab_placeholder_is_not():
    assert "home_path" in scan_text("chemin : /home/adupont/projet\n", known_names=set())
    assert scan_text("chemin : /home/user/projet\n", known_names=set()) == []


def test_clean_terminal_output_has_no_findings():
    text = ("Commande : df -h\n"
           "Statut : succes (code 0)\n"
           "Sortie :\n"
           "Racine 685G libres sur 953G, 29 %.\n")
    assert scan_text(text, known_names=set()) == []
