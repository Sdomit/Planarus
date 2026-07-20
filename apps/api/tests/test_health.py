from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_info_returns_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/info")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Approvo"
    assert "version" in data
    assert data["phase"] == "9-v1-expansion"


def test_info_lan_ip_is_a_real_lan_address_or_none(client: TestClient) -> None:
    # Never loopback or the unspecified address: the UI builds a URL other
    # devices are meant to open, so those values would be silently useless.
    lan_ip = client.get("/api/v1/info").json()["lan_ip"]
    assert lan_ip is None or (
        not lan_ip.startswith("127.") and lan_ip != "0.0.0.0" and lan_ip.count(".") == 3
    )


def test_openapi_schema_renders(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Approvo API"
