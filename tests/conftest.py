"""Shared fixtures."""

from __future__ import annotations

import pytest

from amin import api as api_mod
from amin.config import settings


@pytest.fixture()
def users_dir(tmp_path, monkeypatch):
    """A throwaway household: accounts, libraries and projects under tmp_path."""
    monkeypatch.setattr(settings, "users_path", tmp_path / "users")
    monkeypatch.setattr(settings, "provider", "echo")
    api_mod._engines.clear()
    return tmp_path / "users"
