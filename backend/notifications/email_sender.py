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
import re
from datetime import date
from html import escape
from pathlib import Path
from typing import Optional

import httpx

from models import LeadInfo, TransactionDetail, ValuationResponse

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_BOOKING_URL = "https://meetings-eu1.hubspot.com/ide-la-cuba"
DEFAULT_TEST_EMAIL_TO = "ignacio.delacuba@prophero.com"
_RUNTIME_TEST_EMAIL_MODE: Optional[bool] = None

# Inline PropHero wordmark. Email clients (Gmail/Outlook) don't render inline
# SVG, so we ship a pre-rasterized PNG and attach it inline via a Content-ID
# referenced in the HTML as ``cid:prophero-logo``. Regenerate the PNG with
# ``python -m notifications._gen_logo_png`` if the source SVG changes.
LOGO_CONTENT_ID = "prophero-logo"
_LOGO_PATH = Path(__file__).parent / "assets" / "prophero-logo.png"


def _load_logo_b64() -> str:
    try:
        return base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
    except OSError as exc:  # pragma: no cover - logo is shipped with the package
        logger.warning("PropHero email logo not found at %s: %s", _LOGO_PATH, exc)
        return ""


PROPHERO_LOGO_B64 = _load_logo_b64()


def _logo_attachment() -> Optional[dict]:
    """Inline-image attachment (Content-ID) for the email header logo."""
    if not PROPHERO_LOGO_B64:
        return None
    return {
        "filename": "prophero-logo.png",
        "content": PROPHERO_LOGO_B64,
        "content_id": LOGO_CONTENT_ID,
        "content_type": "image/png",
    }


def _logo_img_tag(*, height: int = 22) -> str:
    """`<img>` referencing the inline logo, with a text fallback for safety."""
    if not PROPHERO_LOGO_B64:
        return (
            '<span style="font-family:Inter,Arial,Helvetica,sans-serif;font-size:17px;'
            'font-weight:700;color:#0E0E0F;letter-spacing:-0.02em;">PropHero</span>'
        )
    return (
        f'<img src="cid:{LOGO_CONTENT_ID}" alt="PropHero" height="{height}" '
        f'style="display:block;height:{height}px;width:auto;border:0;outline:none;'
        'text-decoration:none;" />'
    )


def _reply_to_for_delivery() -> Optional[str]:
    """Optional reply inbox for client responses."""
    reply_to = os.environ.get("RESEND_REPLY_TO", "").strip()
    return reply_to or None


def _env_truthy(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def test_email_recipient() -> str:
    """Inbox used when Resend test mode is enabled."""
    return os.environ.get("RESEND_TEST_EMAIL_TO", DEFAULT_TEST_EMAIL_TO).strip() or DEFAULT_TEST_EMAIL_TO


def is_test_email_mode_enabled() -> bool:
    """Runtime global test-mode flag, falling back to environment config."""
    if _RUNTIME_TEST_EMAIL_MODE is not None:
        return _RUNTIME_TEST_EMAIL_MODE
    return _env_truthy("RESEND_TEST_EMAIL_MODE")


def set_test_email_mode(enabled: bool) -> bool:
    """Set the process-wide email test mode from the coach UI."""
    global _RUNTIME_TEST_EMAIL_MODE
    _RUNTIME_TEST_EMAIL_MODE = enabled
    return enabled


def delivery_recipient(requested_to: str, *, test_mode: bool = False) -> tuple[str, bool]:
    """Return the actual recipient and whether test routing was applied."""
    if test_mode or is_test_email_mode_enabled():
        return test_email_recipient(), True
    return requested_to, False


class EmailDeliveryError(Exception):
    """Raised when Resend returns a non-2xx response."""


def _format_eur_per_m2(value: Optional[float | int]) -> str:
    if value is None:
        return "—"
    return f"{round(value):,} €/m²".replace(",", ".")


def _format_num(value: Optional[float | int]) -> str:
    if value is None:
        return "—"
    return f"{round(value):,}".replace(",", ".")


def _format_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    formatted = f"{value:.1f}".replace(".", ",")
    return f"{sign}{formatted}%"


def _transaction_purchase_eur_per_m2(transaction: Optional[TransactionDetail]) -> Optional[int]:
    if transaction is None:
        return None
    if transaction.purchase_eur_per_m2 is not None:
        return transaction.purchase_eur_per_m2
    if transaction.final_total_price and transaction.landsize_m2:
        return round(transaction.final_total_price / transaction.landsize_m2)
    return None


def _format_place_name(value: Optional[str]) -> str:
    return (value or "").strip().title()


def _render_email_html(
    recipient_name: Optional[str],
    valuation: ValuationResponse,
    request_payload: Optional[dict] = None,
    transaction: Optional[TransactionDetail] = None,
) -> str:
    """Inline-styled HTML compatible with Gmail/Outlook/Apple Mail.

    Design: Variation C from the PropHero design system — dark highlighted
    panel with blue glow, municipal appreciation as the headline number,
    comparison grid on the dark card, and subdued disclaimer note.

    ``recipient_name`` is just the greeting name (full name string); the coach
    flow may not have a complete ``LeadInfo``, so we only take the name.
    """
    stats = valuation.stats
    appreciation = valuation.market_appreciation
    municipio = _format_place_name(valuation.municipio.name)
    address = valuation.municipio.road or municipio
    booking_url = os.environ.get("PROPHERO_BOOKING_URL", DEFAULT_BOOKING_URL)
    full_name = (recipient_name or "").strip()
    first_name = full_name.split(" ", 1)[0] if full_name else ""
    greeting_name = escape(first_name or full_name or "ahí")
    safe_address = escape(address)
    safe_municipio = escape(municipio)
    safe_booking_url = escape(booking_url, quote=True)
    request_payload = request_payload or {}

    postcode = valuation.municipio.postcode or ""
    has_full_address = address != municipio
    if has_full_address and postcode:
        address_line = f"{safe_address} &middot; {safe_municipio}, {escape(postcode)}"
    elif has_full_address:
        address_line = f"{safe_address} &middot; {safe_municipio}"
    else:
        address_line = safe_municipio

    purchase_ppm2 = _transaction_purchase_eur_per_m2(transaction)
    if appreciation:
        current_val = _format_eur_per_m2(appreciation.to_eur_per_m2)
        if purchase_ppm2 is not None and purchase_ppm2 > 0:
            purchase_val = _format_eur_per_m2(purchase_ppm2)
            purchase_label = "Pagaste &middot; compra"
            comparison_note = (
                f"La cifra de compra es tu <strong style=\"font-weight:500;color:#2E2E30;\">€/m² real pagado</strong>; "
                f"el dato de mercado hoy refleja la <strong style=\"font-weight:500;color:#2E2E30;\">mediana del municipio</strong> "
                f"de {safe_municipio}. La ubicación exacta, planta, orientación y estado pueden situar tu caso por encima o por debajo de la mediana."
            )
            variation_pct = ((appreciation.to_eur_per_m2 - purchase_ppm2) / purchase_ppm2) * 100
        else:
            purchase_val = _format_eur_per_m2(appreciation.from_eur_per_m2)
            purchase_label = "Zona &middot; compra"
            comparison_note = (
                f"Ambas cifras reflejan la <strong style=\"font-weight:500;color:#2E2E30;\">mediana del municipio</strong> "
                f"de {safe_municipio}, no el valor específico de tu inmueble. La ubicación exacta, planta, orientación y estado pueden situar tu caso por encima o por debajo de la mediana."
            )
            variation_pct = appreciation.pct_change * 100
        variation = _format_pct(variation_pct)
    else:
        purchase_val = "—"
        purchase_label = "Compra"
        current_val = _format_eur_per_m2(stats.avg_price_per_m2)
        variation = "no disponible"
        comparison_note = (
            "El dato de mercado disponible es una referencia agregada, no el valor específico de tu inmueble. "
            "La ubicación exacta, planta, orientación y estado pueden situar tu caso por encima o por debajo."
        )

    if appreciation:
        is_positive = not variation.startswith("-")
        revalorizacion_text = (
            "Tu referencia de compra queda por debajo del mercado actual."
            if is_positive
            else "Tu referencia de compra queda por encima del mercado actual."
        )
    else:
        revalorizacion_text = "Tenemos una referencia de mercado para revisar contigo."

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
</head>
<body style="margin:0;padding:0;background:#EFEFF2;font-family:Inter,Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#EFEFF2;padding:32px 16px;">
  <tr>
    <td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;width:100%;background:#FFFFFF;border-radius:18px;overflow:hidden;border:1px solid #E3E3E7;">

        <!-- ── Header ── -->
        <tr>
          <td style="padding:20px 32px 18px;border-bottom:1px solid #E3E3E7;background:#FFFFFF;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td style="vertical-align:middle;">
                  {_logo_img_tag(height=22)}
                </td>
                <td align="right" style="vertical-align:middle;">
                  <span style="display:block;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#2E2E30;font-weight:500;">Actualización de mercado</span>
                  <span style="display:block;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A9AA0;">Data &amp; Divestments</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ── Body ── -->
        <tr>
          <td style="padding:40px 32px 32px;">

            <!-- Greeting -->
            <p style="margin:0 0 20px;font-family:Inter,Arial,Helvetica,sans-serif;font-size:18px;font-weight:500;line-height:1.3;color:#0E0E0F;letter-spacing:-0.01em;">Hola {greeting_name},</p>

            <!-- Intro with inline address -->
            <p style="margin:0 0 20px;font-family:Inter,Arial,Helvetica,sans-serif;font-size:15px;line-height:1.65;color:#4A4A4D;">Desde el equipo de Data &amp; Divestments de PropHero queremos compartirte una actualización sobre tu propiedad en <strong style="font-weight:500;color:#0E0E0F;">{address_line}</strong>. Hemos analizado la evolución del mercado y encontramos una señal positiva:</p>

            <!-- ── Dark hero stat card (heroC) ── -->
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-radius:12px;overflow:hidden;margin-top:8px;">

              <!-- Main stat area — dark bg with blue glow from top-right -->
              <tr>
                <td style="background:#0E0E0F;background-image:radial-gradient(ellipse at 85% 0%,rgba(32,80,246,0.4) 0%,transparent 60%);padding:32px 32px 24px;">
                  <p style="margin:0 0 16px;font-family:'Courier New',Courier,monospace;font-size:11px;letter-spacing:0.12em;text-transform:uppercase;color:#99B0FB;">{safe_municipio.upper()} &middot; COMPRA VS MERCADO HOY</p>
                  <p style="margin:0;font-family:Inter,Arial,Helvetica,sans-serif;font-size:68px;line-height:0.95;letter-spacing:-0.035em;font-weight:600;color:#5B7EF9;">{variation}</p>
                  <p style="margin:16px 0 24px;font-family:Inter,Arial,Helvetica,sans-serif;font-size:18px;line-height:1.22;letter-spacing:-0.01em;color:#FFFFFF;font-weight:500;">{revalorizacion_text}</p>

                  <!-- Comparison row -->
                  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-top:1px solid rgba(255,255,255,0.14);">
                    <tr>
                      <td style="padding:20px 0 0;vertical-align:top;">
                        <p style="margin:0 0 5px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:rgba(255,255,255,0.5);">{purchase_label}</p>
                        <p style="margin:0;font-family:'Courier New',Courier,monospace;font-size:18px;font-weight:500;color:#FFFFFF;">{purchase_val}</p>
                      </td>
                      <td style="padding:20px 20px 0;text-align:center;vertical-align:middle;">
                        <span style="font-family:Inter,Arial,Helvetica,sans-serif;font-size:18px;color:rgba(255,255,255,0.3);">&rarr;</span>
                      </td>
                      <td style="padding:20px 0 0;vertical-align:top;">
                        <p style="margin:0 0 5px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:rgba(255,255,255,0.5);">Mercado hoy &middot; mediana</p>
                        <p style="margin:0;font-family:'Courier New',Courier,monospace;font-size:18px;font-weight:500;color:#FFFFFF;">{current_val}</p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>

            </table>

            <!-- Disclaimer note -->
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:20px 0 0;">
              <tr>
                <td style="background:#F4F4F6;border:1px solid #E3E3E7;border-radius:8px;padding:16px 20px;">
                  <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                    <tr>
                      <td style="font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#6B6B6F;vertical-align:top;white-space:nowrap;padding-right:16px;padding-top:2px;">Nota</td>
                      <td style="font-family:Inter,Arial,Helvetica,sans-serif;font-size:13px;line-height:1.5;color:#4A4A4D;">{comparison_note}</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>

            <!-- Divider -->
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:28px 0;">
              <tr><td style="height:1px;background:#F1F1F3;font-size:1px;line-height:1px;">&nbsp;</td></tr>
            </table>

            <!-- Section: ¿Qué significa esto para ti? -->
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 16px;">
              <tr>
                <td style="font-family:'Courier New',Courier,monospace;font-size:11px;color:#2050F6;letter-spacing:0.12em;padding-right:12px;vertical-align:baseline;">&rarr;</td>
                <td style="font-family:Inter,Arial,Helvetica,sans-serif;font-size:15px;font-weight:600;color:#0E0E0F;letter-spacing:-0.01em;vertical-align:baseline;">¿Qué significa esto para ti?</td>
              </tr>
            </table>

            <!-- Body paragraph -->
            <p style="margin:0 0 14px;font-family:Inter,Arial,Helvetica,sans-serif;font-size:15px;line-height:1.65;color:#4A4A4D;">Si quieres explorar cómo aprovechar la revalorización de {safe_municipio} y sacar capital de tu inmueble, podemos ayudarte a aterrizarlo con números reales. Como cliente de PropHero tienes a tu disposición nuestro equipo de expertos y tasadores oficiales para revisar tu caso y valorar las mejores opciones para tu propiedad.</p>
            <p style="margin:0 0 24px;font-family:Inter,Arial,Helvetica,sans-serif;font-size:15px;line-height:1.65;color:#4A4A4D;">En 30 minutos te damos una estimación real, basada en tu inmueble concreto — no en promedios.</p>

            <!-- CTA button -->
            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="background:#2050F6;border-radius:8px;">
                  <a href="{safe_booking_url}" style="display:inline-block;padding:14px 24px;font-family:Inter,Arial,Helvetica,sans-serif;font-size:15px;font-weight:500;color:#FFFFFF;text-decoration:none;letter-spacing:-0.01em;white-space:nowrap;">Descubre cuánto vale tu propiedad hoy &rarr;</a>
                </td>
              </tr>
            </table>
            <p style="margin:12px 0 0;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:0.04em;text-transform:uppercase;color:#9A9AA0;">30 min &middot; Gratis &middot; Expertos y tasadores oficiales</p>

            <!-- Signature -->
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:28px 0 0;">
              <tr>
                <td style="width:38px;height:38px;background:#0E0E0F;border-radius:999px;text-align:center;vertical-align:middle;min-width:38px;">
                  <span style="font-family:'Courier New',Courier,monospace;font-size:13px;font-weight:500;color:#FFFFFF;letter-spacing:0.04em;">PH</span>
                </td>
                <td style="padding-left:12px;vertical-align:middle;">
                  <strong style="display:block;font-family:Inter,Arial,Helvetica,sans-serif;font-size:13px;font-weight:500;color:#0E0E0F;line-height:1.4;">Equipo Data &amp; Divestments</strong>
                  <span style="font-family:Inter,Arial,Helvetica,sans-serif;font-size:13px;color:#6B6B6F;">PropHero</span>
                </td>
              </tr>
            </table>

          </td>
        </tr>

        <!-- ── Footer ── -->
        <tr>
          <td style="border-top:1px solid #E3E3E7;background:#FAFAFB;padding:18px 32px;">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td style="font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A9AA0;">PropHero</td>
                <td align="right" style="font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A9AA0;">Informe completo adjunto en PDF</td>
              </tr>
            </table>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>""".strip()


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
        and stripped[-1:] not in {".", ",", ";", ":", "!", ")"}
        and not stripped.lower().startswith(("hola ", "un saludo", "saludos"))
    )


_URL_RE = re.compile(r"(https?://[^\s\[\]<>]+)")


def _linkify_line(line: str) -> str:
    """Escape a line for HTML, turning bare URLs into clickable <a> tags."""
    parts: list[str] = []
    last = 0
    for m in _URL_RE.finditer(line):
        parts.append(escape(line[last : m.start()]))
        url = m.group(1)
        parts.append(
            f'<a href="{escape(url, quote=True)}" '
            f'style="color:#2050F6;font-weight:500;text-decoration:none;">'
            f"{escape(url)}</a>"
        )
        last = m.end()
    parts.append(escape(line[last:]))
    return "".join(parts)


def _render_lines(lines: list[str]) -> str:
    return "<br>".join(_linkify_line(line) for line in lines)


def _render_custom_email_html(body: str) -> str:
    """Render coach-authored plain text as a readable branded HTML email."""
    blocks = _split_text_blocks(body)
    rendered_blocks: list[str] = []

    for index, lines in enumerate(blocks):
        if len(lines) > 1 and _looks_like_section_heading(lines[0]):
            rendered_blocks.append(
                f"""
                <div style="padding:12px 0;border-top:1px solid #e7edf5;">
                  <div style="margin:0 0 6px;font-size:14px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;color:#2050f6;">{escape(lines[0])}</div>
                  <p style="margin:0;font-size:14px;line-height:1.55;color:#344454;">{_render_lines(lines[1:])}</p>
                </div>
                """.strip()
            )
            continue

        margin_top = "0" if index == 0 else "10px"
        rendered_blocks.append(
            f'<p style="margin:{margin_top} 0 0;font-size:14px;line-height:1.55;color:#344454;">{_render_lines(lines)}</p>'
        )

    content = "\n".join(rendered_blocks)
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" /></head>
<body style="margin:0;padding:0;background:#EFEFF2;font-family:Inter,Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#EFEFF2;padding:32px 16px;">
  <tr>
    <td align="center">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;width:100%;background:#FFFFFF;border-radius:18px;overflow:hidden;border:1px solid #E3E3E7;">
        <tr>
          <td style="padding:20px 32px 18px;border-bottom:1px solid #E3E3E7;">
            {_logo_img_tag(height=22)}
          </td>
        </tr>
        <tr>
          <td style="padding:32px 32px 28px;font-family:Inter,Arial,Helvetica,sans-serif;font-size:15px;line-height:1.65;color:#4A4A4D;">
            {content}
          </td>
        </tr>
        <tr>
          <td style="border-top:1px solid #E3E3E7;background:#FAFAFB;padding:18px 32px;font-family:'Courier New',Courier,monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#9A9AA0;">PropHero</td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>""".strip()


async def send_valuation_email(
    *,
    lead: LeadInfo,
    valuation: ValuationResponse,
    pdf_bytes: bytes,
    request_payload: Optional[dict] = None,
    test_mode: bool = False,
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
    actual_to, routed_to_test = delivery_recipient(lead.email, test_mode=test_mode)
    municipio = _format_place_name(valuation.municipio.name)
    subject = f"Tu propiedad en {municipio} muestra una posible señal de revalorización"
    attachment_name = f"prophero-valoracion-{date.today().isoformat()}.pdf"

    attachments: list[dict] = [
        {
            "filename": attachment_name,
            "content": base64.b64encode(pdf_bytes).decode("ascii"),
        }
    ]
    logo = _logo_attachment()
    if logo:
        attachments.append(logo)

    payload = {
        "from": sender,
        "to": [actual_to],
        "subject": subject,
        "html": _render_email_html(lead.full_name, valuation, request_payload),
        "attachments": attachments,
    }
    reply_to = _reply_to_for_delivery()
    if reply_to:
        payload["reply_to"] = reply_to

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
    if routed_to_test:
        logger.info(
            "Email test mode routed %s to %s via Resend (id=%s)",
            lead.email,
            actual_to,
            message_id,
        )
    else:
        logger.info("Email sent to %s via Resend (id=%s)", actual_to, message_id)


async def send_custom_email(
    *,
    to: str,
    subject: str,
    body: str,
    attachment_filename: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    recipient_name: Optional[str] = None,
    valuation: Optional[ValuationResponse] = None,
    request_payload: Optional[dict] = None,
    transaction: Optional[TransactionDetail] = None,
    test_mode: bool = False,
) -> bool:
    """Send an editable plain-text/HTML email from the coach interface.

    When ``valuation`` is provided we render the branded "Variation C" market
    update (dark hero card + appreciation headline) — the same design used by
    the public ``send_valuation_email`` flow — so coach-sent emails look like
    the structured report instead of plain reflowed text. ``body`` is still
    posted as the plain-text part for clients on text-only mail clients. When
    no valuation is given we fall back to the generic coach text renderer.

    Returns False when RESEND_API_KEY is unset so local dev can exercise the
    flow without sending real email.
    """
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        logger.warning("RESEND_API_KEY not set — skipping coach email send to %s", to)
        return False

    sender = os.environ.get("RESEND_FROM_EMAIL", "PropHero <noreply@prophero.com>")
    actual_to, routed_to_test = delivery_recipient(to, test_mode=test_mode)
    if valuation is not None:
        html = _render_email_html(recipient_name, valuation, request_payload, transaction)
    else:
        html = _render_custom_email_html(body)
    payload = {
        "from": sender,
        "to": [actual_to],
        "subject": subject,
        "text": body,
        "html": html,
    }
    reply_to = _reply_to_for_delivery()
    if reply_to:
        payload["reply_to"] = reply_to
    attachments: list[dict] = []
    if attachment_filename and attachment_bytes is not None:
        attachments.append(
            {
                "filename": attachment_filename,
                "content": base64.b64encode(attachment_bytes).decode("ascii"),
            }
        )
    logo = _logo_attachment()
    if logo:
        attachments.append(logo)
    if attachments:
        payload["attachments"] = attachments

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
    if routed_to_test:
        logger.info(
            "Coach email test mode routed %s to %s via Resend (id=%s)",
            to,
            actual_to,
            message_id,
        )
    else:
        logger.info("Coach email sent to %s via Resend (id=%s)", actual_to, message_id)
    return True
