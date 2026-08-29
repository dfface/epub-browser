import sys
from typing import TextIO, Union

from tqdm import tqdm


class Reporter:
    _LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}

    def __init__(self, log_enabled: Union[bool, str]):
        # Booleans remain supported for internal callers and integrations that
        # used Reporter before named log levels were introduced.
        self.log_level = "info" if log_enabled is True else "error"
        if isinstance(log_enabled, str):
            self.log_level = log_enabled
        if self.log_level not in self._LEVELS:
            raise ValueError(f"Unknown log level: {self.log_level}")
        self.progress_active = False

    def detail(self, message: str) -> None:
        if self._enabled("info"):
            self._write(message, sys.stderr)

    def notice(self, message: str) -> None:
        if self._enabled("info"):
            self._write(message, sys.stderr)

    def warning(self, message: str) -> None:
        if self._enabled("warning"):
            self._write(message, sys.stderr)

    def error(self, message: str) -> None:
        self._write(message, sys.stderr)

    def result(self, message: str) -> None:
        self._write(message, sys.stdout)

    def _write(self, message: str, stream: TextIO) -> None:
        if self.progress_active:
            tqdm.write(message, file=stream)
        else:
            print(message, file=stream)

    def _enabled(self, level: str) -> bool:
        return self._LEVELS[level] >= self._LEVELS[self.log_level]
