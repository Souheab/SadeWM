"""Use configured Qt paths, with a cached fallback for split Nix Qt packages."""
import hashlib
import os
from pathlib import Path
import subprocess


def qml_import_paths(configured):
    import PySide6
    from PySide6 import QtQml
    from PySide6.QtCore import QLibraryInfo

    if any((Path(p) / "QtQuick" / "qmldir").is_file() for p in configured):
        return []
    candidates = [QLibraryInfo.path(QLibraryInfo.LibraryPath.Qml2ImportsPath),
                  str(Path(PySide6.__file__).parent / "Qt" / "qml")]
    if any((Path(p) / "QtQuick" / "qmldir").is_file() for p in candidates):
        return [p for p in candidates if Path(p).is_dir() and p not in configured]
    identity = str(Path(QtQml.__file__).resolve()) + PySide6.__version__
    key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "sadeshell" / ("qt-" + key)
    try:
        cached = cache.read_text().splitlines()
        if cached and all(Path(p).is_dir() for p in cached):
            return cached
    except OSError:
        pass
    paths = []
    try:
        result = subprocess.run(["ldd", QtQml.__file__], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if "libQt6Qml.so" in line and "=>" in line:
                library = Path(line.split("=>")[1].split()[0]).resolve()
                candidate = library.parent.parent / "lib" / "qt-6" / "qml"
                if candidate.is_dir():
                    paths.append(str(candidate))
                break
        if paths:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text("\n".join(paths))
    except (OSError, subprocess.SubprocessError):
        pass
    return paths
