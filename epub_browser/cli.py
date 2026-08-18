import argparse
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

from .urls import normalize_base_path


@dataclass(frozen=True)
class SSGConfig:
    sources: Tuple[Path, ...]
    output_dir: Optional[Path]
    base_path: str = "/"
    legacy_invocation: bool = False
    legacy_temporary_output: bool = False
    log: bool = False


@dataclass(frozen=True)
class ServerConfig:
    sources: Tuple[Path, ...]
    server_dir: Optional[Path]
    ephemeral: bool
    watch: bool = False
    host: str = "127.0.0.1"
    port: int = 8000
    no_browser: bool = False
    log: bool = False
    legacy_sync_dir: Optional[Path] = None
    retain_legacy_temporary_dir: bool = False
    legacy_invocation: bool = False


CommandConfig = Union[SSGConfig, ServerConfig]


def _new_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epub-browser",
        description="EPUB Browser static-site generator and reading server",
    )
    modes = parser.add_subparsers(dest="mode", required=True)

    ssg = modes.add_parser("ssg", help="Generate a standalone static site")
    ssg.add_argument("sources", nargs="+", metavar="SOURCE")
    ssg.add_argument("--output-dir", "-o", required=True)
    ssg.add_argument("--base-path", default="/")
    ssg.add_argument("--log", action="store_true")

    server = modes.add_parser("server", help="Run the stateful reading server")
    server.add_argument("sources", nargs="+", metavar="SOURCE")
    storage = server.add_mutually_exclusive_group(required=True)
    storage.add_argument("--server-dir")
    storage.add_argument("--ephemeral", action="store_true")
    server.add_argument("--watch", "-w", action="store_true")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", "-p", type=int, default=8000)
    server.add_argument("--no-browser", action="store_true")
    server.add_argument("--log", action="store_true")
    server.add_argument("--legacy-sync-dir")
    return parser


def _legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epub-browser",
        description="EPUB to Web Converter - Multi-book Support",
    )
    parser.add_argument("sources", nargs="+", metavar="SOURCE")
    parser.add_argument("--port", "-p", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--output-dir", "-o")
    parser.add_argument("--keep-files", action="store_true")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--no-server", action="store_true")
    parser.add_argument("--watch", "-w", action="store_true")
    parser.add_argument("--sync-dir")
    return parser


def parse_cli(argv: Sequence[str]) -> CommandConfig:
    arguments = list(argv)
    if arguments and arguments[0] in {"ssg", "server"}:
        values = _new_parser().parse_args(arguments)
        sources = tuple(Path(source) for source in values.sources)
        if values.mode == "ssg":
            return SSGConfig(
                sources=sources,
                output_dir=Path(values.output_dir),
                base_path=normalize_base_path(values.base_path),
                log=values.log,
            )
        return ServerConfig(
            sources=sources,
            server_dir=Path(values.server_dir) if values.server_dir else None,
            ephemeral=values.ephemeral,
            watch=values.watch,
            host=values.host,
            port=values.port,
            no_browser=values.no_browser,
            log=values.log,
            legacy_sync_dir=(
                Path(values.legacy_sync_dir) if values.legacy_sync_dir else None
            ),
        )

    values = _legacy_parser().parse_args(arguments)
    sources = tuple(Path(source) for source in values.sources)
    if values.no_server:
        return SSGConfig(
            sources=sources,
            output_dir=Path(values.output_dir) if values.output_dir else None,
            legacy_invocation=True,
            legacy_temporary_output=not bool(values.output_dir),
            log=values.log,
        )
    return ServerConfig(
        sources=sources,
        server_dir=Path(values.output_dir) if values.output_dir else None,
        ephemeral=not bool(values.output_dir),
        watch=values.watch,
        port=values.port,
        no_browser=values.no_browser,
        log=values.log,
        legacy_sync_dir=Path(values.sync_dir) if values.sync_dir else None,
        retain_legacy_temporary_dir=bool(values.keep_files and not values.output_dir),
        legacy_invocation=True,
    )


def format_legacy_migration_hint(config: CommandConfig) -> Optional[str]:
    if not config.legacy_invocation:
        return None

    command = ["epub-browser"]
    if isinstance(config, SSGConfig):
        command.extend(["ssg", *(str(path) for path in config.sources)])
        if config.output_dir is not None:
            command.extend(["--output-dir", str(config.output_dir)])
        if config.base_path != "/":
            command.extend(["--base-path", config.base_path])
        if config.log:
            command.append("--log")
    else:
        command.extend(["server", *(str(path) for path in config.sources)])
        if config.server_dir is not None:
            command.extend(["--server-dir", str(config.server_dir)])
        else:
            command.append("--ephemeral")
        if config.watch:
            command.append("--watch")
        if config.host != "127.0.0.1":
            command.extend(["--host", config.host])
        if config.port != 8000:
            command.extend(["--port", str(config.port)])
        if config.no_browser:
            command.append("--no-browser")
        if config.log:
            command.append("--log")
        if config.legacy_sync_dir is not None:
            command.extend(["--legacy-sync-dir", str(config.legacy_sync_dir)])

    return (
        "Legacy command syntax is deprecated; equivalent command: "
        + shlex.join(command)
    )
