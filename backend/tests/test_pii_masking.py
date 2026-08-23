"""PII masking service (regex fallback path, no Presidio download required)."""
from app.services.pii_masking import PIIMasker


def _masker():
    # Force the deterministic regex fallback for CI stability.
    return PIIMasker({"presidio": {"enabled": False}})


def test_email_and_phone_masked():
    masker = _masker()
    text = "Contact jane.doe@example.com or +1-555-014-2442 about the shipment."
    masked = masker.mask(text)
    assert "jane.doe@example.com" not in masked
    assert "555-014-2442" not in masked
    assert "[REDACTED_EMAIL_ADDRESS]" in masked
    assert "[REDACTED_PHONE_NUMBER]" in masked


def test_credit_card_masked():
    masker = _masker()
    masked = masker.mask("Card on file: 4111 1111 1111 1111")
    assert "4111" not in masked


def test_clean_text_unchanged():
    masker = _masker()
    original = "Supplier reported stable Q3 operations with no disruptions."
    assert masker.mask(original) == original
