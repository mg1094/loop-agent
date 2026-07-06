from loop_agent.cli.commands import run_command


def test_run_command_with_mock_loop(monkeypatch):
    calls = []

    def fake_run(user_message, history=None, session_id=""):
        calls.append(user_message)
        return {"status": "success", "content": f"Echo: {user_message}", "run_id": "r1", "run_dir": "/tmp/r1"}

    monkeypatch.setattr("loop_agent.cli.commands._run_agent", fake_run)
    result = run_command("hello")
    assert result["content"] == "Echo: hello"
    assert calls == ["hello"]


def test_run_command_with_session_id(monkeypatch):
    captured = []

    def fake_run(user_message, session_id=""):
        captured.append((user_message, session_id))
        return {"status": "success", "content": "ok", "run_id": "r", "run_dir": "/tmp"}

    monkeypatch.setattr("loop_agent.cli.commands._run_agent", fake_run)
    result = run_command("hi", session_id="sess-1")
    assert result["content"] == "ok"
    assert captured == [("hi", "sess-1")]
