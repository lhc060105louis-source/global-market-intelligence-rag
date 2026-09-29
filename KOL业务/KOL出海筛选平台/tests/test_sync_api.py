class CloudCredentials:
    def __init__(self):
        self.values = {}

    def set_secret(self, username, value):
        self.values[username] = value

    def get_secret(self, username):
        return self.values.get(username)

    def delete_secret(self, username):
        self.values.pop(username, None)


def test_supabase_settings_never_return_secrets(client):
    client.app.state.credential_store = CloudCredentials()

    response = client.put(
        "/settings/supabase",
        json={
            "url": "https://team.supabase.co",
            "anon_key": "anon-secret",
            "access_token": "user-secret",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "configured": True,
        "url": "https://team.supabase.co",
    }
    assert "secret" not in response.text


def test_sync_status_reports_pending_events_and_offline_state(client):
    response = client.post(
        "/kols",
        json={"platform": "YouTube", "handle": "@pending", "country": "GB"},
    )
    assert response.status_code == 201

    status = client.get("/sync/status")

    assert status.status_code == 200
    assert status.json()["state"] == "offline"
    assert status.json()["pending"] == 1
    assert status.json()["conflicts"] == 0
