from __future__ import annotations

from alsoul.services.calendar_runtime_model_selection import select_model_route
from alsoul.services.calendar_runtime_read_selection import (
    select_credential_binding,
    select_read_permission,
)


class CalendarRuntimeSelector:
    """Resolve unique current runtime bindings without minting transport authority."""

    def __init__(self, engine, *, capability_contract, model_adapter, clock) -> None:
        self.engine = engine
        self.capability_contract = capability_contract
        self.model_adapter = model_adapter
        self.clock = clock

    def select_permission(self, **kwargs):
        return select_read_permission(
            self.engine,
            capability_contract=self.capability_contract,
            clock=self.clock,
            **kwargs,
        )

    def select_credential(self, *, relationship_id, resource_id):
        return select_credential_binding(
            self.engine,
            relationship_id=relationship_id,
            resource_id=resource_id,
            capability_contract=self.capability_contract,
        )

    def select_model_route(self, relationship_id):
        return select_model_route(
            self.engine,
            relationship_id=relationship_id,
            model_adapter=self.model_adapter,
        )


__all__ = ["CalendarRuntimeSelector"]
