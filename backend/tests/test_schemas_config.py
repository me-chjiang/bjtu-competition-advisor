"""AI-assisted tests derived from the frontend contract and Task 1 brief."""

from datetime import date
from pathlib import Path

import pytest

from backend.schemas import (
    AgentDraft,
    AnalysisDraft,
    AppError,
    CandidateCard,
    CandidatePatchRequest,
    CandidateReason,
    ChatRequest,
    CompetitionDetail,
    CompetitionRecord,
    ConfirmRequest,
    CreateSessionRequest,
    Dimension,
    ErrorDetail,
    ErrorResponse,
    Evidence,
    Message,
    Plan,
    PlanDraft,
    PlanTask,
    Profile,
    ProfileChanges,
    ProfilePatchRequest,
    SessionRecord,
    SessionSnapshot,
    Skill,
    SuccessfulRequest,
    WeeklyLoad,
)


def test_profile_defaults_and_patch():
    assert Profile().weekly_hours is None
    assert Profile().additional_context is None
    assert ProfileChanges().model_dump(exclude_unset=True) == {}
    assert ProfileChanges(weekly_hours=None).model_dump(exclude_unset=True) == {
        "weekly_hours": None
    }
    original = Profile(major="示例专业", weekly_hours=6, goals=["兴趣", "实践"])
    changes = ProfileChanges(weekly_hours=None, goals=["项目"])
    merged = Profile.model_validate(
        original.model_dump() | changes.model_dump(exclude_unset=True)
    )
    assert merged.major == "示例专业"
    assert merged.weekly_hours is None
    assert merged.goals == ["项目"]
    assert original.goals == ["兴趣", "实践"]


@pytest.mark.parametrize("model", [Profile, ProfileChanges])
@pytest.mark.parametrize("value", [None, "", "  \n\t", "x" * 2000])
def test_additional_context_normalization(model, value):
    result = model(additional_context=value)
    assert result.additional_context == (value if value and value.strip() else None)


@pytest.mark.parametrize("model", [Profile, ProfileChanges])
def test_additional_context_limit(model):
    with pytest.raises(ValueError):
        model(additional_context="x" * 2001)


@pytest.mark.parametrize("model", [Profile, ProfileChanges])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), -float("inf"), True, False])
def test_weekly_hours_rejects_invalid_numbers(model, value):
    with pytest.raises(ValueError):
        model(weekly_hours=value)


@pytest.mark.parametrize("value", [0.25, 6, 12.5])
def test_weekly_hours_accepts_positive_finite_values(value):
    assert Profile(weekly_hours=value).weekly_hours == value


@pytest.mark.parametrize("model", [Profile, ProfileChanges])
@pytest.mark.parametrize("field", ["skills", "goals", "unavailable_dates"])
def test_profile_arrays_cannot_be_null(model, field):
    with pytest.raises(ValueError):
        model(**{field: None})


def test_profile_date_and_skill_json_shape():
    profile = Profile(
        skills=[{"name": "Python", "evidence": "虚构课程项目"}],
        unavailable_dates=["2026-10-20"],
    )
    assert profile.unavailable_dates == [date(2026, 10, 20)]
    assert profile.model_dump(mode="json")["skills"] == [
        {"name": "Python", "evidence": "虚构课程项目"}
    ]
    assert Profile().skills == []


@pytest.mark.parametrize("content", [None, "", " \t", "x" * 4001])
def test_chat_message_requires_nonblank_limited_content(content):
    with pytest.raises(ValueError):
        ChatRequest(request_id="req_demo", expected_revision=0, action="message", content=content)


def test_chat_generate_and_message_contract():
    generated = ChatRequest(
        request_id="req_demo", expected_revision=0, action="generate", content=None
    )
    assert generated.content is None
    message = ChatRequest(
        request_id="req_demo", expected_revision=1, action="message", content="x" * 4000
    )
    assert len(message.content) == 4000
    with pytest.raises(ValueError):
        ChatRequest(
            request_id="req_demo", expected_revision=0, action="generate", content="生成"
        )


@pytest.mark.parametrize("revision", [-1, True, 1.5, "1"])
def test_mutation_revision_is_a_nonnegative_integer(revision):
    with pytest.raises(ValueError):
        ConfirmRequest(expected_revision=revision, stage="R0")


def test_request_contract_enums_and_fields():
    assert CreateSessionRequest().model_dump() == {}
    assert ProfilePatchRequest(expected_revision=0, changes={}).changes.model_fields_set == set()
    assert CandidatePatchRequest(expected_revision=0, decision="keep").decision == "keep"
    for body in ({"expected_revision": 0, "stage": "R3"},):
        with pytest.raises(ValueError):
            ConfirmRequest(**body)


def test_snapshot_public_shape_and_private_record_round_trip():
    snapshot = SessionSnapshot(session_id="s_demo", message="请介绍你的目标。")
    assert snapshot.model_dump(mode="json") == {
        "session_id": "s_demo", "revision": 0, "stage": "R0", "status": "collecting",
        "processing": False, "last_request_id": None, "message": "请介绍你的目标。",
        "messages": [], "profile": Profile().model_dump(mode="json"), "cards": [],
        "plan": None, "needs_confirmation": False,
    }
    request = ChatRequest(
        request_id="req_demo", expected_revision=0, action="generate", content=None
    )
    record = SessionRecord(
        snapshot=snapshot, confirmed_profile=Profile(major="示例专业"),
        coarse_cards=[], successful_requests={
            "req_demo": SuccessfulRequest(request=request, snapshot=snapshot)
        },
    )
    restored = SessionRecord.model_validate_json(record.model_dump_json())
    assert restored.confirmed_profile.major == "示例专业"
    assert restored.successful_requests["req_demo"].request == request
    assert "confirmed_profile" not in snapshot.model_dump()
    with pytest.raises(ValueError):
        SessionRecord(snapshot=snapshot.model_copy(update={"processing": True}))


def test_snapshot_confirmation_flag_matches_status():
    with pytest.raises(ValueError):
        SessionSnapshot(session_id="s_demo", status="collecting", needs_confirmation=True)
    with pytest.raises(ValueError):
        SessionSnapshot(session_id="s_demo", status="awaiting_review", needs_confirmation=False)


def test_evidence_dates_and_public_competition_fields():
    evidence = Evidence(
        id="ev_demo", url="https://example.com/notice", excerpt="虚构往届通知。",
        fetched_at="2026-10-15T12:00:00+08:00", applicable_year=2025, scope="往届校赛",
    )
    competition = CompetitionRecord(
        competition_instance_id="ci_demo", name="虚构竞赛", year=2026,
        allowed_grades=["大二"], allowed_majors=None, eligibility_evidence_ids=["ev_demo"],
        evidence=[evidence],
    )
    public = CompetitionDetail.model_validate(
        competition.model_dump(
            exclude={"allowed_grades", "allowed_majors", "eligibility_evidence_ids"}
        )
    )
    assert public.registration_deadline is None
    assert public.registration_status == "unknown"
    assert public.evidence[0].applicable_year == 2025
    assert "allowed_grades" not in public.model_dump()


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///private", "https://user:secret@example.com/"])
def test_evidence_rejects_unsafe_source_links(url):
    with pytest.raises(ValueError):
        Evidence(id="ev_demo", url=url, excerpt="虚构", fetched_at="2026-10-15T12:00:00Z")


def test_timestamp_requires_timezone():
    with pytest.raises(ValueError):
        Message(id="m_demo", role="assistant", content="示例", created_at="2026-10-15T12:00:00")


def test_internal_draft_cannot_set_server_rules_or_authority():
    draft = AgentDraft(kind="profile", message="请核对", profile_changes={"weekly_hours": None})
    assert draft.candidates == []
    assert draft.analyses == []
    assert draft.plan is None
    assert draft.profile_changes.model_fields_set == {"weekly_hours"}
    for field, value in {
        "revision": 7, "session_id": "s_fake", "permissions": ["admin"],
        "confirm": True, "needs_confirmation": True, "stage": "R4",
    }.items():
        with pytest.raises(ValueError):
            AgentDraft(kind="question", message="示例", **{field: value})
    for field, value in {"weekly_load": [], "conflicts": [], "feasibility": "feasible"}.items():
        with pytest.raises(ValueError):
            PlanDraft(**{field: value})


def test_plan_unknowns_and_positive_hours():
    task = PlanTask(
        id="t_demo", competition_instance_id="ci_demo", title="虚构任务",
        acceptance_criteria="完成示例",
    )
    plan = Plan(selected_competition_ids=["ci_demo"], tasks=[task])
    assert plan.feasibility == "unknown"
    assert plan.tasks[0].estimated_hours is None
    assert plan.tasks[0].due_date is None
    assert WeeklyLoad(week_start="2026-10-19", estimated_hours=3).budget_hours is None
    with pytest.raises(ValueError):
        WeeklyLoad(week_start="2026-10-20", estimated_hours=3)
    for value in [0, -1, True, float("inf"), float("nan")]:
        with pytest.raises(ValueError):
            PlanTask(**{**task.model_dump(), "estimated_hours": value})


@pytest.mark.parametrize("model,kwargs", [
    (CreateSessionRequest, {}), (Profile, {}), (ProfileChanges, {}),
    (Skill, {"name": "Python", "evidence": None}),
    (ChatRequest, {
        "request_id": "r", "expected_revision": 0, "action": "generate", "content": None,
    }),
    (ProfilePatchRequest, {"expected_revision": 0, "changes": {}}),
    (CandidatePatchRequest, {"expected_revision": 0, "decision": "defer"}),
    (ConfirmRequest, {"expected_revision": 0, "stage": "R0"}),
    (SessionSnapshot, {"session_id": "s_demo"}),
    (CandidateCard, {"competition_instance_id": "ci_demo", "name": "虚构竞赛", "reason": "示例"}),
    (Dimension, {"name": "ability_gap", "assessment": "未知", "basis": "unknown"}),
    (CandidateReason, {"competition_instance_id": "ci_demo", "reason": "示例"}),
    (AnalysisDraft, {"competition_instance_id": "ci_demo", "dimensions": []}),
    (PlanDraft, {}), (Plan, {}),
    (AgentDraft, {"kind": "question", "message": "示例"}),
    (CompetitionDetail, {"competition_instance_id": "ci_demo", "name": "示例"}),
    (ErrorDetail, {"code": "INTERNAL_ERROR", "message": "操作失败"}),
    (ErrorResponse, {"error": {"code": "INTERNAL_ERROR", "message": "操作失败"}}),
])
def test_dtos_forbid_extra_fields(model, kwargs):
    with pytest.raises(ValueError):
        model(**kwargs, unexpected="must not pass")


def test_controlled_error_contract():
    error = AppError("REVISION_CONFLICT", "请刷新", 409, details={"current_revision": 4})
    assert error.code == "REVISION_CONFLICT"
    assert error.status_code == 409
    response = ErrorResponse(
        error=ErrorDetail(
            code=error.code, message=error.message,
            retryable=error.retryable, details=error.details,
        ),
        request_id="req_demo",
    )
    assert response.model_dump()["error"]["details"] == {"current_revision": 4}


def test_env_overrides_yaml(tmp_path):
    from backend.config import Settings

    config = tmp_path / "fictional.yaml"
    config.write_text(
        'deepseek-api-key: "fictional-yaml-key"\nllm-model: "deepseek/yaml-demo"\n',
        encoding="utf-8",
    )
    settings = Settings.from_sources({
        "DEEPSEEK_API_KEY": "fictional-env-key", "LLM_MODEL": "deepseek/env-demo",
        "LLM_TIMEOUT_SECONDS": "12.5", "LLM_MAX_OUTPUT_TOKENS": "1024",
        "BJTU_DATA_DIR": str(tmp_path / "data"),
        "BJTU_CATALOG_PATH": str(tmp_path / "catalog.json"),
        "BJTU_ALLOWED_ORIGINS": "http://localhost:5173, http://127.0.0.1:5173",
    }, config)
    assert settings.deepseek_api_key.get_secret_value() == "fictional-env-key"
    assert settings.llm_model == "deepseek/env-demo"
    assert settings.llm_timeout_seconds == 12.5
    assert settings.llm_max_output_tokens == 1024
    assert settings.data_dir == tmp_path / "data"
    assert settings.catalog_path == tmp_path / "catalog.json"
    assert settings.allowed_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]
    fallback = Settings.from_sources({}, config)
    assert fallback.deepseek_api_key.get_secret_value() == "fictional-yaml-key"
    assert fallback.llm_model == "deepseek/yaml-demo"
    assert Settings.from_sources({"DEEPSEEK_API_KEY": ""}, config).deepseek_api_key is None


def test_settings_defaults_are_repo_relative_not_cwd(tmp_path, monkeypatch):
    from backend.config import Settings

    monkeypatch.chdir(tmp_path)
    root = Path(__file__).resolve().parents[2]
    settings = Settings.from_sources({}, None)
    assert settings.deepseek_api_key is None
    assert settings.llm_model == "deepseek/deepseek-chat"
    assert settings.data_dir == root / "data"
    assert settings.catalog_path == root / "data/competitions.json"
    assert settings.allowed_origins == []
    relative = Settings.from_sources({
        "BJTU_DATA_DIR": "example-data", "BJTU_CATALOG_PATH": "example-catalog.json",
    }, None)
    assert relative.data_dir == root / "example-data"
    assert relative.catalog_path == root / "example-catalog.json"


def test_secret_repr_is_redacted(tmp_path):
    from backend.config import Settings

    settings = Settings.from_sources({"DEEPSEEK_API_KEY": "fictional-never-log-key"}, None)
    assert "fictional-never-log-key" not in repr(settings)
    assert "fictional-never-log-key" not in str(settings)
    assert "fictional-never-log-key" not in settings.model_dump_json()


@pytest.mark.parametrize("name,value", [
    ("LLM_TIMEOUT_SECONDS", "0"), ("LLM_TIMEOUT_SECONDS", "-1"),
    ("LLM_TIMEOUT_SECONDS", "nan"), ("LLM_TIMEOUT_SECONDS", "inf"),
    ("LLM_MAX_OUTPUT_TOKENS", "0"), ("LLM_MAX_OUTPUT_TOKENS", "-1"),
    ("LLM_MAX_OUTPUT_TOKENS", "1.5"), ("LLM_MAX_OUTPUT_TOKENS", "true"),
    ("LLM_TIMEOUT_SECONDS", "fictional-secret-in-invalid-limit"),
])
def test_invalid_limits_fail_safely(name, value):
    from backend.config import Settings

    with pytest.raises(AppError) as caught:
        Settings.from_sources({name: value, "DEEPSEEK_API_KEY": "fictional-private-key"}, None)
    assert caught.value.code == "CONFIG_INVALID"
    assert "fictional" not in str(caught.value)
    assert "fictional" not in repr(caught.value)


@pytest.mark.parametrize("content", [
    "[fictional-private-key", "- fictional-private-key",
    "deepseek-api-key: [fictional-private-key]",
])
def test_invalid_yaml_fails_safely(tmp_path, content):
    from backend.config import Settings

    config = tmp_path / "fictional.yaml"
    config.write_text(content, encoding="utf-8")
    with pytest.raises(AppError) as caught:
        Settings.from_sources({}, config)
    assert caught.value.code == "CONFIG_INVALID"
    assert "fictional-private-key" not in str(caught.value)


def test_explicit_missing_config_fails_safely(tmp_path):
    from backend.config import Settings

    with pytest.raises(AppError) as caught:
        Settings.from_sources({}, tmp_path / "missing.yaml")
    assert caught.value.code == "CONFIG_INVALID"


@pytest.mark.parametrize("origin", [
    "*", "https://example.com/path", "https://user:password@example.com", "file:///tmp",
])
def test_origins_must_be_explicit_http_origins(origin):
    from backend.config import Settings

    with pytest.raises(AppError):
        Settings.from_sources({"BJTU_ALLOWED_ORIGINS": origin}, None)


@pytest.mark.parametrize("field,value", [
    ("request_timeout_seconds", 121), ("max_model_calls", 6),
    ("max_tool_calls", 9), ("llm_max_output_tokens", 4097),
])
def test_settings_cannot_raise_hard_request_budgets(field, value):
    from backend.config import Settings

    with pytest.raises(ValueError):
        Settings(**{field: value})


def test_patch_explicit_context_null_and_array_replacement():
    original = Profile(additional_context="虚构经历", skills=[Skill(name="Python")])
    empty = ProfileChanges()
    assert Profile.model_validate(
        original.model_dump() | empty.model_dump(exclude_unset=True)
    ).additional_context == "虚构经历"
    patch = ProfileChanges(additional_context=None, skills=[])
    updated = Profile.model_validate(
        original.model_dump() | patch.model_dump(exclude_unset=True)
    )
    assert updated.additional_context is None
    assert updated.skills == []


def test_settings_yaml_ignores_unrelated_private_keys(tmp_path):
    from backend.config import Settings

    config = tmp_path / "fictional.yaml"
    config.write_text(
        'api-key: "fictional-lexmount-key"\nbjtu-password: "fictional-password"\n',
        encoding="utf-8",
    )
    settings = Settings.from_sources({}, config)
    assert "fictional" not in repr(settings)
    assert "fictional" not in settings.model_dump_json()


def test_config_validation_exception_does_not_echo_source(tmp_path):
    import traceback

    from backend.config import Settings

    config = tmp_path / "fictional.yaml"
    config.write_text('deepseek-api-key: "fictional-yaml-key"\n[broken', encoding="utf-8")
    with pytest.raises(AppError) as caught:
        Settings.from_sources({}, config)
    displayed = "".join(traceback.format_exception(caught.value))
    assert "fictional-yaml-key" not in displayed
    assert caught.value.__suppress_context__ is True
