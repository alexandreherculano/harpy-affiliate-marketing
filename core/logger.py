"""Structured logging for Harpy."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class Logger:
    _instance: Optional["Logger"] = None

    def __init__(self, log_dir: str = "logs", level: str = "INFO") -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger("harpy")
        self._logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        self._logger.handlers.clear()

        date_str = datetime.now().strftime("%Y-%m-%d")
        file_handler = logging.FileHandler(self.log_dir / f"harpy-{date_str}.log")
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        self._logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        self._logger.addHandler(stream_handler)

    @classmethod
    def get(cls, log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
        if cls._instance is None:
            cls._instance = cls(log_dir=log_dir, level=level)
        return cls._instance._logger


def get_logger(log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    return Logger.get(log_dir=log_dir, level=level)
