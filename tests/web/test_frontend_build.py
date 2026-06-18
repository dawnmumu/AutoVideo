from pathlib import Path

import pytest


FRONTEND_ROOT = Path("frontend")
BUILD_SKIP_REASON = "Run `cd frontend && npm run build` before build-output tests"


def require_frontend_build() -> tuple[Path, Path]:
    index_file = FRONTEND_ROOT / "dist" / "index.html"
    assets_dir = FRONTEND_ROOT / "dist" / "assets"

    if not index_file.exists() or not assets_dir.exists():
        pytest.skip(BUILD_SKIP_REASON)

    return index_file, assets_dir


def test_frontend_source_contains_chinese_product_shell() -> None:
    app_source = (FRONTEND_ROOT / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "混剪工作台" in app_source
    assert "素材库" in app_source
    assert "字幕模板" in app_source
    assert "BGM 管理" in app_source
    assert "音色中心" in app_source
    assert "功能提取处理" in app_source
    assert "任务与输出" in app_source
    assert "系统设置" in app_source


def test_frontend_source_does_not_include_removed_auth_or_netdisk_copy() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (FRONTEND_ROOT / "src").rglob("*")
        if path.suffix in {".ts", ".tsx", ".css"}
    )

    forbidden = [
        "退出登录",
        "个人网盘",
        "NAS 登录",
        "access_token",
        "refresh_token",
        "bearer",
        "authorization",
    ]
    for value in forbidden:
        assert value not in text


def test_frontend_css_protects_tablet_width_online_remix_layout() -> None:
    css = (FRONTEND_ROOT / "src" / "styles.css").read_text(encoding="utf-8")

    assert "@media (max-width: 1100px)" in css
    tablet_rules = css.split("@media (max-width: 1100px)", 1)[1].split(
        "@media",
        1,
    )[0]
    assert ".content-grid" in tablet_rules
    assert "grid-template-columns: 1fr" in tablet_rules
    assert ".candidate-row" in tablet_rules
    assert ".online-remix-form" in tablet_rules


def test_frontend_css_hides_inactive_content_grid_sections() -> None:
    css = (FRONTEND_ROOT / "src" / "styles.css").read_text(encoding="utf-8")

    assert ".content-grid[hidden]" in css
    hidden_section = css.split(".content-grid[hidden]", 1)[1].split("}", 1)[0]
    assert "display: none" in hidden_section


def test_frontend_build_outputs_static_assets() -> None:
    index_file, assets_dir = require_frontend_build()

    assert index_file.exists()
    assert 'id="root"' in index_file.read_text(encoding="utf-8")
    assert assets_dir.exists()
    assert any(path.suffix == ".js" for path in assets_dir.iterdir())
    assert any(path.suffix == ".css" for path in assets_dir.iterdir())


def test_fastapi_serves_built_frontend(client) -> None:
    require_frontend_build()

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AutoVideo" in response.text
    assert 'id="root"' in response.text
