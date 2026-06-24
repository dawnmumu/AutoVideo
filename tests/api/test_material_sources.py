from pathlib import Path

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


def test_material_sources_requires_config(client) -> None:
    response = client.get("/api/material-sources")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MATERIAL_SOURCE_ROOT_NOT_CONFIGURED"


def test_save_source_redacts_absolute_paths_and_queues_job(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path / "data",
            material_allowed_roots=f"demo={root}",
        )
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "clips"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_source"]["source_display_path"] == "demo/clips"
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["attempt_count"] == 0
    assert str(root) not in str(payload)


def test_material_sources_status_includes_latest_job_without_absolute_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path / "data",
            material_allowed_roots=f"demo={root}",
        )
    )

    with TestClient(app) as client:
        save_response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "clips"},
        )
        response = client.get("/api/material-sources")

    assert save_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed_roots"] == [
        {"id": "demo", "alias": "demo", "display_name": "demo"}
    ]
    assert payload["current_source"]["source_display_path"] == "demo/clips"
    assert payload["latest_job"]["id"] == save_response.json()["job"]["id"]
    assert str(root) not in str(payload)


def test_save_source_rejects_out_of_scope_path(tmp_path: Path) -> None:
    root = tmp_path / "source"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path / "data",
            material_allowed_roots=f"demo={root}",
        )
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "../outside"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MATERIAL_SOURCE_PATH_OUT_OF_SCOPE"
