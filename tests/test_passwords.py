"""Tests for the bcrypt password hashing helpers."""

import pytest

from open_notebook.utils.passwords import hash_password, verify_password


class TestHashPassword:
    def test_hash_is_not_plaintext(self):
        h = hash_password("secret123")
        assert h != "secret123"
        assert h.startswith("$2")  # bcrypt marker

    def test_salted_hashes_differ(self):
        assert hash_password("same") != hash_password("same")

    def test_empty_password_raises(self):
        with pytest.raises(ValueError):
            hash_password("")

    def test_long_password_does_not_crash(self):
        # bcrypt has a 72-byte limit; helper truncates instead of raising.
        h = hash_password("x" * 200)
        assert verify_password("x" * 200, h) is True


class TestVerifyPassword:
    def test_correct_password(self):
        assert verify_password("hunter2", hash_password("hunter2")) is True

    def test_wrong_password(self):
        assert verify_password("nope", hash_password("hunter2")) is False

    def test_empty_inputs_are_false(self):
        assert verify_password("", hash_password("x")) is False
        assert verify_password("x", "") is False

    def test_malformed_hash_is_false(self):
        assert verify_password("x", "not-a-bcrypt-hash") is False
