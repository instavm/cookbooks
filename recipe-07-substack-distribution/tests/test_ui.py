from fastapi.testclient import TestClient

from app import app


def test_landing_page_is_html_not_json():
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "application/json" not in resp.text[:120]


def test_landing_has_readable_content():
    client = TestClient(app)
    resp = client.get("/")
    # Cookbook landing OR specialized dashboard/gallery pages
    assert any(
        marker in resp.text
        for marker in ("InstaVM Cookbook", "Revenue Dashboard", "Screen replay", "Computer-use")
    )
