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


_SPANISH_MONTHS_SHORT = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sept", 10: "oct", 11: "nov", 12: "dic",
}


def _format_period_short(period: Optional[str]) -> str:
    """'2022-03' → 'mar 2022'."""
    if not period:
        return ""
    parts = period.split("-")
    if len(parts) < 2:
        return period
    try:
        year, month = int(parts[0]), int(parts[1])
        return f"{_SPANISH_MONTHS_SHORT.get(month, parts[1])} {year}"
    except ValueError:
        return period


def _render_email_html(
    lead: LeadInfo,
    valuation: ValuationResponse,
    request_payload: Optional[dict] = None,
) -> str:
    """Inline-styled HTML compatible with Gmail/Outlook/Apple Mail.

    Framework: valor → probokea → solución.
    We never show a hard sale price. We anchor on zone €/m² and appreciation,
    provoke curiosity about what the exact property is worth, then drive to the
    booking call as the only way to get a personalised answer.
    """
    stats = valuation.stats
    appreciation = valuation.market_appreciation
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
    request_payload = request_payload or {}
    m2 = request_payload.get("m2")

    # ── VALOR block ────────────────────────────────────────────────────────────
    # Primary metric: zone median €/m² + appreciation if known
    if appreciation:
        zone_ppm2 = round(appreciation.to_eur_per_m2)
        appr_pct = appreciation.pct_change * 100
        appr_sign = "+" if appr_pct >= 0 else ""
        appr_badge = f"{appr_sign}{appr_pct:.1f}% desde {_format_period_short(appreciation.from_period)}"
        town_display = escape(appreciation.town_name)
        zone_label = f"Mediana €/m² · {town_display}"
        zone_subline = f"<div style='font-size:13px;color:#0f8b5f;font-weight:700;margin-top:6px;'>{escape(appr_badge)}</div>"
    else:
        zone_ppm2 = stats.avg_price_per_m2
        zone_label = f"Mediana €/m² · {escape(municipio)}"
        zone_subline = ""

    zone_ppm2_fmt = _format_eur(zone_ppm2) + "/m²" if zone_ppm2 else "—"

    # Rough zone reference (NOT shown as the price — only as context)
    zone_ref_total: Optional[int] = round(zone_ppm2 * m2 / 1000) * 1000 if zone_ppm2 and m2 else None
    zone_ref_line = (
        f"<div style='font-size:12px;color:#8493a5;margin-top:6px;'>"
        f"Referencia de zona para {m2} m²: ~{_format_eur(zone_ref_total)}"
        f"</div>"
        if zone_ref_total
        else ""
    )

    return f"""
<!DOCTYPE html>
<html lang="es">
<body style="margin:0;padding:0;background:#f5f7f9;font-family:Inter,Arial,sans-serif;color:#1e252d;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#f5f7f9;padding:28px 14px;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #e0e7f0;box-shadow:0 8px 28px rgba(32,80,246,0.07);">

          <!-- Header -->
          <tr>
            <td style="background:#2050f6;padding:18px 28px;">
              <span style="font-size:16px;font-weight:800;color:#ffffff;letter-spacing:-0.01em;">PropHero</span>
            </td>
          </tr>

          <tr>
            <td style="padding:28px 28px 0;">
              <p style="margin:0 0 16px;font-size:16px;line-height:1.6;color:#1e252d;">Hola {greeting_name},</p>
              <p style="margin:0 0 22px;font-size:15px;line-height:1.7;color:#344454;">
                He revisado los datos de mercado para {location} y quiero compartirte
                lo que hemos encontrado.
              </p>
            </td>
          </tr>

          <!-- VALOR: zone €/m² metric -->
          <tr>
            <td style="padding:0 28px 22px;">
              <div style="background:#f0f4ff;border:1.5px solid #c7d5fb;border-radius:14px;padding:20px 22px;">
                <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.09em;color:#2050f6;font-weight:700;">{zone_label}</div>
                <div style="font-size:32px;font-weight:800;color:#1e252d;letter-spacing:-0.03em;margin:8px 0 2px;">{zone_ppm2_fmt}</div>
                {zone_subline}
                {zone_ref_line}
                <div style="font-size:12px;color:#8493a5;margin-top:8px;">Fuente: serie municipal de cierres registradores (TF Labs) / comparables Idealista.</div>
              </div>
            </td>
          </tr>

          <!-- PROBOKEA -->
          <tr>
            <td style="padding:0 28px 22px;">
              <p style="margin:0 0 12px;font-size:15px;line-height:1.7;color:#344454;">
                Este €/m² es la referencia de <strong>toda la zona</strong>. El valor real de tu
                inmueble puede variar bastante según:
              </p>
              <ul style="margin:0 0 14px;padding-left:20px;font-size:14px;line-height:1.75;color:#344454;">
                <li>La <strong>subzona exacta</strong> (playa vs. pueblo, calle principal vs. interior)</li>
                <li>El <strong>estado de conservación</strong> y si necesita reforma</li>
                <li>Si el inmueble está actualmente <strong>alquilado</strong> — el mercado lo descuenta frente a un piso vacío y entregado</li>
                <li>La <strong>fiscalidad</strong> y documentación disponible</li>
              </ul>
              <p style="margin:0;font-size:15px;line-height:1.7;color:#344454;">
                Por eso no podemos darte un precio exacto por email. Pero sí podemos
                calcularlo en 30 minutos, juntos.
              </p>
            </td>
          </tr>

          <!-- SOLUCIÓN: CTA -->
          <tr>
            <td style="padding:0 28px 24px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  <td align="center" style="background:#f45504;border-radius:14px;box-shadow:0 8px 20px rgba(244,85,4,0.22);">
                    <a href="{safe_booking_url}" style="display:block;padding:17px 22px;color:#ffffff;text-decoration:none;font-weight:800;font-size:16px;letter-spacing:-0.01em;">
                      Agendar llamada gratuita · 30 min
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:10px 0 0;text-align:center;font-size:12px;color:#9aa8b7;">Sin compromiso · Online · Experto PropHero</p>
            </td>
          </tr>

          <!-- What we'll cover -->
          <tr>
            <td style="padding:0 28px 26px;">
              <p style="margin:0 0 10px;font-size:13px;font-weight:700;color:#1e252d;">En esa llamada vemos:</p>
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  <td style="padding:4px 0;font-size:13px;color:#596b7d;">&#10003;&nbsp; Precio de salida real para <em>tu</em> propiedad</td>
                </tr>
                <tr>
                  <td style="padding:4px 0;font-size:13px;color:#596b7d;">&#10003;&nbsp; Efecto del alquiler en el precio (si aplica)</td>
                </tr>
                <tr>
                  <td style="padding:4px 0;font-size:13px;color:#596b7d;">&#10003;&nbsp; Timing de mercado y margen de negociación</td>
                </tr>
                <tr>
                  <td style="padding:4px 0;font-size:13px;color:#596b7d;">&#10003;&nbsp; Fiscalidad y pasos operativos</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Disclaimer -->
          <tr>
            <td style="background:#f8f9fb;padding:16px 28px;border-top:1px solid #edf0f5;">
              <p style="margin:0;font-size:11px;color:#9aa8b7;line-height:1.55;">
                Los datos de zona son una referencia de mercado, no una tasación oficial.
                El valor trasladado asume el inmueble <strong>vacío y en buen estado</strong>;
                si está alquilado, el precio de mercado libre puede diferir. PDF adjunto con metodología completa.
              </p>
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
                  <div style="margin:0 0 8px;font-size:16px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#2050f6;">{escape(lines[0])}</div>
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
    request_payload: Optional[dict] = None,
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
    subject = f"Los datos de zona para tu inmueble en {municipio} — PropHero"
    attachment_name = f"prophero-valoracion-{date.today().isoformat()}.pdf"

    payload = {
        "from": sender,
        "to": [_recipient_for_delivery(lead.email)],
        "subject": subject,
        "html": _render_email_html(lead, valuation, request_payload),
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
