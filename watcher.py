#!/usr/bin/env python3
"""
Watcher: führt den Agent automatisch in einem konfigurierbaren Intervall aus.
Geeignet für den Dauerbetrieb im Docker-Container.

Konfiguration via .env:
    WATCH_INTERVAL_MINUTES=30   (Standard: 30 Minuten)
"""

import time
import os
from datetime import datetime, timedelta
from core import init_db
from agent import scan_vault, process_pending_jobs, _count_pending_jobs

INTERVAL_MINUTES = int(os.getenv("WATCH_INTERVAL_MINUTES", "30"))
INTERVAL_SECONDS = INTERVAL_MINUTES * 60


def run_cycle():
    print(f"\n{'='*60}")
    print(f"[WATCHER] Start: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    print(f"{'='*60}\n")
    scan_vault()
    while _count_pending_jobs() > 0:
        process_pending_jobs()
    print(f"\n[WATCHER] Durchlauf abgeschlossen.")


if __name__ == "__main__":
    print(f"[WATCHER] Gestartet — Intervall: {INTERVAL_MINUTES} Minuten")
    init_db()

    while True:
        run_cycle()
        next_run = datetime.now() + timedelta(seconds=INTERVAL_SECONDS)
        print(f"[WATCHER] Nächster Durchlauf: {next_run.strftime('%d.%m.%Y %H:%M:%S')}\n")
        time.sleep(INTERVAL_SECONDS)
