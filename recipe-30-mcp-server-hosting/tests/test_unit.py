from lib.mcp_stub import TOOLS


def test_tools_defined():
    assert any(t["name"] == "echo" for t in TOOLS)
