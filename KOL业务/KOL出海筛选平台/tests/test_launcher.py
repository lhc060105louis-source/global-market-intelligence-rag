from app.launcher import Launcher, find_available_port


def test_find_available_port_asks_os_for_loopback_ephemeral_port(monkeypatch):
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address): self.address = address
        def getsockname(self): return ("127.0.0.1", 43126)
    probe = Socket()
    monkeypatch.setattr("app.launcher.socket.socket", lambda *args: probe)
    assert find_available_port() == 43126
    assert probe.address == ("127.0.0.1", 0)


def test_repeated_launch_opens_existing_url_without_server(tmp_path):
    lock = tmp_path / "launcher.lock"
    lock.write_text("43123", "utf-8")
    opened, started = [], []
    launcher = Launcher(lock_path=lock, health_check=lambda url: True,
                        browser_open=opened.append, server_factory=lambda port: started.append(port))
    assert launcher.run(show_tray=False) == 0
    assert opened == ["http://127.0.0.1:43123/"]
    assert started == []


def test_repeated_launch_waits_for_existing_server_during_startup(tmp_path):
    lock = tmp_path / "launcher.lock"
    lock.write_text("43123", "utf-8")
    checks, opened, started = [], [], []

    def health_check(url):
        checks.append(url)
        return len(checks) >= 2

    launcher = Launcher(
        lock_path=lock,
        health_check=health_check,
        browser_open=opened.append,
        server_factory=lambda port: started.append(port),
        timeout=1,
        poll_interval=0,
    )

    assert launcher.run(show_tray=False) == 0
    assert checks == ["http://127.0.0.1:43123/health"] * 2
    assert opened == ["http://127.0.0.1:43123/"]
    assert started == []


def test_stale_lock_is_replaced_and_shutdown_stops_server(tmp_path):
    lock = tmp_path / "launcher.lock"; lock.write_text("43123", "utf-8")
    class Server:
        should_exit = False
        def start(self): pass
        def stop(self): self.should_exit = True
    server = Server()
    launcher = Launcher(lock_path=lock, port_finder=lambda: 43124,
                        health_check=lambda url: url.endswith(":43124/health"),
                        browser_open=lambda url: None, server_factory=lambda port: server,
                        timeout=0)
    assert launcher.run(show_tray=False) == 0
    launcher.shutdown()
    assert server.should_exit is True
    assert not lock.exists()


def test_health_timeout_stops_server_and_reports_failure(tmp_path):
    errors = []
    class Server:
        should_exit = False
        def start(self): pass
        def stop(self): self.should_exit = True
    server = Server()
    launcher = Launcher(lock_path=tmp_path / "launcher.lock", port_finder=lambda: 43125,
                        health_check=lambda url: False, browser_open=lambda url: None,
                        server_factory=lambda port: server, error_reporter=errors.append,
                        timeout=0, poll_interval=0)
    assert launcher.run(show_tray=False) == 1
    assert server.should_exit is True
    assert errors and "20" in errors[0]
