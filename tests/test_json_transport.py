from __future__ import annotations

from io import BytesIO

import pytest

from alsoul.adapters import AdapterRejected, UrllibJsonTransport


def test_model_transport_classifies_undecodable_success_body_as_rejected():
    transport = UrllibJsonTransport(max_response_bytes=1024)

    with pytest.raises(AdapterRejected):
        transport._read_bounded(BytesIO(b"\xff"), charset="utf-8")
