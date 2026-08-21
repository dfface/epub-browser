import unittest
from pathlib import Path

from epub_browser.epub_identity import read_embedded_book_id
from epub_browser.identity import source_sha256
from epub_browser.sidecar_identity import read_exact_sidecar


class ExampleIdentityTests(unittest.TestCase):
    EXPECTED = {
        "Mao Ze Dong Xuan Ji - Mao Ze Dong.epub": (
            "6QrgU-nfQSm_M6lmKAuBRg",
            "ee41f0b9a38ca691490e4e0e957cf40b4eaaa86c490c7b0417d33e1a77d8b50e",
        ),
        "TheEconomist.2026.02.14 - Kovid Goyal.epub": (
            "HxcyeSrJTySgmFoJMnyKFw",
            "764459af1ffb78720e1efdbd619139c39daf4f9af82426c62f97c7cdcf3dfc13",
        ),
        "Yi Jiu Ba Si - Qiao Zhi _Ao Wei Er.epub": (
            "W5t_bkH64u-0GwfxFrnEew",
            "e39771bfc05df91a23e9d86a86a319ea57e7c0f94f49b1220f1587f180685192",
        ),
    }

    def test_examples_keep_original_bytes_and_visible_public_ids(self):
        root = Path("examples")
        for filename, (book_id, fingerprint) in self.EXPECTED.items():
            with self.subTest(filename=filename):
                source = root / filename
                sidecar = read_exact_sidecar(source)
                self.assertEqual(source_sha256(source), fingerprint)
                self.assertEqual(sidecar.book_id, book_id)
                self.assertEqual(sidecar.source_fingerprint, fingerprint)
                self.assertIsNone(read_embedded_book_id(source))


if __name__ == "__main__":
    unittest.main()
