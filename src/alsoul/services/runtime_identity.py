from __future__ import annotations

from uuid import UUID, uuid5

_RUNTIME_NAMESPACE = UUID("a7d54b3d-29f4-4f3f-8fa4-70a697078b42")


def response_operation_id(current_input_event_id: UUID, stage: str) -> UUID:
    """Stable application-operation identity for singleton F4 response stages.

    This is an idempotency key, not product-domain identity. The semantic objects
    created by the operation retain their own independently generated IDs.
    """

    return uuid5(
        _RUNTIME_NAMESPACE,
        f"{current_input_event_id}:{stage}:f4-runtime-v1",
    )


__all__ = ["response_operation_id"]
