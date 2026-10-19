"""Offline HTTP transactions with fictional sources (AI-assisted, Task 5)."""

import asyncio
import copy
import json
import socket
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.agent import LiteLLMAgent
from backend.config import REPO_ROOT, Settings
from backend.main import create_app
from backend.schemas import AgentDraft, AppError

NOW = "2026-10-18T04:00:00+00:00"
PROFILE = {
    "grade": "大二",
    "major": "计算机",
    "weekly_hours": 6,
    "additional_context": "偏好算法竞赛",
}
INTRO = "我是大二计算机专业，每周6小时，偏好算法竞赛。"


def clock():
    from datetime import datetime

    return datetime.fromisoformat(NOW)


@pytest.fixture(autouse=True)
def offline_private_boundary(monkeypatch):
    """Fail rather than accidentally consulting private inputs or a paid provider."""

    def forbidden(*args, **kwargs):
        pytest.fail("Offline HTTP tests must not connect to network services")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    original = Path.open

    def safe_open(path, *args, **kwargs):
        resolved = path.resolve()
        if resolved == REPO_ROOT / "lexmount-config.yaml" or any(
            resolved == REPO_ROOT / private or REPO_ROOT / private in resolved.parents
            for private in ("data", ".mcp.json", ".claude", ".claude-memory")
        ):
            pytest.fail("Offline HTTP tests must not read private project files")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", safe_open)


def fictional_record(instance_id="fictional_open", *, year=2026, scope=None):
    evidence_id = "ev_" + instance_id
    return {
        "competition_instance_id": instance_id,
        "name": "虚构算法挑战（AI 辅助生成，非真实竞赛）",
        "series_id": "fictional_algorithm",
        "year": 2026,
        "group": "本科组",
        "stage": "校内选拔",
        "registration_start": "2026-10-01",
        "registration_deadline": "2026-10-25",
        "competition_date": "2026-11-15",
        "allowed_grades": ["大二"],
        "allowed_majors": ["计算机"],
        "eligibility_evidence_ids": [evidence_id],
        "registration_evidence_ids": [evidence_id],
        "competition_date_evidence_ids": [evidence_id],
        "evidence": [
            {
                "id": evidence_id,
                "url": "https://example.com/fictional/2026",
                "excerpt": "虚构：本科组校内选拔，大二计算机，10月1日至25日报名，11月15日比赛。",
                "fetched_at": "2026-10-17T10:00:00+08:00",
                "applicable_year": year,
                "scope": scope or 'applies-to/v1:{"stage":"校内选拔","group":"本科组"}',
            }
        ],
    }


@pytest.fixture
def settings(tmp_path):
    catalog = tmp_path / "fictional-competitions.json"
    catalog.write_text(
        json.dumps(
            [
                fictional_record(),
                fictional_record("fictional_other"),
                fictional_record("fictional_history", year=2025),
            ],
            ensure_ascii=False,
        )
    )
    return Settings(data_dir=tmp_path / "private", catalog_path=catalog, deepseek_api_key=None)


def drafts():
    return [
        {"kind": "profile", "message": "请核对画像。", "profile_changes": copy.deepcopy(PROFILE)},
        {
            "kind": "candidates",
            "message": "虚构候选，请选择。",
            "candidates": [
                {"competition_instance_id": "fictional_open", "reason": "算法方向相关。"},
            ],
        },
        {
            "kind": "analysis",
            "message": "请核对证据分析。",
            "analyses": [
                {
                    "competition_instance_id": "fictional_open",
                    "dimensions": [
                        {
                            "name": "ability_gap",
                            "assessment": "需练习算法。",
                            "basis": "explicit",
                            "evidence_ids": ["ev_fictional_open"],
                            "uncertainties": [],
                        }
                    ],
                }
            ],
        },
        {
            "kind": "plan",
            "message": "请核对路线。",
            "plan": {
                "selected_competition_ids": ["fictional_open"],
                "tasks": [
                    {
                        "id": "task_fictional",
                        "competition_instance_id": "fictional_open",
                        "title": "练习算法",
                        "estimated_hours": 4,
                        "acceptance_criteria": "完成练习",
                        "start_date": "2026-10-19",
                        "due_date": "2026-10-25",
                    }
                ],
                "assumptions": ["虚构样例，不代表真实竞赛。"],
            },
        },
    ]


class ScriptedAgent:
    def __init__(self, script=None):
        self.script = [
            item if isinstance(item, BaseException) else copy.deepcopy(item)
            for item in (script if script is not None else drafts())
        ]
        self.calls = 0

    async def run(self, snapshot, request):
        self.calls += 1
        output = self.script.pop(0)
        if isinstance(output, BaseException):
            raise output
        return AgentDraft.model_validate(output)


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def chat(client, state, *, request_id=None, content=None):
    body = {
        "request_id": request_id or f"req_{state['revision']}",
        "expected_revision": state["revision"],
        "action": "message" if content else "generate",
        "content": content,
    }
    response = await client.post(f"/api/sessions/{state['session_id']}/chat", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


async def confirm(client, state):
    response = await client.post(
        f"/api/sessions/{state['session_id']}/confirm",
        json={
            "expected_revision": state["revision"],
            "stage": state["stage"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def keep(client, state, decision="keep", instance="fictional_open"):
    response = await client.patch(
        f"/api/sessions/{state['session_id']}/candidates/{instance}",
        json={"expected_revision": state["revision"], "decision": decision},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def reach_stage(client, target="R4", *, content=INTRO):
    state = (await client.post("/api/sessions", json={})).json()
    state, _ = await chat(client, state, content=content)
    if target == "R0":
        return state
    state = await confirm(client, state)
    state, _ = await chat(client, state)
    state = await keep(client, state)
    if target == "R1":
        return state
    state = await confirm(client, state)
    state, _ = await chat(client, state)
    if target == "R2":
        return state
    state = await confirm(client, state)
    state, _ = await chat(client, state)
    return state


async def test_i1_exclude_survives_regeneration_restart_and_user_restore(settings):
    script = drafts()[:2]
    script[1]["candidates"].append({"competition_instance_id": "fictional_other", "reason": "次选"})
    script.append(drafts()[1])  # Model legitimately omits the excluded candidate.
    async with client_for(create_app(settings, ScriptedAgent(script), clock)) as client:
        state = await reach_stage(client, "R0")
        state = await confirm(client, state)
        state, _ = await chat(client, state)
        state = await keep(client, state, "exclude", instance="fictional_other")
        regenerated, _ = await chat(client, state)

    agent = ScriptedAgent([])
    async with client_for(create_app(settings, agent, clock)) as restarted:
        loaded = (await restarted.get(f"/api/sessions/{state['session_id']}")).json()
        assert loaded == regenerated
        restored = await keep(restarted, loaded, instance="fictional_other")
        assert restored["revision"] == regenerated["revision"] + 1
        assert {card["competition_instance_id"]: card["decision"] for card in loaded["cards"]} == {
            "fictional_open": "defer",
            "fictional_other": "exclude",
        }
        assert {
            card["competition_instance_id"]: card["decision"] for card in restored["cards"]
        } == {
            "fictional_open": "defer",
            "fictional_other": "keep",
        }
        assert agent.calls == 0


async def test_i1_model_cannot_readd_omitted_exclude_after_restart(settings):
    script = drafts()[:2]
    script[1]["candidates"].append({"competition_instance_id": "fictional_other", "reason": "次选"})
    script.append(drafts()[1])
    async with client_for(create_app(settings, ScriptedAgent(script), clock)) as client:
        state = await reach_stage(client, "R0")
        state = await confirm(client, state)
        state, _ = await chat(client, state)
        state = await keep(client, state, "exclude", instance="fictional_other")
        state, _ = await chat(client, state)

    readd = drafts()[1]
    readd["candidates"].append({"competition_instance_id": "fictional_other", "reason": "擅自恢复"})
    app = create_app(settings, ScriptedAgent([readd]), clock)
    path = settings.data_dir / "sessions" / f"{state['session_id']}.json"
    previous = path.read_bytes()
    async with client_for(app) as restarted:
        response = await restarted.post(
            f"/api/sessions/{state['session_id']}/chat",
            json={
                "request_id": "forbidden_readd",
                "expected_revision": state["revision"],
                "action": "generate",
                "content": None,
            },
        )
        assert response.status_code == 502, response.text
        assert response.json()["error"]["code"] == "LLM_INVALID_OUTPUT"
        assert path.read_bytes() == previous
        assert (await restarted.get(f"/api/sessions/{state['session_id']}")).json() == state
        assert not app.state.service.store.is_processing(state["session_id"])
        assert (
            "forbidden_readd"
            not in app.state.service.store.load(
                state["session_id"],
            ).successful_requests
        )


async def test_i1_regeneration_retains_omitted_keep_rechecks_rules_and_clears_results(settings):
    script = drafts()
    script[1]["candidates"].append({"competition_instance_id": "fictional_other", "reason": "次选"})
    regenerate = drafts()[1]
    regenerate["candidates"] = [
        {"competition_instance_id": "fictional_history", "reason": "背景未知"}
    ]
    script.append(regenerate)
    current = [clock()]
    app = create_app(settings, ScriptedAgent(script), lambda: current[0])
    async with client_for(app) as client:
        state = await reach_stage(client)
        assert state["plan"] is not None
        assert state["cards"][0]["dimensions"]
        state = await keep(client, state, "exclude", instance="fictional_other")
        assert state["stage"] == "R1"
        from datetime import datetime

        current[0] = datetime.fromisoformat("2026-10-26T04:00:00+00:00")
        regenerated, _ = await chat(client, state)
        cards = {card["competition_instance_id"]: card for card in regenerated["cards"]}
        assert set(cards) == {"fictional_open", "fictional_other", "fictional_history"}
        assert cards["fictional_open"]["decision"] == "keep"
        assert cards["fictional_open"]["reason"] == "算法方向相关。"
        assert cards["fictional_open"]["eligibility"] == "ineligible"
        assert cards["fictional_open"]["registration_status"] == "closed"
        assert cards["fictional_other"]["decision"] == "exclude"
        assert cards["fictional_history"]["decision"] == "defer"
        assert all(card["dimensions"] == [] for card in cards.values())
        assert regenerated["plan"] is None
        assert (regenerated["stage"], regenerated["status"]) == ("R1", "awaiting_review")
        saved = app.state.service.store.load(state["session_id"])
        assert [card.model_dump(mode="json") for card in saved.coarse_cards] == regenerated["cards"]
        rejected = await client.post(
            f"/api/sessions/{state['session_id']}/confirm",
            json={
                "expected_revision": regenerated["revision"],
                "stage": "R1",
            },
        )
        assert rejected.status_code == 422


async def test_complete_r0_r1_r2_r4_flow(settings):
    agent = ScriptedAgent()
    app = create_app(settings, agent, clock)
    async with client_for(app) as client:
        state = (await client.post("/api/sessions", json={})).json()
        assert (state["revision"], state["stage"], state["status"]) == (0, "R0", "collecting")
        confirmed_stages = []
        original = None
        request = None
        for stage, revision in [("R0", 1), ("R1", 3), ("R2", 6), ("R4", 8)]:
            state, body = await chat(client, state, content=INTRO if stage == "R0" else None)
            assert (state["revision"], state["stage"], state["status"]) == (
                revision,
                stage,
                "awaiting_review",
            )
            assert state["needs_confirmation"] is True
            assert state["processing"] is False
            if stage == "R0":
                assert state["profile"] == {
                    **PROFILE,
                    "skills": [],
                    "goals": [],
                    "team_preference": None,
                    "unavailable_dates": [],
                }
                original, request = state, body
                assert [message["role"] for message in state["messages"]] == ["user", "assistant"]
            if stage == "R1":
                card = state["cards"][0]
                assert (card["eligibility"], card["registration_status"], card["decision"]) == (
                    "eligible",
                    "open",
                    "defer",
                )
                state = await keep(client, state)
                assert state["revision"] == 4
            if stage == "R2":
                assert state["cards"][0]["dimensions"][0]["evidence_ids"] == ["ev_fictional_open"]
            if stage == "R4":
                assert state["plan"]["weekly_load"] == [
                    {
                        "week_start": "2026-10-19",
                        "estimated_hours": 4.0,
                        "budget_hours": 6.0,
                    }
                ]
                assert state["plan"]["conflicts"] == []
            before = agent.calls
            state = await confirm(client, state)
            assert agent.calls == before
            confirmed_stages.append(state["stage"])
            assert state["needs_confirmation"] is False
        assert confirmed_stages == ["R1", "R2", "R4", "R4"]
        assert state["revision"] == 9
        assert state["status"] == "completed"
        assert state["plan"]["feasibility"] == "feasible"
        calls_before_replay = agent.calls
        replay = await client.post(f"/api/sessions/{state['session_id']}/chat", json=request)
        assert replay.json() == original
        assert agent.calls == calls_before_replay
        assert (await client.get(f"/api/sessions/{state['session_id']}")).json() == state


async def test_successful_chat_replay_after_restart_does_not_call_model(settings):
    async with client_for(create_app(settings, ScriptedAgent(), clock)) as client:
        state = (await client.post("/api/sessions", json={})).json()
        original, body = await chat(client, state, content=INTRO)
    agent = ScriptedAgent([])
    async with client_for(create_app(settings, agent, clock)) as restarted:
        replay = await restarted.post(f"/api/sessions/{state['session_id']}/chat", json=body)
    assert replay.status_code == 200
    assert replay.json() == original
    assert agent.calls == 0


async def test_same_request_id_different_payload_conflicts(settings):
    agent = ScriptedAgent()
    async with client_for(create_app(settings, agent, clock)) as client:
        state = (await client.post("/api/sessions", json={})).json()
        original, body = await chat(client, state, content=INTRO)
        for changes in [
            {"content": "不同内容"},
            {"expected_revision": 1},
            {"action": "generate", "content": None},
        ]:
            response = await client.post(
                f"/api/sessions/{state['session_id']}/chat", json={**body, **changes}
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "REQUEST_ID_REUSED"
        assert agent.calls == 1
        assert (await client.get(f"/api/sessions/{state['session_id']}")).json() == original


async def test_stale_confirmation_does_not_advance(settings):
    agent = ScriptedAgent()
    async with client_for(create_app(settings, agent, clock)) as client:
        state = await reach_stage(client, "R0")
        for body, code in [
            ({"expected_revision": 0, "stage": "R0"}, "REVISION_CONFLICT"),
            ({"expected_revision": 1, "stage": "R1"}, "INVALID_STAGE"),
        ]:
            response = await client.post(f"/api/sessions/{state['session_id']}/confirm", json=body)
            assert response.status_code == 409
            assert response.json()["error"]["code"] == code
        assert (await client.get(f"/api/sessions/{state['session_id']}")).json() == state
        assert agent.calls == 1


@pytest.mark.parametrize("stage", ["R1", "R2", "R4"])
async def test_candidate_edit_invalidates_analysis_and_plan(settings, stage):
    async with client_for(create_app(settings, ScriptedAgent(), clock)) as client:
        state = await reach_stage(client, stage)
        edited = await keep(client, state, "exclude")
        assert edited["revision"] == state["revision"] + 1
        assert (edited["stage"], edited["status"], edited["needs_confirmation"]) == (
            "R1",
            "awaiting_review",
            True,
        )
        assert edited["plan"] is None
        assert edited["cards"][0]["dimensions"] == []
        assert edited["cards"][0]["reason"] == "算法方向相关。"
        response = await client.post(
            f"/api/sessions/{state['session_id']}/confirm",
            json={
                "expected_revision": edited["revision"],
                "stage": "R1",
            },
        )
        assert response.status_code == 422
        restored = await keep(client, edited)
        assert (await confirm(client, restored))["stage"] == "R2"


@pytest.mark.parametrize("method", ["patch", "chat"])
async def test_profile_edit_invalidates_all_results_without_context_lock(settings, method):
    agent = ScriptedAgent(
        drafts()
        + [
            {
                "kind": "profile",
                "message": "请重新核对。",
                "profile_changes": {"weekly_hours": 2},
            }
        ]
    )
    app = create_app(settings, agent, clock)
    async with client_for(app) as client:
        state = await reach_stage(client)
        if method == "patch":
            response = await client.patch(
                f"/api/sessions/{state['session_id']}/profile",
                json={
                    "expected_revision": state["revision"],
                    "changes": {"weekly_hours": 2},
                },
            )
            assert response.status_code == 200
            edited = response.json()
        else:
            edited, _ = await chat(client, state, content="我确认每周2小时，请更正。")
        assert (edited["stage"], edited["status"], edited["needs_confirmation"]) == (
            "R0",
            "collecting",
            False,
        )
        assert edited["profile"]["weekly_hours"] == 2
        assert edited["profile"]["additional_context"] == "偏好算法竞赛"
        assert edited["cards"] == [] and edited["plan"] is None
        record = app.state.service.store.load(state["session_id"])
        assert record.confirmed_profile is None and record.coarse_cards == []


async def test_unknown_budget_does_not_block_r0_but_blocks_feasible_claim(settings):
    script = drafts()
    del script[0]["profile_changes"]["weekly_hours"]
    async with client_for(create_app(settings, ScriptedAgent(script), clock)) as client:
        state = await reach_stage(client, content="我是大二计算机专业，偏好算法竞赛。")
        assert state["profile"]["weekly_hours"] is None
        assert state["plan"]["feasibility"] == "unknown"
        assert any("预算未知" in conflict for conflict in state["plan"]["conflicts"])
        response = await client.post(
            f"/api/sessions/{state['session_id']}/confirm",
            json={
                "expected_revision": state["revision"],
                "stage": "R4",
            },
        )
        assert response.status_code == 422
        assert (await client.get(f"/api/sessions/{state['session_id']}")).json() == state


async def test_model_free_endpoints_work_without_key(settings):
    app = create_app(settings, clock=clock)
    assert isinstance(app.state.service.agent, LiteLLMAgent)
    async with client_for(app) as client:
        state = (await client.post("/api/sessions", json={})).json()
        assert (await client.get(f"/api/sessions/{state['session_id']}")).status_code == 200
        assert (
            await client.patch(
                f"/api/sessions/{state['session_id']}/profile",
                json={
                    "expected_revision": 0,
                    "changes": {"major": "计算机"},
                },
            )
        ).status_code == 200
        detail = await client.get("/api/competitions/fictional_open")
        assert detail.status_code == 200
        assert detail.json()["registration_status"] == "open"
        response = await client.post(
            f"/api/sessions/{state['session_id']}/chat",
            json={
                "request_id": "no_key",
                "expected_revision": 1,
                "action": "generate",
                "content": None,
            },
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"


@pytest.mark.parametrize("mode", ["fail", "cancel", "save"])
async def test_failed_or_cancelled_chat_preserves_file_and_releases_guard(
    settings, mode, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()

    class PausingAgent:
        async def run(self, snapshot, request):
            snapshot.profile.major = "must-not-leak"
            entered.set()
            await release.wait()
            if mode == "fail":
                raise AppError("UPSTREAM_ERROR", "上游失败。", 502)
            return AgentDraft(kind="question", message="只是一条答复。")

    app = create_app(settings, PausingAgent(), clock)
    store = app.state.service.store
    async with client_for(app) as client:
        state = (await client.post("/api/sessions", json={})).json()
        path = settings.data_dir / "sessions" / f"{state['session_id']}.json"
        before = path.read_bytes()
        body = {
            "request_id": "pending",
            "expected_revision": 0,
            "action": "message",
            "content": "虚构问题",
        }
        if mode == "save":
            import backend.storage

            def broken_replace(*args):
                raise OSError("fictional-secret-write-error")

            monkeypatch.setattr(backend.storage.os, "replace", broken_replace)
        task = asyncio.create_task(
            client.post(f"/api/sessions/{state['session_id']}/chat", json=body)
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        busy = (await client.get(f"/api/sessions/{state['session_id']}")).json()
        assert busy == {**state, "processing": True}
        duplicate = await client.post(f"/api/sessions/{state['session_id']}/chat", json=body)
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "REQUEST_IN_PROGRESS"
        if mode == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            release.set()
            response = await task
            assert response.status_code == (502 if mode == "fail" else 500)
            assert "fictional-secret" not in response.text
        assert path.read_bytes() == before
        assert not list(path.parent.glob(".session-*.tmp"))
        assert not store.is_processing(state["session_id"])
        assert (await client.get(f"/api/sessions/{state['session_id']}")).json() == state
        assert store.load(state["session_id"]).successful_requests == {}


async def test_calendar_501_and_openapi_contract(settings):
    async with client_for(create_app(settings, clock=clock)) as client:
        state = (await client.post("/api/sessions", json={})).json()
        response = await client.get(f"/api/sessions/{state['session_id']}/calendar.ics")
        assert response.status_code == 501
        assert response.json()["error"]["code"] == "FEATURE_NOT_ENABLED"
        spec = (await client.get("/openapi.json")).json()
        paths = spec["paths"]
        calendar_responses = paths["/api/sessions/{session_id}/calendar.ics"]["get"]["responses"]
        assert "501" in calendar_responses and "200" not in calendar_responses
        for suffix, verb in [
            ("chat", "post"),
            ("confirm", "post"),
            ("candidates/{candidate_id}", "patch"),
        ]:
            assert paths[f"/api/sessions/{{session_id}}/{suffix}"][verb]["requestBody"]
        schemas = spec["components"]["schemas"]
        assert set(schemas["ChatRequest"]["required"]) == {
            "request_id",
            "expected_revision",
            "action",
            "content",
        }
        assert "additional_context" in schemas["Profile"]["properties"]
        assert "weekly_hours" not in schemas["Profile"].get("required", [])
        assert set(schemas["Plan"]["properties"]) == {
            "selected_competition_ids",
            "tasks",
            "assumptions",
            "weekly_load",
            "conflicts",
            "feasibility",
        }
        assert "successful_requests" not in schemas["SessionSnapshot"]["properties"]


async def test_openapi_errors_describe_the_actual_safe_envelope(settings):
    async with client_for(create_app(settings, clock=clock)) as client:
        spec = (await client.get("/openapi.json")).json()
        paths = spec["paths"]
        for path, method, codes in [
            ("/api/sessions", "post", ["422", "500"]),
            ("/api/sessions/{session_id}/chat", "post", ["404", "409", "422", "503"]),
            ("/api/sessions/{session_id}/confirm", "post", ["409", "422"]),
            ("/api/competitions/{instance_id}", "get", ["404", "503"]),
        ]:
            responses = paths[path][method]["responses"]
            for code in codes:
                assert responses[code]["content"]["application/json"]["schema"] == {
                    "$ref": "#/components/schemas/ErrorResponse",
                }


@pytest.mark.parametrize(
    "broken,code", [(False, "CATALOG_NOT_CONFIGURED"), (True, "CATALOG_INVALID")]
)
async def test_missing_or_broken_catalog_does_not_block_sessions(settings, broken, code):
    if broken:
        settings.catalog_path.write_text("not JSON")
    else:
        settings = settings.model_copy(
            update={"catalog_path": settings.catalog_path.parent / "absent"}
        )
    async with client_for(create_app(settings, clock=clock)) as client:
        state = (await client.post("/api/sessions", json={})).json()
        assert (await client.get(f"/api/sessions/{state['session_id']}")).status_code == 200
        response = await client.get("/api/competitions/fictional_open")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == code
        response = await client.post(
            f"/api/sessions/{state['session_id']}/chat",
            json={
                "request_id": "no_key_no_catalog",
                "expected_revision": 0,
                "action": "generate",
                "content": None,
            },
        )
        assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"


@pytest.mark.parametrize(
    "attack",
    [
        "wrong_stage",
        "mixed_payload",
        "unknown_instance",
        "duplicate_instance",
        "other_owner",
        "unknown_evidence",
        "old_explicit",
        "wrong_scope",
        "future_evidence",
        "history_without_uncertainty",
        "unkept_analysis",
        "unkept_plan",
        "unanalysed_plan",
        "server_plan_fields",
        "mutated_dto",
        "duplicate_dimensions",
        "unselected_task",
    ],
)
async def test_service_rejects_untrusted_runner_drafts(settings, attack):
    script = drafts()
    target = "R0" if attack in {"wrong_stage", "mixed_payload", "mutated_dto"} else "R1"
    if attack in {
        "other_owner",
        "unknown_evidence",
        "old_explicit",
        "wrong_scope",
        "future_evidence",
        "history_without_uncertainty",
        "unkept_analysis",
        "duplicate_dimensions",
    }:
        target = "R2"
    if attack in {"unkept_plan", "unanalysed_plan", "server_plan_fields", "unselected_task"}:
        target = "R4"

    class UntrustedAgent(ScriptedAgent):
        async def run(self, snapshot, request):
            if request.request_id != "attack":
                return await super().run(snapshot, request)
            payload = copy.deepcopy(script[{"R0": 0, "R1": 1, "R2": 2, "R4": 3}[target]])
            if attack == "wrong_stage":
                payload = script[1]
            elif attack == "mixed_payload":
                payload["candidates"] = script[1]["candidates"]
            elif attack in {"unknown_instance", "duplicate_instance"}:
                if attack == "unknown_instance":
                    payload["candidates"][0]["competition_instance_id"] = "forged"
                else:
                    payload["candidates"] *= 2
            elif attack == "other_owner":
                payload["analyses"][0]["dimensions"][0]["evidence_ids"] = ["ev_fictional_other"]
            elif attack == "unknown_evidence":
                payload["analyses"][0]["dimensions"][0]["evidence_ids"] = ["forged"]
            elif attack in {
                "old_explicit",
                "wrong_scope",
                "future_evidence",
                "history_without_uncertainty",
            }:
                if attack == "history_without_uncertainty":
                    payload["analyses"][0]["dimensions"][0]["basis"] = "inferred"
            elif attack == "unkept_analysis":
                payload["analyses"][0]["competition_instance_id"] = "fictional_other"
                payload["analyses"][0]["dimensions"][0]["evidence_ids"] = ["ev_fictional_other"]
            elif attack in {"unkept_plan", "unanalysed_plan"}:
                payload["plan"]["selected_competition_ids"] = ["fictional_other"]
                payload["plan"]["tasks"][0]["competition_instance_id"] = "fictional_other"
            elif attack == "server_plan_fields":
                # Assignment bypasses DTO validation; service must reject server fields.
                from backend.schemas import Plan

                result = AgentDraft.model_validate(payload)
                result.plan = Plan(**result.plan.model_dump(), feasibility="feasible")
                return result
            elif attack == "mutated_dto":
                result = AgentDraft.model_validate(payload)
                result.profile_changes.weekly_hours = -1
                return result
            elif attack == "duplicate_dimensions":
                payload["analyses"][0]["dimensions"] *= 2
            elif attack == "unselected_task":
                payload["plan"]["tasks"][0]["competition_instance_id"] = "fictional_other"
            return AgentDraft.model_validate(payload)

    agent = UntrustedAgent()
    # Include an unselected card to distinguish 'known' from user-authorized.
    agent.script[1]["candidates"].append(
        {"competition_instance_id": "fictional_other", "reason": "次选"}
    )
    app = create_app(settings, agent, clock)
    async with client_for(app) as client:
        state = (await client.post("/api/sessions", json={})).json()
        if target != "R0":
            state, _ = await chat(client, state, content=INTRO)
            state = await confirm(client, state)
        if target in {"R2", "R4"}:
            state, _ = await chat(client, state)
            state = await keep(client, state)
            if attack == "unanalysed_plan":
                state = await keep(client, state, instance="fictional_other")
            state = await confirm(client, state)
        if target == "R4":
            state, _ = await chat(client, state)
            state = await confirm(client, state)
        if attack in {
            "old_explicit",
            "wrong_scope",
            "future_evidence",
            "history_without_uncertainty",
        }:
            # A restart loads the changed fictional source, without touching session bytes.
            records = json.loads(settings.catalog_path.read_text())
            evidence = records[0]["evidence"][0]
            if attack == "wrong_scope":
                evidence["scope"] = 'applies-to/v1:{"stage":"决赛","group":"本科组"}'
            elif attack == "future_evidence":
                evidence["fetched_at"] = "2026-10-20T10:00:00+08:00"
            else:
                evidence["applicable_year"] = 2025
            settings.catalog_path.write_text(json.dumps(records))
            app = create_app(settings, agent, clock)
        path = settings.data_dir / "sessions" / f"{state['session_id']}.json"
        before = path.read_bytes()
        async with client_for(app) as attacker:
            response = await attacker.post(
                f"/api/sessions/{state['session_id']}/chat",
                json={
                    "request_id": "attack",
                    "expected_revision": state["revision"],
                    "action": "message",
                    "content": INTRO,
                },
            )
        assert response.status_code == 502, response.text
        assert response.json()["error"]["code"] == "LLM_INVALID_OUTPUT"
        assert path.read_bytes() == before
        assert not app.state.service.store.is_processing(state["session_id"])


async def test_unknown_eligibility_can_be_kept_but_expired_candidate_cannot(settings):
    script = drafts()
    script[1]["candidates"][0]["competition_instance_id"] = "fictional_history"
    async with client_for(create_app(settings, ScriptedAgent(script), clock)) as client:
        state = await reach_stage(client, "R0")
        state = await confirm(client, state)
        state, _ = await chat(client, state)
        assert state["cards"][0]["eligibility"] == "unknown"
        state = await keep(client, state, instance="fictional_history")
        assert (await confirm(client, state))["stage"] == "R2"

    agent = ScriptedAgent()
    current = [clock()]
    async with client_for(create_app(settings, agent, lambda: current[0])) as client:
        state = await reach_stage(client, "R1")
        from datetime import datetime

        current[0] = datetime.fromisoformat("2026-10-26T04:00:00+00:00")
        for response in [
            await client.patch(
                f"/api/sessions/{state['session_id']}/candidates/fictional_open",
                json={
                    "expected_revision": state["revision"],
                    "decision": "keep",
                },
            ),
            await client.post(
                f"/api/sessions/{state['session_id']}/confirm",
                json={
                    "expected_revision": state["revision"],
                    "stage": "R1",
                },
            ),
        ]:
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_r4_confirmation_rechecks_current_clock(settings):
    current = [clock()]
    async with client_for(create_app(settings, ScriptedAgent(), lambda: current[0])) as client:
        state = await reach_stage(client)
        assert state["plan"]["feasibility"] == "feasible"
        from datetime import datetime

        current[0] = datetime.fromisoformat("2026-10-26T04:00:00+00:00")
        response = await client.post(
            f"/api/sessions/{state['session_id']}/confirm",
            json={
                "expected_revision": state["revision"],
                "stage": "R4",
            },
        )
        assert response.status_code == 422
        assert (await client.get(f"/api/sessions/{state['session_id']}")).json() == state


@pytest.mark.parametrize("stage", ["R0", "R1", "R2", "R4", "completed"])
async def test_question_preserves_review_results_and_noop_candidate_preserves_plan(settings, stage):
    script = drafts()[: {"R0": 1, "R1": 2, "R2": 3, "R4": 4, "completed": 4}[stage]]
    script.append({"kind": "question", "message": "只作解释，不改变结果。"})
    agent = ScriptedAgent(script)
    async with client_for(create_app(settings, agent, clock)) as client:
        state = await reach_stage(client, "R4" if stage == "completed" else stage)
        if stage == "completed":
            state = await confirm(client, state)
        if stage in {"R4", "completed"}:
            noop = await keep(client, state)
            assert noop == state
        result, _ = await chat(client, state, content="请解释这份结果。")
        for field in ("stage", "status", "needs_confirmation", "profile", "cards", "plan"):
            assert result[field] == state[field]
        assert result["revision"] == state["revision"] + 1
        assert result["messages"][-1]["content"] == "只作解释，不改变结果。"


async def test_unsupported_fake_profile_change_becomes_review_question(settings):
    agent = ScriptedAgent(
        drafts()
        + [
            {
                "kind": "profile",
                "message": "擅自覆盖",
                "profile_changes": {"weekly_hours": 2},
            }
        ]
    )
    async with client_for(create_app(settings, agent, clock)) as client:
        state = await reach_stage(client)
        result, _ = await chat(client, state, content="随便聊聊。")
        assert result["profile"] == state["profile"]
        assert result["plan"] == state["plan"]
        assert "每周投入" in result["message"]


async def test_infeasible_plan_is_visible_but_cannot_be_confirmed(settings):
    script = drafts()
    script[3]["plan"]["tasks"][0]["estimated_hours"] = 10
    async with client_for(create_app(settings, ScriptedAgent(script), clock)) as client:
        state = await reach_stage(client)
        assert state["plan"]["feasibility"] == "infeasible"
        assert state["plan"]["weekly_load"][0]["estimated_hours"] == 10
        response = await client.post(
            f"/api/sessions/{state['session_id']}/confirm",
            json={
                "expected_revision": state["revision"],
                "stage": "R4",
            },
        )
        assert response.status_code == 422
        assert (await client.get(f"/api/sessions/{state['session_id']}")).json() == state


async def test_stale_chat_rejected_before_model_and_success_saved_once(settings, monkeypatch):
    agent = ScriptedAgent()
    app = create_app(settings, agent, clock)
    store = app.state.service.store
    async with client_for(app) as client:
        state = (await client.post("/api/sessions", json={})).json()
        saved = []
        save = store.save

        def track_save(record):
            saved.append(record.model_dump(mode="json"))
            save(record)

        monkeypatch.setattr(store, "save", track_save)
        result, _ = await chat(client, state, content=INTRO)
        assert len(saved) == 1
        persisted = saved[0]
        assert persisted["snapshot"] == result
        assert persisted["successful_requests"]["req_0"]["snapshot"] == result
        response = await client.post(
            f"/api/sessions/{state['session_id']}/chat",
            json={
                "request_id": "new_stale",
                "expected_revision": 0,
                "action": "generate",
                "content": None,
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "REVISION_CONFLICT"
        assert agent.calls == 1
        assert len(saved) == 1


async def test_historical_inference_requires_uncertainty_but_can_be_reviewed(settings):
    records = json.loads(settings.catalog_path.read_text())
    records[0]["evidence"][0]["applicable_year"] = 2025
    settings.catalog_path.write_text(json.dumps(records))
    script = drafts()
    dimension = script[2]["analyses"][0]["dimensions"][0]
    dimension["basis"] = "inferred"
    dimension["uncertainties"] = ["往届材料仅供背景，本届未知。"]
    async with client_for(create_app(settings, ScriptedAgent(script), clock)) as client:
        state = await reach_stage(client, "R2")
        assert state["cards"][0]["eligibility"] == "unknown"
        assert state["cards"][0]["dimensions"][0]["basis"] == "inferred"
        assert state["needs_confirmation"] is True


async def test_failed_chat_can_retry_same_id_without_partial_cache(settings):
    agent = ScriptedAgent([AppError("UPSTREAM_ERROR", "上游失败。", 502), drafts()[0]])
    async with client_for(create_app(settings, agent, clock)) as client:
        state = (await client.post("/api/sessions", json={})).json()
        body = {
            "request_id": "retry",
            "expected_revision": 0,
            "action": "message",
            "content": INTRO,
        }
        url = f"/api/sessions/{state['session_id']}/chat"
        failure = await client.post(url, json=body)
        assert failure.status_code == 502
        success = await client.post(url, json=body)
        assert success.status_code == 200
        assert success.json()["revision"] == 1
        assert len(success.json()["messages"]) == 2
        assert agent.calls == 2


def local_provider_app(settings, monkeypatch, script, clock_source=clock):
    """Keep the default factory/Agent; replace only the external provider module."""
    steps = iter(copy.deepcopy(script))
    calls = []

    async def completion(**kwargs):
        calls.append(copy.deepcopy(kwargs))
        step = next(steps)
        is_tool = "tool_calls" in step
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls" if is_tool else "stop",
                    "message": {
                        "role": "assistant",
                        "content": None if is_tool else json.dumps(step, ensure_ascii=False),
                        **(step if is_tool else {}),
                    },
                }
            ]
        }

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=completion))
    app = create_app(
        settings.model_copy(
            update={"deepseek_api_key": Settings(deepseek_api_key="fake").deepseek_api_key}
        ),
        clock=clock_source,
    )
    assert isinstance(app.state.service.agent, LiteLLMAgent)
    assert app.state.service.agent.completion is None
    return app, calls


@pytest.mark.parametrize("runner", ["default_provider", "untrusted_runner"])
@pytest.mark.parametrize(
    "field,wrong,negative,correct,affirmative,label",
    [
        (
            "weekly_hours",
            20,
            "我每周不能投入20小时，实际每周只有6小时。",
            8,
            "每周能投入8小时",
            "每周投入",
        ),
        (
            "major",
            "金融",
            "不要把专业改成金融，我的专业仍是计算机。",
            "金融",
            "请更正专业为金融",
            "专业",
        ),
        ("grade", "大三", "我不是大三，我是大二。", "大三", "我是大三", "年级"),
    ],
)
async def test_final_i1_negated_scalar_preserves_confirmed_results_then_correction_resolves(
    settings, monkeypatch, runner, field, wrong, negative, correct, affirmative, label
):
    bad = {"kind": "profile", "message": "错误提取", "profile_changes": {field: wrong}}
    good = {"kind": "profile", "message": "请核对更正。", "profile_changes": {field: correct}}
    script = drafts() + [bad, good, good]
    if runner == "default_provider":
        # R1 must really discover IDs via a local tool, not bypass its exposure ledger.
        script.insert(
            1,
            {
                "tool_calls": [
                    {
                        "id": "search",
                        "type": "function",
                        "function": {
                            "name": "search_competitions",
                            "arguments": "{}",
                        },
                    }
                ]
            },
        )
        app, _ = local_provider_app(settings, monkeypatch, script)
    else:
        app = create_app(settings, ScriptedAgent(script), clock)
    store = app.state.service.store
    async with client_for(app) as client:
        state = await reach_stage(client)
        saved = store.load(state["session_id"])
        assert saved.confirmed_profile is not None
        assert state["cards"] and state["plan"]["feasibility"] == "feasible"
        reviewed, _ = await chat(client, state, content=negative)
        for key in ("stage", "status", "needs_confirmation", "profile", "cards", "plan"):
            assert reviewed[key] == state[key]
        assert label in reviewed["message"] and "核对" in reviewed["message"]
        after = store.load(state["session_id"])
        assert after.confirmed_profile == saved.confirmed_profile
        assert after.coarse_cards == saved.coarse_cards
        reviewed = await confirm(client, reviewed)
        assert reviewed["status"] == "completed"  # The preserved valid plan is still confirmable.
        edited, _ = await chat(client, reviewed, content=affirmative)
        assert edited["profile"][field] == correct
        assert (edited["stage"], edited["status"]) == ("R0", "collecting")
        assert edited["cards"] == [] and edited["plan"] is None
        assert store.load(state["session_id"]).confirmed_profile is None
        # A following R0 review/confirm still works; no permanent review loop.
        reviewed, _ = await chat(client, edited)
        assert (await confirm(client, reviewed))["stage"] == "R1"


@pytest.mark.parametrize("field,value", [("grade", "大三"), ("major", "金融"), ("weekly_hours", 8)])
async def test_final_i1_direct_patch_remains_authoritative(settings, field, value):
    async with client_for(create_app(settings, ScriptedAgent(), clock)) as client:
        state = await reach_stage(client)
        response = await client.patch(
            f"/api/sessions/{state['session_id']}/profile",
            json={"expected_revision": state["revision"], "changes": {field: value}},
        )
        assert response.status_code == 200
        assert response.json()["profile"][field] == value
        assert response.json()["stage"] == "R0"


@pytest.mark.parametrize("start,end", [("2026-10-05", "2026-10-11"), ("2026-10-17", "2026-10-20")])
async def test_final_i2_default_provider_past_or_cross_today_plan_cannot_confirm(
    settings, monkeypatch, start, end
):
    script = drafts()
    script[3]["plan"]["tasks"][0].update(start_date=start, due_date=end)
    plan = copy.deepcopy(script[3]["plan"])
    script.insert(
        1,
        {
            "tool_calls": [
                {
                    "id": "search",
                    "type": "function",
                    "function": {
                        "name": "search_competitions",
                        "arguments": "{}",
                    },
                }
            ]
        },
    )
    script.insert(
        4,
        {
            "tool_calls": [
                {
                    "id": "evaluate",
                    "type": "function",
                    "function": {
                        "name": "evaluate_plan",
                        "arguments": json.dumps({"plan": plan}),
                    },
                }
            ]
        },
    )
    app, calls = local_provider_app(settings, monkeypatch, script)
    async with client_for(app) as client:
        state = await reach_stage(client)
        assert state["plan"]["feasibility"] == "infeasible"
        assert state["plan"]["weekly_load"] == []
        assert any(
            "重排" in reason and "2026-10-18" in reason for reason in state["plan"]["conflicts"]
        )
        tool = json.loads(calls[-1]["messages"][-1]["content"])
        assert tool["data"] == state["plan"]
        response = await client.post(
            f"/api/sessions/{state['session_id']}/confirm",
            json={"expected_revision": state["revision"], "stage": "R4"},
        )
        assert response.status_code == 422
        assert (await client.get(f"/api/sessions/{state['session_id']}")).json() == state


@pytest.mark.parametrize("delayed", [False, True])
async def test_final_i2_injected_beijing_clock_today_future_and_delayed_confirm(
    settings, monkeypatch, delayed
):
    # UTC still Oct 17, but Beijing already Oct 18. Never consult system today.
    current = [datetime.fromisoformat("2026-10-17T16:30:00+00:00")]
    script = drafts()
    task = script[3]["plan"]["tasks"][0]
    task.update(start_date="2026-10-18", due_date="2026-10-18", estimated_hours=2)
    future = {**task, "id": "future", "start_date": "2026-10-19", "due_date": "2026-10-20"}
    script[3]["plan"]["tasks"].append(future)
    script.insert(
        1,
        {
            "tool_calls": [
                {
                    "id": "search",
                    "type": "function",
                    "function": {
                        "name": "search_competitions",
                        "arguments": "{}",
                    },
                }
            ]
        },
    )
    app, calls = local_provider_app(settings, monkeypatch, script, lambda: current[0])
    async with client_for(app) as client:
        state = await reach_stage(client)
        assert state["plan"]["feasibility"] == "feasible"
        if delayed:
            current[0] = datetime.fromisoformat("2026-10-20T04:00:00+00:00")
            assert (await client.get("/api/competitions/fictional_open")).json()[
                "registration_status"
            ] == "open"
            before = len(calls)
            response = await client.post(
                f"/api/sessions/{state['session_id']}/confirm",
                json={"expected_revision": state["revision"], "stage": "R4"},
            )
            assert response.status_code == 422
            assert len(calls) == before
            assert (await client.get(f"/api/sessions/{state['session_id']}")).json() == state
        else:
            assert (await confirm(client, state))["status"] == "completed"


async def test_final_i2_default_agent_prompt_uses_injected_beijing_date(settings, monkeypatch):
    # Deliberately unrelated to wall-clock today; R0 needs no catalog date fixture.
    now = datetime.fromisoformat("2031-02-04T16:30:00+00:00")
    app, calls = local_provider_app(
        settings,
        monkeypatch,
        [{"kind": "question", "message": "请核对。"}],
        lambda: now,
    )
    async with client_for(app) as client:
        state = (await client.post("/api/sessions", json={})).json()
        await chat(client, state, content="请规划。")
    context = json.loads(calls[0]["messages"][1]["content"].split("\n", 1)[1])
    assert context["current_date"] == "2031-02-05"
    assert context["timezone"] == "Asia/Shanghai"
