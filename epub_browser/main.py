#!/usr/bin/env python3

import sys

from .cli import SSGConfig, format_legacy_migration_hint, parse_cli
from .reporting import Reporter
from .runtime import run_server
from .ssg import run_ssg


def main(argv=None):
    config = parse_cli(sys.argv[1:] if argv is None else argv)
    reporter = Reporter(config.log)
    hint = format_legacy_migration_hint(config)
    if hint:
        reporter.notice(hint)
    if isinstance(config, SSGConfig):
        return run_ssg(config, reporter)
    return run_server(config, reporter)


if __name__ == "__main__":
    raise SystemExit(main())
