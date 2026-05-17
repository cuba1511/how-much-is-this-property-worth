"""Outbound notifications — branded transactional email via Resend."""

from notifications.email_sender import (
    EmailDeliveryError,
    send_valuation_email,
)

__all__ = ["EmailDeliveryError", "send_valuation_email"]
