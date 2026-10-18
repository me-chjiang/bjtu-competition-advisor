"""Offline storage safety tests; AI-assisted, all records are fictional."""

import asyncio
import json
import stat

import pytest

from backend.schemas import AppError, SessionRecord
from backend.storage import SessionStore


def test_create_and_reload_private_record(tmp_path):
    root = tmp_path / "private" / "sessions"
    store = SessionStore(root)
    assert not root.exists()
    record = store.create()
    assert SessionStore(root).load(record.snapshot.session_id) == record
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(root.parent.stat().st_mode) == 0o700
    path = root / f"{record.snapshot.session_id}.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not json.loads(path.read_text())["snapshot"]["processing"]


@pytest.mark.parametrize(
    "session_id",
    [
        "../outside",
        "/tmp/outside",
        "a" * 31,
        "A" * 32,
        "g" * 32,
        "a" * 32 + "\n",
        "a" * 32 + "/../../outside",
        "",
    ],
)
async def test_session_id_cannot_escape_root(tmp_path, session_id):
    root = tmp_path / "sessions"
    store = SessionStore(root)
    with pytest.raises(AppError) as caught:
        store.load(session_id)
    assert caught.value.code == "SESSION_NOT_FOUND"
    with pytest.raises(AppError):
        async with store.guard(session_id):
            pytest.fail("Invalid ID acquired a guard")
    unsafe = SessionRecord.model_validate({"snapshot": {"session_id": session_id or "bad"}})
    with pytest.raises(AppError):
        store.save(unsafe)
    assert not root.exists()


def test_corrupt_session_is_not_replaced(tmp_path):
    store = SessionStore(tmp_path)
    record = store.create()
    path = tmp_path / f"{record.snapshot.session_id}.json"
    path.write_text('{"fictional_secret": "test-only-secret", broken')
    previous = path.read_bytes()
    with pytest.raises(AppError) as caught:
        store.load(record.snapshot.session_id)
    assert caught.value.code == "INTERNAL_ERROR"
    assert "test-only-secret" not in str(caught.value)
    with pytest.raises(AppError):
        store.save(record)
    assert path.read_bytes() == previous


def test_record_id_must_match_filename(tmp_path):
    store = SessionStore(tmp_path)
    first, second = store.create(), store.create()
    path = tmp_path / f"{first.snapshot.session_id}.json"
    path.write_text(second.model_dump_json())
    with pytest.raises(AppError):
        store.load(first.snapshot.session_id)


def test_session_symlink_cannot_read_or_replace_external_file(tmp_path):
    root = tmp_path / "sessions"
    store = SessionStore(root)
    record = store.create()
    external = tmp_path / "outside.json"
    external.write_text(record.model_dump_json())
    path = root / f"{record.snapshot.session_id}.json"
    path.unlink()
    path.symlink_to(external)
    previous = external.read_bytes()
    with pytest.raises(AppError):
        store.load(record.snapshot.session_id)
    with pytest.raises(AppError):
        store.save(record)
    assert path.is_symlink()
    assert external.read_bytes() == previous


@pytest.mark.parametrize("linked_directory", ["root", "ancestor"])
@pytest.mark.parametrize("operation", ["load", "save", "create"])
def test_directory_symlinks_are_rejected_consistently(tmp_path, linked_directory, operation):
    external = tmp_path / "outside"
    external_store = SessionStore(external / "sessions")
    record = external_store.create()
    path = external / "sessions" / f"{record.snapshot.session_id}.json"
    previous = path.read_bytes()
    link = tmp_path / "link"
    link.symlink_to(external / "sessions" if linked_directory == "root" else external)
    root = link if linked_directory == "root" else link / "sessions"
    store = SessionStore(root)

    with pytest.raises(AppError) as caught:
        if operation == "load":
            store.load(record.snapshot.session_id)
        elif operation == "save":
            record.snapshot.revision = 1
            store.save(record)
        else:
            store.create()
    assert caught.value.code == "INTERNAL_ERROR"
    assert path.read_bytes() == previous
    assert list((external / "sessions").iterdir()) == [path]


def test_directory_replaced_with_symlink_after_store_creation_is_rejected(tmp_path):
    root = tmp_path / "trusted" / "sessions"
    store = SessionStore(root)
    record = store.create()
    moved = tmp_path / "moved"
    root.rename(moved)
    root.symlink_to(moved)
    previous = (moved / f"{record.snapshot.session_id}.json").read_bytes()
    with pytest.raises(AppError):
        store.load(record.snapshot.session_id)
    with pytest.raises(AppError):
        store.save(record)
    assert (moved / f"{record.snapshot.session_id}.json").read_bytes() == previous


def test_explicit_trusted_boundary_still_checks_its_descendants(tmp_path):
    boundary = tmp_path / "trusted"
    boundary.mkdir()
    external = tmp_path / "outside"
    external_store = SessionStore(external / "sessions")
    record = external_store.create()
    (boundary / "nested").symlink_to(external)
    store = SessionStore(boundary / "nested" / "sessions", boundary=boundary)
    with pytest.raises(AppError):
        store.load(record.snapshot.session_id)
    with pytest.raises(AppError):
        store.create()


def test_replace_failure_preserves_previous_file(tmp_path, monkeypatch):
    import backend.storage as storage

    store = SessionStore(tmp_path)
    record = store.create()
    path = tmp_path / f"{record.snapshot.session_id}.json"
    previous = path.read_bytes()
    unrelated = tmp_path / "unrelated.tmp"
    unrelated.write_text("leave me alone")
    record.snapshot.revision = 1

    def fail_replace(source, target):
        raise OSError("test-only-secret")

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    with pytest.raises(AppError) as caught:
        store.save(record)
    assert caught.value.code == "INTERNAL_ERROR"
    assert "test-only-secret" not in str(caught.value)
    assert path.read_bytes() == previous
    assert set(tmp_path.iterdir()) == {path, unrelated}


def test_fsync_failure_preserves_previous_file(tmp_path, monkeypatch):
    import backend.storage as storage

    store = SessionStore(tmp_path)
    record = store.create()
    path = tmp_path / f"{record.snapshot.session_id}.json"
    previous = path.read_bytes()
    unrelated = tmp_path / "unrelated.tmp"
    unrelated.write_text("leave me alone")
    record.snapshot.revision = 1

    def fail_fsync(descriptor):
        raise OSError("fictional-secret-fsync")

    monkeypatch.setattr(storage.os, "fsync", fail_fsync)
    with pytest.raises(AppError) as caught:
        store.save(record)
    assert "fictional-secret" not in str(caught.value)
    assert path.read_bytes() == previous
    assert set(tmp_path.iterdir()) == {path, unrelated}


def test_save_revalidates_mutated_record(tmp_path):
    store = SessionStore(tmp_path)
    record = store.create()
    path = tmp_path / f"{record.snapshot.session_id}.json"
    previous = path.read_bytes()
    # Pydantic assignment/model_copy bypass validation, so storage must not trust them.
    record.snapshot = record.snapshot.model_copy(update={"processing": True})
    with pytest.raises(AppError):
        store.save(record)
    assert path.read_bytes() == previous


async def test_guard_is_nonwaiting_and_independent(tmp_path):
    store = SessionStore(tmp_path)
    first, second = store.create(), store.create()
    session_id = first.snapshot.session_id
    async with store.guard(session_id):
        assert store.is_processing(session_id)
        with pytest.raises(AppError) as caught:
            async with store.guard(session_id):
                pytest.fail("Busy guard was acquired")
        assert caught.value.code == "REQUEST_IN_PROGRESS"
        assert caught.value.status_code == 409
        async with store.guard(second.snapshot.session_id):
            assert store.is_processing(session_id)
    assert not store.is_processing(session_id)


async def test_exception_guard_is_released(tmp_path):
    store = SessionStore(tmp_path)
    session_id = store.create().snapshot.session_id
    with pytest.raises(RuntimeError):
        async with store.guard(session_id):
            raise RuntimeError("fictional error")
    async with store.guard(session_id):
        assert store.is_processing(session_id)
    assert not store.is_processing(session_id)


async def test_cancelled_guard_is_released(tmp_path):
    store = SessionStore(tmp_path)
    session_id = store.create().snapshot.session_id
    entered = asyncio.Event()

    async def work():
        async with store.guard(session_id):
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(work())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not store.is_processing(session_id)
    async with store.guard(session_id):
        assert store.is_processing(session_id)
