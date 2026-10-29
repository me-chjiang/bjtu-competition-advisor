"""Strict local read-only tool whitelist, AI-assisted from the Task 3 brief."""

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, ValidationError, model_validator

from backend.catalog import (
    CompetitionCatalog,
    assess_competition,
    check_eligibility,
    evaluate_plan,
    utc_now,
)
from backend.schemas import (
    DTO,
    AppError,
    CompetitionDetail,
    ErrorDetail,
    PlanDraft,
    SessionSnapshot,
)


class ToolResult(DTO):
    status: Literal["ok", "partial", "error"]
    data: dict[str, Any] | list[Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: ErrorDetail | None = None

    @model_validator(mode="after")
    def consistent_result(self) -> "ToolResult":
        if self.status == "error":
            valid = self.error is not None and self.data is None and not self.evidence_ids
        else:
            valid = self.error is None and self.data is not None
        if not valid or (self.status == "partial" and not self.warnings):
            raise ValueError("Tool results must contain data or a controlled error.")
        return self


class _Arguments(DTO):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class _Search(_Arguments):
    query: str | None = Field(default=None, max_length=1000)


class _Instance(_Arguments):
    instance_id: str = Field(min_length=1, max_length=300)


class _Evidence(_Arguments):
    ids: list[str] = Field(max_length=100)


class _Plan(_Arguments):
    plan: PlanDraft


_TOOLS = {
    "search_competitions": (_Search, "Search local competition instances."),
    "get_competition": (_Instance, "Read one instance with supported dates and evidence."),
    "get_evidence": (_Evidence, "Read local evidence by IDs."),
    "check_eligibility": (_Instance, "Check eligibility using the backend session profile."),
    "evaluate_plan": (_Plan, "Check a draft schedule using the backend profile and clock."),
}
_STAGES = {
    "R0": (),
    "R1": tuple(name for name in _TOOLS if name != "evaluate_plan"),
    "R2": tuple(name for name in _TOOLS if name != "evaluate_plan"),
    "R4": tuple(_TOOLS),
}


class ToolRegistry:
    def __init__(
        self,
        catalog: CompetitionCatalog,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.catalog = catalog
        self.clock = clock if clock is not None else utc_now

    def definitions(self, stage: str) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": _TOOLS[name][1],
                    "parameters": _TOOLS[name][0].model_json_schema(),
                },
            }
            for name in _STAGES.get(stage, ())
        ]

    def execute(self, name: str, arguments: dict, snapshot: SessionSnapshot) -> ToolResult:
        try:
            if name not in _STAGES.get(snapshot.stage, ()):
                raise AppError("TOOL_NOT_ALLOWED", "本阶段不允许调用该工具。", 422)
            if not isinstance(arguments, dict):
                raise AppError("VALIDATION_ERROR", "工具参数必须是对象。", 422)
            # Nested date strings are normal JSON, not Python date objects. Re-encode
            # through the strict JSON validator; strings never coerce to hours/IDs.
            args = _TOOLS[name][0].model_validate_json(json.dumps(arguments), strict=True)
            now = self.clock()
            warnings: list[str] = []
            evidence_ids: list[str] = []
            if name == "search_competitions":
                data = [self._detail(item, now) for item in self.catalog.search(args.query)]
                for detail in data:
                    evidence_ids.extend(item["id"] for item in detail["evidence"])
                    warnings.extend(self._date_warnings(detail))
            elif name == "get_competition":
                data = self._detail(self.catalog.get(args.instance_id), now)
                evidence_ids = [item["id"] for item in data["evidence"]]
                warnings = self._date_warnings(data)
            elif name == "get_evidence":
                data = [item.model_dump(mode="json") for item in self.catalog.evidence(args.ids)]
                evidence_ids = [item["id"] for item in data]
            elif name == "check_eligibility":
                checked = check_eligibility(
                    snapshot.profile,
                    self.catalog.get(args.instance_id),
                    now,
                )
                data = checked.model_dump(mode="json")
                evidence_ids = checked.evidence_ids
                if checked.status == "unknown":
                    warnings = checked.reasons
            else:
                checked_plan = evaluate_plan(
                    snapshot.profile,
                    args.plan,
                    self.catalog,
                    now,
                )
                data = checked_plan.model_dump(mode="json")
                evidence_ids = [
                    item.id
                    for instance_id in checked_plan.selected_competition_ids
                    for item in self.catalog.get(instance_id).evidence
                ]
                if checked_plan.feasibility == "unknown":
                    warnings = checked_plan.conflicts
            return ToolResult(
                status="partial" if warnings else "ok",
                data=data,
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                warnings=list(dict.fromkeys(warnings)),
            )
        except AppError as error:
            return ToolResult(
                status="error",
                error=ErrorDetail(
                    code=error.code,
                    message=error.message,
                    retryable=error.retryable,
                ),
            )
        except (ValidationError, ValueError, TypeError):
            return ToolResult(
                status="error",
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="工具参数无效。",
                ),
            )
        except Exception:
            # No exception content, model arguments, profile or raw catalog in errors/logs.
            return ToolResult(
                status="error",
                error=ErrorDetail(
                    code="TOOL_ERROR",
                    message="本地工具暂不可用。",
                ),
            )

    @staticmethod
    def _date_warnings(detail: dict) -> list[str]:
        return [
            f"{detail['competition_instance_id']}：{label}尚未核实。"
            for field, label in (
                ("registration_start", "本届报名开始日期"),
                ("registration_deadline", "本届报名截止日期"),
                ("competition_date", "本届比赛日期"),
            )
            if detail[field] is None
        ]

    @staticmethod
    def _detail(instance, now: datetime) -> dict:
        assessed = assess_competition(instance, now)
        return CompetitionDetail.model_validate(
            {
                key: value
                for key, value in assessed.model_dump().items()
                if key in CompetitionDetail.model_fields
            }
        ).model_dump(mode="json")
