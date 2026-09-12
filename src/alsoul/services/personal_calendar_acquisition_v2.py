from __future__ import annotations

from alsoul.domain.errors import fail
from alsoul.services.personal_calendar_acquisition import (
    PersonalCalendarAcquisitionServices as PersonalCalendarAcquisitionServicesV1,
)


class PersonalCalendarAcquisitionServices(PersonalCalendarAcquisitionServicesV1):
    """Current F5.A acquisition boundary with explicit adapter/query qualification."""

    def _qualify_contract(self) -> None:
        super()._qualify_contract()
        contract = self.capability_contract
        adapter_contract_version = getattr(
            self.adapter, "capability_contract_version", None
        )
        if adapter_contract_version != contract.contract_version:
            fail(
                "CALENDAR_ADAPTER_CAPABILITY_MISMATCH",
                "calendar adapter is not qualified for the trusted capability contract",
            )
        if contract.query_interval_semantics != "OVERLAP_COMPLETE_HALF_OPEN_WINDOW":
            fail(
                "CALENDAR_QUERY_SEMANTICS_UNTRUSTED",
                "calendar adapter contract must guarantee complete half-open interval overlap semantics",
            )
        if contract.history_compensation_mode != "PROHIBITED":
            fail(
                "CALENDAR_QUERY_SEMANTICS_UNTRUSTED",
                "calendar acquisition must not compensate with unbounded history queries",
            )


__all__ = ["PersonalCalendarAcquisitionServices"]
