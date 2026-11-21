"""Shared pytest fixtures guarding Tafreegh tests against live OneDrive access."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_onedrive_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Redirect TAFREEGH_ONEDRIVE_BASE to a dedicated per-test scratch directory."""
    scratch_onedrive = tmp_path_factory.mktemp("scratch_onedrive")
    monkeypatch.setenv("TAFREEGH_ONEDRIVE_BASE", str(scratch_onedrive))
    return scratch_onedrive
