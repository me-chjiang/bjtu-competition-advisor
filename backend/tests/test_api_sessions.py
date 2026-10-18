"""Fictional, offline API checks; AI-assisted from the frontend contract."""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from backend.config import Settings
from backend.main import create_app
from backend.schemas import (
    CandidateCard,
    ChatRequest,
    Plan,
    Profile,
    SessionRecord,
    SuccessfulRequest,
)
from backend.storage import SessionStore


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "private", deepseek_api_key=None)


@pytest.fixture
async def client(settings):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as client:
        yield client


async def test_create_and_reload_session(client, settings):
    assert not settings.data_dir.exists()
    created_response = await client.post("/api/sessions", json={})
    assert created_response.status_code == 201
    created = created_response.json()
    assert created["stage"] == "R0"
    assert created["revision"] == 0
    assert created["status"] == "collecting"
    assert created["processing"] is False
    assert created["last_request_id"] is None
    assert created["message"]
    assert created["messages"] == []
    assert created["cards"] == []
    assert created["plan"] is None
    assert created["needs_confirmation"] is False
    assert created["profile"] == {
        "grade": None,
        "major": None,
        "skills": [],
        "weekly_hours": None,
        "goals": [],
        "team_preference": None,
        "unavailable_dates": [],
        "additional_context": None,
    }
    assert len(created["session_id"]) == 32
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as restarted:
        reloaded_response = await restarted.get(f"/api/sessions/{created['session_id']}")
    assert reloaded_response.json() == created_response.json()


async def test_profile_patch_invalidates_results(client, settings):
    created = (await client.post("/api/sessions", json={})).json()
    store = SessionStore(settings.data_dir / "sessions")
    record = store.load(created["session_id"])
    values = record.model_dump()
    values["snapshot"].update(
        {
            "stage": "R4",
            "status": "awaiting_review",
            "needs_confirmation": True,
            "profile": Profile(major="fictional major", weekly_hours=6).model_dump(),
            "cards": [
                CandidateCard(
                    competition_instance_id="fictional_2026", name="Fictional", reason="Demo only"
                ).model_dump()
            ],
            "plan": Plan(selected_competition_ids=["fictional_2026"]).model_dump(),
        }
    )
    values["confirmed_profile"] = values["snapshot"]["profile"]
    values["coarse_cards"] = values["snapshot"]["cards"]
    store.save(SessionRecord.model_validate(values))
    response = await client.patch(
        f"/api/sessions/{created['session_id']}/profile",
        json={
            "expected_revision": 0,
            "changes": {"weekly_hours": None, "additional_context": "Fictional preference"},
        },
    )
    assert response.status_code == 200
    patched = response.json()
    assert patched["revision"] == 1
    assert patched["stage"] == "R0"
    assert patched["status"] == "collecting"
    assert patched["cards"] == []
    assert patched["plan"] is None
    assert patched["processing"] is False
    assert patched["needs_confirmation"] is False
    assert patched["profile"]["major"] == "fictional major"
    assert patched["profile"]["weekly_hours"] is None
    assert patched["profile"]["additional_context"] == "Fictional preference"
    saved = store.load(created["session_id"])
    assert saved.confirmed_profile is None
    assert saved.coarse_cards == []
    assert (await client.get(f"/api/sessions/{created['session_id']}")).json() == patched


async def test_revision_conflict_preserves_state(client):
    created = (await client.post("/api/sessions", json={})).json()
    url = f"/api/sessions/{created['session_id']}/profile"
    first = await client.patch(url, json={"expected_revision": 0, "changes": {"major": "Demo"}})
    stale = await client.patch(url, json={"expected_revision": 0, "changes": {"major": "Other"}})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
    assert stale.json()["error"]["details"] == {"current_revision": 1}
    assert (await client.get(f"/api/sessions/{created['session_id']}")).json() == first.json()


async def test_busy_session_is_readable(settings):
    app = create_app(settings)
    store = app.state.service.store
    record = store.create()
    session_id = record.snapshot.session_id
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async with store.guard(session_id):
            response = await client.get(f"/api/sessions/{session_id}")
            assert response.status_code == 200
            assert response.json()["processing"] is True
            assert response.json()["revision"] == 0
            busy = await client.patch(
                f"/api/sessions/{session_id}/profile",
                json={
                    "expected_revision": 0,
                    "changes": {"grade": "Demo"},
                },
            )
            assert busy.status_code == 409
            assert busy.json()["error"]["code"] == "REQUEST_IN_PROGRESS"
            assert store.load(session_id).snapshot.processing is False
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=create_app(settings)), base_url="http://test"
            ) as restarted:
                assert (await restarted.get(f"/api/sessions/{session_id}")).json()[
                    "processing"
                ] is False
        assert (await client.get(f"/api/sessions/{session_id}")).json()["processing"] is False


async def test_validation_error_does_not_echo_secret(client):
    created = (await client.post("/api/sessions", json={})).json()
    secret = "fictional-secret-do-not-echo"
    for payload in [
        {"expected_revision": 0, "changes": {"weekly_hours": secret}},
        {"expected_revision": 0, "changes": {secret: secret}},
        {"expected_revision": secret, "changes": {"major": "Demo"}},
        {"expected_revision": 0, "changes": {"additional_context": secret * 100}},
    ]:
        response = await client.patch(
            f"/api/sessions/{created['session_id']}/profile",
            json=payload,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert response.json()["request_id"] is None
        assert secret not in response.text
        assert "input" not in response.text
        assert "ctx" not in response.text
        assert "Traceback" not in response.text
    malformed = await client.post(
        "/api/sessions",
        content='{"fictional-secret-do-not-echo":',
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code == 422
    assert secret not in malformed.text


async def test_cors_defaults_closed(client):
    response = await client.post(
        "/api/sessions", json={}, headers={"Origin": "http://localhost:5173"}
    )
    assert "access-control-allow-origin" not in response.headers
    preflight = await client.options(
        "/api/sessions",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in preflight.headers


async def test_cors_allows_only_explicit_origins(settings):
    app = create_app(settings.model_copy(update={"allowed_origins": ["http://localhost:5173"]}))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for origin, allowed in [("http://localhost:5173", True), ("https://evil.example", False)]:
            response = await client.options(
                "/api/sessions/demo/profile",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "PATCH",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert response.headers.get("access-control-allow-origin") == (
                origin if allowed else None
            )


async def test_missing_session_and_http_errors_have_envelopes(client, settings):
    for url in ["/api/sessions/not-a-uuid", "/api/sessions/" + "a" * 32]:
        response = await client.get(url)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
    unknown = await client.get("/does-not-exist")
    assert unknown.status_code == 404
    assert "error" in unknown.json()
    unsupported = await client.put("/api/sessions", json={})
    assert unsupported.status_code == 405
    assert "error" in unsupported.json()
    assert not settings.data_dir.exists()


async def test_internal_errors_are_safe_and_release_lock(settings, monkeypatch, caplog):
    app = create_app(settings)
    store = app.state.service.store
    record = store.create()
    previous = store.load(record.snapshot.session_id)

    def fail_save(record):
        raise RuntimeError("fictional-secret-traceback")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        with monkeypatch.context() as patcher:
            patcher.setattr(store, "save", fail_save)
            response = await client.patch(
                f"/api/sessions/{record.snapshot.session_id}/profile",
                json={"expected_revision": 0, "changes": {"major": "Demo"}},
            )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "fictional-secret" not in response.text
        assert "Traceback" not in response.text
        assert "fictional-secret" not in caplog.text
        assert all(record.exc_info is None for record in caplog.records)
        assert not store.is_processing(record.snapshot.session_id)
        assert store.load(record.snapshot.session_id) == previous
        retry = await client.patch(
            f"/api/sessions/{record.snapshot.session_id}/profile",
            json={
                "expected_revision": 0,
                "changes": {"major": "Demo"},
            },
        )
        assert retry.status_code == 200


@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("http://localhost:5173", True),
        ("https://evil.example", False),
    ],
)
async def test_unexpected_error_keeps_cors_policy(settings, monkeypatch, origin, allowed):
    app = create_app(settings.model_copy(update={"allowed_origins": ["http://localhost:5173"]}))
    store = app.state.service.store
    record = store.create()

    def fail_save(record):
        raise RuntimeError("fictional-secret-cors")

    monkeypatch.setattr(store, "save", fail_save)
    # Raw ASGI records both headers and exception propagation, without suppressing either.
    payload = json.dumps({"expected_revision": 0, "changes": {"major": "Demo"}}).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "PATCH",
        "scheme": "http",
        "query_string": b"",
        "root_path": "",
        "path": f"/api/sessions/{record.snapshot.session_id}/profile",
        "headers": [(b"origin", origin.encode()), (b"content-type", b"application/json")],
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    async def send(message):
        sent.append(message)

    propagated = None
    try:
        await app(scope, receive, send)
    except Exception as error:
        propagated = error
    start = next(message for message in sent if message["type"] == "http.response.start")
    assert start["status"] == 500
    assert dict(start["headers"]).get(b"access-control-allow-origin") == (
        origin.encode() if allowed else None
    )
    assert propagated is None, "Ordinary route exceptions must not reach the ASGI server"


async def test_uvicorn_error_path_never_logs_original_exception(settings, monkeypatch, caplog):
    import h11
    from uvicorn.protocols.http.flow_control import FlowControl
    from uvicorn.protocols.http.h11_impl import RequestResponseCycle

    app = create_app(settings)
    store = app.state.service.store
    record = store.create()
    secret = "fictional-secret-uvicorn"

    def fail_save(record):
        raise RuntimeError(secret)

    monkeypatch.setattr(store, "save", fail_save)
    body = json.dumps({"expected_revision": 0, "changes": {"major": "Demo"}}).encode()
    path = f"/api/sessions/{record.snapshot.session_id}/profile"
    connection = h11.Connection(h11.SERVER)
    connection.receive_data(
        f"PATCH {path} HTTP/1.1\r\nHost: test\r\nContent-Length: {len(body)}\r\n\r\n".encode()
        + body
    )
    for event_type in (h11.Request, h11.Data, h11.EndOfMessage):
        assert isinstance(connection.next_event(), event_type)

    class MemoryTransport(asyncio.Transport):
        def __init__(self):
            self.output = bytearray()

        def write(self, data):
            self.output.extend(data)

        def close(self):
            pass

        def resume_reading(self):
            pass

    transport = MemoryTransport()
    logger = logging.getLogger("task2.test-server")
    cycle = RequestResponseCycle(
        scope={
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "PATCH",
            "scheme": "http",
            "query_string": b"",
            "root_path": "",
            "path": path,
            "headers": [(b"content-type", b"application/json")],
        },
        conn=connection,
        transport=transport,
        flow=FlowControl(transport),
        logger=logger,
        access_logger=logger,
        access_log=False,
        default_headers=[],
        message_event=asyncio.Event(),
        on_response=lambda: None,
    )
    cycle.body = bytearray(body)
    cycle.more_body = False
    cycle.message_event.set()
    with caplog.at_level(logging.ERROR):
        await cycle.run_asgi(app)
    assert cycle.response_complete
    assert b'"code":"INTERNAL_ERROR"' in transport.output
    assert secret not in transport.output.decode()
    assert secret not in caplog.text
    assert "Traceback" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert [record.getMessage() for record in caplog.records if record.name == "backend.main"] == [
        "HTTP request failed: INTERNAL_ERROR",
    ]


async def test_http_cancellation_propagates_and_releases_guard(settings, caplog):
    app = create_app(settings)
    store = app.state.service.store
    record = store.create()
    entered = asyncio.Event()

    @app.get("/test-cancellation")
    async def cancelled_operation():
        async with store.guard(record.snapshot.session_id):
            entered.set()
            await asyncio.Event().wait()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        task = asyncio.create_task(client.get("/test-cancellation"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not store.is_processing(record.snapshot.session_id)
    assert store.load(record.snapshot.session_id) == record
    assert not [entry for entry in caplog.records if entry.levelno >= logging.ERROR]


async def test_get_rejects_sessions_directory_symlink(settings, tmp_path):
    external = SessionStore(tmp_path / "outside")
    record = external.create()
    settings.data_dir.mkdir(mode=0o700)
    (settings.data_dir / "sessions").symlink_to(external.root)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/sessions/{record.snapshot.session_id}")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert record.snapshot.session_id not in response.text


async def test_internal_caches_never_leak(client, settings):
    created = (await client.post("/api/sessions", json={})).json()
    store = SessionStore(settings.data_dir / "sessions")
    record = store.load(created["session_id"])
    record.confirmed_profile = Profile(major="fictional-private-confirmed")
    record.successful_requests["private-cache"] = SuccessfulRequest(
        request=ChatRequest(
            request_id="private-cache",
            expected_revision=0,
            action="message",
            content="fictional-private-cache",
        ),
        snapshot=record.snapshot,
    )
    store.save(record)
    response = await client.get(f"/api/sessions/{created['session_id']}")
    assert response.json() == created
    assert "fictional-private" not in response.text
    assert "successful_requests" not in response.text


def test_factory_defaults_never_read_private_config_or_write(tmp_path, monkeypatch):
    # Any filesystem content access would be a bug: defaults only parse environment.
    def forbidden(*args, **kwargs):
        pytest.fail("App factory must not read configuration or write data")

    monkeypatch.setenv("BJTU_DATA_DIR", str(tmp_path / "unused"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    app = create_app()
    assert app.state.settings.data_dir == tmp_path / "unused"
    assert app.state.settings.deepseek_api_key is None


def test_first_project_import_has_no_file_io(tmp_path):
    # Preload third-party metadata before prohibiting project-level explicit I/O.
    # A fresh process, rather than reload(), proves first import of backend.main.
    script = """
import fastapi, pydantic, yaml
from pathlib import Path
import os

def forbidden(*args, **kwargs):
    raise AssertionError("Project import must not read content or create directories")

Path.open = forbidden
Path.mkdir = forbidden
import backend.main
assert backend.main.app.state.settings.data_dir == Path(os.environ["BJTU_DATA_DIR"])
assert not backend.main.app.state.settings.data_dir.exists()
print("import-safe")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env={
            "BJTU_DATA_DIR": str(tmp_path / "unused"),
            "DEEPSEEK_API_KEY": "fictional-import-key",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "import-safe"
    assert not (tmp_path / "unused").exists()


async def test_noop_patch_preserves_revision(client):
    created = (await client.post("/api/sessions", json={})).json()
    response = await client.patch(
        f"/api/sessions/{created['session_id']}/profile",
        json={
            "expected_revision": 0,
            "changes": {"additional_context": "   "},
        },
    )
    assert response.status_code == 200
    assert response.json() == created


async def test_noop_patch_preserves_valid_results_and_internal_state(client, settings):
    created = (await client.post("/api/sessions", json={})).json()
    store = SessionStore(settings.data_dir / "sessions")
    values = store.load(created["session_id"]).model_dump()
    values["snapshot"].update(
        {
            "revision": 8,
            "stage": "R4",
            "status": "awaiting_review",
            "needs_confirmation": True,
            "profile": Profile(major="Fictional", weekly_hours=6).model_dump(),
            "cards": [
                CandidateCard(
                    competition_instance_id="fictional_2026",
                    name="Fictional",
                    reason="Demo only",
                ).model_dump()
            ],
            "plan": Plan(selected_competition_ids=["fictional_2026"]).model_dump(),
        }
    )
    values["confirmed_profile"] = values["snapshot"]["profile"]
    values["coarse_cards"] = values["snapshot"]["cards"]
    store.save(SessionRecord.model_validate(values))
    before = (await client.get(f"/api/sessions/{created['session_id']}")).json()
    path = settings.data_dir / "sessions" / f"{created['session_id']}.json"
    previous_bytes = path.read_bytes()
    response = await client.patch(
        f"/api/sessions/{created['session_id']}/profile",
        json={
            "expected_revision": 8,
            "changes": {"weekly_hours": 6},
        },
    )
    assert response.status_code == 200
    assert response.json() == before
    assert path.read_bytes() == previous_bytes


async def test_corrupt_file_returns_safe_error_without_replacement(client, settings):
    created = (await client.post("/api/sessions", json={})).json()
    path = settings.data_dir / "sessions" / f"{created['session_id']}.json"
    path.write_text(json.dumps({"fictional-secret": "do-not-echo"}))
    previous = path.read_bytes()
    for response in [
        await client.get(f"/api/sessions/{created['session_id']}"),
        await client.patch(
            f"/api/sessions/{created['session_id']}/profile",
            json={
                "expected_revision": 0,
                "changes": {"major": "Demo"},
            },
        ),
    ]:
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "fictional-secret" not in response.text
        assert "do-not-echo" not in response.text
    assert path.read_bytes() == previous
