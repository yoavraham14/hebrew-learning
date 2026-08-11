"""Regression coverage for the billing-error detector — this is the exact
logic that missed a real depleted-prepayment-credits 429 on first live run
(see git history / SPEC.md §2.1). Never weaken this without re-testing
against a real Gemini error payload.
"""

from app.services.gemini_client import _is_billing_error


class _FakeApiError(Exception):
    """Mimics google.genai.errors.APIError's shape (code/status/message)
    without needing the real SDK or network access.
    """

    def __init__(self, *, code: int | None = None, status: str | None = None, message: str = ""):
        self.code = code
        self.status = status
        self.message = message
        super().__init__(f"{code} {status}. {{'error': {{'message': '{message}'}}}}")


def test_402_payment_required_is_billing_error():
    assert _is_billing_error(_FakeApiError(code=402, status="PAYMENT_REQUIRED", message="")) is True


def test_429_resource_exhausted_is_billing_error():
    # This is the real shape that was missed on first live run: a plain 429
    # RESOURCE_EXHAUSTED whose message text turned out to reference billing.
    assert (
        _is_billing_error(
            _FakeApiError(
                code=429,
                status="RESOURCE_EXHAUSTED",
                message=(
                    "Your prepayment credits are depleted. Please go to AI Studio "
                    "to manage your project and billing."
                ),
            )
        )
        is True
    )


def test_429_status_string_alone_triggers_halt_even_without_billing_wording():
    # Belt-and-suspenders: even if a future message omits billing language,
    # the status code/name alone is enough — see the docstring in
    # gemini_client.py for why RESOURCE_EXHAUSTED is treated as billing.
    assert _is_billing_error(_FakeApiError(code=429, status="RESOURCE_EXHAUSTED", message="quota exceeded")) is True


def test_message_only_billing_keyword_triggers_halt():
    exc = Exception("This model requires a billing account to continue.")
    assert _is_billing_error(exc) is True


def test_credit_and_prepay_keywords_trigger_halt():
    assert _is_billing_error(Exception("prepayment required to continue")) is True
    assert _is_billing_error(Exception("insufficient credit balance")) is True


def test_unrelated_error_is_not_a_billing_error():
    """Negative control — a genuinely unrelated failure (network timeout,
    malformed response, etc.) must NOT halt generation; that's the
    (retryable) GeminiGenerationError path instead.
    """
    assert _is_billing_error(TimeoutError("Connection timed out")) is False
    assert _is_billing_error(ValueError("could not parse response JSON")) is False
    assert _is_billing_error(_FakeApiError(code=500, status="INTERNAL", message="server error")) is False
