"""Exercise startup locking, staging, and recovery without touching real stores."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from src.equitylens import bootstrap


def write_stores(directory):
    for name in bootstrap.STORE_NAMES:
        (directory / name).write_text(name, encoding="utf-8")


def test_concurrent_startups_share_one_build(tmp_path, monkeypatch):
    started = Event()
    finish_build = Event()
    builds = []

    def build(root, staging):
        builds.append(root)
        started.set()
        assert finish_build.wait(timeout=5)
        write_stores(staging)

    monkeypatch.setattr(bootstrap, "_build", build)
    monkeypatch.setattr(bootstrap, "_validate_stores", lambda directory, **kwargs: None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(bootstrap.ensure_data, tmp_path)
        assert started.wait(timeout=5)
        second = pool.submit(bootstrap.ensure_data, tmp_path)
        assert not any((tmp_path / "data/warehouse" / name).exists() for name in bootstrap.STORE_NAMES)
        finish_build.set()
        first.result(timeout=5)
        second.result(timeout=5)
    assert builds == [tmp_path]


def test_failed_validation_keeps_existing_files_and_retries_publication(tmp_path, monkeypatch):
    directory = tmp_path / "data/warehouse"
    directory.mkdir(parents=True)
    marker = directory / ".bootstrap-publishing"
    marker.touch()
    write_stores(directory)
    existing = directory / bootstrap.STORE_NAMES[0]
    existing.write_text("previous generation", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "_build", lambda root, staging: write_stores(staging))

    def reject_staged_snapshot(staging, *, frozen):
        assert frozen and staging.parent == directory
        raise ValueError("Snapshot lineage mismatch")

    monkeypatch.setattr(bootstrap, "_validate_stores", reject_staged_snapshot)
    with pytest.raises(bootstrap.BootstrapError, match="Snapshot lineage mismatch"):
        bootstrap.ensure_data(tmp_path)
    assert marker.exists()
    assert existing.read_text(encoding="utf-8") == "previous generation"
    assert list(directory.glob(".bootstrap-*/")) == []

    monkeypatch.setattr(bootstrap, "_validate_stores", lambda staging, *, frozen: None)
    bootstrap.ensure_data(tmp_path)
    assert not marker.exists()
    assert existing.read_text(encoding="utf-8") == bootstrap.STORE_NAMES[0]
