import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from epub_browser.auth import (
    AuthConfig,
    AuthService,
    BootstrapCredentials,
    Principal,
    hash_password,
    session_cookie_options,
    token_digest,
    verify_password,
)
from epub_browser.state import StateStore


class AuthPrimitiveTests(unittest.TestCase):
    def test_argon2_hash_is_verifiable_but_does_not_contain_password(self):
        encoded = hash_password("correct horse battery staple")

        self.assertNotIn("correct horse battery staple", encoded)
        self.assertTrue(verify_password(encoded, "correct horse battery staple"))
        self.assertFalse(verify_password(encoded, "wrong"))

    def test_trusted_proxy_cidr_alone_enables_forwarded_address_trust(self):
        config = AuthConfig.from_values(["172.16.0.0/12"])

        self.assertTrue(config.is_trusted_proxy("172.16.0.1"))

    def test_proxy_config_rejects_malformed_cidr(self):
        with self.assertRaises(ValueError):
            AuthConfig.from_values(["not-a-cidr"])

    def test_proxy_config_parses_cidrs_and_cookie_options(self):
        config = AuthConfig.from_values(
            ["10.0.0.0/8", "2001:db8::/32"],
            cookie_secure=True,
        )

        self.assertTrue(config.is_trusted_proxy("10.1.2.3"))
        self.assertFalse(config.is_trusted_proxy("203.0.113.8"))
        self.assertEqual(
            session_cookie_options(config),
            {"httponly": True, "samesite": "lax", "secure": True, "path": "/"},
        )


class MutableClock:
    def __init__(self, value=1_000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class SetupAuthTests(unittest.TestCase):
    def test_setup_completion_returns_an_authenticated_session_for_pending_admin(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.db")
            pending = store.initialize()
            clock = MutableClock()
            service = AuthService(
                store,
                AuthConfig.from_values([]),
                clock=clock,
            )

            raw_token, principal = service.complete_setup("Owner", "secret")

            self.assertEqual(principal.user_id, pending.user_id)
            self.assertEqual(principal.username, "owner")
            self.assertEqual(service.principal_from_session(raw_token), principal)
            self.assertEqual(
                service.authenticate_password("owner", "secret", "client"),
                principal,
            )


class SessionAndProxyTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "state.db"
        self.store = StateStore(self.database_path)
        self.store.initialize(bootstrap=BootstrapCredentials("owner", "secret"))
        self.clock = MutableClock()
        self.config = AuthConfig.from_values(
            ["10.0.0.0/8"],
        )
        self.service = AuthService(self.store, self.config, clock=self.clock)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _principal(self, username, password="secret"):
        return self.store.create_user(username, hash_password(password))

    def _session_row(self, raw_token):
        with sqlite3.connect(self.database_path) as connection:
            return connection.execute(
                "SELECT * FROM sessions WHERE token_digest = ?",
                (token_digest(raw_token),),
            ).fetchone()

    def test_database_stores_digest_not_raw_session_token(self):
        principal = self._principal("alice")

        token, csrf = self.service.create_session(principal)

        self.assertEqual(
            self.store.principal_from_session(token, now=self.clock()), principal
        )
        self.assertNotIn(token, self.store.raw_session_rows())
        self.assertEqual(self._session_row(token)[1], token_digest(token))
        self.assertTrue(self.service.verify_csrf_token(principal, token, csrf))

    def test_session_expiry_slides_only_while_session_is_valid(self):
        principal = self._principal("alice")
        token, _ = self.service.create_session(principal)
        original_expiry = float(self._session_row(token)[3])

        self.clock.advance(60)
        self.assertEqual(self.service.principal_from_session(token), principal)
        extended_expiry = float(self._session_row(token)[3])
        self.assertEqual(extended_expiry, original_expiry + 60)

        self.clock.advance(self.config.session_ttl_seconds + 1)
        self.assertIsNone(self.service.principal_from_session(token))
        self.assertEqual(float(self._session_row(token)[3]), extended_expiry)

    def test_revoked_session_and_revoke_all_are_invalid_immediately(self):
        principal = self._principal("alice")
        first, _ = self.service.create_session(principal)
        second, _ = self.service.create_session(principal)

        self.assertTrue(self.service.revoke_session(first))
        self.assertIsNone(self.service.principal_from_session(first))
        self.assertEqual(self.store.revoke_all_sessions(principal.user_id), 1)
        self.assertIsNone(self.service.principal_from_session(second))

    def test_disabling_account_immediately_rejects_its_existing_session(self):
        principal = self._principal("alice")
        token, _ = self.service.create_session(principal)

        self.store.set_user_enabled(principal.user_id, False)

        self.assertIsNone(self.service.principal_from_session(token))

    def test_csrf_token_is_bound_to_both_principal_and_session(self):
        alice = self._principal("alice")
        bob = self._principal("bob")
        alice_token, alice_csrf = self.service.create_session(alice)
        bob_token, _ = self.service.create_session(bob)

        self.assertFalse(
            self.service.verify_csrf_token(bob, alice_token, alice_csrf)
        )
        self.assertFalse(
            self.service.verify_csrf_token(alice, bob_token, alice_csrf)
        )
        self.assertFalse(self.service.verify_csrf_token(alice, alice_token, "bad"))

    def test_failed_password_attempts_are_throttled_without_user_enumeration(self):
        self._principal("alice", "correct")

        self.assertIsNone(
            self.service.authenticate_password("alice", "wrong", "ip")
        )
        for _ in range(4):
            self.assertIsNone(
                self.service.authenticate_password("missing", "bad", "other-ip")
            )
        self.assertIsNone(
            self.service.authenticate_password("missing", "bad", "other-ip")
        )

        self.assertIsNone(self.service.authenticate_password("alice", "wrong", "ip"))
        self.assertFalse(self.service.login_is_throttled("ip", "alice"))
        self.assertTrue(self.service.login_is_throttled("other-ip"))
        self.assertTrue(self.service.login_is_throttled("other-ip", "MISSING"))

    def test_throttle_normalizes_username_and_expires_without_capacity_churn(self):
        service = AuthService(
            self.store,
            self.config,
            clock=self.clock,
            throttle_capacity=3,
        )
        for _ in range(5):
            service.authenticate_password(" Alice ", "bad", "ip")

        self.assertTrue(service.login_is_throttled("ip", "ALICE"))
        self.assertFalse(service.login_is_throttled("ip", "bob"))
        self.assertEqual(service.login_retry_after_seconds("ip", "alice"), 300)

        self.clock.advance(1)
        self.assertEqual(service.login_retry_after_seconds("ip", "alice"), 299)

        self.clock.advance(service.throttle_window_seconds)
        self.assertFalse(service.login_is_throttled("ip", "alice"))
        self.assertEqual(service.login_retry_after_seconds("ip", "alice"), 0)

    def test_active_throttle_survives_new_key_churn_at_capacity(self):
        service = AuthService(
            self.store,
            self.config,
            clock=self.clock,
            throttle_limit=1,
            throttle_capacity=2,
        )
        self.assertIsNone(
            service.authenticate_password("target", "bad", "203.0.113.8")
        )
        self.assertTrue(
            service.login_is_throttled("203.0.113.8", "target")
        )

        for index in range(6):
            self.assertIsNone(
                service.authenticate_password(
                    "churn{}".format(index), "bad", "203.0.113.8"
                )
            )

        self.assertTrue(
            service.login_is_throttled("203.0.113.8", "target")
        )
        self.assertLessEqual(service.tracked_login_keys, 2)

    def test_saturated_throttle_denies_unseen_valid_login_until_window_expires(self):
        principal = self._principal("alice", "correct")
        service = AuthService(
            self.store,
            self.config,
            clock=self.clock,
            throttle_limit=1,
            throttle_capacity=2,
        )
        for username in ("slot-one", "slot-two"):
            self.assertIsNone(
                service.authenticate_password(
                    username, "bad", "203.0.113.8"
                )
            )
        self.assertEqual(service.tracked_login_keys, 2)

        self.assertIsNone(
            service.authenticate_password("alice", "correct", "203.0.113.8")
        )
        self.assertTrue(
            service.login_is_throttled("203.0.113.8", "alice")
        )

        self.clock.advance(service.throttle_window_seconds + 1)
        self.assertEqual(
            service.authenticate_password("alice", "correct", "203.0.113.8"),
            principal,
        )
        self.assertFalse(
            service.login_is_throttled("203.0.113.8", "alice")
        )

    def test_concurrent_failures_are_counted_and_throttle_state_stays_bounded(self):
        service = AuthService(
            self.store,
            self.config,
            clock=self.clock,
            throttle_limit=2,
            throttle_capacity=8,
        )
        usernames = ["user{}".format(index % 8) for index in range(32)]

        with ThreadPoolExecutor(max_workers=16) as executor:
            results = tuple(
                executor.map(
                    lambda username: service.authenticate_password(
                        username, "bad", "203.0.113.8"
                    ),
                    usernames,
                )
            )

        self.assertEqual(results, (None,) * len(usernames))
        self.assertLessEqual(service.tracked_login_keys, 8)
        for index in range(8):
            self.assertTrue(
                service.login_is_throttled(
                    "203.0.113.8", "user{}".format(index)
                )
            )

    def test_successful_password_authentication_clears_prior_failures(self):
        principal = self._principal("Alice", "correct")
        for _ in range(4):
            self.assertIsNone(
                self.service.authenticate_password(" ALICE ", "bad", "ip")
            )

        self.assertEqual(
            self.service.authenticate_password("alice", "correct", "ip"), principal
        )
        self.assertFalse(self.service.login_is_throttled("ip", "alice"))
