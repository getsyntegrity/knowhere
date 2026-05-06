from shared.utils.api_keys import (
    API_KEY_PREFIX,
    generate_api_key,
    hash_api_key,
    is_api_key_token,
    mask_api_key,
)


def test_generate_api_key_should_use_api_key_prefix_and_random_secret() -> None:
    first_api_key = generate_api_key()
    second_api_key = generate_api_key()

    assert first_api_key.startswith(API_KEY_PREFIX)
    assert second_api_key.startswith(API_KEY_PREFIX)
    assert first_api_key != second_api_key
    assert len(first_api_key) > len(API_KEY_PREFIX) + 32


def test_hash_api_key_should_return_deterministic_sha256_lookup_hash() -> None:
    api_key = "sk_contract_test_secret"

    assert hash_api_key(api_key) == hash_api_key(api_key)
    assert len(hash_api_key(api_key)) == 64


def test_mask_api_key_should_hide_middle_characters() -> None:
    assert mask_api_key("sk_1234567890abcdef") == "sk_12345•••••••cdef"


def test_is_api_key_token_should_match_only_api_key_prefix() -> None:
    assert is_api_key_token("sk_test") is True
    assert is_api_key_token("jwt_test") is False
    assert is_api_key_token(None) is False
