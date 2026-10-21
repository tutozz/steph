"""status_text : formulation du statut d'une commande pour le prompt du modèle."""

import pytest

from steph.prompts import status_text


@pytest.mark.parametrize("code, expected", [
    (0, "succès (code 0)"),
    (130, "interrompue par l'utilisateur (Ctrl+C, code 130)"),
    (137, "tuée par un signal (code 137)"),  # SIGKILL, 128 + 9
    (143, "tuée par un signal (code 143)"),  # SIGTERM, 128 + 15
])
def test_status_text_signal_codes(code, expected):
    assert status_text(code) == expected


def test_status_text_255_is_not_a_signal():
    """255 dépasse le plus grand signal réel (128 + 64) : ce n'est pas une mort par signal."""
    assert status_text(255) == "échec (code 255)"
    assert "signal" not in status_text(255)


@pytest.mark.parametrize("code", [1, 2, 100, 127])
def test_status_text_plain_failures(code):
    assert status_text(code) == f"échec (code {code})"
