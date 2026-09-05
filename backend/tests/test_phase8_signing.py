"""Dedicated unit tests for the low-level HMAC signing scheme
(app/integrations/signing.py) — shared by every outbound delivery and by
the inbound API. Every other Phase 8 test file exercises this indirectly
through a real connector or route; this file isolates the primitive
itself, so a regression here is caught at the smallest possible unit."""

from app.integrations.signing import current_timestamp, sign_payload, verify_signature


def _sign(secret="a-shared-secret", **overrides):
    kwargs = {
        "body": b'{"hello":"world"}',
        "timestamp": "1700000000",
        "delivery_id": "delivery-1",
        "event_id": "event-1",
        "schema_version": "1",
    }
    kwargs.update(overrides)
    signature = sign_payload(secret, **kwargs)
    return signature, kwargs


class TestSignAndVerifyRoundTrip:
    def test_a_correctly_signed_request_verifies(self):
        signature, kwargs = _sign()
        assert verify_signature("a-shared-secret", signature=signature, **kwargs) is True

    def test_current_timestamp_is_a_string_of_digits(self):
        ts = current_timestamp()
        assert ts.isdigit()


class TestTamperDetection:
    def test_a_single_byte_body_change_invalidates_the_signature(self):
        signature, kwargs = _sign()
        kwargs["body"] = kwargs["body"][:-1] + b"X"
        assert verify_signature("a-shared-secret", signature=signature, **kwargs) is False

    def test_a_changed_timestamp_invalidates_the_signature(self):
        signature, kwargs = _sign()
        kwargs["timestamp"] = "1700000001"
        assert verify_signature("a-shared-secret", signature=signature, **kwargs) is False

    def test_a_changed_delivery_id_invalidates_the_signature(self):
        signature, kwargs = _sign()
        kwargs["delivery_id"] = "delivery-2"
        assert verify_signature("a-shared-secret", signature=signature, **kwargs) is False

    def test_a_changed_event_id_invalidates_the_signature(self):
        signature, kwargs = _sign()
        kwargs["event_id"] = "event-2"
        assert verify_signature("a-shared-secret", signature=signature, **kwargs) is False

    def test_a_changed_schema_version_invalidates_the_signature(self):
        signature, kwargs = _sign()
        kwargs["schema_version"] = "2"
        assert verify_signature("a-shared-secret", signature=signature, **kwargs) is False

    def test_the_wrong_secret_invalidates_the_signature(self):
        signature, kwargs = _sign()
        assert verify_signature("a-different-secret", signature=signature, **kwargs) is False

    def test_a_retried_delivery_with_a_different_delivery_id_produces_a_different_signature(self):
        """Proves delivery_id is genuinely part of the signed material —
        so a retried delivery of the same event never reuses the exact
        same signature, and signature equality can never be mistaken for
        an idempotency/de-duplication signal (event_id in the body is)."""
        signature_a, kwargs_a = _sign(delivery_id="attempt-1")
        signature_b, _ = _sign(delivery_id="attempt-2")
        assert signature_a != signature_b
        # But each is independently valid for its own delivery_id.
        assert verify_signature("a-shared-secret", signature=signature_a, **kwargs_a) is True


class TestCanonicalSigningIsDeterministic:
    def test_signing_the_same_inputs_twice_produces_the_same_signature(self):
        signature_a, kwargs = _sign()
        signature_b = sign_payload("a-shared-secret", **kwargs)
        assert signature_a == signature_b

    def test_signature_is_a_valid_hex_sha256_digest(self):
        signature, _ = _sign()
        assert len(signature) == 64
        int(signature, 16)  # raises ValueError if not valid hex
