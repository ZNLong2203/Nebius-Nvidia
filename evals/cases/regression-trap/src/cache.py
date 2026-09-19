"""A tiny bounded cache with a time-to-live."""

import time


class TTLCache:
    """Least-recently-used cache whose entries also expire.

    Two rules, and they interact: an entry is gone once it is older than
    ``ttl``, and the cache never holds more than ``maxsize`` live entries.
    """

    def __init__(self, maxsize: int = 2, ttl: float = 60.0) -> None:
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: dict = {}
        self._stamps: dict = {}

    def set(self, key, value) -> None:
        self._data[key] = value
        self._stamps[key] = time.monotonic()
        if len(self._data) > self.maxsize:
            oldest = min(self._stamps, key=self._stamps.get)
            self._data.pop(oldest, None)
            self._stamps.pop(oldest, None)

    def get(self, key, now: float | None = None):
        if key not in self._data:
            return None
        now = time.monotonic() if now is None else now
        if now - self._stamps[key] > self.ttl:
            return None
        return self._data[key]

    def __len__(self) -> int:
        return len(self._data)
