import struct
import tempfile
import unittest
import gzip
import io
import tarfile
import zipfile
from pathlib import Path

from epub_browser.auth import BootstrapCredentials
from epub_browser.dictionary_service import DictionaryService, DictionaryServiceError
from epub_browser.state import StateStore


class DictionaryServiceTests(unittest.TestCase):
    def test_installs_stardict_tar_bz2_with_a_nested_compressed_dictionary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root / "data" / "epub-browser.db")
            admin = store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
            definition = b"to move quickly"
            index = b"run\0" + struct.pack(">II", 0, len(definition))
            files = {
                "stardict-oxford-gb-2.4.2/oxford-gb.ifo": (
                    "StarDict's dict ifo file\nversion=2.4.2\nbookname=Oxford GB\nwordcount=1\n"
                    "idxfilesize=" + str(len(index)) + "\nsametypesequence=m\n"
                ).encode("utf-8"),
                "stardict-oxford-gb-2.4.2/oxford-gb.idx": index,
                "stardict-oxford-gb-2.4.2/oxford-gb.dict.dz": gzip.compress(definition),
            }
            payload = io.BytesIO()
            with tarfile.open(fileobj=payload, mode="w:bz2") as archive:
                for name, content in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))

            service = DictionaryService(store, root)
            try:
                record = service.install_upload(
                    payload.getvalue(), "stardict-oxford-gb-2.4.2.tar.bz2",
                    created_by_user_id=admin.user_id,
                )
            except DictionaryServiceError as error:
                self.fail("tar.bz2 StarDict package was rejected: " + error.code)

            self.assertEqual(record.display_name, "stardict-oxford-gb-2.4.2")
            self.assertEqual(service.lookup(record.id, "run").entries[0]["definition"], "to move quickly")

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
            record = service.install_archive(payload.getvalue(), created_by_user_id=admin.user_id)
            self.assertEqual(record.display_name, "Zip")
            self.assertEqual(list((root / "data" / "dictionaries").glob(".import-*")), [])

    def test_installs_an_mdx_upload_directly(self):
        try:
            from mdict_utils.base.writemdict import MDictWriter
        except ImportError:
            self.skipTest("mdict-utils is installed with the server dependency")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root / "data" / "epub-browser.db")
            admin = store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
            payload = io.BytesIO()
            MDictWriter(
                {"词典": "<b>本地释义</b>"}, title="Sample", description="",
                encoding="utf8", compression_type=2, version="2.0",
            ).write(payload)

            service = DictionaryService(store, root)
            record = service.install_upload(payload.getvalue(), "sample.mdx", created_by_user_id=admin.user_id)

            self.assertEqual(record.display_name, "sample")
            self.assertEqual(service.lookup(record.id, "词典").entries[0]["definition"], "本地释义")

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

            record = service.install(base.with_suffix(".ifo"), created_by_user_id=admin.user_id)
            result = service.lookup(record.id, "running")

            self.assertTrue(result.found)
            self.assertEqual(result.entries[0]["headword"], "run")
            self.assertEqual(result.entries[0]["definition"], "to move quickly")
            self.assertTrue((root / "data" / "dictionaries" / (record.id + ".sqlite")).is_file())

    def test_missing_dictionary_does_not_create_query_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root / "data" / "epub-browser.db")
            store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
            service = DictionaryService(store, root)
            with self.assertRaisesRegex(DictionaryServiceError, "dictionary_unavailable"):
                service.lookup("missing", "run")


if __name__ == "__main__":
    unittest.main()
