"""Remembers which slots were already reported, so alerts are not repeated."""

from __future__ import annotations

import json
from pathlib import Path


class State:
    """
    Holds the set of slot keys already announced.

    A slot that disappears is forgotten, so if it frees up again later it is
    announced again — which is exactly what someone waiting for a cancellation
    wants.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.reported = self._load()

    def _load(self):
        try:
            with open(self.path) as fh:
                return set(json.load(fh).get("reported", []))
        except FileNotFoundError:
            return set()
        except Exception:
            return set()

    def new_among(self, keys):
        return keys - self.reported

    def sync(self, keys):
        """Replace the remembered set with what is currently available."""
        if keys == self.reported:
            return False
        self.reported = set(keys)
        self._save()
        return True

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w") as fh:
                json.dump({"reported": sorted(self.reported)}, fh, indent=2)
            tmp.replace(self.path)
        except Exception:
            pass
