import struct
import tempfile
import unittest
import io
import zipfile
from pathlib import Path

from epub_browser.auth import BootstrapCredentials
from epub_browser.dictionary_service import DictionaryService, DictionaryServiceError
from epub_browser.state import StateStore


class DictionaryServiceTests(unittest.TestCase):
    def test_installs_stardict_zip_without_retaining_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root / "data" / "epub-browser.db")
            admin = store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
            definition = b"to move quickly"
            index = b"run\0" + struct.pack(">II", 0, len(definition))
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as archive:
                archive.writestr("sample.ifo", "StarDict's dict ifo file\nversion=2.4.2\nbookname=Zip\nwordcount=1\nidxfilesize=" + str(len(index)) + "\nsametypesequence=m\n")
                archive.writestr("sample.idx", index)
                archive.writestr("sample.dict", definition)
            service = DictionaryService(store, root)
            record = service.install_archive(payload.getvalue(), source_language="en", target_language="en", created_by_user_id=admin.user_id)
            self.assertEqual(record.display_name, "Zip")
            self.assertEqual(list((root / "data" / "dictionaries").glob(".import-*")), [])

    def test_installs_stardict_into_isolated_sqlite_and_looks_up_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root / "data" / "epub-browser.db")
            admin = store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
            base = root / "local"
            definition = b"to move quickly"
            index = b"run\0" + struct.pack(">II", 0, len(definition))
            base.with_suffix(".ifo").write_text(
                "StarDict's dict ifo file\nversion=2.4.2\nbookname=Local\nwordcount=1\nidxfilesize="
                + str(len(index)) + "\nsametypesequence=m\n", encoding="utf-8"
            )
            base.with_suffix(".idx").write_bytes(index)
            base.with_suffix(".dict").write_bytes(definition)
            base.with_suffix(".syn").write_bytes(b"running\0" + struct.pack(">I", 0))
            service = DictionaryService(store, root)

            record = service.install(base.with_suffix(".ifo"), source_language="en", target_language="en", created_by_user_id=admin.user_id)
            service.set_default("en", record.id, admin.user_id)
            result = service.lookup("en", "running")

            self.assertTrue(result.found)
            self.assertEqual(result.entries[0]["headword"], "run")
            self.assertEqual(result.entries[0]["definition"], "to move quickly")
            self.assertTrue((root / "data" / "dictionaries" / (record.id + ".sqlite")).is_file())

    def test_missing_default_does_not_create_query_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root / "data" / "epub-browser.db")
            store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
            service = DictionaryService(store, root)
            with self.assertRaisesRegex(DictionaryServiceError, "dictionary_not_configured"):
                service.lookup("en", "run")


if __name__ == "__main__":
    unittest.main()
