import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile


def test_installed_wheel_and_sdist_contain_resources(tmp_path):
    project = Path(__file__).resolve().parents[2] / "shell"
    dist = tmp_path / "dist"
    subprocess.run([sys.executable, "-m", "build", "--no-isolation", "--outdir", str(dist), str(project)],
                   check=True, capture_output=True)
    wheel = next(dist.glob("*.whl"))
    expected = {"sadeshell/" + str(path.relative_to(project / "src/sadeshell"))
                for path in (project / "src/sadeshell").rglob("*")
                if path.is_file() and (path.suffix in (".qml", ".svg") or path.name == "qmldir")}
    with zipfile.ZipFile(wheel) as archive:
        assert expected <= set(archive.namelist())
        assert not any("/tests/" in name for name in archive.namelist())
    with tarfile.open(next(dist.glob("*.tar.gz"))) as archive:
        files = {"/".join(name.split("/")[2:]) for name in archive.getnames() if "/src/" in name}
        assert expected <= files
    installed = tmp_path / "installed"
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-compile",
                    "--target", str(installed), str(wheel)], check=True, capture_output=True)
    script = """import pathlib, sys, sadeshell, sadeshell.main
assert pathlib.Path(sadeshell.__file__).is_relative_to(sys.argv[1])
assert 'PySide6' not in sys.modules
assert (pathlib.Path(sadeshell.__file__).parent / 'components/bar/Shell.qml').is_file()
"""
    subprocess.run([sys.executable, "-c", script, str(installed)], cwd=tmp_path,
                   env=dict(os.environ, PYTHONPATH=str(installed)), check=True)
