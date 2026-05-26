from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import main  # noqa: E402
from models import (  # noqa: E402
    CoachEmailSendRequest,
    LeadInfo,
    MunicipioInfo,
    ReportPdfRenderRequest,
    SearchMetadata,
    SearchStageResult,
    TransactionDetail,
    ValuationRequest,
    ValuationResponse,
    ValuationStats,
)


def _valuation() -> ValuationResponse:
    return ValuationResponse(
        municipio=MunicipioInfo(name="Madrid", slug="madrid", road="Calle Granada"),
        listings=[],
        stats=ValuationStats(total_comparables=3, estimated_value=300_000),
        search_url="https://idealista.test/search",
        search_metadata=SearchMetadata(
            strategy="test",
            target_comparables=5,
            final_stage="strict",
            total_duration_ms=10,
            stages=[
                SearchStageResult(
                    name="strict",
                    label="Strict",
                    query="Calle Granada, Madrid",
                    search_url="https://idealista.test/search",
                    listings_found=3,
                    duration_ms=10,
                    bedrooms_mode="exact",
                    bathrooms_mode="exact",
                )
            ],
        ),
    )


def _lead() -> LeadInfo:
    return LeadInfo(
        full_name="Test User",
        email="test@example.com",
        phone="+34611222333",
    )


def _transaction() -> TransactionDetail:
    return TransactionDetail(
        id="rec123",
        transaction_name="Test Transaction",
        address="Calle Granada, Madrid",
        client_email="test@example.com",
        raw_fields={},
    )


def test_send_report_in_background_marks_email_sent(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, object]] = []

    def fake_render_report_html(*, valuation, request_payload, lead):
        calls.append(("render", (valuation, request_payload, lead)))
        return "<html>report</html>"

    async def fake_generate_pdf_bytes(html: str) -> bytes:
        calls.append(("pdf", html))
        return b"%PDF-1.4 report"

    async def fake_send_valuation_email(*, lead, valuation, pdf_bytes):
        calls.append(("email", (lead, valuation, pdf_bytes)))

    def fake_mark_email_sent(valuation_id: int, *, error: str | None = None):
        calls.append(("mark", (valuation_id, error)))

    monkeypatch.setattr(main, "render_report_html", fake_render_report_html)
    monkeypatch.setattr(main, "generate_pdf_bytes", fake_generate_pdf_bytes)
    monkeypatch.setattr(main, "send_valuation_email", fake_send_valuation_email)
    monkeypatch.setattr(main.db, "mark_email_sent", fake_mark_email_sent)

    valuation = _valuation()
    lead = _lead()
    request_payload = {"address": "Calle Granada, Madrid", "m2": 90}

    asyncio.run(
        main._send_report_in_background(
            valuation_id=123,
            lead=lead,
            valuation=valuation,
            request_payload=request_payload,
        )
    )

    assert calls == [
        ("render", (valuation, request_payload, lead)),
        ("pdf", "<html>report</html>"),
        ("email", (lead, valuation, b"%PDF-1.4 report")),
        ("mark", (123, None)),
    ]


def test_send_report_in_background_persists_delivery_error(monkeypatch: pytest.MonkeyPatch):
    marked: list[tuple[int, str | None]] = []

    monkeypatch.setattr(main, "render_report_html", lambda **kwargs: "<html>report</html>")

    async def fake_generate_pdf_bytes(html: str) -> bytes:
        return b"%PDF-1.4 report"

    async def fake_send_valuation_email(*, lead, valuation, pdf_bytes):
        raise main.EmailDeliveryError("Resend 422: bad sender")

    def fake_mark_email_sent(valuation_id: int, *, error: str | None = None):
        marked.append((valuation_id, error))

    monkeypatch.setattr(main, "generate_pdf_bytes", fake_generate_pdf_bytes)
    monkeypatch.setattr(main, "send_valuation_email", fake_send_valuation_email)
    monkeypatch.setattr(main.db, "mark_email_sent", fake_mark_email_sent)

    asyncio.run(
        main._send_report_in_background(
            valuation_id=456,
            lead=_lead(),
            valuation=_valuation(),
            request_payload={"address": "Calle Granada, Madrid", "m2": 90},
        )
    )

    assert marked == [(456, "Resend 422: bad sender")]


def test_report_pdf_render_uses_supplied_valuation(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, object]] = []

    def fake_render_report_html(
        *,
        valuation,
        request_payload,
        lead,
        transaction=None,
        include_comparables=True,
    ):
        calls.append(("render", (valuation, request_payload, lead, transaction, include_comparables)))
        return "<html>report</html>"

    async def fake_generate_pdf_bytes(html: str) -> bytes:
        calls.append(("pdf", html))
        return b"%PDF-1.4 report"

    monkeypatch.setattr(main, "render_report_html", fake_render_report_html)
    monkeypatch.setattr(main, "generate_pdf_bytes", fake_generate_pdf_bytes)

    valuation = _valuation()
    request = ValuationRequest(
        address="Calle Granada, Madrid",
        m2=90,
        bedrooms=2,
        bathrooms=1,
    )
    lead = _lead()
    payload = ReportPdfRenderRequest(
        valuation=valuation,
        valuation_request=request,
        lead=lead,
    )

    response = asyncio.run(main.post_report_pdf_render(payload))

    assert response.media_type == "application/pdf"
    assert response.body == b"%PDF-1.4 report"
    assert response.headers["content-disposition"] == 'inline; filename="prophero-valoracion.pdf"'
    assert calls == [
        ("render", (valuation, request.model_dump(mode="json"), lead, None, True)),
        ("pdf", "<html>report</html>"),
    ]


def test_report_pdf_render_honors_include_comparables_flag(monkeypatch: pytest.MonkeyPatch):
    """When the caller opts out of comparables, the flag must be threaded
    through to ``render_report_html`` so the template can drop the section."""
    received: dict[str, object] = {}

    def fake_render_report_html(
        *,
        valuation,
        request_payload,
        lead,
        transaction=None,
        include_comparables=True,
    ):
        received["include_comparables"] = include_comparables
        return "<html>report</html>"

    async def fake_generate_pdf_bytes(html: str) -> bytes:
        return b"%PDF-1.4 report"

    monkeypatch.setattr(main, "render_report_html", fake_render_report_html)
    monkeypatch.setattr(main, "generate_pdf_bytes", fake_generate_pdf_bytes)

    payload = ReportPdfRenderRequest(
        valuation=_valuation(),
        valuation_request=ValuationRequest(
            address="Calle Granada, Madrid",
            m2=90,
            bedrooms=2,
            bathrooms=1,
        ),
        lead=_lead(),
        include_comparables=False,
    )

    asyncio.run(main.post_report_pdf_render(payload))

    assert received == {"include_comparables": False}


def test_send_coach_transaction_email_attaches_rendered_pdf(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, object]] = []
    transaction = _transaction()
    valuation = _valuation()
    request = ValuationRequest(
        address="Calle Granada, Madrid",
        m2=90,
        bedrooms=2,
        bathrooms=1,
    )

    monkeypatch.setattr(main, "_airtable_config", lambda: object())

    async def fake_get_transaction(*, config, record_id):
        calls.append(("transaction", record_id))
        return transaction

    def fake_render_report_html(
        *,
        valuation,
        request_payload,
        lead,
        transaction=None,
        include_comparables=True,
    ):
        calls.append(("render", (valuation, request_payload, lead, transaction, include_comparables)))
        return "<html>coach report</html>"

    async def fake_generate_pdf_bytes(html: str) -> bytes:
        calls.append(("pdf", html))
        return b"%PDF-1.4 coach"

    async def fake_send_custom_email(
        *,
        to,
        subject,
        body,
        attachment_filename=None,
        attachment_bytes=None,
    ):
        calls.append(
            (
                "email",
                (to, subject, body, attachment_filename, attachment_bytes),
            )
        )
        return True

    monkeypatch.setattr(main, "get_transaction", fake_get_transaction)
    monkeypatch.setattr(main, "render_report_html", fake_render_report_html)
    monkeypatch.setattr(main, "generate_pdf_bytes", fake_generate_pdf_bytes)
    monkeypatch.setattr(main, "send_custom_email", fake_send_custom_email)

    response = asyncio.run(
        main.send_coach_transaction_email(
            "rec123",
            CoachEmailSendRequest(
                to="client@example.com",
                subject="Informe",
                body="Hola",
                valuation_request=request,
                valuation=valuation,
                include_comparables=False,
            ),
        )
    )

    assert response.sent is True
    assert calls == [
        ("transaction", "rec123"),
        ("render", (valuation, request.model_dump(mode="json"), None, transaction, False)),
        ("pdf", "<html>coach report</html>"),
        (
            "email",
            (
                "client@example.com",
                "Informe",
                "Hola",
                "prophero-valoracion-rec123.pdf",
                b"%PDF-1.4 coach",
            ),
        ),
    ]
