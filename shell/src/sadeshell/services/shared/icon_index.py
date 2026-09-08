"""Shared lazy XDG icon index, including cached misses and explicit invalidation."""
import os
from pathlib import Path
import threading


class IconIndex:
    def __init__(self):
        self.lock = threading.RLock()
        self.index = None
        self.cache = {}
        self.directories = []

    @staticmethod
    def roots():
        data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
        bases = [data, *os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"),
                 str(Path.home() / ".nix-profile/share"), "/run/current-system/sw/share"]
        return list(dict.fromkeys([str(Path.home() / ".icons"),
                                   *(str(Path(base) / kind) for base in bases if base for kind in ("icons", "pixmaps"))]))

    def invalidate(self):
        with self.lock:
            self.index = None
            self.cache.clear()

    def _build(self):
        self.index = {}
        self.directories = []
        scores = {}
        visited = set()
        for priority, root in enumerate(self.roots()):
            for directory, subdirs, files in os.walk(root, followlinks=True):
                try:
                    st = os.stat(directory)
                except OSError:
                    subdirs[:] = []
                    continue
                identity = (st.st_dev, st.st_ino)
                if identity in visited:
                    subdirs[:] = []
                    continue
                visited.add(identity)
                subdirs.sort()
                self.directories.append(directory)
                for filename in sorted(files):
                    stem, ext = os.path.splitext(filename)
                    if ext.lower() not in (".png", ".svg", ".xpm"):
                        continue
                    path = os.path.join(directory, filename)
                    score = (priority, "/apps/" not in path, ext != ".svg", path)
                    for key in (stem.casefold(), filename.casefold()):
                        if key not in scores or score < scores[key]:
                            scores[key] = score
                            self.index[key] = path

    def resolve(self, name):
        if not name:
            return ""
        if os.path.isabs(name):
            return name if os.path.isfile(name) else ""
        with self.lock:
            if self.index is None:
                self._build()
            key = name.casefold()
            if key not in self.cache:
                if len(self.cache) >= 1024:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[key] = self.index.get(key, self.index.get(key.replace(" ", "-"), ""))
            return self.cache[key]


icons = IconIndex()
