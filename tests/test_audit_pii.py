"""Regression test for bench/matrix/finetune/audit_pii.py.

Found while auditing the K2 English macOS corpus: `ps aux` routinely prints
paths like `/Applications/iTerm 2.app/Contents/MacOS/...`. RULES["domain"]
treated ".app" as a domain-like TLD, so any macOS application bundle whose
name ends in a digit ("iTerm 2.app", "Affinity Photo 2.app"...) was flagged
as a private_domain finding - a structural false positive on every macOS
capture, not a real leak. A genuine ".dev"/".io"-style domain must still be
caught.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

from audit_pii import scan_text


def test_macos_app_bundle_name_is_not_a_private_domain():
    text = "user 31408 /Applications/iTerm 2.app/Contents/MacOS/iTerm2\n"
    assert "private_domain" not in scan_text(text, names=[])


def test_real_private_domain_is_still_caught():
    text = "connecting to internal-tracker.dev now\n"
    assert scan_text(text, names=[]).count("private_domain") == 1


def test_local_mdns_hostname_is_still_caught():
    text = "mac.local\n"
    assert scan_text(text, names=[]).count("private_domain") == 1


# `system_profiler SPHardwareDataType` on the K2 macOS capture leaked the
# real hardware serial number and provisioning UDID: neither matches any
# existing generic rule (the serial is short, mixed-case-insensitive
# alphanumeric with only 2 character classes; the UDID is not shaped like a
# standard 8-4-4-4-12 UUID).

def test_hardware_serial_number_is_caught():
    text = "      Serial Number (system): LFQDJJ6QCQ\n"
    assert scan_text(text, names=[]).count("serial_number") == 1


def test_placeholder_serial_number_is_not_flagged():
    text = "      Serial Number (system): 0000000000\n"
    assert "serial_number" not in scan_text(text, names=[])


def test_provisioning_udid_is_caught():
    text = "      Provisioning UDID: 00006030-001A11DC1104001C\n"
    assert scan_text(text, names=[]).count("provisioning_udid") == 1


def test_redacted_serial_and_udid_tokens_are_not_flagged():
    text = "      Serial Number (system): [SERIE_SUPPRIMEE]\n      Provisioning UDID: [IDENTIFIANT_SUPPRIME]\n"
    found = scan_text(text, names=[])
    assert "serial_number" not in found and "provisioning_udid" not in found


# Training rows keep their text under "messages": scanning only top-level
# strings let every chat-format file pass with TOTAL 0 without being read.
def test_scan_file_reads_chat_message_contents(tmp_path):
    from audit_pii import load_names, scan_file
    names_file = tmp_path / "names.tsv"
    names_file.write_text("zorglub-host\tmachine\n")
    data = tmp_path / "rows.jsonl"
    data.write_text('{"source": "qa", "messages": [{"role": "user", "content": "ssh zorglub-host"}]}\n')
    per_type, _ = scan_file(str(data), load_names(str(names_file)))
    assert per_type["known_name"] == 1
