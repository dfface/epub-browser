import contextlib
import io
import subprocess
import sys
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
    def test_book_id_storage_defaults_to_sidecar_in_both_modes(self):
        ssg = parse_cli(["ssg", "books", "--output-dir", "dist"])
        server = parse_cli(["server", "books", "--server-dir", "state"])
        self.assertEqual(ssg.book_id_storage, "sidecar")
        self.assertEqual(server.book_id_storage, "sidecar")

    def test_book_id_storage_is_invocation_wide_in_both_modes(self):
        ssg = parse_cli(
            [
                "ssg",
                "one.epub",
                "two.epub",
                "--output-dir",
                "dist",
                "--book-id-storage",
                "embedded",
            ]
        )
        server = parse_cli(
            [
                "server",
                "books",
                "--server-dir",
                "state",
                "--book-id-storage",
                "embedded",
            ]
        )
        self.assertEqual(ssg.book_id_storage, "embedded")
        self.assertEqual(server.book_id_storage, "embedded")

    def test_invalid_book_id_storage_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_cli(
                [
                    "ssg",
                    "books",
                    "--output-dir",
                    "dist",
                    "--book-id-storage",
                    "database",
                ]
            )

    def test_book_id_storage_help_explains_pdf_fallback(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout, self.assertRaises(
            SystemExit
        ) as raised:
            parse_cli(["ssg", "--help"])

        self.assertEqual(raised.exception.code, 0)
        help_text = " ".join(stdout.getvalue().split())
        self.assertIn("embedded storage is EPUB-only", help_text)
        self.assertIn("PDF always uses a sidecar", help_text)

    def test_ssg_cli_parses_without_loading_argon2(self):
        script = """
import builtins
original_import = builtins.__import__

def without_argon2(name, *args, **kwargs):
    if name == 'argon2' or name.startswith('argon2.'):
        raise ImportError('argon2 must not load for SSG')
    return original_import(name, *args, **kwargs)

builtins.__import__ = without_argon2
from epub_browser.cli import parse_cli
config = parse_cli(['ssg', 'books', '--output-dir', 'dist'])
assert config.output_dir.name == 'dist'
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ssg_parses_output_and_base_path(self):
        config = parse_cli(
            ["ssg", "books", "--output-dir", "dist", "--base-path", "/reader/"]
        )

    def test_ssg_normalizes_and_validates_base_path_at_the_cli_boundary(self):
        config = parse_cli(
            ["ssg", "books", "--output-dir", "dist", "--base-path", "reader"]
        )
        self.assertEqual(config.base_path, "/reader/")

        with contextlib.redirect_stderr(io.StringIO()) as stderr, self.assertRaises(
            SystemExit
        ):
            parse_cli(
                [
                    "ssg",
                    "books",
                    "--output-dir",
                    "dist",
                    "--base-path",
                    "https://example.com/reader/",
                ]
            )
        self.assertIn("Base path must be a URL path", stderr.getvalue())

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

    def test_server_parses_trusted_proxy_cidr_without_affecting_ssg(self):
        config = parse_cli(
            [
                "server",
                "library",
                "--server-dir",
                "data",
                "--trusted-proxy-cidr",
                "10.0.0.0/8",
                "--cookie-secure",
            ]
        )

        self.assertEqual(config.auth.trusted_proxy_cidrs, ("10.0.0.0/8",))
        self.assertTrue(config.auth.cookie_secure)

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_cli(["ssg", "books", "--output-dir", "dist", "--cookie-secure"])

    def test_server_allows_trusted_proxy_cidr_without_identity_headers(self):
        config = parse_cli(
            [
                "server",
                "books",
                "--server-dir",
                "state",
                "--trusted-proxy-cidr",
                "172.16.0.0/12",
            ]
        )

        self.assertEqual(config.auth.trusted_proxy_cidrs, ("172.16.0.0/12",))

    def test_server_rejects_invalid_trusted_proxy_cidr_and_removed_identity_flags(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_cli(
                [
                    "server",
                    "books",
                    "--server-dir",
                    "state",
                    "--trusted-proxy-cidr",
                    "not-a-cidr",
                ]
            )

        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_cli(
                [
                    "server",
                    "books",
                    "--server-dir",
                    "state",
                    "--proxy-subject-header",
                    "X-Remote-User",
                ]
            )

    def test_server_help_documents_bootstrap_environment_fallbacks(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout, self.assertRaises(
            SystemExit
        ) as raised:
            parse_cli(["server", "--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("EPUB_BROWSER_ADMIN_USERNAME", stdout.getvalue())
        self.assertIn("EPUB_BROWSER_ADMIN_PASSWORD_FILE", stdout.getvalue())
        self.assertIn("EPUB_BROWSER_ADMIN_PASSWORD", stdout.getvalue())

    def test_top_level_help_discovers_the_two_v2_modes(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout, self.assertRaises(
            SystemExit
        ) as raised:
            parse_cli(["--help"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("{ssg,server}", stdout.getvalue())
        self.assertIn("static-site generator", stdout.getvalue())


class LegacyCommandTests(unittest.TestCase):
    def test_legacy_book_id_storage_maps_to_the_new_command(self):
        config = parse_cli(
            [
                "books",
                "--output-dir",
                "state",
                "--book-id-storage",
                "embedded",
            ]
        )
        self.assertEqual(config.book_id_storage, "embedded")
        self.assertEqual(
            format_legacy_migration_hint(config),
            "Legacy command syntax is deprecated; equivalent command: "
            "epub-browser server books --server-dir state "
            "--book-id-storage embedded",
        )

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

    def test_main_keeps_legacy_hint_silent_without_log(self):
        with (
            mock.patch("epub_browser.main.run_server", return_value=0),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            status = main(["books", "--output-dir", "state"])

        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")

    def test_main_prints_one_legacy_hint_with_log(self):
        with (
            mock.patch("epub_browser.main.run_server", return_value=0),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            status = main(["books", "--output-dir", "state", "--log"])

        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue().count("Legacy command syntax is deprecated"), 1)


if __name__ == "__main__":
    unittest.main()
