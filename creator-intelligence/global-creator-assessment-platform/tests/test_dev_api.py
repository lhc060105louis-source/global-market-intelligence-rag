def test_reset_database_is_not_exposed_in_production(client):
    assert client.post("/dev/reset-database").status_code == 404
