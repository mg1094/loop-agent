from loop_agent.agent.memory import WorkspaceMemory


def test_increment_counter():
    mem = WorkspaceMemory()
    assert mem.increment("echo") == 1
    assert mem.increment("echo") == 2


def test_summary():
    mem = WorkspaceMemory(run_dir="/tmp/run")
    mem.increment("echo")
    summary = mem.to_summary()
    assert "/tmp/run" in summary
    assert "echo=1" in summary
