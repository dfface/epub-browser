from typing import Optional

from .cli import ServerConfig
from .migration import MigrationError, MigrationManager
from .reporting import Reporter


def run_server(
    config: ServerConfig,
    reporter: Optional[Reporter] = None,
) -> int:
    active_reporter = reporter or Reporter(config.log)
    if not config.ephemeral:
        try:
            result = MigrationManager(
                config.server_dir,
                config.legacy_sync_dir,
            ).prepare_data()
        except MigrationError as error:
            active_reporter.error(f"Server data migration failed: {error}")
            return 3
        for warning in result.warnings:
            active_reporter.notice(warning)

    # Task 9 replaces this compatibility startup after the persistent data and
    # incremental cache layers are both available.
    from .main import _run_existing_pipeline

    return _run_existing_pipeline(config, active_reporter)
