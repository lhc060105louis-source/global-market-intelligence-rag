"""Read-only original MaxKB capability probe.

Usage:
  python scripts/maxkb_probe.py --base-url http://127.0.0.1:8080 --workspace-id <id> --username admin --password <password>
  python scripts/maxkb_probe.py --base-url http://127.0.0.1:8080 --workspace-id <id> --token <token>

The probe never creates or mutates resources; it records route availability only.
"""
from __future__ import annotations
import argparse, json
import httpx


def _unwrap(body):
    return body.get("data", body) if isinstance(body, dict) else body


def _id(value, *keys: str) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            if value.get(key) is not None:
                return str(value[key])
    return str(value) if value is not None and not isinstance(value, (dict, list)) else None


def _login(client: httpx.Client, username: str, password: str) -> str:
    response = client.post("/admin/api/user/login", json={"username": username, "password": password})
    response.raise_for_status()
    data = _unwrap(response.json())
    token = _id(data, "token")
    if not token:
        raise RuntimeError("MaxKB login did not return a token")
    return token


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--workspace-id", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    args = parser.parse_args()
    client = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=10)
    token = args.token
    checks = {
        "health": ("GET", "/admin/api/health"),
        "knowledge_list": ("GET", f"/admin/api/workspace/{args.workspace_id}/knowledge"),
        "knowledge_options": ("OPTIONS", f"/admin/api/workspace/{args.workspace_id}/knowledge"),
        "chat_options": ("OPTIONS", "/chat/api/open/chat/completions"),
    }
    result = {"base_url": args.base_url, "workspace_id": args.workspace_id, "read_only": True, "checks": {}}
    for name, (method, path) in checks.items():
        try:
            headers = {"Authorization": f"Bearer {token}"} if token and path.startswith("/admin/api") else {}
            response = client.request(method, path, headers=headers)
            if response.status_code == 401 and args.username and args.password and path.startswith("/admin/api"):
                token = _login(client, args.username, args.password)
                response = client.request(method, path, headers={"Authorization": f"Bearer {token}"})
            result["checks"][name] = {"method": method, "path": path, "status_code": response.status_code,
                                      "available": response.status_code not in {404, 405}}
        except httpx.HTTPError as exc:
            result["checks"][name] = {"method": method, "path": path, "available": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
