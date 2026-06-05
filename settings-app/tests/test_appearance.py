import pytest

pytest.importorskip("PySide6")

from sadesettings.main import sade_stylesheet


def test_sade_stylesheet_is_bundled():
    qss = sade_stylesheet()

    assert "sadewm Qt6 QSS Theme" in qss
    assert "#1a1b26" in qss
    assert "QPushButton" in qss
