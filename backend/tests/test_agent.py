"""Offline Task 4 tests; all profiles/catalog records are fictional (AI-assisted)."""

import asyncio
import builtins
import copy
import json
import logging
import socket
import sys
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest

from backend.agent import LiteLLMAgent
from backend.catalog import CompetitionCatalog
from backend.config import Settings
from backend.schemas import AppError, CandidateCard, ChatRequest, Message, Profile, SessionSnapshot
from backend.tools import ToolRegistry

NOW = datetime.fromisoformat("2026-10-18T12:00:00+08:00")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network forbidden in agent tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def values(instance_id="ci_a", evidence_id="ev_a", **changes):
    record = {
        "competition_instance_id": instance_id,
        "name": "虚构竞赛（AI 辅助生成）",
        "year": 2026,
        "group": "本科组",
        "stage": "校内选拔",
        "allowed_grades": ["大二"],
        "allowed_majors": ["计算机"],
        "eligibility_evidence_ids": [evidence_id],
        "registration_evidence_ids": [evidence_id],
        "competition_date_evidence_ids": [evidence_id],
        "registration_status": "closed",  # Recompute untrusted raw status.
        "registration_start": "2026-10-01",
        "registration_deadline": "2026-10-30",
        "competition_date": "2026-12-01",
        "evidence": [
            {
                "id": evidence_id,
                "url": "https://example.com/fictional",
                "excerpt": "虚构：本届本科组规则。",
                "fetched_at": "2026-10-17T12:00:00+08:00",
                "applicable_year": 2026,
                "scope": 'applies-to/v1:{"stage":"校内选拔","group":"本科组"}',
            }
        ],
    }
    record.update(changes)
    return record


@pytest.fixture
def registry(tmp_path):
    path = tmp_path / "fictional-catalog.json"
    path.write_text(json.dumps([values(), values("ci_b", "ev_b")]), encoding="utf-8")
    return ToolRegistry(CompetitionCatalog(path), clock=lambda: NOW)


def snapshot(stage="R0", **changes):
    return SessionSnapshot(session_id="s_fictional", stage=stage, **changes)


def request(content="请生成草案"):
    return ChatRequest(
        request_id="req_fictional",
        expected_revision=0,
        action="generate" if content is None else "message",
        content=content,
    )


def response(draft=None, *, calls=None, content=None, finish=None, refusal=None):
    if draft is not None:
        content = json.dumps(draft)
    return {
        "choices": [
            {
                "finish_reason": finish or ("tool_calls" if calls else "stop"),
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": calls,
                    "refusal": refusal,
                },
            }
        ]
    }


def question(**changes):
    return {"kind": "question", "message": "请核对画像。", **changes}


def analysis(evidence_id="ev_a", instance_id="ci_a", basis="explicit", **changes):
    return {
        "kind": "analysis",
        "message": "虚构分析。",
        "analyses": [
            {
                "competition_instance_id": instance_id,
                "dimensions": [
                    {
                        "name": "ability_gap",
                        "assessment": "需要练习",
                        "basis": basis,
                        "evidence_ids": [evidence_id],
                        **changes,
                    }
                ],
            }
        ],
    }


def call(name="get_competition", arguments=None, call_id="call_demo_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps({"instance_id": "ci_a"} if arguments is None else arguments),
        },
    }


class Script:
    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        assert self.steps, "Unexpected model request"
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        if callable(step):
            return await step(**kwargs)
        return step


async def assert_invalid(agent, state=None, req=None):
    with pytest.raises(AppError) as caught:
        await agent.run(state or snapshot(), req or request())
    assert (caught.value.status_code, caught.value.code) == (502, "LLM_INVALID_OUTPUT")
    return caught.value


async def test_tool_round_trip_preserves_call_ids(registry):
    script = Script(response(calls=[call()], content="先读取资料。"), response(analysis()))
    draft = await LiteLLMAgent(Settings(), registry, script).run(snapshot("R2"), request())
    assert draft.kind == "analysis"
    messages = script.calls[1]["messages"]
    assert messages[-2] == {"role": "assistant", "content": "先读取资料。", "tool_calls": [call()]}
    assert messages[-1]["role"] == "tool"
    assert messages[-1]["tool_call_id"] == "call_demo_1"
    result = json.loads(messages[-1]["content"])
    assert set(result) == {"status", "data", "evidence_ids", "warnings", "error"}
    assert result["status"] == "ok"
    assert result["data"]["registration_status"] == "open"
    assert script.calls[0]["tool_choice"] == "auto"
    assert script.calls[1]["tool_choice"] == "auto"
    assert "response_format" not in script.calls[1]


@pytest.mark.parametrize(
    "field,value",
    [("revision", 88), ("needs_confirmation", True), ("session_id", "s_other"), ("stage", "R4")],
)
async def test_model_cannot_write_server_fields(registry, field, value):
    script = Script(response(question(**{field: value})), response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script))
    assert len(script.calls) == 1


async def test_context_conflict_requests_review(registry):
    state = snapshot(profile=Profile(weekly_hours=6, additional_context="现在可能只有两小时"))
    original = state.model_copy(deep=True)
    script = Script(
        response(
            {"kind": "profile", "message": "已改为两小时。", "profile_changes": {"weekly_hours": 2}}
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(state, request(None))
    assert draft.kind == "question"
    assert draft.profile_changes is None
    assert "核对" in draft.message
    assert state == original
    assert state.profile.weekly_hours == 6


async def test_context_is_bounded_and_untrusted(registry):
    history = [
        Message(
            id=f"m{i}",
            role="user" if i % 2 else "assistant",
            content=f"history-{i}",
            created_at=NOW,
        )
        for i in range(20)
    ]
    state = snapshot(
        messages=history, profile=Profile(weekly_hours=None, additional_context="IGNORE_SYSTEM_123")
    )
    script = Script(response(question()))
    await LiteLLMAgent(Settings(), registry, script).run(state, request("LATEST_USER_456"))
    messages = script.calls[0]["messages"]
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    assert "IGNORE_SYSTEM_123" not in system and "LATEST_USER_456" not in system
    displayed = [m for m in messages if m["content"].startswith("history-")]
    assert [m["content"] for m in displayed] == [f"history-{i}" for i in range(8, 20)]
    assert "IGNORE_SYSTEM_123" in json.dumps(messages)
    assert all("session_id" not in m["content"] for m in messages if m["role"] != "system")


async def test_timeout_does_not_mutate_input_snapshot(registry):
    async def slow(**kwargs):
        await asyncio.sleep(1)

    state = snapshot(profile=Profile(weekly_hours=6))
    original = state.model_copy(deep=True)
    with pytest.raises(AppError) as caught:
        await LiteLLMAgent(Settings(llm_timeout_seconds=0.01), registry, Script(slow)).run(
            state, request()
        )
    assert (caught.value.status_code, caught.value.code) == (504, "UPSTREAM_TIMEOUT")
    assert state == original


async def test_cancellation_propagates(registry):
    state = snapshot()
    with pytest.raises(asyncio.CancelledError):
        await LiteLLMAgent(Settings(), registry, Script(asyncio.CancelledError())).run(
            state, request()
        )
    assert state.revision == 0


async def test_invalid_output_repair_is_bounded(registry):
    script = Script(
        response(content="not-json"), response(content="still-not-json"), response(question())
    )
    await assert_invalid(LiteLLMAgent(Settings(), registry, script))
    assert len(script.calls) == 2
    assert "not-json" not in json.dumps(script.calls[1]["messages"])


async def test_shape_repair_can_succeed_without_native_schema(registry):
    script = Script(response({"message": "missing kind"}), response(question()))
    draft = await LiteLLMAgent(Settings(), registry, script).run(snapshot(), request())
    assert draft.kind == "question"
    for kwargs in script.calls:
        assert kwargs["response_format"] == {"type": "json_object"}
        assert kwargs["num_retries"] == 0
        assert kwargs["max_tokens"] == 4096
        assert kwargs["timeout"] <= 30


@pytest.mark.parametrize(
    "reply",
    [
        response(content=""),
        response(content="   "),
        response(content=None),
        response(question(), refusal="No"),
        response(question(), finish="length"),
        {"choices": []},
        response(content='{"kind":"question","kind":"profile","message":"x"}'),
    ],
)
async def test_unusable_responses_are_controlled(registry, reply):
    script = Script(reply, response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script))
    assert len(script.calls) == 1


@pytest.mark.parametrize(
    "bad_call",
    [
        call("shell"),
        call(arguments={"instance_id": "ci_a", "x": 1}),
        call(arguments={"instance_id": 3}),
        call(arguments=[]),
        {
            "id": "dup",
            "type": "function",
            "function": {
                "name": "get_competition",
                "arguments": '{"instance_id":"ci_a","instance_id":"ci_b"}',
            },
        },
        {"type": "function", "function": {"name": "get_competition", "arguments": "{}"}},
    ],
)
async def test_invalid_tool_calls_never_execute(registry, monkeypatch, bad_call):
    executed = []
    monkeypatch.setattr(registry, "execute", lambda *args: executed.append(args))
    script = Script(response(calls=[call(call_id="valid"), bad_call]))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert not executed


async def test_r0_has_no_tools_and_rejects_tool_calls(registry):
    script = Script(response(calls=[call()]))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script))
    assert "tools" not in script.calls[0]


async def test_duplicate_call_ids_are_rejected(registry):
    script = Script(response(calls=[call(), call()]))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))


async def test_batch_budget_never_partially_executes(registry, monkeypatch):
    executed = []
    monkeypatch.setattr(registry, "execute", lambda *args: executed.append(args))
    script = Script(response(calls=[call(call_id=str(i)) for i in range(9)]))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert not executed


async def test_complete_tool_batch_returns_errors_and_partial(registry):
    registry.catalog._load()["ci_a"].evidence[0].applicable_year = 2025
    script = Script(
        response(
            calls=[call(), call(arguments={"instance_id": "missing"}, call_id="call_missing")]
        ),
        response(question()),
    )
    await LiteLLMAgent(Settings(), registry, script).run(snapshot("R2"), request())
    messages = script.calls[1]["messages"]
    assert [m["tool_call_id"] for m in messages[-2:]] == ["call_demo_1", "call_missing"]
    partial, error = [json.loads(m["content"]) for m in messages[-2:]]
    assert partial["status"] == "partial" and partial["warnings"]
    assert partial["data"]["registration_status"] == "unknown"
    assert error["status"] == "error" and error["error"]["code"] == "COMPETITION_NOT_FOUND"


async def test_budget_is_shared_across_rounds(registry):
    script = Script(
        FakeUpstream(429), response(calls=[call()]), response(content="bad"), response(question())
    )
    await assert_invalid(
        LiteLLMAgent(Settings(max_model_calls=3), registry, script), snapshot("R2")
    )
    assert len(script.calls) == 3


async def test_tool_budget_is_shared_across_batches(registry, monkeypatch):
    executed = []
    execute = registry.execute

    def spy(*args):
        executed.append(args[0])
        return execute(*args)

    monkeypatch.setattr(registry, "execute", spy)
    first = [call(call_id=f"first_{i}") for i in range(5)]
    second = [call(call_id=f"second_{i}") for i in range(4)]
    script = Script(response(calls=first), response(calls=second))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert len(executed) == 5


async def test_final_json_after_exhausting_tools_counts_as_model_call(registry):
    script = Script(response(calls=[call(call_id=f"c{i}") for i in range(8)]), response(question()))
    await LiteLLMAgent(Settings(), registry, script).run(snapshot("R2"), request())
    assert "tools" not in script.calls[1]
    assert script.calls[1]["response_format"] == {"type": "json_object"}
    exhausted = Script(response(calls=[call()]), response(question()))
    await assert_invalid(
        LiteLLMAgent(Settings(max_model_calls=1), registry, exhausted), snapshot("R2")
    )
    assert len(exhausted.calls) == 1


async def test_total_deadline_is_shared(registry, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("backend.agent.monotonic", lambda: clock[0])

    async def step(**kwargs):
        clock[0] = 119.5
        return response(calls=[call()])

    script = Script(step, response(question()))
    await LiteLLMAgent(Settings(), registry, script).run(snapshot("R2"), request())
    assert script.calls[1]["timeout"] <= 0.5


@pytest.mark.parametrize("ref,instance_id", [("fake", "ci_a"), ("ev_b", "ci_a"), ("ev_a", "ci_b")])
async def test_fake_evidence_and_cross_instance_ids_are_rejected(registry, ref, instance_id):
    script = Script(
        response(calls=[call()]), response(analysis(ref, instance_id)), response(question())
    )
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert len(script.calls) == 2


async def test_catalog_evidence_not_exposed_this_request_is_rejected(registry):
    script = Script(response(analysis()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))


@pytest.mark.parametrize("mutation", ["year", "scope", "future"])
async def test_readable_background_cannot_become_explicit_fact(registry, mutation):
    item = registry.catalog._load()["ci_a"].evidence[0]
    if mutation == "year":
        item.applicable_year = 2025
    elif mutation == "scope":
        item.scope = "非本科组、非校内选拔"
    else:
        item.fetched_at = datetime.fromisoformat("2027-01-01T00:00:00+08:00")
    script = Script(response(calls=[call()]), response(analysis()), response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert len(script.calls) == 2


async def test_background_inference_must_disclose_uncertainty(registry):
    registry.catalog._load()["ci_a"].evidence[0].applicable_year = 2025
    script = Script(
        response(calls=[call()]),
        response(analysis(basis="inferred", uncertainties=["往届背景，本届要求未知"])),
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(snapshot("R2"), request())
    assert draft.analyses[0].dimensions[0].basis == "inferred"


@pytest.mark.parametrize(
    "stage,draft",
    [
        ("R0", {"kind": "candidates", "message": "x", "candidates": []}),
        ("R1", analysis()),
        ("R2", question(analyses=analysis()["analyses"])),
        ("R4", {"kind": "plan", "message": "x", "plan": None}),
        ("R0", {"kind": "profile", "message": "x", "profile_changes": None}),
    ],
)
async def test_stage_and_kind_must_match_contents(registry, stage, draft):
    script = Script(response(draft), response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot(stage))
    assert len(script.calls) == 1


class FakeUpstream(Exception):
    def __init__(self, status_code):
        super().__init__("sk-FAKE-SECRET https://secret.invalid account=PRIVATE")
        self.status_code = status_code


@pytest.mark.parametrize(
    "status,http,code,count",
    [
        (401, 503, "LLM_NOT_CONFIGURED", 1),
        (402, 503, "LLM_NOT_CONFIGURED", 1),
        (403, 503, "LLM_NOT_CONFIGURED", 1),
        (429, 429, "RATE_LIMITED", 2),
        (500, 502, "UPSTREAM_ERROR", 2),
        (400, 502, "UPSTREAM_ERROR", 1),
        (408, 504, "UPSTREAM_TIMEOUT", 1),
    ],
)
async def test_upstream_errors_do_not_leak_key(registry, caplog, status, http, code, count):
    script = Script(FakeUpstream(status), FakeUpstream(status))
    with pytest.raises(AppError) as caught:
        await LiteLLMAgent(Settings(), registry, script).run(snapshot(), request())
    assert (caught.value.status_code, caught.value.code) == (http, code)
    assert len(script.calls) == count
    assert caught.value.__cause__ is None
    assert "FAKE-SECRET" not in str(caught.value) + repr(caught.value.details) + caplog.text


async def test_transient_retry_is_once_for_entire_request(registry):
    script = Script(
        FakeUpstream(429), response(calls=[call()]), FakeUpstream(500), response(question())
    )
    with pytest.raises(AppError) as caught:
        await LiteLLMAgent(Settings(), registry, script).run(snapshot("R2"), request())
    assert caught.value.code == "UPSTREAM_ERROR"
    assert len(script.calls) == 3


async def test_default_without_key_is_controlled_and_never_imports_provider(registry, monkeypatch):
    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        assert not name.startswith("litellm"), "Provider should stay lazy"
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    with pytest.raises(AppError) as caught:
        await LiteLLMAgent(Settings(), registry).run(snapshot(), request())
    assert (caught.value.status_code, caught.value.code) == (503, "LLM_NOT_CONFIGURED")


async def test_default_provider_passes_explicit_key_without_calling_real_model(
    registry, monkeypatch
):
    script = Script(response(question()))
    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=script))
    await LiteLLMAgent(Settings(deepseek_api_key="fictional-key"), registry).run(
        snapshot(), request()
    )
    assert script.calls[0]["api_key"] == "fictional-key"
    assert script.calls[0]["model"] == "deepseek/deepseek-chat"


def test_import_has_no_provider_or_config_side_effects(monkeypatch):
    import importlib

    import backend.agent as module

    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        assert not name.startswith("litellm")
        return real_import(name, *args, **kwargs)

    def no_read(*args, **kwargs):
        raise AssertionError("Import must not read config")

    monkeypatch.setattr(builtins, "__import__", guard)
    monkeypatch.setattr("pathlib.Path.read_text", no_read)
    importlib.reload(module)


async def test_semantic_failures_cannot_hide_behind_format_repair(registry):
    bad = analysis("forged")
    del bad["message"]
    script = Script(response(calls=[call()]), response(bad), response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert len(script.calls) == 2


async def test_deeply_nested_output_is_controlled(registry):
    script = Script(response(content="[" * 2000 + "0" + "]" * 2000))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script))


async def test_unsubstantiated_profile_change_is_a_review_question(registry):
    script = Script(
        response(
            {"kind": "profile", "message": "每周六小时。", "profile_changes": {"weekly_hours": 6}}
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(snapshot(), request("继续吧"))
    assert draft.kind == "question" and draft.profile_changes is None


async def test_explicit_profile_changes_preserve_unset_fields(registry):
    state = snapshot(profile=Profile(major="计算机", weekly_hours=None))
    script = Script(
        response({"kind": "profile", "message": "请核对。", "profile_changes": {"weekly_hours": 6}})
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(state, request("每周六小时"))
    assert draft.kind == "profile"
    assert draft.profile_changes.model_dump(exclude_unset=True) == {"weekly_hours": 6}
    assert state.profile.weekly_hours is None and state.profile.major == "计算机"


async def test_context_uses_reassessed_catalog_and_preserves_decisions(registry):
    state = snapshot(
        "R2",
        profile=Profile(grade="大二", major="计算机"),
        cards=[
            CandidateCard(
                competition_instance_id="ci_a",
                name="stale",
                reason="current reason",
                registration_status="closed",
                decision="keep",
            ),
        ],
    )
    script = Script(response(analysis()))
    draft = await LiteLLMAgent(Settings(), registry, script).run(state, request())
    assert draft.kind == "analysis"
    context = json.loads(script.calls[0]["messages"][1]["content"].split("\n", 1)[1])
    related = context["backend_decisions"][0]
    assert related["decision"] == "keep"
    assert related["detail"]["registration_status"] == "open"
    assert related["detail"]["eligibility_check"]["status"] == "eligible"
    assert related["detail"]["current_fact_evidence_ids"] == ["ev_a"]


async def test_candidates_use_rules_not_raw_registration_status(registry):
    script = Script(
        response(calls=[call("search_competitions", {})]),
        response(
            {
                "kind": "candidates",
                "message": "仅为草案。",
                "candidates": [{"competition_instance_id": "ci_a", "reason": "相关"}],
            }
        ),
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(snapshot("R1"), request())
    assert draft.kind == "candidates"


@pytest.mark.parametrize("excluded", [True, False])
async def test_excluded_or_ineligible_candidates_are_not_promoted(registry, excluded):
    state = snapshot(
        "R1",
        profile=Profile(grade="大一" if not excluded else "大二"),
        cards=[
            CandidateCard(
                competition_instance_id="ci_a",
                name="虚构",
                reason="待查",
                decision="exclude" if excluded else "keep",
            ),
        ],
    )
    script = Script(
        response(
            {
                "kind": "candidates",
                "message": "x",
                "candidates": [{"competition_instance_id": "ci_a", "reason": "相关"}],
            }
        ),
        response(question()),
    )
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), state)
    assert len(script.calls) == 1


async def test_r4_plan_remains_a_draft_with_unknown_budget(registry):
    state = snapshot(
        "R4",
        cards=[
            CandidateCard(
                competition_instance_id="ci_a", name="虚构", reason="相关", decision="keep"
            )
        ],
    )
    plan = {
        "selected_competition_ids": ["ci_a"],
        "tasks": [
            {
                "id": "t1",
                "competition_instance_id": "ci_a",
                "title": "练习",
                "estimated_hours": 6,
                "acceptance_criteria": "通过样例",
                "start_date": None,
                "due_date": None,
            }
        ],
    }
    script = Script(response({"kind": "plan", "message": "预算未知，待核对。", "plan": plan}))
    draft = await LiteLLMAgent(Settings(), registry, script).run(state, request())
    assert draft.plan.model_dump(mode="json") == {**plan, "assumptions": []}
    assert not hasattr(draft.plan, "feasibility")
    assert state.profile.weekly_hours is None


async def test_tool_response_chains_are_request_local(registry):
    script = Script(response(calls=[call()]), response(question()), response(analysis()))
    agent = LiteLLMAgent(Settings(), registry, script)
    await agent.run(snapshot("R2"), request())
    await assert_invalid(agent, snapshot("R2"))
    assert not any(m["role"] == "tool" for m in script.calls[2]["messages"])


@pytest.mark.filterwarnings("ignore:Item 'summary' on TypedDict class:UserWarning")
async def test_review_i4_default_provider_blocks_real_sdk_raw_logs(
    registry,
    monkeypatch,
    caplog,
    capsys,
):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import litellm

    import backend.agent as module

    real_completion = litellm.acompletion

    async def local_sdk(**kwargs):
        # Exercise the actual SDK decorators, logging, parsing and async path;
        # only the model response is mocked by LiteLLM itself. No HTTP/key needed.
        return await real_completion(**kwargs, mock_response=json.dumps(question()))

    monkeypatch.setattr(litellm, "acompletion", local_sdk)
    monkeypatch.setattr(module, "_SYSTEM", "SYSTEM_PRIVATE_MARKER\n" + module._SYSTEM)
    for name in ("LiteLLM", "LiteLLM Proxy", "LiteLLM Router", "openai._base_client"):
        logger = logging.getLogger(name)
        monkeypatch.setattr(logger, "disabled", False)
        monkeypatch.setattr(logger, "propagate", True)
        monkeypatch.setattr(logger, "level", logging.NOTSET)
    uvicorn = logging.getLogger("uvicorn.error")
    monkeypatch.setattr(uvicorn, "disabled", False)
    monkeypatch.setattr(uvicorn, "propagate", True)
    monkeypatch.setattr(uvicorn, "level", logging.DEBUG)
    state = snapshot(profile=Profile(additional_context="PROFILE_PRIVATE_MARKER"))
    with caplog.at_level(logging.DEBUG):
        handlers = list(logging.getLogger().handlers)
        draft = await LiteLLMAgent(Settings(deepseek_api_key="fictional-key"), registry).run(
            state, request("USER_PRIVATE_MARKER")
        )
        await asyncio.sleep(0.02)  # Include SDK async post-call logging.
        logging.getLogger("backend.agent-test").debug("APPLICATION_LOG_STILL_WORKS")
        uvicorn.debug("UVICORN_LOG_STILL_WORKS")
        assert logging.getLogger().level == logging.DEBUG
        assert logging.getLogger().handlers == handlers
        assert uvicorn.level == logging.DEBUG and not uvicorn.disabled
    assert draft.kind == "question"
    assert "APPLICATION_LOG_STILL_WORKS" in caplog.text
    assert "UVICORN_LOG_STILL_WORKS" in caplog.text
    captured = capsys.readouterr()
    output = caplog.text + captured.out + captured.err
    for marker in ("SYSTEM_PRIVATE_MARKER", "USER_PRIVATE_MARKER", "PROFILE_PRIVATE_MARKER"):
        assert marker not in output


async def test_pinned_litellm_exception_mapping_without_network(registry, monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from litellm import exceptions

    cases = [
        (exceptions.AuthenticationError, 503, "LLM_NOT_CONFIGURED", 1),
        (exceptions.PermissionDeniedError, 503, "LLM_NOT_CONFIGURED", 1),
        (exceptions.PaymentRequiredError, 503, "LLM_NOT_CONFIGURED", 1),
        (exceptions.RateLimitError, 429, "RATE_LIMITED", 2),
        (exceptions.Timeout, 504, "UPSTREAM_TIMEOUT", 1),
        (exceptions.APIConnectionError, 502, "UPSTREAM_ERROR", 2),
        (exceptions.UnsupportedParamsError, 502, "UPSTREAM_ERROR", 1),
    ]
    for cls, http, code, count in cases:
        extra = {}
        if cls is exceptions.PermissionDeniedError:
            extra["response"] = httpx.Response(
                403, request=httpx.Request("GET", "https://example.com")
            )
        error = cls(
            message="FAKE-secret-do-not-log", model="fictional", llm_provider="deepseek", **extra
        )
        script = Script(error, error)
        with pytest.raises(AppError) as caught:
            await LiteLLMAgent(Settings(), registry, script).run(snapshot(), request())
        assert (caught.value.status_code, caught.value.code) == (http, code)
        assert len(script.calls) == count


async def test_ineligibility_cannot_hide_behind_shape_repair(registry):
    state = snapshot(
        "R1",
        profile=Profile(grade="大一"),
        cards=[
            CandidateCard(
                competition_instance_id="ci_a", name="虚构", reason="待查", decision="keep"
            )
        ],
    )
    script = Script(
        response(
            {
                "kind": "candidates",
                "candidates": [{"competition_instance_id": "ci_a", "reason": "相关"}],
            }
        ),
        response(question()),
    )
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), state)
    assert len(script.calls) == 1


async def test_stage_violation_cannot_hide_behind_shape_repair(registry):
    script = Script(response({"kind": "plan"}), response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script))
    assert len(script.calls) == 1


@pytest.mark.filterwarnings("ignore:Item 'summary' on TypedDict class:UserWarning")
async def test_model_output_object_and_call_ids_across_rounds(registry, monkeypatch):
    monkeypatch.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    from litellm import ModelResponse

    script = Script(
        ModelResponse(**response(calls=[call()])), ModelResponse(**response(analysis()))
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(snapshot("R2"), request())
    assert draft.kind == "analysis"
    repeated = Script(response(calls=[call()]), response(calls=[call()]))
    await assert_invalid(LiteLLMAgent(Settings(), registry, repeated), snapshot("R2"))


async def test_model_limit_is_five_including_repair(registry):
    script = Script(
        *[response(calls=[call(call_id=f"c{i}")]) for i in range(4)],
        response(content="bad"),
        response(question()),
    )
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert len(script.calls) == 5


async def test_deadline_includes_tool_time(registry, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("backend.agent.monotonic", lambda: clock[0])
    execute = registry.execute

    def tool(*args):
        clock[0] = 121
        return execute(*args)

    monkeypatch.setattr(registry, "execute", tool)
    script = Script(response(calls=[call()]), response(question()))
    with pytest.raises(AppError) as caught:
        await LiteLLMAgent(Settings(), registry, script).run(snapshot("R2"), request())
    assert caught.value.code == "UPSTREAM_TIMEOUT"
    assert len(script.calls) == 1


async def test_failed_tool_cannot_mutate_input_snapshot(registry, monkeypatch):
    original_execute = registry.execute

    def tool(name, args, state):
        state.profile.weekly_hours = 99
        return original_execute(name, args, state)

    monkeypatch.setattr(registry, "execute", tool)
    state = snapshot("R2", profile=Profile(weekly_hours=6))
    original = state.model_copy(deep=True)
    script = Script(response(calls=[call()]), response(analysis("fake")))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), state)
    assert state == original


async def test_tool_argument_date_format_is_validated_before_execution(registry, monkeypatch):
    executed = []
    monkeypatch.setattr(registry, "execute", lambda *args: executed.append(args))
    bad = call(
        "evaluate_plan",
        {
            "plan": {
                "selected_competition_ids": ["ci_a"],
                "tasks": [
                    {
                        "id": "t1",
                        "competition_instance_id": "ci_a",
                        "title": "虚构",
                        "acceptance_criteria": "检查",
                        "start_date": "not-a-date",
                    }
                ],
            }
        },
        "bad_date",
    )
    script = Script(response(calls=[call(), bad]))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R4"))
    assert not executed


async def test_background_scope_failure_cannot_be_format_repaired(registry):
    registry.catalog._load()["ci_a"].evidence[0].applicable_year = 2025
    bad = analysis(basis="inferred")
    del bad["message"]
    script = Script(response(calls=[call()]), response(bad), response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert len(script.calls) == 2


async def test_r4_context_preserves_prior_analysis(registry):
    dimensions = analysis()["analyses"][0]["dimensions"]
    state = snapshot(
        "R4",
        cards=[
            CandidateCard(
                competition_instance_id="ci_a",
                name="虚构",
                reason="相关",
                decision="keep",
                dimensions=dimensions,
            )
        ],
    )
    script = Script(response(question()))
    await LiteLLMAgent(Settings(), registry, script).run(state, request())
    context = json.loads(script.calls[0]["messages"][1]["content"].split("\n", 1)[1])
    assert context["backend_decisions"][0]["dimensions"][0]["evidence_ids"] == ["ev_a"]


@pytest.mark.parametrize("failure", ["ineligible", "unselected_task"])
async def test_plan_fact_failures_cannot_be_format_repaired(registry, failure):
    state = snapshot(
        "R4",
        profile=Profile(grade="大一" if failure == "ineligible" else "大二"),
        cards=[
            CandidateCard(
                competition_instance_id="ci_a", name="虚构", reason="相关", decision="keep"
            )
        ],
    )
    script = Script(
        response(
            {
                "kind": "plan",
                "plan": {
                    "selected_competition_ids": ["ci_a"],
                    "tasks": [
                        {
                            "id": "t1",
                            "competition_instance_id": "ci_b"
                            if failure == "unselected_task"
                            else "ci_a",
                            "title": "练习",
                            "acceptance_criteria": "检查",
                        }
                    ],
                },
            }
        ),
        response(question()),
    )
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), state)
    assert len(script.calls) == 1


async def test_mixed_malformed_reference_cannot_hide_forgery_in_repair(registry):
    bad = analysis(evidence_ids=["forged", 123])
    script = Script(response(calls=[call()]), response(bad), response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert len(script.calls) == 2


@pytest.mark.parametrize(
    "malformation",
    ["string_refs", "missing_owner", "wrong_owner_type", "string_dimensions", "string_analyses"],
)
async def test_review_i1_citation_structure_fails_closed(registry, malformation):
    bad = analysis()
    item = bad["analyses"][0]
    if malformation == "string_refs":
        item["dimensions"][0]["evidence_ids"] = "forged"
    elif malformation == "missing_owner":
        del item["competition_instance_id"]
        item["dimensions"][0]["evidence_ids"] = ["forged"]
    elif malformation == "wrong_owner_type":
        item["competition_instance_id"] = 123
    elif malformation == "string_dimensions":
        item["dimensions"] = "forged"
    else:
        bad["analyses"] = "forged"
    script = Script(response(calls=[call()]), response(bad), response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), snapshot("R2"))
    assert len(script.calls) == 2


@pytest.mark.parametrize("selected", ["ci_a", None, {"ci_a": True}])
async def test_review_i1_task_validation_does_not_depend_on_selected_shape(registry, selected):
    state = snapshot(
        "R4",
        cards=[
            CandidateCard(
                competition_instance_id="ci_a", name="虚构", reason="相关", decision="keep"
            )
        ],
    )
    bad = {
        "kind": "plan",
        "message": "草案",
        "plan": {
            "selected_competition_ids": selected,
            "tasks": [
                {
                    "id": "t1",
                    "competition_instance_id": "ci_b",
                    "title": "练习",
                    "acceptance_criteria": "完成",
                }
            ],
        },
    }
    script = Script(response(bad), response(question()))
    await assert_invalid(LiteLLMAgent(Settings(), registry, script), state)
    assert len(script.calls) == 1


@pytest.mark.parametrize("context", ["偏好算法竞赛", "现在可能只有两小时"])
async def test_review_i2_explicit_correction_is_not_locked_by_context(registry, context):
    state = snapshot(profile=Profile(weekly_hours=6, additional_context=context))
    original = state.model_copy(deep=True)
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "请核对更正草案。",
                "profile_changes": {"weekly_hours": 2},
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        state, request("请将每周投入从六小时改为两小时，我确认是每周两小时")
    )
    assert draft.kind == "profile"
    assert draft.profile_changes.model_dump(exclude_unset=True) == {"weekly_hours": 2}
    assert state == original


async def test_review_i2_ambiguous_change_names_field_and_confirmation_resolves_it(registry):
    state = snapshot(profile=Profile(weekly_hours=6, additional_context="偏好算法竞赛"))
    proposed = {"kind": "profile", "message": "请核对。", "profile_changes": {"weekly_hours": 2}}
    script = Script(response(proposed), response(proposed))
    agent = LiteLLMAgent(Settings(), registry, script)
    draft = await agent.run(state, request("也许每周两小时，但我还不确定"))
    assert draft.kind == "question" and draft.profile_changes is None
    assert "每周" in draft.message and "6" in draft.message and "2" in draft.message
    confirmed = await agent.run(state, request("我确认是每周两小时，请更正"))
    assert confirmed.kind == "profile" and confirmed.profile_changes.weekly_hours == 2


@pytest.mark.parametrize(
    "field,value,text",
    [
        ("weekly_hours", 8, "每周6小时，每周8小时。"),
        ("grade", "大三", "我是大二，我是大三。"),
        ("major", "金融", "我的专业是计算机，我的专业是金融。"),
        ("grade", "大三", "我可能是大三。"),
        ("major", "金融", "专业也许是金融。"),
        ("weekly_hours", 8, "每周可能8小时。"),
        ("grade", "大三", "不是大三，我是大三。"),
        ("major", "金融", "不要改成金融，请更正专业为金融。"),
        ("weekly_hours", 8, "每周不能投入8小时，每周能投入8小时。"),
        ("grade", "大三", "朋友是大三。"),
        ("major", "金融", "我想参加金融竞赛。"),
        ("weekly_hours", 6, "每周6小时，每周也能8小时。"),
        ("grade", "大三", "我是大三，我目前大二。"),
        ("major", "金融", "我的专业是金融，我专业计算机。"),
        ("weekly_hours", 8, "每周8小时，也许每周6小时。"),
        ("grade", "大三", "我是大三，也许我是大二。"),
        ("major", "金融", "我的专业是金融，也许专业是计算机。"),
    ],
)
async def test_final_i1_conflicting_uncertain_or_unattributed_scalar_gets_review(
    registry, field, value, text
):
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "错误提取",
                "profile_changes": {field: value},
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(snapshot(), request(text))
    assert draft.kind == "question" and draft.profile_changes is None
    assert "核对" in draft.message


async def test_final_i1_affirmative_scalar_and_not_teaming_are_independent(registry):
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "请核对。",
                "profile_changes": {"grade": "大三", "team_preference": "solo"},
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        snapshot(),
        request("我是大三，我不组队。"),
    )
    assert draft.kind == "profile"
    assert draft.profile_changes.grade == "大三"
    assert draft.profile_changes.team_preference == "solo"


@pytest.mark.parametrize("existing", [[], [{"name": "Python", "evidence": "课程项目"}]])
async def test_review_i3_name_alone_cannot_authorize_invented_evidence(registry, existing):
    state = snapshot(profile=Profile(skills=existing))
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "技能草案。",
                "profile_changes": {
                    "skills": [
                        {"name": "Python", "evidence": "取得全国一等奖（虚构，用户未提供）"}
                    ],
                },
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(state, request("我学过Python"))
    assert draft.kind == "question" and draft.profile_changes is None
    assert "Python" in draft.message and "依据" in draft.message


async def test_review_i3_preserve_old_skill_and_add_supported_new_skill(registry):
    old = {"name": "Python", "evidence": "课程项目"}
    new = {"name": "Java", "evidence": "完成Java课程项目"}
    state = snapshot(profile=Profile(skills=[old]))
    script = Script(
        response(
            {"kind": "profile", "message": "技能草案。", "profile_changes": {"skills": [old, new]}}
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        state, request("我还会Java，完成Java课程项目，请保留已有技能")
    )
    assert draft.kind == "profile"
    assert draft.profile_changes.model_dump(exclude_unset=True)["skills"] == [old, new]
    assert state.profile.skills[0].evidence == "课程项目" and len(state.profile.skills) == 1


async def test_review_i3_removal_needs_specific_user_basis_and_can_be_confirmed(registry):
    state = snapshot(profile=Profile(skills=[{"name": "Python", "evidence": "课程项目"}]))
    proposed = {
        "kind": "profile",
        "message": "技能草案。",
        "profile_changes": {
            "skills": [{"name": "Java", "evidence": None}],
        },
    }
    script = Script(response(proposed), response(proposed))
    agent = LiteLLMAgent(Settings(), registry, script)
    draft = await agent.run(state, request("我还会Java，请保留已有技能"))
    assert draft.kind == "question" and draft.profile_changes is None
    assert "Python" in draft.message and "删除" in draft.message
    confirmed = await agent.run(state, request("我确认删除Python，只保留Java"))
    assert confirmed.kind == "profile"
    assert [item.name for item in confirmed.profile_changes.skills] == ["Java"]


@pytest.mark.parametrize("negative", ["不要删除Python", "不删除Python", "不能删除Python"])
async def test_review_i3_do_not_delete_is_not_removal_authority(registry, negative):
    state = snapshot(profile=Profile(skills=[{"name": "Python", "evidence": None}]))
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "技能草案。",
                "profile_changes": {
                    "skills": [{"name": "Java", "evidence": None}],
                },
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        state, request("我还会Java，" + negative)
    )
    assert draft.kind == "question" and draft.profile_changes is None


async def test_review_i3_explicit_evidence_clear_is_not_a_permanent_review_loop(registry):
    state = snapshot(profile=Profile(skills=[{"name": "Python", "evidence": "课程项目"}]))
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "技能草案。",
                "profile_changes": {
                    "skills": [{"name": "Python", "evidence": None}],
                },
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        state, request("请清空Python的经历，保留Python技能")
    )
    assert draft.kind == "profile" and draft.profile_changes.skills[0].evidence is None


async def test_review_i3_changed_evidence_requires_its_own_basis(registry):
    state = snapshot(profile=Profile(skills=[{"name": "Python", "evidence": "课程项目"}]))
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "技能草案。",
                "profile_changes": {
                    "skills": [{"name": "Python", "evidence": "完成Python实习项目"}],
                },
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        state, request("请更正Python的经历为完成Python实习项目")
    )
    assert (
        draft.kind == "profile" and draft.profile_changes.skills[0].evidence == "完成Python实习项目"
    )


@pytest.mark.parametrize(
    "text,preference",
    [
        ("我只想个人参赛，不想组队", "solo"),
        ("我希望组队参赛", "team"),
        ("个人参赛或组队都可以", "either"),
    ],
)
async def test_review_m1_clear_chinese_team_preferences(registry, text, preference):
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "偏好草案。",
                "profile_changes": {
                    "team_preference": preference,
                },
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(snapshot(), request(text))
    assert draft.kind == "profile" and draft.profile_changes.team_preference == preference


async def test_review_m1_negated_team_preference_is_not_positive_basis(registry):
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "偏好草案。",
                "profile_changes": {
                    "team_preference": "team",
                },
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        snapshot(), request("我只想个人参赛，不想组队")
    )
    assert draft.kind == "question" and draft.profile_changes is None


async def test_review_m2_large_json_integer_is_controlled(registry, caplog):
    large = "7" * 5000
    script = Script(
        response(content='{"kind":"question","message":' + large + "}"), response(question())
    )
    error = await assert_invalid(LiteLLMAgent(Settings(), registry, script))
    assert len(script.calls) == 1
    assert large not in str(error) + caplog.text


@pytest.mark.parametrize(
    "text,evidence",
    [
        ("我学过Python，但没有取得全国一等奖。", "取得全国一等奖"),
        ("Python经历：入门课程；Java经历：校赛一等奖。", "校赛一等奖"),
        ("Python经历：没有取得全国一等奖。", "取得全国一等奖"),
        ("Java经历：完成Python课程项目；我学过Python。", "完成Python课程项目"),
        ("Python经历：入门课程 Java经历：校赛一等奖。", "入门课程 Java经历：校赛一等奖"),
    ],
)
async def test_fix2_i3a_negation_or_other_skill_is_not_python_evidence(registry, text, evidence):
    state = snapshot()
    original = state.model_copy(deep=True)
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "技能草案。",
                "profile_changes": {
                    "skills": [{"name": "Python", "evidence": evidence}],
                },
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(state, request(text))
    assert draft.kind == "question" and draft.profile_changes is None
    assert "Python" in draft.message and "依据" in draft.message
    assert state == original


async def test_fix2_n1_evidence_list_clear_does_not_authorize_skill_removal(registry):
    python = {"name": "Python", "evidence": "Python课程项目"}
    java = {"name": "Java", "evidence": "Java课程项目"}
    state = snapshot(profile=Profile(skills=[python, java]))
    original = state.model_copy(deep=True)
    script = Script(
        response(
            {"kind": "profile", "message": "技能草案。", "profile_changes": {"skills": [java]}}
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        state, request("请删除Python和Java的经历，保留这两项技能。")
    )
    assert draft.kind == "question" and draft.profile_changes is None
    assert "Python" in draft.message and "删除" in draft.message
    assert state == original


async def test_fix2_positive_python_evidence_control(registry):
    expected = {"name": "Python", "evidence": "完成Python课程项目"}
    script = Script(
        response(
            {"kind": "profile", "message": "技能草案。", "profile_changes": {"skills": [expected]}}
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        snapshot(), request("我学过Python，完成Python课程项目。")
    )
    assert draft.kind == "profile"
    assert draft.profile_changes.model_dump(exclude_unset=True)["skills"] == [expected]


async def test_fix2_positive_explicit_skill_removal_control(registry):
    java = {"name": "Java", "evidence": "Java课程项目"}
    state = snapshot(
        profile=Profile(
            skills=[
                {"name": "Python", "evidence": "Python课程项目"},
                java,
            ]
        )
    )
    script = Script(
        response(
            {"kind": "profile", "message": "技能草案。", "profile_changes": {"skills": [java]}}
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        state, request("请删除Python技能，保留Java。")
    )
    assert draft.kind == "profile"
    assert draft.profile_changes.model_dump(exclude_unset=True)["skills"] == [java]


async def test_fix2_i3a_unscoped_evidence_gets_a_resolvable_skill_question(registry):
    expected = {"name": "Python", "evidence": "校赛一等奖"}
    proposal = {
        "kind": "profile",
        "message": "技能草案。",
        "profile_changes": {"skills": [expected]},
    }
    script = Script(response(proposal), response(proposal))
    agent = LiteLLMAgent(Settings(), registry, script)
    first = await agent.run(snapshot(), request("我学过Python，校赛一等奖。"))
    assert first.kind == "question" and first.profile_changes is None
    assert "Python" in first.message and "依据" in first.message
    resolved = await agent.run(snapshot(), request("Python经历：校赛一等奖。"))
    assert resolved.kind == "profile"
    assert resolved.profile_changes.model_dump(exclude_unset=True)["skills"] == [expected]


@pytest.mark.parametrize(
    "text", ["请删除Python和Java的经历。", "请删除Python技能，保留Python技能。"]
)
async def test_fix2_n1_incomplete_target_or_keep_constraint_blocks_skill_removal(registry, text):
    java = {"name": "Java", "evidence": "Java课程项目"}
    state = snapshot(
        profile=Profile(
            skills=[
                {"name": "Python", "evidence": "Python课程项目"},
                java,
            ]
        )
    )
    script = Script(
        response(
            {"kind": "profile", "message": "技能草案。", "profile_changes": {"skills": [java]}}
        )
    )
    result = await LiteLLMAgent(Settings(), registry, script).run(state, request(text))
    assert result.kind == "question" and result.profile_changes is None
    assert "Python" in result.message


@pytest.mark.parametrize(
    "text,kind",
    [
        ("Python经历：校赛一等奖，但没有校赛一等奖。", "question"),
        ("Python经历：校赛一等奖；Java没有完成Java项目。", "profile"),
    ],
)
async def test_fix2_i3a_denied_evidence_is_not_rescued_by_another_clause(registry, text, kind):
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "技能草案。",
                "profile_changes": {
                    "skills": [{"name": "Python", "evidence": "校赛一等奖"}],
                },
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(snapshot(), request(text))
    assert draft.kind == kind
    if kind == "question":
        assert draft.profile_changes is None and "Python" in draft.message


@pytest.mark.parametrize("line_break", ["", "\n", "\r\n"])
async def test_fix3_explicit_owner_is_not_lost_at_line_break(registry, line_break):
    state = snapshot()
    original = state.model_copy(deep=True)
    script = Script(
        response(
            {
                "kind": "profile",
                "message": "虚构复审草案（AI 辅助生成）",
                "profile_changes": {
                    "skills": [
                        {"name": "Python", "evidence": "完成Python课程项目"},
                    ]
                },
            }
        )
    )
    draft = await LiteLLMAgent(Settings(), registry, script).run(
        state, request("Java经历：" + line_break + "完成Python课程项目；我学过Python。")
    )
    assert draft.kind == "question" and draft.profile_changes is None
    assert "Python" in draft.message and "依据" in draft.message
    assert state == original
    assert len(script.calls) == 1
