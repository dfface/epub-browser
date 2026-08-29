import contextlib
import io
import unittest
from unittest import mock

from epub_browser.reporting import Reporter


class ReporterTests(unittest.TestCase):
    def test_routine_output_and_warnings_are_silent_by_default(self):
        reporter = Reporter(log_enabled=False)

        with (
            contextlib.redirect_stdout(io.StringIO()) as stdout,
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            reporter.detail("cache hit")
            reporter.warning("recoverable warning")
            reporter.error("conversion failed")

        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "conversion failed\n")

    def test_warning_level_includes_warnings_but_not_details(self):
        reporter = Reporter(log_enabled="warning")

        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            reporter.detail("cache hit")
            reporter.warning("recoverable warning")

        self.assertEqual(stderr.getvalue(), "recoverable warning\n")

    def test_detail_is_visible_with_log(self):
        reporter = Reporter(log_enabled=True)

        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            reporter.detail("cache hit")

        self.assertEqual(stderr.getvalue(), "cache hit\n")

    def test_notice_is_silent_without_log(self):
        reporter = Reporter(log_enabled=False)
        reporter.progress_active = True

        with mock.patch("epub_browser.reporting.tqdm.write") as write:
            reporter.notice("legacy syntax")

        write.assert_not_called()

    def test_active_progress_log_uses_tqdm_writer(self):
        reporter = Reporter(log_enabled=True)
        reporter.progress_active = True

        with mock.patch("epub_browser.reporting.tqdm.write") as write:
            reporter.notice("migration warning")

        write.assert_called_once()
        self.assertEqual(write.call_args.args[0], "migration warning")

    def test_result_uses_stdout_when_progress_is_inactive(self):
        reporter = Reporter(log_enabled=False)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            reporter.result("Files generated")

        self.assertEqual(stdout.getvalue(), "Files generated\n")


if __name__ == "__main__":
    unittest.main()
