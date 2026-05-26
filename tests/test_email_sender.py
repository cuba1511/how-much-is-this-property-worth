from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from models import (  # noqa: E402
    LeadInfo,
    MunicipioInfo,
    SearchMetadata,
    SearchStageResult,
    ValuationResponse,
    ValuationStats,
)
from notifications import email_sender  # noqa: E402
from notifications.email_sender import (  # noqa: E402
    EmailDeliveryError,
    send_custom_email,
    send_valuation_email,
)


class FakeResponse:
    def __init__(self, status_code: int = 200, body: str = '{"id":"email_123"}'):
        self.status_code = status_code
        self.text = body

    def json(self) -> dict[str, str]:
        return {"id": "email_123"}


class FakeAsyncClient:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.response


def _valuation() -> ValuationResponse:
    return ValuationResponse(
        municipio=MunicipioInfo(
            name="Madrid",
            slug="madrid",
            province="Madrid",
            road="Calle Granada",
        ),
        listings=[],
        stats=ValuationStats(
            total_comparables=4,
            estimated_value=350_000,
            price_range_low=325_000,
            price_range_high=375_000,
        ),
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
                    listings_found=4,
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


def test_send_valuation_email_noops_without_resend_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    def fail_if_network_is_used(*args, **kwargs):
        raise AssertionError("Network client should not be created without RESEND_API_KEY")

    monkeypatch.setattr(email_sender.httpx, "AsyncClient", fail_if_network_is_used)

    asyncio.run(
        send_valuation_email(
            lead=_lead(),
            valuation=_valuation(),
            pdf_bytes=b"%PDF-1.4 test",
        )
    )


def test_send_custom_email_returns_false_without_resend_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    def fail_if_network_is_used(*args, **kwargs):
        raise AssertionError("Network client should not be created without RESEND_API_KEY")

    monkeypatch.setattr(email_sender.httpx, "AsyncClient", fail_if_network_is_used)

    sent = asyncio.run(
        send_custom_email(
            to="test@example.com",
            subject="Hello",
            body="Plain body",
        )
    )

    assert sent is False


def test_send_valuation_email_posts_resend_payload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "PropHero <noreply@example.com>")
    client = FakeAsyncClient(FakeResponse())
    monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda timeout: client)

    asyncio.run(
        send_valuation_email(
            lead=_lead(),
            valuation=_valuation(),
            pdf_bytes=b"%PDF-1.4 test",
        )
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == email_sender.RESEND_API_URL
    assert call["headers"] == {
        "Authorization": "Bearer re_test",
        "Content-Type": "application/json",
    }
    payload = call["json"]
    assert payload["from"] == "PropHero <noreply@example.com>"
    assert payload["to"] == ["test@example.com"]
    assert payload["subject"] == "Tu valoración PropHero — Madrid"
    assert "Test User" in payload["html"]
    assert "350.000 €" in payload["html"]
    assert payload["attachments"][0]["filename"].startswith("prophero-valoracion-")
    assert payload["attachments"][0]["filename"].endswith(".pdf")
    assert payload["attachments"][0]["content"] == base64.b64encode(b"%PDF-1.4 test").decode(
        "ascii"
    )


def test_send_valuation_email_raises_on_resend_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    client = FakeAsyncClient(FakeResponse(status_code=422, body="bad sender"))
    monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda timeout: client)

    with pytest.raises(EmailDeliveryError, match="Resend 422: bad sender"):
        asyncio.run(
            send_valuation_email(
                lead=_lead(),
                valuation=_valuation(),
                pdf_bytes=b"%PDF-1.4 test",
            )
        )


def test_send_custom_email_posts_text_and_escaped_html(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "PropHero <noreply@example.com>")
    client = FakeAsyncClient(FakeResponse())
    monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda timeout: client)

    sent = asyncio.run(
        send_custom_email(
            to="test@example.com",
            subject="Coach note",
            body="Hola <script>alert(1)</script> & gracias",
        )
    )

    assert sent is True
    payload = client.calls[0]["json"]
    assert payload["from"] == "PropHero <noreply@example.com>"
    assert payload["to"] == ["test@example.com"]
    assert payload["subject"] == "Coach note"
    assert payload["text"] == "Hola <script>alert(1)</script> & gracias"
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; gracias" in payload["html"]
    assert "<script>" not in payload["html"]
