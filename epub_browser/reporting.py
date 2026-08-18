import sys
from typing import TextIO

from tqdm import tqdm


class Reporter:
    def __init__(self, log_enabled: bool):
        self.log_enabled = log_enabled
        self.progress_active = False

    def detail(self, message: str) -> None:
        if self.log_enabled:
            self._write(message, sys.stderr)

    def notice(self, message: str) -> None:
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
