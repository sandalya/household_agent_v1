"""Захист від дублікатів процесів."""
import os
import sys
import logging
from pathlib import Path

log = logging.getLogger("core.lock")
LOCK_FILE = Path("/tmp/household_agent.lock")

def acquire_lock():
    if LOCK_FILE.exists():
        pid = LOCK_FILE.read_text().strip()
        try:
            os.kill(int(pid), 0)
            log.error(f"Вже запущено (PID {pid}). Виходжу.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            log.warning("Старий lock файл, видаляю.")
            LOCK_FILE.unlink()
    LOCK_FILE.write_text(str(os.getpid()))
    log.info(f"Lock отримано (PID {os.getpid()})")

def release_lock():
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()
    log.info("Lock знято")
