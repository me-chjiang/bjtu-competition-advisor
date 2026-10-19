"""Offline rules tests; all records and sources are fictional (AI-assisted)."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

from backend.catalog import (
    CompetitionCatalog,
    assess_competition,
    check_eligibility,
    evaluate_plan,
)
from backend.config import Settings
from backend.main import create_app
from backend.schemas import AppError, CompetitionRecord, PlanDraft, Profile, SessionSnapshot
from backend.tools import ToolRegistry, ToolResult

NOW = datetime.fromisoformat("2026-10-18T12:00:00+08:00")
EXAMPLES = Path(__file__).parents[1] / "examples" / "competitions.json"


def record_values(**changes):
    values = {
        "competition_instance_id": "fictional_2026_school",
        "name": "虚构测试竞赛 2026 校内选拔（AI 辅助生成）",
        "series_id": "fictional",
        "year": 2026,
        "stage": "校内选拔",
        "registration_start": "2026-10-01",
        "registration_deadline": "2026-10-20",
        "competition_date": "2026-11-15",
        "allowed_grades": ["大二"],
        "allowed_majors": ["计算机"],
        "eligibility_evidence_ids": ["ev_rules"],
        "registration_evidence_ids": ["ev_rules"],
        "competition_date_evidence_ids": ["ev_rules"],
        "evidence": [
            {
                "id": "ev_rules",
                "url": "https://example.com/fictional-2026",
                "excerpt": "虚构：本届校内选拔仅大二计算机专业；10月1日至20日报名，11月15日比赛。",
                "fetched_at": "2026-10-17T12:00:00+08:00",
                "applicable_year": 2026,
                "scope": 'applies-to/v1:{"stage":"校内选拔","group":null}',
            }
        ],
    }
    values.update(changes)
    return values


def instance(**changes):
    return CompetitionRecord.model_validate(record_values(**changes))


def catalog_at(tmp_path, values=None):
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(values if values is not None else [record_values()]), encoding="utf-8"
    )
    return CompetitionCatalog(path)


def draft(*tasks, selected=None):
    return PlanDraft.model_validate(
        {
            "selected_competition_ids": selected or ["fictional_2026_school"],
            "tasks": [
                {
                    "id": f"t{i}",
                    "competition_instance_id": "fictional_2026_school",
                    "title": "虚构备赛",
                    "acceptance_criteria": "完成练习",
                    "estimated_hours": 6,
                    "start_date": "2026-10-19",
                    "due_date": "2026-10-25",
                    **task,
                }
                for i, task in enumerate(tasks)
            ],
        }
    )


def test_only_explicit_conflicts_exclude():
    assert check_eligibility(Profile(grade="大一"), instance(), NOW).status == "ineligible"
    assert check_eligibility(Profile(grade="大二"), instance(), NOW).status == "unknown"
    assert (
        check_eligibility(
            Profile(grade="大一"),
            instance(eligibility_evidence_ids=[]),
            NOW,
        ).status
        == "unknown"
    )
    assert (
        check_eligibility(
            Profile(grade="大二", major="计算机"),
            instance(),
            NOW,
        ).status
        == "eligible"
    )


def test_historical_dates_do_not_become_current_dates():
    values = record_values()
    values["evidence"][0]["applicable_year"] = 2025
    historical = CompetitionRecord.model_validate(values)
    assessed = assess_competition(historical, NOW)
    assert assessed.registration_status == "unknown"
    assert assessed.registration_deadline is None
    assert assessed.competition_date is None
    assert check_eligibility(Profile(grade="大一"), historical, NOW).status == "unknown"
    old = instance(year=2025, registration_start="2025-10-01", registration_deadline="2025-10-20")
    old.evidence[0].applicable_year = 2025
    assert assess_competition(old, NOW).registration_status == "closed"
    assert old.registration_deadline == date(2025, 10, 20)


@pytest.mark.parametrize("mutation", ["no_refs", "wrong_scope", "future", "wrong_date_year"])
def test_unproven_dates_are_unknown(mutation):
    values = record_values()
    if mutation == "no_refs":
        values["registration_evidence_ids"] = []
    elif mutation == "wrong_scope":
        values["evidence"][0]["scope"] = "全国决赛"
    elif mutation == "future":
        values["evidence"][0]["fetched_at"] = "2026-10-19T00:00:00+08:00"
    else:
        values["registration_deadline"] = "2025-10-20"
    assert (
        assess_competition(CompetitionRecord.model_validate(values), NOW).registration_status
        == "unknown"
    )


@pytest.mark.parametrize(
    ("when", "status"),
    [
        ("2026-09-30T15:59:59+00:00", "upcoming"),
        ("2026-10-20T15:59:59+00:00", "open"),
        ("2026-10-20T16:00:00+00:00", "closed"),
    ],
)
def test_registration_uses_beijing_inclusive_days(when, status):
    item = instance()
    item.evidence[0].fetched_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
    assert assess_competition(item, datetime.fromisoformat(when)).registration_status == status


def test_missing_budget_keeps_plan_unknown(tmp_path):
    result = evaluate_plan(Profile(), draft({}), catalog_at(tmp_path), NOW)
    assert result.feasibility == "unknown"
    assert all(week.budget_hours is None for week in result.weekly_load)
    assert result.weekly_load[0].estimated_hours == 6
    assert result.conflicts


def test_unavailable_days_and_overlapping_weekly_load(tmp_path):
    # Each task has two available days (Sunday and Monday): 3h/day, 6h/week total.
    plan = draft(
        {"start_date": "2026-10-24", "due_date": "2026-10-26"},
        {"start_date": "2026-10-24", "due_date": "2026-10-26"},
    )
    profile = Profile(weekly_hours=5, unavailable_dates=[date(2026, 10, 24)])
    result = evaluate_plan(profile, plan, catalog_at(tmp_path), NOW)
    assert result.feasibility == "infeasible"
    assert [(w.week_start, w.estimated_hours, w.budget_hours) for w in result.weekly_load] == [
        (date(2026, 10, 19), 6, 5),
        (date(2026, 10, 26), 6, 5),
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"estimated_hours": None},
        {"start_date": None},
        {"due_date": None},
    ],
)
def test_missing_task_inputs_never_feasible(tmp_path, changes):
    # Overrides are merged rather than passed twice as keyword arguments.
    plan = draft({})
    task = plan.tasks[0].model_dump()
    task.update(changes)
    plan = PlanDraft(selected_competition_ids=plan.selected_competition_ids, tasks=[task])
    result = evaluate_plan(Profile(weekly_hours=20), plan, catalog_at(tmp_path), NOW)
    assert result.feasibility == "unknown"


def test_tasks_may_continue_after_registration_before_competition(tmp_path):
    result = evaluate_plan(Profile(weekly_hours=6), draft({}), catalog_at(tmp_path), NOW)
    assert result.feasibility == "feasible"
    assert result.conflicts == []


@pytest.mark.parametrize(
    "task",
    [
        {"start_date": "2026-10-05", "due_date": "2026-10-11"},
        {"start_date": "2026-10-17", "due_date": "2026-10-20"},
        {"start_date": "2026-10-17", "due_date": None},
    ],
)
def test_final_i2_past_start_is_conflict_without_allocating_elapsed_capacity(tmp_path, task):
    catalog = catalog_at(tmp_path)
    profile = Profile(grade="大二", major="计算机", weekly_hours=6)
    plan = draft(task)
    # UTC Oct 17 is Beijing Oct 18: injected clock owns the lower bound.
    now = datetime.fromisoformat("2026-10-17T16:30:00+00:00")
    result = evaluate_plan(profile, plan, catalog, now)
    assert result.feasibility == "infeasible"
    assert result.weekly_load == []
    assert any("重排" in reason and "2026-10-18" in reason for reason in result.conflicts)
    tool = ToolRegistry(catalog, clock=lambda: now).execute(
        "evaluate_plan",
        {"plan": plan.model_dump(mode="json")},
        SessionSnapshot(session_id="s", stage="R4", profile=profile),
    )
    assert tool.data == result.model_dump(mode="json")


def test_no_available_day_and_late_tasks_are_conflicts(tmp_path):
    plan = draft({})
    plan.tasks[0].due_date = date(2026, 10, 19)
    profile = Profile(weekly_hours=20, unavailable_dates=[date(2026, 10, 19)])
    assert evaluate_plan(profile, plan, catalog_at(tmp_path), NOW).feasibility == "infeasible"
    plan.tasks[0].due_date = date(2026, 11, 16)
    assert (
        evaluate_plan(Profile(weekly_hours=100), plan, catalog_at(tmp_path), NOW).feasibility
        == "infeasible"
    )


def test_closed_registration_cannot_be_kept(tmp_path):
    catalog = catalog_at(tmp_path, [record_values(registration_deadline="2026-10-17")])
    assert (
        check_eligibility(Profile(), catalog.get("fictional_2026_school"), NOW).status
        == "ineligible"
    )
    assert (
        evaluate_plan(Profile(weekly_hours=100), draft({}), catalog, NOW).feasibility
        == "infeasible"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "{",
        "{}",
        "null",
        '[{"name": "secret-invalid"}]',
    ],
)
def test_catalog_missing_or_corrupt_is_explicit_error(tmp_path, bad):
    path = tmp_path / "missing.json"
    catalog = CompetitionCatalog(path)
    with pytest.raises(AppError) as missing:
        catalog.search()
    assert (missing.value.code, missing.value.status_code) == ("CATALOG_NOT_CONFIGURED", 503)
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(AppError) as broken:
        catalog.search()
    assert (broken.value.code, broken.value.status_code) == ("CATALOG_INVALID", 503)
    assert "secret-invalid" not in str(broken.value)


@pytest.mark.parametrize("mutation", ["instance", "evidence", "missing_reference", "json_key"])
def test_duplicate_ids_and_invalid_evidence_fail_explicitly(tmp_path, mutation):
    values = [record_values()]
    if mutation == "instance":
        values.append(record_values())
    elif mutation == "evidence":
        values[0]["evidence"].append(values[0]["evidence"][0].copy())
    elif mutation == "missing_reference":
        values[0]["eligibility_evidence_ids"] = ["not-in-this-instance"]
    catalog = catalog_at(tmp_path, values)
    if mutation == "json_key":
        catalog.path.write_text('[{"name":"one","name":"two"}]', encoding="utf-8")
    with pytest.raises(AppError, match="竞赛资料"):
        catalog.search()


def test_catalog_search_preserves_instances_and_returns_defensive_copies(tmp_path):
    older = record_values(competition_instance_id="fictional_2025_school", year=2025)
    older["evidence"][0]["id"] = "ev_older"
    for key in (
        "eligibility_evidence_ids",
        "registration_evidence_ids",
        "competition_date_evidence_ids",
    ):
        older[key] = ["ev_older"]
    catalog = catalog_at(tmp_path, [record_values(), older])
    assert len(catalog.search("虚构")) == 2
    assert catalog.search("nonexistent") == []
    catalog.get("fictional_2026_school").name = "mutated"
    assert catalog.get("fictional_2026_school").name != "mutated"
    assert catalog.evidence(["ev_rules"])[0].applicable_year == 2026
    with pytest.raises(AppError) as missing:
        catalog.get("../secret")
    assert missing.value.code == "COMPETITION_NOT_FOUND"
    with pytest.raises(AppError):
        catalog.evidence(["unknown"])


def test_fixtures_only_loaded_explicitly():
    settings = Settings.from_sources({}, None)
    assert settings.catalog_path != EXAMPLES
    explicit = Settings.from_sources({"BJTU_CATALOG_PATH": str(EXAMPLES)}, None)
    catalog = CompetitionCatalog(explicit.catalog_path)
    records = catalog.search()
    assert len(records) == 3
    assert {assess_competition(item, NOW).registration_status for item in records} == {
        "open",
        "closed",
        "unknown",
    }
    assert all("虚构" in item.name for item in records)
    assert all(ev.url.host == "example.com" for item in records for ev in item.evidence)


def test_tool_rejects_unknown_names_and_extra_arguments(tmp_path):
    registry = ToolRegistry(catalog_at(tmp_path), clock=lambda: NOW)
    snapshot = SessionSnapshot(session_id="s_backend", stage="R1")
    for name, args in [
        ("supplement", {}),
        ("search_competitions", {"session_id": "s_forged"}),
        (
            "check_eligibility",
            {"instance_id": "fictional_2026_school", "profile": {"grade": "大二"}},
        ),
        ("search_competitions", {"query": 42}),
        ("evaluate_plan", {"plan": draft({}).model_dump(mode="json")}),
    ]:
        result = registry.execute(name, args, snapshot)
        assert isinstance(result, ToolResult)
        assert result.status == "error" and result.error is not None and result.data is None
    assert registry.definitions("R0") == []
    assert len(registry.definitions("R4")) == 5
    assert registry.definitions("invalid") == []
    assert not any("supplement" in str(tool) for tool in registry.definitions("R4"))


def test_tools_use_snapshot_profile_and_clock(tmp_path):
    registry = ToolRegistry(catalog_at(tmp_path), clock=lambda: NOW)
    snapshot = SessionSnapshot(session_id="s_backend", stage="R4", profile=Profile(grade="大一"))
    result = registry.execute(
        "check_eligibility", {"instance_id": "fictional_2026_school"}, snapshot
    )
    assert result.status == "ok" and result.data["status"] == "ineligible"
    result = registry.execute("get_competition", {"instance_id": "fictional_2026_school"}, snapshot)
    assert result.status == "ok" and result.data["registration_status"] == "open"
    assert "allowed_grades" not in result.data
    assert registry.execute("search_competitions", {}, snapshot).status == "ok"
    assert registry.execute("get_evidence", {"ids": ["ev_rules"]}, snapshot).status == "ok"
    result = registry.execute(
        "evaluate_plan", {"plan": draft({}).model_dump(mode="json")}, snapshot
    )
    assert result.status == "ok" and result.data["feasibility"] == "infeasible"
    missing = ToolRegistry(CompetitionCatalog(tmp_path / "missing.json"))
    result = missing.execute("search_competitions", {}, snapshot)
    assert result.status == "error" and result.error.code == "CATALOG_NOT_CONFIGURED"


async def test_catalog_is_lazy_and_clock_is_wired_to_api(tmp_path, monkeypatch):
    path = tmp_path / "missing.json"
    settings = Settings(data_dir=tmp_path / "sessions-root", catalog_path=path)

    def forbidden_read(*args, **kwargs):
        raise AssertionError("Catalog constructor must not read content")

    with monkeypatch.context() as context:
        context.setattr(Path, "read_text", forbidden_read)
        app = create_app(settings, clock=lambda: NOW)
        assert app.state.service.clock() == NOW
        assert app.state.service.catalog.path == path
    assert not settings.data_dir.exists()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/api/sessions", json={})
        assert created.status_code == 201
        session_id = created.json()["session_id"]
        assert (await client.get(f"/api/sessions/{session_id}")).status_code == 200
        assert (
            await client.patch(
                f"/api/sessions/{session_id}/profile",
                json={
                    "expected_revision": 0,
                    "changes": {"grade": "大二"},
                },
            )
        ).status_code == 200
        assert (await client.get("/api/competitions/fictional_2026_school")).status_code == 503
        path.write_text(json.dumps([record_values()]), encoding="utf-8")
        response = await client.get("/api/competitions/fictional_2026_school")
        assert response.status_code == 200
        assert response.json()["registration_status"] == "open"
        assert "allowed_grades" not in response.json()
        assert (await client.get("/api/competitions/nonexistent")).status_code == 404


def test_tool_nested_plan_does_not_coerce_model_hours(tmp_path):
    registry = ToolRegistry(catalog_at(tmp_path), clock=lambda: NOW)
    snapshot = SessionSnapshot(session_id="s_backend", stage="R4")
    plan = draft({}).model_dump(mode="json")
    plan["tasks"][0]["estimated_hours"] = "6"
    result = registry.execute("evaluate_plan", {"plan": plan}, snapshot)
    assert result.status == "error" and result.error.code == "VALIDATION_ERROR"


def test_unknown_estimate_marks_overlapping_week_unknown(tmp_path):
    plan = draft({}, {"estimated_hours": None})
    result = evaluate_plan(Profile(weekly_hours=10), plan, catalog_at(tmp_path), NOW)
    assert result.feasibility == "unknown"
    assert result.weekly_load[0].estimated_hours is None
    result = evaluate_plan(Profile(weekly_hours=5), plan, catalog_at(tmp_path), NOW)
    assert result.feasibility == "infeasible"


@pytest.mark.parametrize("mutation", ["selected", "task", "foreign_task"])
def test_invalid_plan_references_are_controlled_errors(tmp_path, mutation):
    plan = draft({})
    if mutation == "selected":
        plan.selected_competition_ids *= 2
    elif mutation == "task":
        plan.tasks *= 2
    else:
        plan.tasks[0].competition_instance_id = "not-selected"
    with pytest.raises(AppError) as error:
        evaluate_plan(Profile(), plan, catalog_at(tmp_path), NOW)
    assert (error.value.code, error.value.status_code) == ("VALIDATION_ERROR", 422)


def test_unknown_catalog_dates_and_reversed_tasks_never_feasible(tmp_path):
    catalog = catalog_at(tmp_path, [record_values(competition_date_evidence_ids=[])])
    result = evaluate_plan(Profile(weekly_hours=6), draft({}), catalog, NOW)
    assert result.feasibility == "unknown"
    plan = draft({"start_date": "2026-10-25", "due_date": "2026-10-19"})
    assert evaluate_plan(Profile(), plan, catalog, NOW).feasibility == "infeasible"


def test_default_service_clock_is_aware_utc(tmp_path):
    service = create_app(Settings(data_dir=tmp_path / "unused")).state.service
    now = service.clock()
    assert now.tzinfo is not None and now.utcoffset().total_seconds() == 0
    with pytest.raises(AppError) as error:
        assess_competition(instance(), datetime(2026, 10, 18))
    assert error.value.code == "CLOCK_INVALID"


def test_unexpected_tool_failure_is_sanitized(tmp_path):
    def bad_clock():
        raise RuntimeError("fake-secret-not-for-response")

    registry = ToolRegistry(catalog_at(tmp_path), clock=bad_clock)
    result = registry.execute(
        "search_competitions", {}, SessionSnapshot(session_id="s", stage="R1")
    )
    assert result.status == "error" and result.error.code == "TOOL_ERROR"
    assert "fake-secret" not in result.model_dump_json()


def test_optional_date_evidence_serialization_remains_backward_compatible():
    old = CompetitionRecord(competition_instance_id="old", name="虚构旧记录")
    assert "registration_evidence_ids" not in old.model_dump()
    assert "competition_date_evidence_ids" not in old.model_dump()
    complete = instance()
    restored = CompetitionRecord.model_validate(complete.model_dump())
    assert restored.registration_evidence_ids == ["ev_rules"]
    assert restored.competition_date_evidence_ids == ["ev_rules"]


@pytest.mark.parametrize(
    "scope",
    [
        "非校内选拔；不适用于本科组",
        "校内选拔赛 / 本科组",
        "校内选拔 / 本科组甲",
        "校内选拔 / 非本科组",
        "校内选拔 / 本科组",  # Unstructured prose is not an affirmative assertion.
        'applies-to/v1:{"stage":"非校内选拔","group":"本科组"}',
        'applies-to/v1:{"stage":"校内选拔赛","group":"本科组"}',
        'applies-to/v1:{"stage":"校内选拔","group":"本科组甲"}',
        'applies-to/v1:{"stage":"校内选拔","group":"非本科组"}',
        'applies-to/v1:{"stage":"校内选拔","group":"本科组","negated":true}',
        'applies-to/v1:{"stage":"校内选拔","group":"本科组","group":"本科组甲"}',
        '不适用 applies-to/v1:{"stage":"校内选拔","group":"本科组"}',
        'applies-to/v1:{"stage":"校内选拔","group":"本科组"} 不适用',
        'applies-to/v1:{"stage":"校内选拔","group":null}',  # No wildcard group.
        'applies-to/v1:{"stage":"校内选拔"}',
        'applies-to/v1:{"stage":"校内选拔","group":false}',
        'applies-to/v1:{"stage":"校内选拔","group":""}',
        'applies-to/v1:{"stage":"校内选拔","group":"本科组"',
        None,
    ],
)
def test_scope_negation_and_neighbor_names_cannot_establish_facts(scope):
    item = instance(group="本科组")
    item.evidence[0].scope = scope
    eligibility = check_eligibility(Profile(grade="大一", major="计算机"), item, NOW)
    assert eligibility.status == "unknown"
    assert eligibility.evidence_ids == []
    assessed = assess_competition(item, NOW)
    assert assessed.registration_status == "unknown"
    assert assessed.registration_start is None
    assert assessed.registration_deadline is None
    assert assessed.competition_date is None


@pytest.mark.parametrize("group", [None, "本科组"])
def test_scope_exact_affirmative_grammar_supports_facts(group):
    item = instance(group=group)
    item.evidence[0].scope = "applies-to/v1:" + json.dumps({"stage": "校内选拔", "group": group})
    eligibility = check_eligibility(Profile(grade="大一", major="计算机"), item, NOW)
    assert eligibility.status == "ineligible" and eligibility.evidence_ids == ["ev_rules"]
    assessed = assess_competition(item, NOW)
    assert assessed.registration_status == "open"
    assert assessed.competition_date == date(2026, 11, 15)


def assert_tool_envelope(result, status):
    payload = result.model_dump(mode="json")
    assert set(payload) == {"status", "data", "evidence_ids", "warnings", "error"}
    assert payload["status"] == status
    assert isinstance(payload["evidence_ids"], list)
    assert isinstance(payload["warnings"], list)
    if status == "error":
        assert payload["data"] is None and payload["evidence_ids"] == []
        assert payload["error"]["code"] and payload["error"]["message"]
    else:
        assert payload["data"] is not None and payload["error"] is None
        if status == "partial":
            assert payload["warnings"]
    return payload


@pytest.mark.parametrize("name", ["get_competition", "get_evidence", "check_eligibility"])
def test_tool_envelope_complete_success(tmp_path, name):
    registry = ToolRegistry(catalog_at(tmp_path), clock=lambda: NOW)
    snapshot = SessionSnapshot(
        session_id="s_backend",
        stage="R4",
        profile=Profile(grade="大二", major="计算机"),
    )
    args = (
        {"ids": ["ev_rules"]}
        if name == "get_evidence"
        else {"instance_id": "fictional_2026_school"}
    )
    payload = assert_tool_envelope(registry.execute(name, args, snapshot), "ok")
    assert payload["evidence_ids"] == ["ev_rules"]
    assert payload["warnings"] == []


@pytest.mark.parametrize(
    "name", ["search_competitions", "get_competition", "check_eligibility", "evaluate_plan"]
)
def test_tool_envelope_partial_unknowns(tmp_path, name):
    catalog = catalog_at(tmp_path, [record_values(competition_date_evidence_ids=[])])
    registry = ToolRegistry(catalog, clock=lambda: NOW)
    snapshot = SessionSnapshot(session_id="s_backend", stage="R4")
    if name == "evaluate_plan":
        args = {"plan": draft({}).model_dump(mode="json")}
    elif name == "search_competitions":
        args = {}
    else:
        args = {"instance_id": "fictional_2026_school"}
    payload = assert_tool_envelope(registry.execute(name, args, snapshot), "partial")
    assert payload["evidence_ids"] == ["ev_rules"]


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        ("arguments", "VALIDATION_ERROR"),
        ("missing", "CATALOG_NOT_CONFIGURED"),
        ("corrupt", "CATALOG_INVALID"),
        ("name", "TOOL_NOT_ALLOWED"),
    ],
)
def test_tool_envelope_controlled_errors(tmp_path, failure, code):
    path = tmp_path / "catalog.json"
    if failure == "corrupt":
        path.write_text("fake-secret-corrupt", encoding="utf-8")
    registry = ToolRegistry(CompetitionCatalog(path), clock=lambda: NOW)
    name = "supplement" if failure == "name" else "search_competitions"
    args = {"profile": "fake-secret-profile"} if failure == "arguments" else {}
    result = registry.execute(name, args, SessionSnapshot(session_id="s_backend", stage="R1"))
    payload = assert_tool_envelope(result, "error")
    assert payload["error"]["code"] == code
    assert "fake-secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    ("hours", "feasibility"), [(0.5, "feasible"), (0.500000000000001, "infeasible")]
)
def test_fractional_nine_week_budget_boundary(tmp_path, hours, feasibility):
    catalog = catalog_at(tmp_path, [record_values(competition_date="2026-12-31")])
    plan = draft(
        *[
            {"estimated_hours": hours, "start_date": "2026-10-19", "due_date": "2026-12-20"}
            for _ in range(18)
        ]
    )
    result = evaluate_plan(Profile(weekly_hours=1), plan, catalog, NOW)
    assert result.feasibility == feasibility
    assert len(result.weekly_load) == 9
    assert all(week.budget_hours == 1 for week in result.weekly_load)
    if feasibility == "feasible":
        assert all(week.estimated_hours == 1 for week in result.weekly_load)
        assert result.conflicts == []
    else:
        assert all(week.estimated_hours > 1 for week in result.weekly_load)
        assert len(result.conflicts) == 9
