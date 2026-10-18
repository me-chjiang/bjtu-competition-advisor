"""Session transactions for the basic API (AI-assisted from the frontend contract)."""

from collections.abc import Callable
from datetime import datetime

from backend.catalog import CompetitionCatalog, assess_competition, utc_now
from backend.schemas import (
    AgentRunner,
    AppError,
    CompetitionDetail,
    Profile,
    ProfilePatchRequest,
    SessionRecord,
    SessionSnapshot,
)
from backend.storage import SessionStore


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

    async def patch_profile(
        self,
        session_id: str,
        request: ProfilePatchRequest,
    ) -> SessionSnapshot:
        async with self.store.guard(session_id):
            record = self.store.load(session_id)
            if request.expected_revision != record.snapshot.revision:
                raise AppError(
                    "REVISION_CONFLICT",
                    "会话已更新，请刷新后重试。",
                    409,
                    details={"current_revision": record.snapshot.revision},
                )
            profile_values = record.snapshot.profile.model_dump()
            profile_values.update(request.changes.model_dump(exclude_unset=True))
            profile = Profile.model_validate(profile_values)
            if profile == record.snapshot.profile:
                return record.snapshot

            values = record.model_dump()
            values["snapshot"].update(
                {
                    "profile": profile.model_dump(),
                    "revision": record.snapshot.revision + 1,
                    "stage": "R0",
                    "status": "collecting",
                    "needs_confirmation": False,
                    "cards": [],
                    "plan": None,
                    "message": "画像已更新，请重新核对后继续。",
                }
            )
            values["confirmed_profile"] = None
            values["coarse_cards"] = []
            updated = SessionRecord.model_validate(values)
            self.store.save(updated)
            return updated.snapshot
