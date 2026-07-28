"""Exclusive process locks for job runners (fcntl flock)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from portfolio_analysis.paths import job_lock_path, locks_dir


class JobLock:
    """Exclusive non-blocking flock for one job id."""

    def __init__(self, job_id: str, path: Path | None = None) -> None:
        self.job_id = job_id
        self.path = path or job_lock_path(job_id)
        self._fd: int | None = None
        self.held = False

    def try_acquire(self) -> bool:
        import fcntl

        locks_dir().mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            self._fd = None
            self.held = False
            return False
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode("utf-8"))
        except OSError:
            pass
        self._fd = fd
        self.held = True
        return True

    def release(self) -> None:
        import fcntl

        if self._fd is None:
            self.held = False
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            self.held = False

    def __enter__(self) -> JobLock:
        if not self.try_acquire():
            raise RuntimeError(f"job lock already held: {self.job_id}")
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


def is_job_lock_held(job_id: str, path: Path | None = None) -> bool:
    """True if another process holds the lock for ``job_id``."""
    import fcntl

    lock_path = path or job_lock_path(job_id)
    if not lock_path.exists():
        return False
    try:
        fd = os.open(str(lock_path), os.O_RDWR)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)
