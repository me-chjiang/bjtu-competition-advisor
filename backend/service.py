"""Single-commit session transactions (AI-assisted from the frontend contract)."""

from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from backend.agent import LiteLLMAgent, _Context
from backend.catalog import (
    CompetitionCatalog,
    assess_competition,
    check_eligibility,
    evaluate_plan,
    utc_now,
)
from backend.schemas import (
    AgentDraft,
    AgentRunner,
    AppError,
    CandidateCard,
    CandidatePatchRequest,
    ChatRequest,
    CompetitionDetail,
    ConfirmRequest,
    Message,
    PlanDraft,
    Profile,
    ProfileChanges,
    ProfilePatchRequest,
    SessionRecord,
    SessionSnapshot,
    SuccessfulRequest,
)
from backend.storage import SessionStore
from backend.tools import ToolRegistry


class SessionService:
    def __init__(
        self,
        store: SessionStore,
        agent: AgentRunner | None = None,
        catalog: CompetitionCatalog | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.agent = agent
        self.catalog = catalog
        self.clock = clock if clock is not None else utc_now

    def get_competition(self, instance_id: str) -> CompetitionDetail:
        if self.catalog is None:
            raise AppError("CATALOG_NOT_CONFIGURED", "竞赛资料尚未配置。", 503)
        instance = assess_competition(self.catalog.get(instance_id), self.clock())
        return CompetitionDetail.model_validate(
            {
                key: value
                for key, value in instance.model_dump().items()
                if key in CompetitionDetail.model_fields
            }
        )

    def create_session(self) -> SessionSnapshot:
        return self.store.create().snapshot

    def get_session(self, session_id: str) -> SessionSnapshot:
        values = self.store.load(session_id).snapshot.model_dump()
        values["processing"] = self.store.is_processing(session_id)
        return SessionSnapshot.model_validate(values)

    @staticmethod
    def _revision(record: SessionRecord, expected: int) -> None:
        if expected != record.snapshot.revision:
            raise AppError(
                "REVISION_CONFLICT",
                "会话已更新，请刷新后重试。",
                409,
                details={"current_revision": record.snapshot.revision},
            )

    def _catalog(self) -> CompetitionCatalog:
        if self.catalog is None:
            raise AppError("CATALOG_NOT_CONFIGURED", "竞赛资料尚未配置。", 503)
        return self.catalog

    def _save(self, record: SessionRecord) -> SessionSnapshot:
        # There is no await between the final validation and atomic replace.
        # processing is owned by the guard, never persisted into this snapshot.
        record.snapshot.revision += 1
        self.store.save(record)
        return record.snapshot

    @staticmethod
    def _profile_change(record: SessionRecord, changes: ProfileChanges) -> bool:
        values = record.snapshot.profile.model_dump()
        values.update(changes.model_dump(exclude_unset=True))
        profile = Profile.model_validate(values)
        if profile == record.snapshot.profile:
            return False
        snapshot = record.snapshot
        snapshot.profile = profile
        snapshot.stage = "R0"
        snapshot.status = "collecting"
        snapshot.needs_confirmation = False
        snapshot.cards = []
        snapshot.plan = None
        record.confirmed_profile = None
        record.coarse_cards = []
        return True

    def _cards(
        self, cards: list[CandidateCard], profile: Profile, now: datetime
    ) -> list[CandidateCard]:
        result = []
        for card in cards:
            instance = self._catalog().get(card.competition_instance_id)
            assessed = assess_competition(instance, now)
            checked = check_eligibility(profile, instance, now)
            result.append(
                CandidateCard(
                    competition_instance_id=instance.competition_instance_id,
                    name=instance.name,
                    registration_status=assessed.registration_status,
                    registration_deadline=assessed.registration_deadline,
                    eligibility=checked.status,
                    decision=card.decision,
                    reason=card.reason,
                    dimensions=card.dimensions,
                    evidence=instance.evidence,
                )
            )
        return result

    def _validate_draft(
        self,
        output: AgentDraft,
        snapshot: SessionSnapshot,
        request: ChatRequest,
    ) -> AgentDraft:
        invalid = AppError("LLM_INVALID_OUTPUT", "模型输出未通过校验，请稍后重试。", 502)
        try:
            if not isinstance(output, AgentDraft):
                raise invalid
            # Revalidate mutated/model_construct DTOs too. serialize_as_any prevents
            # a Plan subclass from hiding forbidden server-owned fields.
            payload = output.model_dump(
                mode="json",
                exclude_unset=True,
                serialize_as_any=True,
                warnings="error",
            )
            draft = AgentDraft.model_validate(payload)
        except (ValidationError, ValueError, TypeError, PydanticSerializationError):
            raise invalid from None

        # Reuse the reviewed authority gate, not another drifting citation policy.
        # The service builds its OWN scope; it does not trust a runner's ledger.
        context = _Context(ToolRegistry(self.catalog, clock=self.clock), snapshot)
        context.validate(draft)
        if draft.kind == "candidates":
            context.instances.update(
                item.competition_instance_id for item in self._catalog().search()
            )
        elif draft.kind in {"analysis", "plan"}:
            for card in snapshot.cards:
                if card.decision == "keep" and (draft.kind != "plan" or card.dimensions):
                    context.detail(card.competition_instance_id)
        context.preflight(payload)
        # Literal, conservative provenance is shared with the default Agent;
        # additional_context is not a global edit lock for any runner.
        return LiteLLMAgent._review_conflict(draft, snapshot, request)

    async def chat(self, session_id: str, request: ChatRequest) -> SessionSnapshot:
        async with self.store.guard(session_id):
            record = self.store.load(session_id)
            cached = record.successful_requests.get(request.request_id)
            if cached is not None:
                if cached.request != request:
                    raise AppError("REQUEST_ID_REUSED", "请求 ID 已用于不同请求。", 409)
                return cached.snapshot
            self._revision(record, request.expected_revision)
            if self.agent is None:
                raise AppError("LLM_NOT_CONFIGURED", "模型尚未配置。", 503)
            snapshot = record.snapshot
            # A custom runner can mutate arguments; never lend it transaction state.
            output = await self.agent.run(
                snapshot.model_copy(deep=True), request.model_copy(deep=True)
            )
            draft = self._validate_draft(output, snapshot, request)
            now = self.clock()
            original_stage = snapshot.stage
            if draft.kind == "profile":
                self._profile_change(record, draft.profile_changes)
                if original_stage == "R0":
                    snapshot.status = "awaiting_review"
                    snapshot.needs_confirmation = True
            elif draft.kind == "candidates":
                # Model omission is not a user decision. Retain old cards so
                # keep/exclude survive regeneration and remain editable after restart.
                cards = {
                    card.competition_instance_id: card.model_copy(deep=True)
                    for card in snapshot.cards
                }
                for item in draft.candidates:
                    previous = cards.get(item.competition_instance_id)
                    cards[item.competition_instance_id] = CandidateCard(
                        competition_instance_id=item.competition_instance_id,
                        name="",
                        reason=item.reason,
                        decision=previous.decision if previous is not None else "defer",
                    )
                for card in cards.values():
                    card.dimensions = []
                snapshot.cards = self._cards(list(cards.values()), snapshot.profile, now)
                record.coarse_cards = [card.model_copy(deep=True) for card in snapshot.cards]
                snapshot.plan = None
                snapshot.status = "awaiting_review"
                snapshot.needs_confirmation = True
            elif draft.kind == "analysis":
                dimensions = {
                    item.competition_instance_id: item.dimensions for item in draft.analyses
                }
                snapshot.cards = self._cards(snapshot.cards, snapshot.profile, now)
                for card in snapshot.cards:
                    card.dimensions = dimensions.get(card.competition_instance_id, [])
                snapshot.plan = None
                snapshot.status = "awaiting_review"
                snapshot.needs_confirmation = True
            elif draft.kind == "plan":
                snapshot.plan = evaluate_plan(snapshot.profile, draft.plan, self._catalog(), now)
                snapshot.status = "awaiting_review"
                snapshot.needs_confirmation = True
            snapshot.message = draft.message
            if request.action == "message":
                snapshot.messages.append(
                    Message(
                        id=uuid4().hex,
                        role="user",
                        content=request.content,
                        created_at=now,
                    )
                )
            snapshot.messages.append(
                Message(
                    id=uuid4().hex,
                    role="assistant",
                    content=draft.message,
                    created_at=now,
                )
            )
            snapshot.last_request_id = request.request_id
            # Cache the EXACT final response at its new revision before one save.
            snapshot.revision += 1
            record.successful_requests[request.request_id] = SuccessfulRequest(
                request=request.model_copy(deep=True),
                snapshot=snapshot.model_copy(deep=True),
            )
            self.store.save(record)
            return snapshot

    async def patch_profile(
        self,
        session_id: str,
        request: ProfilePatchRequest,
    ) -> SessionSnapshot:
        async with self.store.guard(session_id):
            record = self.store.load(session_id)
            self._revision(record, request.expected_revision)
            if not self._profile_change(record, request.changes):
                return record.snapshot
            record.snapshot.message = "画像已更新，请重新核对后继续。"
            return self._save(record)

    async def patch_candidate(
        self,
        session_id: str,
        candidate_id: str,
        request: CandidatePatchRequest,
    ) -> SessionSnapshot:
        async with self.store.guard(session_id):
            record = self.store.load(session_id)
            self._revision(record, request.expected_revision)
            snapshot = record.snapshot
            if snapshot.stage not in {"R1", "R2", "R4"}:
                raise AppError("INVALID_STAGE", "当前阶段不能修改候选。", 409)
            cards = self._cards(snapshot.cards, snapshot.profile, self.clock())
            card = next(
                (item for item in cards if item.competition_instance_id == candidate_id), None
            )
            if card is None:
                raise AppError("COMPETITION_NOT_FOUND", "当前候选不存在。", 404)
            if request.decision == "keep" and card.eligibility == "ineligible":
                raise AppError(
                    "VALIDATION_ERROR", "存在明确资格冲突或报名已经截止，不能保留。", 422
                )
            if card.decision == request.decision:
                return snapshot
            decisions = {item.competition_instance_id: item.decision for item in cards}
            decisions[candidate_id] = request.decision
            coarse = self._cards(record.coarse_cards or cards, snapshot.profile, self.clock())
            for item in coarse:
                item.decision = decisions[item.competition_instance_id]
                item.dimensions = []
            snapshot.cards = coarse
            record.coarse_cards = [item.model_copy(deep=True) for item in coarse]
            snapshot.stage = "R1"
            snapshot.status = "awaiting_review"
            snapshot.needs_confirmation = True
            snapshot.plan = None
            snapshot.message = "候选已更新，请重新确认筛选结果。"
            return self._save(record)

    async def confirm(self, session_id: str, request: ConfirmRequest) -> SessionSnapshot:
        async with self.store.guard(session_id):
            record = self.store.load(session_id)
            self._revision(record, request.expected_revision)
            snapshot = record.snapshot
            if snapshot.stage != request.stage or snapshot.status != "awaiting_review":
                raise AppError("INVALID_STAGE", "当前阶段没有可确认的结果。", 409)
            if snapshot.stage == "R0":
                record.confirmed_profile = snapshot.profile.model_copy(deep=True)
            else:
                now = self.clock()
                cards = self._cards(snapshot.cards, snapshot.profile, now)
                kept = [card for card in cards if card.decision == "keep"]
                if not kept or any(card.eligibility == "ineligible" for card in kept):
                    raise AppError(
                        "VALIDATION_ERROR", "请保留至少一个没有明确资格冲突的候选。", 422
                    )
                if snapshot.stage in {"R2", "R4"} and not any(card.dimensions for card in kept):
                    raise AppError("VALIDATION_ERROR", "请先生成保留候选的精查结果。", 422)
                if snapshot.stage == "R4":
                    if snapshot.plan is None:
                        raise AppError("VALIDATION_ERROR", "请先生成路线。", 422)
                    selected = set(snapshot.plan.selected_competition_ids)
                    if not selected <= {
                        card.competition_instance_id for card in kept if card.dimensions
                    }:
                        raise AppError("VALIDATION_ERROR", "路线必须使用已保留并分析的候选。", 422)
                    plan = PlanDraft.model_validate(
                        {field: getattr(snapshot.plan, field) for field in PlanDraft.model_fields}
                    )
                    evaluated = evaluate_plan(snapshot.profile, plan, self._catalog(), now)
                    if evaluated.feasibility != "feasible":
                        raise AppError(
                            "VALIDATION_ERROR", "路线存在冲突或未知信息，不能确认为可行方案。", 422
                        )
                    snapshot.plan = evaluated
                snapshot.cards = cards
            if snapshot.stage == "R4":
                snapshot.status = "completed"
                snapshot.message = "方案已确认。"
            else:
                snapshot.stage = {"R0": "R1", "R1": "R2", "R2": "R4"}[snapshot.stage]
                snapshot.status = "collecting"
                snapshot.message = "当前结果已确认，请生成下一阶段草案。"
            snapshot.needs_confirmation = False
            return self._save(record)
