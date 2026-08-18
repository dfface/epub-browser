import contextlib
import io
import unittest
from pathlib import Path
from unittest import mock

from epub_browser.cli import (
    SSGConfig,
    ServerConfig,
    format_legacy_migration_hint,
    parse_cli,
)
from epub_browser.main import main


class NewCommandTests(unittest.TestCase):
    def test_ssg_parses_output_and_base_path(self):
        config = parse_cli(
            ["ssg", "books", "--output-dir", "dist", "--base-path", "/reader/"]
        )

        self.assertEqual(
            config,
            SSGConfig(
                sources=(Path("books"),),
                output_dir=Path("dist"),
                base_path="/reader/",
            ),
        )

    def test_server_parses_persistent_storage_and_safe_network_defaults(self):
        config = parse_cli(["server", "books", "--server-dir", "state"])

        self.assertEqual(
            config,
            ServerConfig(
                sources=(Path("books"),),
                server_dir=Path("state"),
                ephemeral=False,
            ),
        )
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8000)

    def test_server_requires_exactly_one_storage_mode(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_cli(["server", "books"])

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_cli(
                ["server", "books", "--server-dir", "state", "--ephemeral"]
            )

    def test_mode_specific_options_are_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_cli(["ssg", "books", "--output-dir", "dist", "--port", "9000"])

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_cli(
                ["server", "books", "--server-dir", "state", "--base-path", "/reader/"]
            )


class LegacyCommandTests(unittest.TestCase):
    def test_old_output_dir_maps_to_persistent_server(self):
        config = parse_cli(
            [
                "books",
                "--output-dir",
                "state",
                "--sync-dir",
                "old-sync",
                "--watch",
                "--keep-files",
            ]
        )

        self.assertIsInstance(config, ServerConfig)
        self.assertEqual(config.server_dir, Path("state"))
        self.assertEqual(config.legacy_sync_dir, Path("old-sync"))
        self.assertTrue(config.watch)
        self.assertTrue(config.legacy_invocation)
        self.assertFalse(config.retain_legacy_temporary_dir)

    def test_old_no_server_maps_to_ssg(self):
        config = parse_cli(
            ["books", "--no-server", "--output-dir", "dist"]
        )

        self.assertEqual(
            config,
            SSGConfig(
                sources=(Path("books"),),
                output_dir=Path("dist"),
                base_path="/",
                legacy_invocation=True,
            ),
        )

    def test_old_without_output_maps_to_ephemeral_server(self):
        config = parse_cli(["book.epub"])

        self.assertIsInstance(config, ServerConfig)
        self.assertTrue(config.ephemeral)
        self.assertIsNone(config.server_dir)
        self.assertTrue(config.legacy_invocation)

    def test_old_temporary_keep_files_is_preserved_for_compatibility(self):
        config = parse_cli(["book.epub", "--keep-files"])

        self.assertTrue(config.ephemeral)
        self.assertTrue(config.retain_legacy_temporary_dir)

    def test_legacy_hint_shows_the_equivalent_new_command(self):
        config = parse_cli(
            ["books", "--output-dir", "state", "--watch", "--no-browser"]
        )

        self.assertEqual(
            format_legacy_migration_hint(config),
            "Legacy command syntax is deprecated; equivalent command: "
            "epub-browser server books --server-dir state --watch --no-browser",
        )

    def test_new_command_has_no_legacy_hint(self):
        config = parse_cli(["server", "books", "--server-dir", "state"])

        self.assertIsNone(format_legacy_migration_hint(config))


class MainDispatchTests(unittest.TestCase):
    def test_main_dispatches_ssg_config_to_the_ssg_runner(self):
        with mock.patch("epub_browser.main.run_ssg", return_value=23) as run_ssg:
            status = main(["ssg", "books", "--output-dir", "dist"])

        self.assertEqual(status, 23)
        config = run_ssg.call_args.args[0]
        self.assertEqual(config.output_dir, Path("dist"))

    def test_main_prints_one_legacy_hint_before_dispatch(self):
        with (
            mock.patch("epub_browser.main.run_server", return_value=0),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            status = main(["books", "--output-dir", "state"])

        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue().count("Legacy command syntax is deprecated"), 1)


if __name__ == "__main__":
    unittest.main()
