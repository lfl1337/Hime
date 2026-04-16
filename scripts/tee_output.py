"""
Shared TeeOutput utility for training scripts.

Wraps a file-like object (stdout/stderr) so all output is both forwarded
to the original stream and written to a timestamped log file.

Import:
    from tee_output import TeeOutput
"""

from datetime import datetime


class TeeOutput:
    def __init__(self, original, log_file):
        self.original = original
        self.log_file = log_file
        self._buffer = ""

    def _timestamp(self) -> str:
        return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

    def write(self, text):
        self.original.write(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self.log_file.write(f"{self._timestamp()} {line}\n")
                self.log_file.flush()

    def flush(self):
        self.original.flush()
        if self._buffer.strip():
            self.log_file.write(f"{self._timestamp()} {self._buffer}\n")
            self.log_file.flush()
            self._buffer = ""

    def isatty(self): return False
