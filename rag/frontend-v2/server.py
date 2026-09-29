"""Serve the second-generation RAG UI and proxy the formal RAG Hub locally."""
from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
STATIC_ROOT = Path(os.getenv("RAG_FRONTEND_STATIC_ROOT", str(DIST if (DIST / "index.html").exists() else HERE))).expanduser()
SERVICE_ENV = Path(
    os.getenv("RAG_HUB_SERVICE_ENV", str(HERE.parent / "service" / ".env"))
).expanduser()
RAG_HUB_URL = os.getenv("RAG_HUB_INTERNAL_URL", "http://127.0.0.1:8001").rstrip("/")
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = 75.0


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class FrontendHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/backend/health":
            self._proxy(authenticated=False)
        elif self.path.startswith("/backend/"):
            self._proxy(authenticated=True)
        else:
            if self.path == "/":
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.startswith("/backend/"):
            self._proxy(authenticated=True)
        else:
            self.send_error(404)

    def _proxy(self, *, authenticated: bool) -> None:
        parsed = urlsplit(self.path)
        upstream_path = parsed.path.removeprefix("/backend")
        url = f"{RAG_HUB_URL}{upstream_path}"
        if parsed.query:
            url += f"?{parsed.query}"

        body = None
        if self.command in {"POST", "PUT", "PATCH"}:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""

        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = self.headers.get("Content-Type", "application/json")
        if authenticated:
            api_key = load_env(SERVICE_ENV).get("RAG_HUB_API_KEY", "")
            if not api_key:
                self._json_error(503, "RAG Hub 本机密钥尚未配置")
                return
            headers["X-API-Key"] = api_key

        env_values = load_env(SERVICE_ENV)
        configured_timeout = os.getenv(
            "RAG_FRONTEND_UPSTREAM_TIMEOUT_SECONDS",
            env_values.get("RAG_FRONTEND_UPSTREAM_TIMEOUT_SECONDS", str(DEFAULT_UPSTREAM_TIMEOUT_SECONDS)),
        )
        try:
            timeout = max(float(configured_timeout), 1.0)
        except ValueError:
            timeout = DEFAULT_UPSTREAM_TIMEOUT_SECONDS

        try:
            with urlopen(Request(url, data=body, headers=headers, method=self.command), timeout=timeout) as response:
                payload = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
        except HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.end_headers()
            self.wfile.write(payload)
        except (URLError, TimeoutError) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            self._json_error(502, f"无法连接 RAG Hub：{reason}")

    def _json_error(self, status: int, message: str) -> None:
        payload = json.dumps({"detail": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    host = os.getenv("RAG_FRONTEND_HOST", "127.0.0.1")
    port = int(os.getenv("RAG_FRONTEND_PORT", "8010"))
    print(f"RAG frontend v2 available at http://{host}:{port}")
    ThreadingHTTPServer((host, port), FrontendHandler).serve_forever()
