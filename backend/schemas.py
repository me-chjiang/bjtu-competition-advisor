"""Contract DTOs and internal drafts, AI-assisted from docs/frontend-contract.md.

These types validate shapes only; the service owns authorization, evidence scope,
stage transitions and feasibility checks. Model drafts never contain authority.
"""

from datetime import date
from typing import Annotated, Any, Literal, Protocol

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

Stage = Literal["R0", "R1", "R2", "R4"]
Status = Literal["collecting", "awaiting_review", "completed"]
Decision = Literal["keep", "exclude", "defer"]
RegistrationStatus = Literal["open", "upcoming", "closed", "unknown"]
Eligibility = Literal["eligible", "ineligible", "unknown"]
Basis = Literal["explicit", "inferred", "unknown"]
DimensionName = Literal[
    "ability_gap",
    "goal_value",
    "time_cost",
    "preparation_risk",
    "team_requirement",
    "schedule_conflict",
]
Revision = Annotated[int, Field(strict=True, ge=0)]
NonemptyString = Annotated[str, Field(min_length=1)]


def _reject_boolean(value: Any) -> Any:
    if isinstance(value, bool):
        raise ValueError("Hours must be a positive finite number, not a boolean.")
    return value


PositiveHours = Annotated[float, BeforeValidator(_reject_boolean), Field(gt=0, allow_inf_nan=False)]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Skill(DTO):
    name: NonemptyString
    evidence: str | None = None


class Profile(DTO):
    grade: str | None = None
    major: str | None = None
    skills: list[Skill] = Field(default_factory=list)
    weekly_hours: PositiveHours | None = None
    goals: list[str] = Field(default_factory=list)
    team_preference: Literal["solo", "team", "either"] | None = None
    unavailable_dates: list[date] = Field(default_factory=list)
    additional_context: Annotated[str, Field(max_length=2000)] | None = None

    @field_validator("additional_context", mode="before")
    @classmethod
    def normalize_blank_context(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class ProfileChanges(Profile):
    """Merge ONLY model_dump(exclude_unset=True); null clears nullable fields.

    Arrays remain non-nullable and replace the entire previous array. Defaults
    do not imply that a field was supplied: model_fields_set tracks presence.
    """


class CreateSessionRequest(DTO):
    pass


class ChatRequest(DTO):
    request_id: NonemptyString
    expected_revision: Revision
    action: Literal["message", "generate"]
    content: Annotated[str, Field(max_length=4000)] | None

    @model_validator(mode="after")
    def validate_content(self) -> "ChatRequest":
        if self.action == "message" and (self.content is None or not self.content.strip()):
            raise ValueError("A message requires nonblank content.")
        if self.action == "generate" and self.content is not None:
            raise ValueError("Generate content must be null.")
        return self


class ProfilePatchRequest(DTO):
    expected_revision: Revision
    changes: ProfileChanges


class CandidatePatchRequest(DTO):
    expected_revision: Revision
    decision: Decision


class ConfirmRequest(DTO):
    expected_revision: Revision
    stage: Stage


class Message(DTO):
    id: NonemptyString
    role: Literal["user", "assistant"]
    content: str
    created_at: AwareDatetime


class Evidence(DTO):
    id: NonemptyString
    url: HttpUrl
    excerpt: str
    fetched_at: AwareDatetime
    applicable_year: int | None = None
    scope: str | None = None

    @field_validator("url")
    @classmethod
    def reject_url_credentials(cls, value: HttpUrl) -> HttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("Source URLs must not contain credentials.")
        return value


class Dimension(DTO):
    name: DimensionName
    assessment: str
    basis: Basis
    evidence_ids: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class CandidateCard(DTO):
    competition_instance_id: NonemptyString
    name: str
    registration_status: RegistrationStatus = "unknown"
    registration_deadline: date | None = None
    eligibility: Eligibility = "unknown"
    decision: Decision = "defer"
    reason: str
    dimensions: list[Dimension] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class CompetitionDetail(DTO):
    competition_instance_id: NonemptyString
    name: str
    series_id: str | None = None
    year: int | None = None
    group: str | None = None
    stage: str | None = None
    eligibility_description: str | None = None
    registration_status: RegistrationStatus = "unknown"
    registration_start: date | None = None
    registration_deadline: date | None = None
    competition_date: date | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class CompetitionRecord(CompetitionDetail):
    """Private catalog eligibility inputs, never accepted as HTTP edits."""

    allowed_grades: list[str] | None = None
    allowed_majors: list[str] | None = None
    eligibility_evidence_ids: list[str] = Field(default_factory=list)
    # Absent date provenance keeps legacy internal serialization unchanged;
    # nonempty references remain round-trippable for explicit catalog records.
    registration_evidence_ids: list[str] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )
    competition_date_evidence_ids: list[str] = Field(
        default_factory=list, exclude_if=lambda value: not value
    )


class PlanTask(DTO):
    id: NonemptyString
    competition_instance_id: NonemptyString
    title: str
    estimated_hours: PositiveHours | None = None
    acceptance_criteria: str
    start_date: date | None = None
    due_date: date | None = None


class WeeklyLoad(DTO):
    week_start: date
    estimated_hours: PositiveHours | None = None
    budget_hours: PositiveHours | None = None

    @field_validator("week_start")
    @classmethod
    def require_monday(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("The week must start on Monday.")
        return value


class PlanDraft(DTO):
    selected_competition_ids: list[str] = Field(default_factory=list)
    tasks: list[PlanTask] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class Plan(PlanDraft):
    weekly_load: list[WeeklyLoad] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    feasibility: Literal["feasible", "infeasible", "unknown"] = "unknown"


class SessionSnapshot(DTO):
    session_id: NonemptyString
    revision: Revision = 0
    stage: Stage = "R0"
    status: Status = "collecting"
    processing: bool = False
    last_request_id: str | None = None
    message: str = ""
    messages: list[Message] = Field(default_factory=list)
    profile: Profile = Field(default_factory=Profile)
    cards: list[CandidateCard] = Field(default_factory=list)
    plan: Plan | None = None
    needs_confirmation: bool = False

    @model_validator(mode="after")
    def validate_confirmation_flag(self) -> "SessionSnapshot":
        if self.needs_confirmation != (self.status == "awaiting_review"):
            raise ValueError("Confirmation is required exactly when awaiting review.")
        return self


class SuccessfulRequest(DTO):
    request: ChatRequest
    snapshot: SessionSnapshot

    @field_validator("snapshot")
    @classmethod
    def reject_processing_snapshot(cls, value: SessionSnapshot) -> SessionSnapshot:
        if value.processing:
            raise ValueError("Processing state must not be persisted.")
        return value


class SessionRecord(DTO):
    snapshot: SessionSnapshot
    confirmed_profile: Profile | None = None
    coarse_cards: list[CandidateCard] = Field(default_factory=list)
    successful_requests: dict[str, SuccessfulRequest] = Field(default_factory=dict)

    @field_validator("snapshot")
    @classmethod
    def reject_processing_snapshot(cls, value: SessionSnapshot) -> SessionSnapshot:
        if value.processing:
            raise ValueError("Processing state must not be persisted.")
        return value


class CandidateReason(DTO):
    competition_instance_id: NonemptyString
    reason: str


class AnalysisDraft(DTO):
    competition_instance_id: NonemptyString
    dimensions: list[Dimension] = Field(default_factory=list)


class AgentDraft(DTO):
    kind: Literal["question", "profile", "candidates", "analysis", "plan"]
    message: str
    profile_changes: ProfileChanges | None = None
    candidates: list[CandidateReason] = Field(default_factory=list)
    analyses: list[AnalysisDraft] = Field(default_factory=list)
    plan: PlanDraft | None = None


class AgentRunner(Protocol):
    async def run(self, snapshot: SessionSnapshot, request: ChatRequest) -> AgentDraft: ...


class ErrorDetail(DTO):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None


class ErrorResponse(DTO):
    error: ErrorDetail
    request_id: str | None = None


class AppError(Exception):
    """Controlled error; callers must pass safe messages/details, never raw exceptions."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details
