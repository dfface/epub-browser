import hashlib
import unittest

from epub_browser.pat import (
    PAT_SCOPES,
    generate_pat,
    normalize_scopes,
    pat_digest,
)


class PersonalAccessTokenPrimitiveTests(unittest.TestCase):
    def test_generated_token_has_indexed_prefix_and_one_way_digest(self):
        raw_token, public_id, digest = generate_pat()

        self.assertTrue(raw_token.startswith("epub_pat_" + public_id + "_"))
        self.assertGreaterEqual(len(public_id), 16)
        self.assertEqual(digest, hashlib.sha256(raw_token.encode("utf-8")).hexdigest())
        self.assertEqual(pat_digest(raw_token), digest)
        self.assertNotIn(raw_token, digest)

    def test_scope_normalization_requires_read_for_each_write_scope(self):
        with self.assertRaisesRegex(ValueError, "matching read scope"):
            normalize_scopes(["reviews:write"])

        self.assertEqual(
            normalize_scopes(["reviews:write", "reviews:read", "library:read"]),
            ("library:read", "reviews:read", "reviews:write"),
        )

    def test_scope_normalization_rejects_unknown_and_empty_sets(self):
        self.assertIn("admin:data:read", PAT_SCOPES)
        with self.assertRaisesRegex(ValueError, "At least one"):
            normalize_scopes([])
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            normalize_scopes(["system:write"])


if __name__ == "__main__":
    unittest.main()
