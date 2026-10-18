"""Lazy local catalog and deterministic rules (AI-assisted from the frontend contract).

Catalog records are source facts, not time-sensitive recommendations. Consumers
must call assess_competition/check_eligibility with their backend-owned clock.
Dates are Beijing calendar days; evidence must match the instance year/scope.
"""

import json
import math
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, TypeAdapter, ValidationError

from backend.schemas import (
    DTO,
    AppError,
    CompetitionRecord,
    Eligibility,
    Evidence,
    Plan,
    PlanDraft,
    Profile,
    WeeklyLoad,
)

# The plan's conceptual CompetitionInstance is the existing, reviewed model.
CompetitionInstance = CompetitionRecord
BEIJING = ZoneInfo("Asia/Shanghai")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise AppError("CLOCK_INVALID", "后端时钟必须包含时区。", 500)
    return now


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


class CompetitionCatalog:
    """Construction does no content I/O; the first successful query loads once.

    Failures are not cached, so a missing/broken catalog may be repaired without
    restarting. Returned records/evidence are independent copies. No path comes
    from a model or a competition ID; only the trusted configured path is read.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._records: dict[str, CompetitionRecord] | None = None
        self._evidence: dict[str, Evidence] = {}

    def _load(self) -> dict[str, CompetitionRecord]:
        if self._records is not None:
            return self._records
        try:
            payload = json.loads(
                self.path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object,
            )
            records = TypeAdapter(list[CompetitionRecord]).validate_python(payload)
            by_id: dict[str, CompetitionRecord] = {}
            evidence: dict[str, Evidence] = {}
            for record in records:
                if record.competition_instance_id in by_id or not record.name.strip():
                    raise ValueError("Duplicate/invalid instance")
                local_ids = set()
                for item in record.evidence:
                    if item.id in evidence or not item.id.strip() or not item.excerpt.strip():
                        raise ValueError("Duplicate/invalid evidence")
                    evidence[item.id] = item
                    local_ids.add(item.id)
                for refs in (
                    record.eligibility_evidence_ids,
                    record.registration_evidence_ids,
                    record.competition_date_evidence_ids,
                ):
                    if len(set(refs)) != len(refs) or not set(refs) <= local_ids:
                        raise ValueError("Invalid instance evidence reference")
                if (
                    record.registration_start is not None
                    and record.registration_deadline is not None
                    and record.registration_start > record.registration_deadline
                ):
                    raise ValueError("Reversed registration dates")
                by_id[record.competition_instance_id] = record
        except FileNotFoundError:
            raise AppError("CATALOG_NOT_CONFIGURED", "竞赛资料尚未配置。", 503) from None
        except (OSError, UnicodeError, ValueError, TypeError, ValidationError):
            raise AppError("CATALOG_INVALID", "竞赛资料无效，请检查目录文件。", 503) from None
        self._records = by_id
        self._evidence = evidence
        return by_id

    def search(self, query: str | None = None) -> list[CompetitionInstance]:
        needle = (query or "").strip().casefold()
        return [
            record.model_copy(deep=True)
            for record in self._load().values()
            if not needle
            or needle
            in " ".join(
                str(value or "")
                for value in (
                    record.name,
                    record.series_id,
                    record.year,
                    record.group,
                    record.stage,
                )
            ).casefold()
        ]

    def get(self, instance_id: str) -> CompetitionInstance:
        record = self._load().get(instance_id)
        if record is None:
            raise AppError("COMPETITION_NOT_FOUND", "竞赛实例不存在。", 404)
        return record.model_copy(deep=True)

    def evidence(self, ids: list[str]) -> list[Evidence]:
        self._load()
        if any(evidence_id not in self._evidence for evidence_id in ids):
            raise AppError("EVIDENCE_NOT_FOUND", "引用的竞赛证据不存在。", 404)
        return [self._evidence[evidence_id].model_copy(deep=True) for evidence_id in ids]


def _scope_matches(instance: CompetitionInstance, scope: str | None) -> bool:
    """Accept only applies-to/v1:{"stage": <exact string>, "group": <string|null>}.

    Both keys are required, extra/duplicate keys and surrounding prose are not
    assertions. Null group matches only an instance with no declared group; it
    is not a wildcard. Free text remains readable but never establishes facts.
    """
    prefix = "applies-to/v1:"
    if not scope or not scope.startswith(prefix) or not instance.stage:
        return False
    try:
        declared = json.loads(scope[len(prefix) :], object_pairs_hook=_unique_object)
    except (ValueError, TypeError):
        return False
    return (
        isinstance(declared, dict)
        and set(declared) == {"stage", "group"}
        and isinstance(declared["stage"], str)
        and bool(declared["stage"].strip())
        and (
            declared["group"] is None
            or (isinstance(declared["group"], str) and bool(declared["group"].strip()))
        )
        and declared["stage"] == instance.stage
        and declared["group"] == instance.group
    )


def _applicable(instance: CompetitionInstance, ids: list[str], now: datetime) -> list[str]:
    """Require the same year, affirmative exact scope and already fetched evidence."""
    evidence = {item.id: item for item in instance.evidence}
    return [
        evidence_id
        for evidence_id in ids
        if (
            (item := evidence.get(evidence_id)) is not None
            and instance.year is not None
            and item.applicable_year == instance.year
            and item.fetched_at <= now
            and item.excerpt.strip()
            and _scope_matches(instance, item.scope)
        )
    ]


def assess_competition(instance: CompetitionInstance, now: datetime) -> CompetitionInstance:
    """Return a copy with only supported dates and freshly computed registration status."""
    today = _aware(now).astimezone(BEIJING).date()
    values = instance.model_dump()
    registration_supported = bool(_applicable(instance, instance.registration_evidence_ids, now))
    competition_supported = bool(_applicable(instance, instance.competition_date_evidence_ids, now))
    # Never upgrade old dates into the instance year, even with a new notice nearby.
    for field in ("registration_start", "registration_deadline", "competition_date"):
        supported = competition_supported if field == "competition_date" else registration_supported
        value = values[field]
        if not supported or (value is not None and value.year != instance.year):
            values[field] = None
    start, deadline = values["registration_start"], values["registration_deadline"]
    status = "unknown"
    if deadline is not None and today > deadline:
        status = "closed"
    elif start is not None and today < start:
        status = "upcoming"
    elif start is not None and deadline is not None and start <= today <= deadline:
        status = "open"
    values["registration_status"] = status
    return CompetitionRecord.model_validate(values)


class EligibilityCheck(DTO):
    status: Eligibility
    reasons: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


def check_eligibility(
    profile: Profile,
    instance: CompetitionInstance,
    now: datetime,
) -> EligibilityCheck:
    assessed = assess_competition(instance, now)
    refs = _applicable(instance, instance.eligibility_evidence_ids, now)
    conflicts, unknowns = [], []
    if assessed.registration_status == "closed":
        conflicts.append("本届报名已经截止，不能保留为推荐项。")
    if not refs:
        unknowns.append("缺少适用于本届、本阶段的资格证据。")
    else:
        for label, value, allowed in (
            ("年级", profile.grade, instance.allowed_grades),
            ("专业", profile.major, instance.allowed_majors),
        ):
            if allowed is None or value is None or not value.strip():
                unknowns.append(f"{label}资格尚未核实。")
            elif value not in allowed:
                conflicts.append(f"{label}与本届明确规则冲突。")
    return EligibilityCheck(
        status="ineligible" if conflicts else "unknown" if unknowns else "eligible",
        reasons=conflicts + unknowns,
        evidence_ids=list(
            dict.fromkeys(
                refs
                + (
                    _applicable(instance, instance.registration_evidence_ids, now)
                    if assessed.registration_status == "closed"
                    else []
                ),
            )
        ),
    )


def evaluate_plan(
    profile: Profile,
    plan: PlanDraft,
    catalog: CompetitionCatalog,
    now: datetime,
) -> Plan:
    """Spread each task uniformly over available days, then aggregate Monday weeks.

    Qualification unknowns do not exclude a competition. Feasibility here is the
    time check: supported registration/race dates, task estimates, and budget.
    Known conflicts dominate unknowns; neither can produce a feasible result.
    """
    _aware(now)
    selected = plan.selected_competition_ids
    if len(set(selected)) != len(selected) or len({t.id for t in plan.tasks}) != len(plan.tasks):
        raise AppError("VALIDATION_ERROR", "方案包含重复的竞赛或任务 ID。", 422)
    if any(task.competition_instance_id not in selected for task in plan.tasks):
        raise AppError("VALIDATION_ERROR", "任务必须引用已选择的竞赛。", 422)
    instances = {instance_id: catalog.get(instance_id) for instance_id in selected}
    assessed = {key: assess_competition(item, now) for key, item in instances.items()}
    conflicts: list[str] = []
    unknowns: list[str] = []
    if not selected or not plan.tasks:
        unknowns.append("尚未提供完整的竞赛和任务。")
    if profile.weekly_hours is None:
        unknowns.append("每周时间预算未知，不能验证可行性。")
    for key, item in instances.items():
        eligibility = check_eligibility(profile, item, now)
        if eligibility.status == "ineligible":
            conflicts.extend(f"{key}：{reason}" for reason in eligibility.reasons)
        if assessed[key].registration_status == "unknown" or assessed[key].competition_date is None:
            unknowns.append(f"{key}：本届报名或比赛日期尚未核实。")
        if not any(task.competition_instance_id == key for task in plan.tasks):
            unknowns.append(f"{key}：缺少备赛任务。")

    totals: dict[date, Fraction] = {}
    uncertain_weeks: set[date] = set()
    unavailable = set(profile.unavailable_dates)
    for task in plan.tasks:
        start, end = task.start_date, task.due_date
        race_date = assessed[task.competition_instance_id].competition_date
        if race_date is not None and end is not None and end > race_date:
            conflicts.append(f"{task.id}：任务结束晚于明确比赛日。")
        if start is None or end is None:
            unknowns.append(f"{task.id}：任务起止日期未知。")
            continue
        if end < start:
            conflicts.append(f"{task.id}：任务结束早于开始日期。")
            continue
        days = (end - start).days + 1 - sum(start <= day <= end for day in unavailable)
        if days == 0:
            conflicts.append(f"{task.id}：任务范围内没有可用日期。")
            continue
        if task.estimated_hours is None:
            unknowns.append(f"{task.id}：任务投入未知。")
        week = start - timedelta(days=start.weekday())
        last_week = end - timedelta(days=end.weekday())
        while True:
            # Ordinals avoid overflow near date.max while splitting calendar weeks.
            left = max(start.toordinal(), week.toordinal())
            right = min(end.toordinal(), week.toordinal() + 6)
            count = right - left + 1 - sum(left <= day.toordinal() <= right for day in unavailable)
            if count:
                totals.setdefault(week, Fraction(0))
                if task.estimated_hours is None:
                    uncertain_weeks.add(week)
                else:
                    totals[week] += Fraction(str(task.estimated_hours)) * count / days
            if week == last_week:
                break
            week += timedelta(days=7)
    loads = []
    for week, hours in sorted(totals.items()):
        if profile.weekly_hours is not None and hours > Fraction(str(profile.weekly_hours)):
            conflicts.append(f"{week.isoformat()}：已知任务工时超过每周预算。")
        # All arithmetic and budget comparisons above are exact rationals built
        # from decimal input strings. Conversion is only for the public DTO.
        try:
            output_hours = float(hours)
        except OverflowError:
            raise AppError("VALIDATION_ERROR", "方案工时总量超出可计算范围。", 422) from None
        if not math.isfinite(output_hours):
            raise AppError("VALIDATION_ERROR", "方案工时总量超出可计算范围。", 422)
        loads.append(
            WeeklyLoad(
                week_start=week,
                estimated_hours=None if week in uncertain_weeks else output_hours,
                budget_hours=profile.weekly_hours,
            )
        )
    return Plan(
        **plan.model_dump(),
        weekly_load=loads,
        conflicts=conflicts + unknowns,
        feasibility="infeasible" if conflicts else "unknown" if unknowns else "feasible",
    )
