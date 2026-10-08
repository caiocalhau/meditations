"""Test fixtures shared by the small local helper tests."""

import pytest


@pytest.fixture(autouse=True)
def isolated_machine_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "machine-settings"))
