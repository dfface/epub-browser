import argparse
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

from .auth import AuthConfig, ServerAuthOptions
from .book_identity import (
    BOOK_ID_STORAGE_CHOICES,
    BOOK_ID_STORAGE_SIDECAR,
)
from .urls import normalize_base_path


@dataclass(frozen=True)
class SSGConfig:
    sources: Tuple[Path, ...]
    output_dir: Optional[Path]
    base_path: str = "/"
    legacy_invocation: bool = False
    legacy_temporary_output: bool = False
    log: bool = False
    book_id_storage: str = BOOK_ID_STORAGE_SIDECAR


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
    book_id_storage: str = BOOK_ID_STORAGE_SIDECAR
    auth: ServerAuthOptions = ServerAuthOptions()


CommandConfig = Union[SSGConfig, ServerConfig]


def _parse_base_path(value: str) -> str:
    try:
        return normalize_base_path(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _add_book_id_storage(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--book-id-storage",
        choices=BOOK_ID_STORAGE_CHOICES,
        default=BOOK_ID_STORAGE_SIDECAR,
        help="Store stable IDs in visible sidecars (default) or EPUB OPF metadata",
    )


def _new_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epub-browser",
        description="EPUB Browser static-site generator and reading server",
    )
    modes = parser.add_subparsers(dest="mode", required=True)

    ssg = modes.add_parser("ssg", help="Generate a standalone static site")
    ssg.add_argument("sources", nargs="+", metavar="SOURCE")
    ssg.add_argument("--output-dir", "-o", required=True)
    ssg.add_argument("--base-path", default="/", type=_parse_base_path)
    ssg.add_argument("--log", action="store_true")
    _add_book_id_storage(ssg)

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
    _add_book_id_storage(server)
    server.add_argument(
        "--admin-username",
        help=(
            "first-start administrator username "
            "(fallback: EPUB_BROWSER_ADMIN_USERNAME)"
        ),
    )
    server.add_argument(
        "--admin-password-file",
        help=(
            "first-start administrator password file "
            "(fallback: EPUB_BROWSER_ADMIN_PASSWORD_FILE, then "
            "EPUB_BROWSER_ADMIN_PASSWORD when no file is configured)"
        ),
    )
    server.add_argument("--trusted-proxy-cidr", action="append", default=[])
    server.add_argument("--proxy-subject-header")
    server.add_argument("--proxy-display-name-header")
    server.add_argument("--proxy-issuer")
    server.add_argument("--cookie-secure", action="store_true", default=None)
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
    _add_book_id_storage(parser)
    return parser


def parse_cli(argv: Sequence[str]) -> CommandConfig:
    arguments = list(argv)
    if not arguments or arguments[0] in {"ssg", "server", "-h", "--help"}:
        parser = _new_parser()
        values = parser.parse_args(arguments)
        sources = tuple(Path(source) for source in values.sources)
        if values.mode == "ssg":
            return SSGConfig(
                sources=sources,
                output_dir=Path(values.output_dir),
                base_path=values.base_path,
                log=values.log,
                book_id_storage=values.book_id_storage,
            )
        try:
            auth = _server_auth_options(values)
        except ValueError as error:
            parser.error(str(error))
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
            book_id_storage=values.book_id_storage,
            auth=auth,
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
            book_id_storage=values.book_id_storage,
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
        book_id_storage=values.book_id_storage,
    )


def _server_auth_options(values: argparse.Namespace) -> ServerAuthOptions:
    auth = ServerAuthOptions(
        admin_username=values.admin_username,
        admin_password_file=(
            Path(values.admin_password_file) if values.admin_password_file else None
        ),
        trusted_proxy_cidrs=tuple(values.trusted_proxy_cidr),
        proxy_subject_header=values.proxy_subject_header,
        proxy_display_name_header=values.proxy_display_name_header,
        proxy_issuer=values.proxy_issuer,
        cookie_secure=values.cookie_secure,
    )
    AuthConfig.from_values(
        auth.trusted_proxy_cidrs,
        auth.proxy_subject_header,
        auth.proxy_issuer,
        auth.proxy_display_name_header,
        cookie_secure=bool(auth.cookie_secure),
    )
    return auth


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

    if config.book_id_storage != BOOK_ID_STORAGE_SIDECAR:
        command.extend(["--book-id-storage", config.book_id_storage])

    return (
        "Legacy command syntax is deprecated; equivalent command: "
        + shlex.join(command)
    )
