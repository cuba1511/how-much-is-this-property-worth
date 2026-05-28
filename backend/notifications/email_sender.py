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
from html import escape
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
    greeting_name = escape(first_name or lead.full_name or "ahí")
    safe_address = escape(address)
    safe_municipio = escape(municipio)
    safe_booking_url = escape(booking_url, quote=True)
    location = (
        f"<strong>{safe_address}</strong>{f', {safe_municipio}' if address != municipio else ''}"
    )

    return f"""
<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:0;background:#f7f4ef;font-family:Inter,Arial,sans-serif;color:#1e252d;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f7f4ef;padding:28px 14px;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #eadfd2;box-shadow:0 12px 36px rgba(30,37,45,0.08);">
          <tr>
            <td style="padding:26px 28px 30px;">
              <p style="margin:0 0 14px;font-size:16px;line-height:1.55;color:#1e252d;">Hola {greeting_name},</p>
              <p style="margin:0 0 18px;font-size:16px;line-height:1.65;color:#344454;">
                Te dejo una primera lectura de {location}. Hemos preparado el PDF
                adjunto con los comparables y la metodología por si querés mirarlo con calma.
              </p>

              <div style="background:#fff7ed;border:1px solid #ffd3b8;border-radius:14px;padding:22px 20px;margin:0 0 22px;">
                <div style="font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:#a14300;font-weight:700;">Estimación inicial</div>
                <div style="font-size:34px;font-weight:800;color:#1e252d;letter-spacing:-0.03em;margin:8px 0 4px;">{estimated}</div>
                <div style="font-size:14px;line-height:1.5;color:#596b7d;">Rango orientativo: {range_str}</div>
                <div style="font-size:12px;color:#8493a5;margin-top:8px;">Basado en {stats.total_comparables} comparables recientes.</div>
              </div>

              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:0 0 22px;">
                <tr>
                  <td align="center" style="background:#f45504;border-radius:14px;box-shadow:0 8px 20px rgba(244,85,4,0.25);">
                    <a href="{safe_booking_url}" style="display:block;padding:16px 22px;color:#ffffff;text-decoration:none;font-weight:800;font-size:16px;letter-spacing:-0.01em;">Agendar una llamada de 30 min</a>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 18px;font-size:15px;line-height:1.65;color:#344454;">
                Si te encaja, en esa llamada vemos si el precio tiene sentido,
                qué margen de negociación habría y qué pasos conviene dar.
                Sin compromiso.
              </p>

              <p style="margin:0 0 22px;font-size:15px;line-height:1.65;color:#344454;">
                Y si preferís, respondé a este correo con cualquier duda y te
                contestamos por aquí.
              </p>

              <p style="margin:0;font-size:12px;color:#9aa8b7;line-height:1.55;">
                Esta valoración es una estimación automatizada basada en datos públicos.
                No sustituye a una tasación oficial ni a asesoramiento fiscal o legal.
              </p>
            </td>
          </tr>
          <tr>
            <td style="background:#fbfaf8;padding:14px 28px;text-align:center;font-size:12px;color:#9aa8b7;">
              PropHero · PDF adjunto con tu valoración
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
""".strip()


def _split_text_blocks(body: str) -> list[list[str]]:
    """Split plain text into non-empty blocks separated by blank lines."""
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw_line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _looks_like_section_heading(line: str) -> bool:
    """Coach emails use short, punctuation-free first lines as section titles."""
    stripped = line.strip()
    return (
        len(stripped) <= 80
        and stripped[-1:] not in {".", ",", ";", ":", "!", "?", ")"}
        and not stripped.lower().startswith(("hola ", "un saludo", "saludos"))
    )


def _render_lines(lines: list[str]) -> str:
    return "<br>".join(escape(line) for line in lines)


def _render_custom_email_html(body: str) -> str:
    """Render coach-authored plain text as a readable branded HTML email."""
    blocks = _split_text_blocks(body)
    rendered_blocks: list[str] = []

    for index, lines in enumerate(blocks):
        if len(lines) > 1 and _looks_like_section_heading(lines[0]):
            rendered_blocks.append(
                f"""
                <div style="padding:18px 0;border-top:1px solid #e7edf5;">
                  <div style="margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#2050f6;">{escape(lines[0])}</div>
                  <p style="margin:0;font-size:15px;line-height:1.7;color:#344454;">{_render_lines(lines[1:])}</p>
                </div>
                """.strip()
            )
            continue

        margin_top = "0" if index == 0 else "16px"
        rendered_blocks.append(
            f'<p style="margin:{margin_top} 0 0;font-size:15px;line-height:1.7;color:#344454;">{_render_lines(lines)}</p>'
        )

    content = "\n".join(rendered_blocks)
    return f"""
<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:0;background:#f5f7f9;font-family:Inter,Arial,sans-serif;color:#1e252d;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f5f7f9;padding:28px 14px;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="640" style="max-width:640px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e7edf5;">
          <tr>
            <td style="padding:28px;">
              {content}
            </td>
          </tr>
          <tr>
            <td style="background:#f5f7f9;padding:16px 28px;text-align:center;font-size:12px;color:#8493a5;">
              PropHero · Informe adjunto en PDF
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
    subject = f"Tu propiedad podría haber ganado valor — {municipio}"
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
    payload = {
        "from": sender,
        "to": [_recipient_for_delivery(to)],
        "subject": subject,
        "text": body,
        "html": _render_custom_email_html(body),
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
