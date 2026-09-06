from __future__ import annotations

from datetime import datetime, timezone

import pytest

from alsoul.adapters import AdapterRejected, F4JsonMemoryRequirementExtractor
from alsoul.domain.models import CapturedWorldMaterial


def _material(*, source_identity: str, content: str) -> CapturedWorldMaterial:
    captured_at = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    return CapturedWorldMaterial(
        source_identity=source_identity,
        requested_locator="https://source.invalid/requirements",
        resolved_locator=source_identity,
        content=content,
        captured_at=captured_at,
    )


def test_source_specific_world_extractor_accepts_same_https_origin():
    extractor = F4JsonMemoryRequirementExtractor(
        expected_https_origin="https://source.invalid",
    )

    result = extractor.extract(
        _material(
            source_identity="https://source.invalid/requirements-v2",
            content='{"minimum_memory_gb":24}',
        )
    )

    assert result.result_kind == "REQUIREMENT"
    assert result.predicate == "software.minimum_memory_gb"
    assert result.value == 24
    assert result.valid_as_of == datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def test_source_specific_world_extractor_rejects_cross_origin_capture():
    extractor = F4JsonMemoryRequirementExtractor(
        expected_https_origin="https://source.invalid",
    )

    with pytest.raises(AdapterRejected, match="outside the configured HTTPS origin"):
        extractor.extract(
            _material(
                source_identity="https://other.invalid/requirements",
                content='{"minimum_memory_gb":24}',
            )
        )


def test_source_specific_world_extractor_rejects_invalid_semantic_field():
    extractor = F4JsonMemoryRequirementExtractor(
        expected_https_origin="https://source.invalid",
    )

    with pytest.raises(AdapterRejected, match="minimum_memory_gb"):
        extractor.extract(
            _material(
                source_identity="https://source.invalid/requirements",
                content='{"minimum_memory_gb":"24"}',
            )
        )


def test_source_specific_world_extractor_rejects_non_object_json():
    extractor = F4JsonMemoryRequirementExtractor()

    with pytest.raises(AdapterRejected, match="must be an object"):
        extractor.extract(
            _material(
                source_identity="fixture://requirements",
                content="[24]",
            )
        )


def test_source_specific_world_extractor_requires_valid_configured_origin():
    with pytest.raises(ValueError, match="absolute HTTPS origin"):
        F4JsonMemoryRequirementExtractor(
            expected_https_origin="https://source.invalid/path",
        )
