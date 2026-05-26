"""Email delivery via Resend.

Why Resend (over SES/SendGrid/Mailgun):
- Cleanest REST API, no SDK install needed (httpx is already a dep).
- 3000 emails/month free tier covers MVP and small production.
- Verified domain → DKIM/SPF auto-configured.

The module is intentionally tiny — one public coroutine `send_valuation_email`
that posts the HTML email + PDF attachment to Resend's API. If `RESEND_API_KEY`
is unset we log a warning and skip silently (useful in dev where you don't
want to spam test inboxes).
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import date
from typing import Optional

import httpx

from models import LeadInfo, ValuationResponse

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_BOOKING_URL = "https://prophero.com"


def _recipient_for_delivery(actual_to: str) -> str:
    """Route all mail to a test inbox when RESEND_TEST_TO is set."""
    test_to = os.environ.get("RESEND_TEST_TO", "").strip()
    if test_to:
        logger.info("RESEND_TEST_TO set — routing email for %s to %s", actual_to, test_to)
        return test_to
    return actual_to


class EmailDeliveryError(Exception):
    """Raised when Resend returns a non-2xx response."""


def _format_eur(value: Optional[int]) -> str:
    if value is None:
        return "—"
    return f"{int(value):,} €".replace(",", ".")


def _render_email_html(lead: LeadInfo, valuation: ValuationResponse) -> str:
    """Inline-styled HTML compatible with Gmail/Outlook/Apple Mail."""
    stats = valuation.stats
    estimated = _format_eur(stats.estimated_value)
    range_str = (
        f"{_format_eur(stats.price_range_low)} – {_format_eur(stats.price_range_high)}"
        if stats.price_range_low and stats.price_range_high
        else "—"
    )
    municipio = valuation.municipio.name
    address = valuation.municipio.road or municipio
    booking_url = os.environ.get("PROPHERO_BOOKING_URL", DEFAULT_BOOKING_URL)
    first_name = lead.full_name.split(" ", 1)[0] if lead.full_name else ""

    return f"""
<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:0;background:#f5f7f9;font-family:Inter,system-ui,sans-serif;color:#1e252d;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f5f7f9;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(32,80,246,0.06);">
          <tr>
            <td style="padding:24px 32px;border-bottom:1px solid rgba(32,80,246,0.18);">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  <td>
                    <span style="display:inline-block;width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#2050f6,#65c6eb);vertical-align:middle;"></span>
                    <span style="font-weight:700;font-size:16px;letter-spacing:-0.01em;margin-left:8px;vertical-align:middle;">PropHero</span>
                  </td>
                  <td align="right" style="font-size:11px;color:#abb8c7;letter-spacing:0.04em;text-transform:uppercase;">
                    Reporte preliminar
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <p style="margin:0 0 8px;font-size:14px;color:#596b7d;">Hola {first_name or lead.full_name},</p>
              <p style="margin:0 0 24px;font-size:14px;line-height:1.6;">
                Adjuntamos tu valoración preliminar para
                <strong>{address}</strong>{f", {municipio}" if address != municipio else ""}.
                Es una primera lectura cuantitativa del mercado — útil como referencia,
                pero todavía no es tu plan de salida.
              </p>

              <div style="background:#f3f5fe;border:1px solid rgba(32,80,246,0.18);border-radius:12px;padding:24px;text-align:center;">
                <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.08em;color:#596b7d;font-weight:600;">Valor estimado</div>
                <div style="font-size:32px;font-weight:700;color:#1e252d;letter-spacing:-0.02em;margin:8px 0 4px;">{estimated}</div>
                <div style="font-size:13px;color:#596b7d;">Rango: {range_str}</div>
                <div style="font-size:11px;color:#abb8c7;margin-top:8px;">Basado en {stats.total_comparables} comparables analizados en tiempo real</div>
              </div>

              <p style="margin:28px 0 8px;font-size:14px;line-height:1.6;">
                En el PDF adjunto vas a encontrar los comparables uno por uno, la
                metodología y el rango de mercado para tu microzona.
              </p>

              <div style="margin:24px 0 8px;padding:20px 22px;background:#ffffff;border:1px solid rgba(32,80,246,0.18);border-left:3px solid #2050f6;border-radius:8px;">
                <div style="font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#162eb7;">Próximo paso</div>
                <p style="margin:6px 0 12px;font-size:15px;font-weight:600;color:#1e252d;line-height:1.4;">
                  Diseñá tu plan de salida con un asesor de PropHero
                </p>
                <p style="margin:0 0 14px;font-size:13px;line-height:1.6;color:#596b7d;">
                  30 minutos, sin compromiso. Revisamos juntos timing de mercado,
                  fiscalidad, alternativas a la venta directa (alquiler, permuta,
                  reinversión) y cuál es el precio de salida realista para tu caso —
                  no el del algoritmo.
                </p>
                <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                  <tr>
                    <td style="background:#f45504;border-radius:999px;">
                      <a href="{booking_url}" style="display:inline-block;padding:12px 28px;color:#ffffff;text-decoration:none;font-weight:600;font-size:14px;">Agendar llamada</a>
                    </td>
                  </tr>
                </table>
              </div>

              <p style="margin:24px 0 0;font-size:13px;line-height:1.6;color:#596b7d;">
                Si preferís, también podés responder este email con tus dudas y te
                contesta directamente un asesor.
              </p>

              <p style="margin:28px 0 0;font-size:12px;color:#abb8c7;line-height:1.6;">
                Esta valoración es una estimación automatizada basada en datos públicos.
                No sustituye a una tasación oficial ni a asesoramiento fiscal o legal —
                los precios reales pueden variar según condición, documentación, vistas
                y negociación.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background:#f5f7f9;padding:16px 32px;text-align:center;font-size:11px;color:#abb8c7;">
              PropHero · Valoración automatizada con datos en tiempo real
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
""".strip()


async def send_valuation_email(
    *,
    lead: LeadInfo,
    valuation: ValuationResponse,
    pdf_bytes: bytes,
) -> None:
    """Send the branded valuation email with the PDF attached.

    No-op (with a warning log) if `RESEND_API_KEY` is unset — convenient for
    local dev where we don't want to actually send mail.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.warning(
            "RESEND_API_KEY not set — skipping email send to %s. "
            "The PDF was generated and persisted, just not delivered.",
            lead.email,
        )
        return

    sender = os.environ.get("RESEND_FROM_EMAIL", "PropHero <noreply@prophero.com>")
    municipio = valuation.municipio.name
    subject = f"Tu valoración preliminar PropHero — {municipio}"
    attachment_name = f"prophero-valoracion-{date.today().isoformat()}.pdf"

    payload = {
        "from": sender,
        "to": [_recipient_for_delivery(lead.email)],
        "subject": subject,
        "html": _render_email_html(lead, valuation),
        "attachments": [
            {
                "filename": attachment_name,
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
            }
        ],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 300:
        body = response.text[:500]
        logger.error("Resend rejected the request (%d): %s", response.status_code, body)
        raise EmailDeliveryError(f"Resend {response.status_code}: {body}")

    message_id = response.json().get("id")
    logger.info("Email sent to %s via Resend (id=%s)", lead.email, message_id)


async def send_custom_email(
    *,
    to: str,
    subject: str,
    body: str,
    attachment_filename: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
) -> bool:
    """Send an editable plain-text/HTML email from the coach interface.

    Returns False when RESEND_API_KEY is unset so local dev can exercise the
    flow without sending real email.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY not set — skipping coach email send to %s", to)
        return False

    sender = os.environ.get("RESEND_FROM_EMAIL", "PropHero <noreply@prophero.com>")
    html = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = "<br>".join(html.splitlines())
    payload = {
        "from": sender,
        "to": [_recipient_for_delivery(to)],
        "subject": subject,
        "text": body,
        "html": f"<div style=\"font-family:Inter,system-ui,sans-serif;line-height:1.6;color:#1e252d;\">{html}</div>",
    }
    if attachment_filename and attachment_bytes is not None:
        payload["attachments"] = [
            {
                "filename": attachment_filename,
                "content": base64.b64encode(attachment_bytes).decode("ascii"),
            }
        ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if response.status_code >= 300:
        body_preview = response.text[:500]
        logger.error("Resend rejected coach email (%d): %s", response.status_code, body_preview)
        raise EmailDeliveryError(f"Resend {response.status_code}: {body_preview}")

    message_id = response.json().get("id")
    logger.info("Coach email sent to %s via Resend (id=%s)", to, message_id)
    return True
