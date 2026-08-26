import struct
import tempfile
import unittest
from pathlib import Path

from epub_browser.dictionary_formats import parse_local_dictionary, read_mdict_resources


class DictionaryFormatTests(unittest.TestCase):
    def test_reads_stardict_words_aliases_and_plain_text_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "sample"
            definition = b"<b>to `move`</b><script>alert(1)</script> quickly"
            index = b"run\0" + struct.pack(">II", 0, len(definition))
            (base.with_suffix(".ifo")).write_text(
                "StarDict's dict ifo file\nversion=2.4.2\nbookname=Sample\nwordcount=1\nidxfilesize="
                + str(len(index)) + "\nsametypesequence=m\n", encoding="utf-8"
            )
            base.with_suffix(".idx").write_bytes(index)
            base.with_suffix(".dict").write_bytes(definition)
            base.with_suffix(".syn").write_bytes(b"running\0" + struct.pack(">I", 0))

            result = parse_local_dictionary(base.with_suffix(".ifo"))

        self.assertEqual(result.format, "stardict")
        self.assertEqual(result.display_name, "Sample")
        self.assertEqual(result.entries[0].headword, "run")
        self.assertEqual(result.entries[0].aliases, ("running",))
        self.assertEqual(result.entries[0].definition_text, "to `move` quickly")

    def test_reads_unencrypted_mdict_entries_when_optional_runtime_is_installed(self):
        try:
            from mdict_utils.base.writemdict import MDictWriter
        except ImportError:
            self.skipTest("mdict-utils is installed with the server extra")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.mdx"
            writer = MDictWriter(
                {"run": "<b>to move</b>"}, title="Sample", description="",
                encoding="utf8", compression_type=2, version="2.0",
            )
            with path.open("wb") as handle:
                writer.write(handle)
            result = parse_local_dictionary(path)
        self.assertEqual(result.format, "mdict")
        self.assertEqual(result.entries[0].definition_text, "to move")

    def test_skips_unusable_empty_mdict_entries_without_rejecting_the_dictionary(self):
        try:
            from mdict_utils.base.writemdict import MDictWriter
        except ImportError:
            self.skipTest("mdict-utils is installed with the server extra")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.mdx"
            with path.open("wb") as handle:
                MDictWriter(
                    {"usable": "definition", "empty": "<img src=\"https://example.test/image.png\">"},
                    title="Sample", description="", encoding="utf8", compression_type=2, version="2.0",
                ).write(handle)
            result = parse_local_dictionary(path)
        self.assertEqual([entry.headword for entry in result.entries], ["usable"])

    def test_reads_mdd_resources_without_an_arbitrary_asset_count_limit(self):
        try:
            from mdict_utils.base.writemdict import MDictWriter
        except ImportError:
            self.skipTest("mdict-utils is installed with the server extra")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.mdd"
            assets = {
                "\\\\images\\\\%03d.png" % number: b"\x89PNG\r\n\x1a\nasset"
                for number in range(513)
            }
            with path.open("wb") as handle:
                MDictWriter(assets, title="Sample", description="", compression_type=2, version="2.0", is_mdd=True).write(handle)
            resources = read_mdict_resources(
                path, {"images/%03d.png" % number for number in range(513)},
            )
        self.assertEqual(len(resources), 513)


if __name__ == "__main__":
    unittest.main()
