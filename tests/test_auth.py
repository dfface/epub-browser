import unittest

from epub_browser.auth import (
    AuthConfig,
    hash_password,
    session_cookie_options,
    verify_password,
)


class AuthPrimitiveTests(unittest.TestCase):
    def test_argon2_hash_is_verifiable_but_does_not_contain_password(self):
        encoded = hash_password("correct horse battery staple")

        self.assertNotIn("correct horse battery staple", encoded)
        self.assertTrue(verify_password(encoded, "correct horse battery staple"))
        self.assertFalse(verify_password(encoded, "wrong"))

    def test_proxy_config_requires_subject_header_issuer_and_trusted_cidr(self):
        with self.assertRaises(ValueError):
            AuthConfig.from_values(["10.0.0.0/8"], "X-Remote-User", None)

    def test_proxy_config_parses_cidrs_and_cookie_options(self):
        config = AuthConfig.from_values(
            ["10.0.0.0/8", "2001:db8::/32"],
            "X-Remote-User",
            "https://sso.example",
            cookie_secure=True,
        )

        self.assertTrue(config.is_trusted_proxy("10.1.2.3"))
        self.assertFalse(config.is_trusted_proxy("203.0.113.8"))
        self.assertEqual(
            session_cookie_options(config),
            {"httponly": True, "samesite": "lax", "secure": True, "path": "/"},
        )

