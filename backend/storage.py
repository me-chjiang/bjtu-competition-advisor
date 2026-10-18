"""Single-process JSON sessions and nonwaiting guards (AI-assisted).

Only validated UUID hex IDs become filenames. No directories are created until
a write; processing is runtime-only and never serialized into a record.
"""

import os
import re
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from backend.schemas import AppError, SessionRecord, SessionSnapshot


def _storage_error() -> AppError:
    return AppError("INTERNAL_ERROR", "会话存储暂不可用，请稍后重试。", 500)


class SessionStore:
    def __init__(self, root: Path, *, boundary: Path | None = None) -> None:
        # Keep lexical paths: resolving here would silently trust pre-existing links.
        # The app passes Settings' canonical data_dir as its explicit trusted boundary.
        self.root = Path(os.path.abspath(root))
        self._boundary = (
            Path(os.path.abspath(boundary)) if boundary is not None else Path(self.root.anchor)
        )
        self._processing: set[str] = set()

    def _check_directories(self) -> None:
        try:
            relative = self.root.relative_to(self._boundary)
            directory = self._boundary
            if directory.is_symlink():
                raise _storage_error()
            for part in relative.parts:
                directory = directory / part
                if directory.is_symlink():
                    raise _storage_error()
        except (OSError, ValueError):
            raise _storage_error() from None

    def _path(self, session_id: str) -> Path:
        if not isinstance(session_id, str) or re.fullmatch(r"[0-9a-f]{32}", session_id) is None:
            raise AppError("SESSION_NOT_FOUND", "会话不存在或不可访问。", 404)
        # Shared by reads and writes, including missing roots and intermediate dirs.
        self._check_directories()
        return self.root / f"{session_id}.json"

    def create(self) -> SessionRecord:
        session_id = uuid4().hex
        while self._path(session_id).exists():
            session_id = uuid4().hex
        record = SessionRecord(
            snapshot=SessionSnapshot(
                session_id=session_id,
                message="请介绍你的专业、年级和想参加竞赛的目标。",
            )
        )
        self.save(record)
        return record

    def load(self, session_id: str) -> SessionRecord:
        path = self._path(session_id)
        try:
            if path.is_symlink():
                raise _storage_error()
            record = SessionRecord.model_validate_json(path.read_bytes())
            if record.snapshot.session_id != session_id:
                raise _storage_error()
            return record
        except FileNotFoundError:
            raise AppError("SESSION_NOT_FOUND", "会话不存在或不可访问。", 404) from None
        except (OSError, ValidationError, ValueError):
            raise _storage_error() from None

    def _prepare_root(self) -> None:
        self._check_directories()
        # pathlib's parents=True uses default permissions on intermediate dirs.
        # Create each missing directory explicitly without changing existing parents.
        missing = []
        directory = self.root
        while not directory.exists():
            missing.append(directory)
            directory = directory.parent
        for directory in reversed(missing):
            directory.mkdir(mode=0o700, exist_ok=True)
        self._check_directories()
        self.root.chmod(0o700)

    def save(self, record: SessionRecord) -> None:
        temporary: Path | None = None
        try:
            # Revalidate serialized fields, not model instances: assignment and
            # model_copy(update=...) bypass Pydantic's construction validators.
            validated = SessionRecord.model_validate(record.model_dump(mode="json"))
            path = self._path(validated.snapshot.session_id)
            if path.exists() or path.is_symlink():
                self.load(validated.snapshot.session_id)  # Never repair/replace corrupt records.
            payload = validated.model_dump_json()
            self._prepare_root()
            descriptor, name = tempfile.mkstemp(prefix=".session-", suffix=".tmp", dir=self.root)
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except (OSError, ValidationError, ValueError, TypeError):
            raise _storage_error() from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass  # Never delete other files or mask the original failure.

    @asynccontextmanager
    async def guard(self, session_id: str) -> AsyncIterator[None]:
        self._path(session_id)
        # No await between testing and adding: atomic within this process's event loop.
        if session_id in self._processing:
            raise AppError(
                "REQUEST_IN_PROGRESS",
                "会话正在处理中，请稍后查看。",
                409,
                retryable=True,
            )
        self._processing.add(session_id)
        try:
            yield
        finally:
            self._processing.remove(session_id)

    def is_processing(self, session_id: str) -> bool:
        self._path(session_id)
        return session_id in self._processing
