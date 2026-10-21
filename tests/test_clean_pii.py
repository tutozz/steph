"""Regression test for bench/matrix/finetune/clean_pii.py.

Found while anonymizing the K2 English corpus: `ip a` / `ip link` on modern
iproute2 print a udev "altname" (enx<mac>, wlx<mac>) that encodes the real
MAC address without colons. RULES["mac_altname"] in audit_pii.py already
flags it, but Cleaner.clean() never masked it - a real machine identifier
survived anonymization.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench" / "matrix" / "finetune"))

from clean_pii import Cleaner


def test_clean_masks_mac_altname():
    cleaner = Cleaner(names=[], main_lan_octet=None)
    text = "    altname enx8cec4bd96f91\n    altname wlx9c305b1ee2b3\n"
    cleaned = cleaner.clean(text)
    assert "8cec4bd96f91" not in cleaned
    assert "9c305b1ee2b3" not in cleaned
    assert "enxaabbccddeeff" in cleaned
    assert "wlxaabbccddeeff" in cleaned


def test_clean_leaves_placeholder_altname_alone():
    cleaner = Cleaner(names=[], main_lan_octet=None)
    text = "    altname enxaabbccddeeff\n"
    assert cleaner.clean(text) == text


def test_clean_masks_hardware_serial_number():
    cleaner = Cleaner(names=[], main_lan_octet=None)
    text = "      Serial Number (system): LFQDJJ6QCQ\n"
    cleaned = cleaner.clean(text)
    assert "LFQDJJ6QCQ" not in cleaned
    assert "Serial Number (system): " in cleaned


def test_clean_masks_provisioning_udid():
    cleaner = Cleaner(names=[], main_lan_octet=None)
    text = "      Provisioning UDID: 00006030-001A11DC1104001C\n"
    cleaned = cleaner.clean(text)
    assert "001A11DC1104001C" not in cleaned
    assert "Provisioning UDID: " in cleaned
