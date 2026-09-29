from typing import Any

import httpx


class SupabaseTransport:
    def __init__(
        self,
        url: str,
        anon_key: str,
        access_token: str,
        client: httpx.Client | None = None,
    ):
        self.base = url.rstrip("/")
        self.client = client or httpx.Client(timeout=20)
        self.headers = {
            "apikey": anon_key,
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def push(self, events: list[dict[str, Any]]) -> None:
        response = self.client.post(
            f"{self.base}/rest/v1/sync_events",
            headers={
                **self.headers,
                "Prefer": "resolution=ignore-duplicates",
            },
            json=events,
        )
        response.raise_for_status()

    def pull(self, cursor: str) -> dict[str, Any]:
        response = self.client.get(
            f"{self.base}/functions/v1/kol-sync-pull",
            headers=self.headers,
            params={"cursor": cursor},
        )
        response.raise_for_status()
        return response.json()

    def health(self) -> bool:
        response = self.client.get(
            f"{self.base}/rest/v1/",
            headers=self.headers,
        )
        return response.is_success
