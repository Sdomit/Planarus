"""Phase 7C1: Argon2id credential service."""
from app.services import api_credentials


def test_generate_key_format_and_uniqueness():
    key_id, secret, full = api_credentials.generate_key()
    assert full == f"agbk_{key_id}_{secret}"
    assert full.startswith("agbk_")
    # key_id is hex (underscore-free, log-safe); secret has real entropy.
    assert "_" not in key_id and len(key_id) == 32
    assert len(secret) >= 32
    # Two keys differ.
    assert api_credentials.generate_key()[2] != full


def test_hash_is_argon2id_and_verifies_without_plaintext():
    key_id, secret, _ = api_credentials.generate_key()
    encoded = api_credentials.hash_secret(secret)
    assert encoded.startswith("$argon2id$")
    # The raw secret is never embedded in the verifier.
    assert secret not in encoded
    assert api_credentials.verify_secret(encoded, secret) is True
    assert api_credentials.verify_secret(encoded, secret + "x") is False


def test_argon2_profile_is_explicit_and_locked():
    assert api_credentials.ARGON2_TIME_COST == 2
    assert api_credentials.ARGON2_MEMORY_COST == 19456
    assert api_credentials.ARGON2_PARALLELISM == 1
    ph = api_credentials._hasher
    assert ph.time_cost == 2 and ph.memory_cost == 19456 and ph.parallelism == 1


def test_parse_authorization_strict():
    p = api_credentials.parse_authorization("Bearer agbk_abc123_sEcReT-_value")
    assert p == ("abc123", "sEcReT-_value")  # secret keeps trailing underscores
    # Malformed forms all reject.
    for bad in [
        None,
        "",
        "agbk_abc_secret",  # no scheme
        "Basic agbk_abc_secret",  # wrong scheme
        "bearer agbk_abc_secret",  # case-sensitive scheme
        "Bearer ",  # empty token
        "Bearer notakey",  # no underscores
        "Bearer agbk_abc",  # missing secret segment
        "Bearer xxxx_abc_secret",  # wrong prefix
        "Bearer agbk__secret",  # empty key_id
        "Bearer  agbk_abc_secret",  # double space → 3 parts
    ]:
        assert api_credentials.parse_authorization(bad) is None, bad


def test_verify_secret_never_raises_on_garbage():
    assert api_credentials.verify_secret("not-a-hash", "x") is False
    assert api_credentials.verify_secret("", "") is False


def test_dummy_verify_runs_without_raising():
    # The unknown-key path performs a real Argon2 verification (timing equalizer).
    api_credentials.dummy_verify()
