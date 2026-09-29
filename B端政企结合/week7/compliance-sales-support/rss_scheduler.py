# -*- coding: utf-8 -*-
"""RSS 抓取执行器与 FastAPI 生命周期内的轻量定时调度。"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import get_session
from models import FetchLog, IntelligenceItem

INTERVAL_MINUTES = max(1, int(os.getenv("RSS_INTERVAL_MINUTES", "60")))
ENABLED = os.getenv("RSS_SCHEDULER_ENABLED", "true").lower() not in {"0", "false", "no"}
_run_lock = threading.Lock()
_task: asyncio.Task | None = None
_state = {"running": False, "next_run": None, "last_trigger": None, "last_status": None}


def run_fetch(trigger: str = "manual") -> dict:
    """运行一次抓取并记录审计日志；自动与手动入口共享。"""
    if not _run_lock.acquire(blocking=False):
        return {"status": "busy", "new_items": 0, "message": "已有抓取任务正在运行"}
    now = datetime.now(timezone.utc)
    _state.update(running=True, last_trigger=trigger)
    try:
        with get_session() as session:
            total_old = session.query(IntelligenceItem).count()
        script = Path(__file__).resolve().parent / "rss_fetcher.py"
        try:
            result = subprocess.run(
                [sys.executable, str(script)], capture_output=True, text=True, timeout=90
            )
            ok = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            ok = False
        with get_session() as session:
            total_new = session.query(IntelligenceItem).count()
            new_count = max(0, total_new - total_old)
            session.add(FetchLog(
                run_at=now, sources=f"EUR-Lex,UK Parliament,TED ({trigger})",
                new_count=new_count, duplicate_count=0, status="ok" if ok else "error",
            ))
            session.commit()
        status = "ok" if ok else "error"
        _state["last_status"] = status
        return {
            "status": status, "trigger": trigger,
            "fetch_time": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "new_items": new_count, "total": total_new,
        }
    finally:
        _state["running"] = False
        _run_lock.release()


async def _scheduler_loop() -> None:
    while True:
        next_run = datetime.now(timezone.utc) + timedelta(minutes=INTERVAL_MINUTES)
        _state["next_run"] = next_run.strftime("%Y-%m-%dT%H:%M:%SZ")
        await asyncio.sleep(INTERVAL_MINUTES * 60)
        await asyncio.to_thread(run_fetch, "scheduled")


def start_scheduler() -> None:
    global _task
    if ENABLED and (_task is None or _task.done()):
        _task = asyncio.create_task(_scheduler_loop(), name="rss-scheduler")


async def stop_scheduler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    _state["next_run"] = None


def scheduler_status() -> dict:
    return {
        "enabled": ENABLED,
        "active": bool(_task and not _task.done()),
        "interval_minutes": INTERVAL_MINUTES,
        **_state,
    }
