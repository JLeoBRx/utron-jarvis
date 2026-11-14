import pytest

from safra.core.errors import InvalidInput
from safra.security import passwords, tokens

FAST = passwords.ScryptParams(n=2 ** 10, r=8, p=1)             # só para os testes que não medem o custo
GOOD = "uma senha bem comprida 123"


def test_default_parameters_follow_the_documented_cost():
    assert (passwords.DEFAULT_PARAMS.n, passwords.DEFAULT_PARAMS.r, passwords.DEFAULT_PARAMS.p) == (2 ** 17, 8, 1)


def test_hash_and_verify_with_the_real_parameters():
    encoded = passwords.hash_password(GOOD)
    assert encoded.startswith("scrypt$131072$8$1$") and GOOD not in encoded
    assert passwords.verify_password(GOOD, encoded)
    assert not passwords.verify_password(GOOD + "x", encoded)
    assert not passwords.needs_rehash(encoded)


def test_same_password_gives_different_hashes():
    assert passwords.hash_password(GOOD, FAST) != passwords.hash_password(GOOD, FAST)


@pytest.mark.parametrize("bad", ["", "curta", "a" * 11, "a" * 257])
def test_policy_rejects_short_and_oversized_passwords(bad):
    with pytest.raises(InvalidInput) as info:
        passwords.hash_password(bad, FAST)
    assert bad not in info.value.message or bad == ""


@pytest.mark.parametrize("encoded", ["", "texto", "scrypt$abc$8$1$xx$yy", "scrypt$1024$8$1$$", "bcrypt$1024$8$1$aa$bb",
                                     "scrypt$1000$8$1$YWJj$YWJj", "scrypt$1024$8$1$YWJj"])
def test_malformed_stored_values_never_verify_and_never_raise(encoded):
    assert passwords.verify_password(GOOD, encoded) is False
    assert passwords.needs_rehash(encoded) is True


def test_verify_refuses_empty_and_oversized_input_without_raising():
    encoded = passwords.hash_password(GOOD, FAST)
    assert passwords.verify_password("", encoded) is False
    assert passwords.verify_password("a" * 100_000, encoded) is False


def test_older_parameters_are_flagged_for_rehash():
    assert passwords.needs_rehash(passwords.hash_password(GOOD, FAST)) is True


def test_tokens_are_unpredictable_and_only_the_digest_is_stored():
    values = {tokens.new_token() for _ in range(500)}
    assert len(values) == 500 and all(len(v) >= 43 for v in values)
    token = tokens.new_token()
    digest = tokens.token_digest(token)
    assert len(digest) == 64 and token not in digest and digest == tokens.token_digest(token)
    assert tokens.constant_time_equals(digest, tokens.token_digest(token))
    assert not tokens.constant_time_equals(digest, tokens.token_digest(token + "x"))
    with pytest.raises(ValueError):
        tokens.new_token(8)
