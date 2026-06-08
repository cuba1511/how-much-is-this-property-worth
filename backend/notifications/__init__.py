"""Outbound notifications — branded transactional email via Resend."""

from notifications.email_sender import (
    EmailDeliveryError,
    delivery_recipient,
    is_test_email_mode_enabled,
    send_custom_email,
    send_valuation_email,
    set_test_email_mode,
    test_email_recipient,
)

__all__ = [
    "EmailDeliveryError",
    "delivery_recipient",
    "is_test_email_mode_enabled",
    "send_custom_email",
    "send_valuation_email",
    "set_test_email_mode",
    "test_email_recipient",
]
