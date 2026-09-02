"""Unit tests for the pre-run preview: response parsing and the client facade."""

from __future__ import annotations

from typing import Any

import pytest

from sateais_qgis.core.api.client import Client
from sateais_qgis.core.api.errors import InvalidAnalysisRequestError
from sateais_qgis.core.api.types import AnalysisRequest, Preview, preview_from_dict

# docs/API.md (POST /analyze/{endpoint}/preview) のレスポンス例そのまま
FULL_PAYLOAD: dict[str, Any] = {
    "endpoint_id": "newbuilding",
    "area_sqkm": 78.4,
    "coverage": {
        "method": "estimated",
        "requested_area_sqkm": 100.2,
        "ratio": 0.78,
        "polygon": "POLYGON ((139.000000 35.000000, 139.110000 35.000000, 139.000000 35.000000))",
    },
    "credits": {"estimated": 1.0, "balance": 480.0, "sufficient": True},
    "warnings": [
        {"code": "LOW_AOI_COVERAGE", "message": "Scenes cover only 78% of the requested area."}
    ],
}


class TestPreviewFromDict:
    def test_full_payload(self):
        p = preview_from_dict(FULL_PAYLOAD)
        assert p.endpoint_id == "newbuilding"
        assert p.area_sqkm == 78.4
        assert p.credits is not None
        assert p.credits.estimated == 1.0
        assert p.credits.sufficient is True
        assert p.coverage is not None
        assert p.coverage.ratio == 0.78
        assert p.coverage.polygon.startswith("POLYGON")
        assert len(p.warnings) == 1

    def test_coverage_omitted_means_unknown(self):
        # カタログ検索が時間切れだと credits だけが返る。coverage 無し = 不明で
        # あって全被覆ではない
        p = preview_from_dict({"credits": {"estimated": 81.44, "balance": 100, "sufficient": True}})
        assert p.coverage is None
        assert p.credits is not None
        assert p.credits.estimated == 81.44

    def test_null_estimate_survives_as_none(self):
        # estimated: null は「投入前には確定しない」。0 に潰さない
        p = preview_from_dict(
            {"credits": {"estimated": None, "balance": 480.0, "sufficient": None}}
        )
        assert p.credits is not None
        assert p.credits.estimated is None
        assert p.credits.sufficient is None

    def test_empty_and_garbage_are_safe(self):
        p = preview_from_dict({})
        assert p == Preview()
        p = preview_from_dict(
            {"credits": "?", "coverage": 3, "warnings": ["x", {"code": "A", "message": "m"}]}
        )
        assert p.credits is None
        assert p.coverage is None
        assert p.warnings == [{"code": "A", "message": "m"}]

    def test_non_finite_numbers_become_none(self):
        # json.loads は既定で NaN / Infinity を通す。数値として持つと
        # 表示側が「不明」ではなく事実として出してしまう
        import json

        raw = json.loads('{"credits":{"estimated":NaN},"coverage":{"ratio":Infinity}}')
        p = preview_from_dict(raw)
        assert p.credits is not None
        assert p.credits.estimated is None
        assert p.coverage is not None
        assert p.coverage.ratio is None

    def test_bool_is_not_a_number(self):
        p = preview_from_dict({"area_sqkm": True})
        assert p.area_sqkm is None

    def test_empty_polygon_becomes_none(self):
        p = preview_from_dict({"coverage": {"ratio": 1.0, "polygon": ""}})
        assert p.coverage is not None
        assert p.coverage.polygon is None


class FakeApiClient:
    """Captures preview requests; other methods are unused here."""

    def __init__(self) -> None:
        self.previewed: list[AnalysisRequest] = []

    def preview_analysis(self, request: AnalysisRequest) -> Preview:
        self.previewed.append(request)
        return preview_from_dict(FULL_PAYLOAD)

    def close(self) -> None:  # pragma: no cover - interface completeness
        pass


class TestClientPreview:
    def test_builds_and_validates_request(self):
        api = FakeApiClient()
        client = Client(api_key="sk_test", api=api)
        preview = client.analyze.preview(
            "newbuilding",
            polygon="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            date_start="2026-01-01",
            date_end="2026-06-30",
        )
        assert preview.credits is not None
        assert len(api.previewed) == 1
        request = api.previewed[0]
        assert request.analysis_type.value == "newbuilding"
        assert request.date_start == "2026-01-01"

    def test_incomplete_request_fails_client_side(self):
        # 投入と同じ検証を通す。preview だけ緩いと、投入で初めて弾かれる
        api = FakeApiClient()
        client = Client(api_key="sk_test", api=api)
        with pytest.raises(InvalidAnalysisRequestError):
            client.analyze.preview("newbuilding", polygon="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")
        assert api.previewed == []

    def test_bad_type_and_bad_kwarg_are_input_errors(self):
        # 生の ValueError / TypeError のままだと worker が
        # ERROR_NETWORK_ERROR に落とし、利用者は通信障害だと誤解する
        api = FakeApiClient()
        client = Client(api_key="sk_test", api=api)
        with pytest.raises(InvalidAnalysisRequestError):
            client.analyze.preview("nope", polygon="P", date_start="a", date_end="b")
        with pytest.raises(InvalidAnalysisRequestError):
            client.analyze.preview("newbuilding", polygonn="typo")
        assert api.previewed == []
