import json
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright


FRONTEND_ROOT = Path("frontend")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _wait_for_http(url: str) -> None:
    deadline = time.monotonic() + 20
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as error:
            last_error = error
            time.sleep(0.25)
    raise AssertionError(f"Vite preview did not start at {url}: {last_error}")


def _fulfill_json(route, payload: object) -> None:
    route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(payload, ensure_ascii=False),
    )


def test_material_workbench_mobile_has_no_page_horizontal_scroll_after_build() -> None:
    if not (FRONTEND_ROOT / "dist" / "index.html").exists():
        pytest.fail("Run `cd frontend && npm run build` before this mobile browser test")

    port = _free_port()
    process = subprocess.Popen(
        ["npm", "run", "preview", "--", "--host", "127.0.0.1", "--port", str(port)],
        cwd=FRONTEND_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"

    try:
        _wait_for_http(base_url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 375, "height": 812})
            page.route(
                "**/api/material-sources",
                lambda route: _fulfill_json(
                    route,
                    {
                        "allowed_roots": [{"id": "demo", "alias": "demo", "display_name": "demo"}],
                        "current_source": {
                            "id": "source_1",
                            "allowed_root_id": "demo",
                            "allowed_root_alias": "demo",
                            "source_display_path": "demo/very-long-folder-name-that-must-wrap",
                            "source_relative_path": "very-long-folder-name-that-must-wrap",
                            "status": "active",
                        },
                        "latest_job": {
                            "id": "job_1",
                            "status": "failed",
                            "stage": "segmenting",
                            "progress": {"current": 1, "total": 2},
                            "counts": {"raw": 1, "segments": 0, "failed": 1},
                            "error_summary": "MATERIAL_INDEX_JOB_FAILED_WITH_A_LONG_RECOVERY_MESSAGE",
                        },
                    },
                ),
            )
            page.route(
                "**/api/material-index/summary",
                lambda route: _fulfill_json(
                    route,
                    {
                        "totals": {"raw": 1, "segments": 0, "portrait": 0, "landscape": 0, "failed": 1},
                        "current_source": None,
                        "latest_job": {
                            "id": "job_1",
                            "status": "failed",
                            "stage": "segmenting",
                            "progress": {"current": 1, "total": 2},
                            "counts": {"raw": 1, "segments": 0, "failed": 1},
                            "error_summary": "MATERIAL_INDEX_JOB_FAILED_WITH_A_LONG_RECOVERY_MESSAGE",
                        },
                    },
                ),
            )
            page.route(
                re.compile(r".*/api/material-index/raw-files(\?.*)?$"),
                lambda route: _fulfill_json(
                    route,
                    {
                        "items": [
                            {
                                "id": "raw_1",
                                "filename": "very-long-local-material-file-name-that-wraps-on-mobile-without-page-scroll.mp4",
                                "source_display_path": "demo/very-long-folder-name-that-must-wrap/very-long-local-material-file-name-that-wraps-on-mobile-without-page-scroll.mp4",
                                "size_bytes": 2048,
                                "duration_seconds": 12,
                                "orientation": "portrait",
                                "segments": 0,
                                "status": "failed",
                                "error_summary": "MATERIAL_INDEX_JOB_FAILED_WITH_A_LONG_RECOVERY_MESSAGE",
                            }
                        ],
                        "limit": 50,
                        "offset": 0,
                        "total": 1,
                    },
                ),
            )
            page.goto(f"{base_url}/#materials", wait_until="networkidle")

            expect(page.get_by_role("heading", name="素材库", level=1)).to_be_visible()
            nav = page.get_by_role("navigation", name="移动端导航")
            expect(nav.get_by_text("素材")).to_be_visible()
            expect(
                page.locator(".material-raw-row strong").get_by_text(
                    "very-long-local-material-file-name-that-wraps-on-mobile-without-page-scroll.mp4",
                    exact=True,
                )
            ).to_be_visible()
            expect(page.get_by_text("MATERIAL_INDEX_JOB_FAILED_WITH_A_LONG_RECOVERY_MESSAGE")).to_be_visible()
            assert page.evaluate("document.body.scrollWidth <= window.innerWidth")

            button_boxes = page.locator(".material-library-panel button").evaluate_all(
                """
                (buttons) => buttons
                  .filter((button) => {
                    const style = window.getComputedStyle(button);
                    const rect = button.getBoundingClientRect();
                    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
                  })
                  .map((button) => {
                    const rect = button.getBoundingClientRect();
                    return { width: rect.width, height: rect.height, text: button.textContent || "" };
                  })
                """
            )
            assert button_boxes
            assert not [box for box in button_boxes if box["height"] < 44], button_boxes
            assert page.evaluate("document.body.scrollWidth <= window.innerWidth")
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
