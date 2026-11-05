"""Remembered yes/no settings (e.g. 'Info Wizard is on'). The renderer stores them; tests use the in-memory one."""
from typing import Protocol


class Preferences(Protocol):
    def get_bool(self, key: str, default: bool = False) -> bool: ...
    def set_bool(self, key: str, value: bool) -> None: ...


class MemoryPreferences:
    def __init__(self, **values: bool) -> None:
        self.values: dict[str, bool] = dict(values)

    def get_bool(self, key: str, default: bool = False) -> bool:
        return self.values.get(key, default)

    def set_bool(self, key: str, value: bool) -> None:
        self.values[key] = value
