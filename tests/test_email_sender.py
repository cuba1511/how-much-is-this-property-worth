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
    MarketAppreciation,
    MunicipioInfo,
    SearchMetadata,
    SearchStageResult,
    TransactionDetail,
    ValuationResponse,
    ValuationStats,
)
from notifications import email_sender  # noqa: E402
from notifications.email_sender import (  # noqa: E402
    EmailDeliveryError,
    send_custom_email,
    send_valuation_email,
)


@pytest.fixture(autouse=True)
def _disable_resend_test_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RESEND_TEST_EMAIL_MODE", raising=False)
    monkeypatch.delenv("RESEND_TEST_EMAIL_TO", raising=False)


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
            name="massamagrell",
            slug="massamagrell",
            province="Valencia",
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
        market_appreciation=MarketAppreciation(
            town_name="Massamagrell",
            settlement_date="2021-05-15",
            from_period="2021-05",
            from_eur_per_m2=4_000,
            to_period="2025-12",
            to_eur_per_m2=4_600,
            pct_change=0.15,
            months_elapsed=55,
            sample_quality="exact",
            resolution_strategy="name_match",
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
        transaction_name="Test User",
        address="Calle Granada",
        final_total_price=92_100,
        landsize_m2=100,
        purchase_eur_per_m2=921,
        raw_fields={},
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
    monkeypatch.setenv("RESEND_REPLY_TO", "divestments@erkaugaruu.resend.app")
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
    assert payload["reply_to"] == "divestments@erkaugaruu.resend.app"
    assert payload["subject"] == (
        "Tu propiedad en Massamagrell muestra una posible señal de revalorización"
    )
    assert "Hola Test" in payload["html"]
    assert "4.000 €/m²" in payload["html"]
    assert "4.600 €/m²" in payload["html"]
    assert "+15,0%" in payload["html"]
    assert "Descubre cuánto vale tu propiedad hoy" in payload["html"]
    assert f'cid:{email_sender.LOGO_CONTENT_ID}' in payload["html"]
    assert any(
        a.get("content_id") == email_sender.LOGO_CONTENT_ID
        for a in payload["attachments"]
    )
    assert payload["attachments"][0]["filename"].startswith("prophero-valoracion-")
    assert payload["attachments"][0]["filename"].endswith(".pdf")
    assert payload["attachments"][0]["content"] == base64.b64encode(b"%PDF-1.4 test").decode(
        "ascii"
    )


def test_send_valuation_email_can_route_to_test_inbox(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_TEST_EMAIL_TO", "qa@example.com")
    client = FakeAsyncClient(FakeResponse())
    monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda timeout: client)

    asyncio.run(
        send_valuation_email(
            lead=_lead(),
            valuation=_valuation(),
            pdf_bytes=b"%PDF-1.4 test",
            test_mode=True,
        )
    )

    payload = client.calls[0]["json"]
    assert payload["to"] == ["qa@example.com"]


def test_send_custom_email_uses_real_purchase_ppm2_when_transaction_is_available(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    client = FakeAsyncClient(FakeResponse())
    monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda timeout: client)

    valuation = _valuation()
    valuation.market_appreciation.from_eur_per_m2 = 1_169
    valuation.market_appreciation.to_eur_per_m2 = 1_200

    asyncio.run(
        send_custom_email(
            to="test@example.com",
            subject="Informe",
            body="Plain body",
            recipient_name="Test User",
            valuation=valuation,
            transaction=_transaction(),
        )
    )

    html = client.calls[0]["json"]["html"]
    assert "Pagaste &middot; compra" in html
    assert "921 €/m²" in html
    assert "1.200 €/m²" in html
    assert "€/m² real pagado" in html
    assert "1.169 €/m²" not in html


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
    monkeypatch.setenv("RESEND_REPLY_TO", "coach@erkaugaruu.resend.app")
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
    assert payload["reply_to"] == "coach@erkaugaruu.resend.app"
    assert payload["subject"] == "Coach note"
    assert payload["text"] == "Hola <script>alert(1)</script> & gracias"
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; gracias" in payload["html"]
    assert "<script>" not in payload["html"]


def test_send_custom_email_respects_global_test_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("RESEND_TEST_EMAIL_MODE", "true")
    monkeypatch.setenv("RESEND_TEST_EMAIL_TO", "qa@example.com")
    client = FakeAsyncClient(FakeResponse())
    monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda timeout: client)

    sent = asyncio.run(
        send_custom_email(
            to="client@example.com",
            subject="Coach note",
            body="Plain body",
        )
    )

    assert sent is True
    assert client.calls[0]["json"]["to"] == ["qa@example.com"]


def test_send_custom_email_formats_coach_sections_for_gmail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    client = FakeAsyncClient(FakeResponse())
    monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda timeout: client)

    body = "\n".join(
        [
            "Hola Paola,",
            "",
            "El PDF adjunto contiene todos los datos.",
            "",
            "Posible revalorización",
            "Hemos preparado una estimación inicial.",
            "La ganancia potencial estimada estaría entre 65.770 € y 74.770 €.",
            "",
            "Un saludo,",
            "PropHero",
        ]
    )

    asyncio.run(
        send_custom_email(
            to="test@example.com",
            subject="Coach note",
            body=body,
        )
    )

    payload = client.calls[0]["json"]
    assert payload["text"] == body
    assert "text-transform:uppercase" in payload["html"]
    assert "Posible revalorización" in payload["html"]
    assert "Hemos preparado una estimación inicial.<br>La ganancia potencial" in payload["html"]
    # Only the inline Content-ID logo is allowed; no remote/tracking images.
    assert 'src="http' not in payload["html"]
    assert payload["html"].count("<img") == 1
    assert f'cid:{email_sender.LOGO_CONTENT_ID}' in payload["html"]
    assert "font-size:22px;line-height:1;font-weight:800" not in payload["html"]
    assert "PropHero" in payload["html"]


def test_send_custom_email_can_attach_pdf(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    client = FakeAsyncClient(FakeResponse())
    monkeypatch.setattr(email_sender.httpx, "AsyncClient", lambda timeout: client)

    sent = asyncio.run(
        send_custom_email(
            to="test@example.com",
            subject="Coach note",
            body="Plain body",
            attachment_filename="report.pdf",
            attachment_bytes=b"%PDF-1.4 coach",
        )
    )

    assert sent is True
    payload = client.calls[0]["json"]
    assert payload["attachments"][0] == {
        "filename": "report.pdf",
        "content": base64.b64encode(b"%PDF-1.4 coach").decode("ascii"),
    }
    # Inline logo is appended as a Content-ID attachment referenced via cid:.
    logo_attachments = [
        a for a in payload["attachments"] if a.get("content_id") == email_sender.LOGO_CONTENT_ID
    ]
    assert len(logo_attachments) == 1
    assert f'cid:{email_sender.LOGO_CONTENT_ID}' in payload["html"]

