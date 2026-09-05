import pytest
from app.config import Settings
from app.core.crypto import (
    SecretDecryptionError,
    api_key_display_metadata,
    decrypt_secret,
    encrypt_secret,
    generate_api_key,
    hash_api_key,
    redact_secret_for_display,
    verify_api_key,
)
from cryptography.fernet import Fernet


def _settings(**overrides) -> Settings:
    defaults = {"integration_encryption_key": Fernet.generate_key().decode("utf-8")}
    defaults.update(overrides)
    return Settings(**defaults)


class TestApiKeyLifecycle:
    def test_generated_key_has_the_configured_prefix(self):
        key = generate_api_key(prefix="airk_")
        assert key.startswith("airk_")
        assert len(key) > len("airk_") + 30

    def test_verify_api_key_accepts_the_correct_key(self):
        key = generate_api_key(prefix="airk_")
        stored_hash = hash_api_key(key)
        assert verify_api_key(key, expected_hash=stored_hash) is True

    def test_verify_api_key_rejects_a_wrong_key(self):
        key = generate_api_key(prefix="airk_")
        stored_hash = hash_api_key(key)
        assert verify_api_key("airk_wrong-key-entirely", expected_hash=stored_hash) is False

    def test_two_generated_keys_never_collide(self):
        keys = {generate_api_key(prefix="airk_") for _ in range(50)}
        assert len(keys) == 50

    def test_display_metadata_reveals_only_prefix_and_last_four(self):
        key = generate_api_key(prefix="airk_")
        prefix, last_four = api_key_display_metadata(key, prefix="airk_")
        assert prefix == "airk_"
        assert last_four == key[-4:]
        assert len(last_four) == 4


class TestSecretEncryption:
    def test_encrypt_then_decrypt_round_trips(self):
        settings = _settings()
        ciphertext, key_version = encrypt_secret("my-webhook-signing-secret", settings=settings)
        assert ciphertext != "my-webhook-signing-secret"
        plaintext = decrypt_secret(ciphertext, key_version=key_version, settings=settings)
        assert plaintext == "my-webhook-signing-secret"

    def test_encrypt_raises_without_a_configured_key(self):
        settings = Settings(integration_encryption_key=None)
        with pytest.raises(RuntimeError, match="INTEGRATION_ENCRYPTION_KEY"):
            encrypt_secret("secret", settings=settings)

    def test_encrypt_raises_for_a_malformed_key(self):
        settings = _settings(integration_encryption_key="not-a-valid-fernet-key")
        with pytest.raises(RuntimeError, match="not a valid Fernet key"):
            encrypt_secret("secret", settings=settings)

    def test_decrypt_raises_for_a_key_version_mismatch(self):
        settings = _settings(integration_encryption_key_version=1)
        ciphertext, _ = encrypt_secret("secret", settings=settings)
        newer_settings = _settings(
            integration_encryption_key=settings.integration_encryption_key, integration_encryption_key_version=2
        )
        with pytest.raises(SecretDecryptionError, match="key version"):
            decrypt_secret(ciphertext, key_version=1, settings=newer_settings)

    def test_decrypt_raises_for_corrupted_ciphertext(self):
        settings = _settings()
        with pytest.raises(SecretDecryptionError):
            decrypt_secret("not-real-ciphertext", key_version=1, settings=settings)

    def test_decrypt_with_a_different_key_fails(self):
        settings_a = _settings()
        ciphertext, version = encrypt_secret("secret", settings=settings_a)
        settings_b = _settings(integration_encryption_key_version=version)
        with pytest.raises(SecretDecryptionError):
            decrypt_secret(ciphertext, key_version=version, settings=settings_b)


class TestRedaction:
    def test_redacts_a_present_value(self):
        assert redact_secret_for_display("a-real-secret") == "[set]"

    def test_redacts_a_missing_value(self):
        assert redact_secret_for_display(None) == "[not set]"
        assert redact_secret_for_display("") == "[not set]"
