import struct
import tempfile
import unittest
import gzip
import io
import sqlite3
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

    def test_installs_stardict_archive_with_more_than_the_former_16_file_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root / "data" / "epub-browser.db")
            admin = store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
            definition = b"to move quickly"
            index = b"run\0" + struct.pack(">II", 0, len(definition))
            payload = io.BytesIO()
            with zipfile.ZipFile(payload, "w") as archive:
                archive.writestr("sample.ifo", "StarDict's dict ifo file\nversion=2.4.2\nbookname=Many files\nwordcount=1\nidxfilesize=" + str(len(index)) + "\nsametypesequence=m\n")
                archive.writestr("sample.idx", index)
                archive.writestr("sample.dict", definition)
                for number in range(14):
                    archive.writestr("extra-%02d.txt" % number, "metadata")

            service = DictionaryService(store, root)
            record = service.install_upload(payload.getvalue(), "many-files.zip", created_by_user_id=admin.user_id)

            self.assertEqual(record.display_name, "many-files")
            self.assertEqual(service.lookup(record.id, "run").entries[0]["definition"], "to move quickly")

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
            entry = service.lookup(record.id, "词典").entries[0]
            self.assertEqual(entry["definition"], "<b>本地释义</b>")
            self.assertEqual(entry["definition_format"], "mdict")

    def test_attaches_mdd_images_and_audio_referenced_by_mdx_entries(self):
        try:
            from mdict_utils.base.writemdict import MDictWriter
        except ImportError:
            self.skipTest("mdict-utils is installed with the server dependency")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root / "data" / "epub-browser.db")
            admin = store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
            mdx = io.BytesIO()
            MDictWriter(
                {
                    "run": (
                        "<link rel=\"stylesheet\" href=\"entry.css\"><p>to move</p><img src=\"file://\\\\images\\\\run.png\">"
                        "<audio src=\"file://\\\\audio\\\\run.mp3\"></audio>"
                    )
                }, title="Media", description="", encoding="utf8", compression_type=2, version="2.0",
            ).write(mdx)
            mdd = io.BytesIO()
            MDictWriter(
                {
                    "entry.css": b".entry { color: #123456; }",
                    "\\\\images\\\\run.png": b"\x89PNG\r\n\x1a\nimage-data",
                    "\\\\audio\\\\run.mp3": b"ID3audio-data",
                }, title="Media", description="", compression_type=2, version="2.0", is_mdd=True,
            ).write(mdd)

            service = DictionaryService(store, root)
            record = service.install_upload(mdx.getvalue(), "media.mdx", created_by_user_id=admin.user_id)
            service.attach_mdict_resources(record.id, mdd.getvalue(), "media.mdd")

            entry = service.lookup(record.id, "run").entries[0]
            self.assertEqual(
                entry["definition"],
                '<link rel="stylesheet" href="entry.css"><p>to move</p><img src="file://\\\\images\\\\run.png"><audio src="file://\\\\audio\\\\run.mp3"></audio>',
            )
            self.assertEqual(entry["definition_format"], "mdict")
            self.assertEqual([item["kind"] for item in entry["media"]], ["stylesheet", "image", "audio"])
            self.assertEqual([item["reference"] for item in entry["media"]], ["entry.css", "images/run.png", "audio/run.mp3"])
            stylesheet = service.get_media(record.id, entry["media"][0]["id"])
            image = service.get_media(record.id, entry["media"][1]["id"])
            audio = service.get_media(record.id, entry["media"][2]["id"])
            self.assertEqual(stylesheet["content_type"], "text/css; charset=utf-8")
            self.assertEqual(image["content_type"], "image/png")
            self.assertEqual(image["content"], b"\x89PNG\r\n\x1a\nimage-data")
            self.assertEqual(audio["content_type"], "audio/mpeg")
            self.assertEqual(audio["content"], b"ID3audio-data")

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

    def test_discards_existing_dictionary_files_that_lost_source_formatting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root / "data" / "epub-browser.db")
            admin = store.initialize(BootstrapCredentials("admin", "correct horse battery staple"))
            dictionary_id = "legacy"
            store.create_dictionary(
                dictionary_id=dictionary_id, display_name="Legacy", source_language="und", target_language="und",
                entry_count=1, content_sha256="a" * 64, attribution="", created_by_user_id=admin.user_id,
            )
            dictionary_directory = root / "data" / "dictionaries"
            dictionary_directory.mkdir()
            with sqlite3.connect(dictionary_directory / (dictionary_id + ".sqlite")) as connection:
                connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute("INSERT INTO meta(key, value) VALUES ('format', 'stardict')")
                connection.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY, headword TEXT NOT NULL, normalized_headword TEXT NOT NULL, definition_text TEXT NOT NULL)")
                connection.execute("CREATE TABLE forms (normalized_form TEXT NOT NULL, entry_id INTEGER NOT NULL, PRIMARY KEY(normalized_form, entry_id))")
                connection.execute("INSERT INTO entries(id, headword, normalized_headword, definition_text) VALUES (1, 'run', 'run', 'legacy definition')")
                connection.execute("INSERT INTO forms(normalized_form, entry_id) VALUES ('run', 1)")

            DictionaryService(store, root)

            self.assertIsNone(store.get_dictionary(dictionary_id))
            self.assertFalse((dictionary_directory / (dictionary_id + ".sqlite")).exists())


if __name__ == "__main__":
    unittest.main()
