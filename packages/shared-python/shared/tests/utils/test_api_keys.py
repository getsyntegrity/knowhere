from shared.utils.api_keys import (
    API_KEY_PREFIX,
    generate_api_key,
    hash_api_key,
    is_api_key_token,
    mask_api_key,
)


def configure_hash_secret(monkeypatch) -> None:
    """Configure deterministic API-key hashing for tests."""
    monkeypatch.setenv("API_KEY_HASH_SECRET", "contract-hash-secret")


def test_generate_api_key_should_use_api_key_prefix_and_random_secret() -> None:
    first_api_key: str = generate_api_key()
    second_api_key: str = generate_api_key()

    assert first_api_key.startswith(API_KEY_PREFIX)
    assert second_api_key.startswith(API_KEY_PREFIX)
    assert first_api_key != second_api_key
    assert len(first_api_key) > len(API_KEY_PREFIX) + 32


def test_hash_api_key_should_return_deterministic_keyed_lookup_hash(monkeypatch) -> None:
    configure_hash_secret(monkeypatch)
    api_key: str = "sk_contract_test_secret"

    assert hash_api_key(api_key) == hash_api_key(api_key)
    assert len(hash_api_key(api_key)) == 64


def test_hash_api_key_should_require_hash_secret(monkeypatch) -> None:
    monkeypatch.delenv("API_KEY_HASH_SECRET", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    try:
        hash_api_key("sk_contract_test_secret")
    except RuntimeError as error:
        assert "API_KEY_HASH_SECRET" in str(error)
    else:
        raise AssertionError("hash_api_key should require a hash secret")


def test_mask_api_key_should_hide_middle_characters() -> None:
    assert mask_api_key("sk_1234567890abcdef") == "sk_12345•••••••cdef"


def test_is_api_key_token_should_match_only_api_key_prefix() -> None:
    assert is_api_key_token("sk_test") is True
    assert is_api_key_token("jwt_test") is False
    assert is_api_key_token(None) is False
