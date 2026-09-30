from unittest import mock

import pytest

from sadeshell.services.shared.icon_index import IconIndex


def install_icon(root, relative):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return str(path)


def test_application_icon_wins_over_unrelated_high_contrast_theme(tmp_path):
    install_icon(tmp_path, "HighContrast/16x16/apps/firefox.png")
    install_icon(tmp_path, "HighContrast/scalable/apps/firefox.svg")
    expected = install_icon(tmp_path, "hicolor/64x64/apps/firefox.png")
    index = IconIndex()
    with mock.patch.object(index, "roots", return_value=[str(tmp_path)]):
        assert index.resolve("firefox") == expected
        assert index.resolve("Firefox.png") == expected


@pytest.mark.parametrize("sizes, chosen", [
    ([16, 32, 48, 64, 128, 256], 64),
    ([16, 32, 48, 128, 256], 128),
    ([16, 32, 48], 48),
])
def test_raster_resolution_suits_launcher_and_picker(tmp_path, sizes, chosen):
    for size in sizes:
        install_icon(tmp_path, f"hicolor/{size}x{size}/apps/demo.png")
    index = IconIndex()
    with mock.patch.object(index, "roots", return_value=[str(tmp_path)]):
        assert index.resolve("demo") == str(tmp_path / f"hicolor/{chosen}x{chosen}/apps/demo.png")


def test_user_override_retains_precedence_over_system_application_icon(tmp_path):
    user, system = tmp_path / "user", tmp_path / "system"
    expected = install_icon(user, "custom/32x32/apps/demo.png")
    install_icon(system, "hicolor/scalable/apps/demo.svg")
    index = IconIndex()
    with mock.patch.object(index, "roots", return_value=[str(user), str(system)]):
        assert index.resolve("demo") == expected


def test_svg_fallback_theme_and_explicit_symbolic_icon_remain_available(tmp_path):
    install_icon(tmp_path, "hicolor/64x64/apps/demo.png")
    vector = install_icon(tmp_path, "hicolor/scalable/apps/demo.svg")
    fallback = install_icon(tmp_path, "HighContrast/48x48/apps/other.png")
    symbolic = install_icon(tmp_path, "hicolor/symbolic/apps/demo-symbolic.svg")
    index = IconIndex()
    with mock.patch.object(index, "roots", return_value=[str(tmp_path)]):
        assert index.resolve("demo") == vector
        assert index.resolve("other") == fallback
        assert index.resolve("demo-symbolic") == symbolic
        assert index.resolve(fallback) == fallback
