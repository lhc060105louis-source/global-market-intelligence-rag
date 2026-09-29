from __future__ import annotations

import logging
import os
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable

from app.paths import AppPaths


def find_available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class UvicornServer:
    def __init__(self, port: int):
        import uvicorn
        from app.main import create_app

        self.server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="info"))
        self.thread = threading.Thread(target=self.server.run, name="kol-platform-server", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.should_exit = True
        if self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=5)


def _health_check(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:
            return response.status == 200
    except Exception:
        return False


def _show_error(message: str) -> None:
    try:
        from tkinter import messagebox

        messagebox.showerror("KOL 合作管理平台", message)
    except Exception:
        pass


class Launcher:
    def __init__(
        self,
        *,
        lock_path: Path | None = None,
        port_finder: Callable[[], int] = find_available_port,
        health_check: Callable[[str], bool] = _health_check,
        browser_open: Callable[[str], object] = webbrowser.open,
        server_factory: Callable[[int], object] = UvicornServer,
        error_reporter: Callable[[str], None] = _show_error,
        timeout: float = 20,
        poll_interval: float = 0.1,
    ):
        paths = AppPaths.from_environment()
        self.lock_path = lock_path or paths.data_dir / "launcher.lock"
        self.log_path = paths.log_dir / "launcher.log"
        self.port_finder = port_finder
        self.health_check = health_check
        self.browser_open = browser_open
        self.server_factory = server_factory
        self.error_reporter = error_reporter
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.server = None
        self.port = None
        self._owns_lock = False
        self.tray = None

    def _existing_port(self) -> int | None:
        try:
            return int(self.lock_path.read_text("utf-8").strip())
        except (OSError, ValueError):
            return None

    def _claim_lock(self, port: int) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(str(port))
        self._owns_lock = True
        return True

    def _report_failure(self, message: str) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            logging.basicConfig(filename=self.log_path, level=logging.INFO, force=True)
            logging.exception(message)
        except OSError:
            pass
        self.error_reporter(message)

    def _run_tray(self) -> None:
        import pystray
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (64, 64), "#0D9488")
        ImageDraw.Draw(image).text((20, 13), "K", fill="white")
        self.tray = pystray.Icon("kol-platform", image, "KOL 合作管理平台", pystray.Menu(
            pystray.MenuItem("打开平台", lambda icon, item: self.open_platform()),
            pystray.MenuItem("退出平台", lambda icon, item: self.shutdown()),
        ))
        self.tray.run()

    def open_platform(self) -> None:
        if self.port is not None:
            self.browser_open(f"http://127.0.0.1:{self.port}/")

    def _wait_until_healthy(self, url: str) -> bool:
        deadline = time.monotonic() + self.timeout
        healthy = self.health_check(url)
        while not healthy and time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            healthy = self.health_check(url)
        return healthy

    def run(self, *, show_tray: bool = True) -> int:
        existing = self._existing_port()
        if existing is not None and self._wait_until_healthy(f"http://127.0.0.1:{existing}/health"):
            self.port = existing
            self.open_platform()
            return 0
        if self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except OSError:
                self._report_failure("无法获取单实例锁。")
                return 1
        self.port = self.port_finder()
        if not self._claim_lock(self.port):
            self._report_failure("平台已在启动，请稍后重试。")
            return 1
        try:
            self.server = self.server_factory(self.port)
            self.server.start()
            if not self._wait_until_healthy(f"http://127.0.0.1:{self.port}/health"):
                raise TimeoutError("服务未在 20 秒内就绪。")
            self.open_platform()
            if show_tray:
                self._run_tray()
            return 0
        except Exception as exc:
            self.shutdown()
            self._report_failure(f"启动失败：{exc}")
            return 1

    def shutdown(self) -> None:
        if self.server is not None:
            self.server.stop()
        if self.tray is not None:
            self.tray.stop()
        if self._owns_lock:
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass
            self._owns_lock = False


def main() -> int:
    return Launcher().run()


if __name__ == "__main__":
    raise SystemExit(main())
