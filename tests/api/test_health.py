def test_health_endpoint_reports_app_and_runtime(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "AutoVideo"
    assert payload["status"] == "degraded"
    assert payload["environment"] == "development"
    assert payload["data_dir"]
    assert payload["data_dir"].startswith("/")
    assert payload["checks"]["ffmpeg"]["ok"] is False
    assert payload["checks"]["ffmpeg"]["required"] is True
    assert payload["checks"]["fish_speech"]["ok"] is False
    assert payload["checks"]["fish_speech"]["required"] is False


def test_openapi_is_available(client) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "AutoVideo"
