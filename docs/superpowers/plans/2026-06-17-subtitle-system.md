# Subtitle System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a junxincode-parity subtitle template system to AutoVideo, including template management, ASS generation, FFmpeg burn-in, source subtitle masking, online mix options, frontend controls, and documentation.

**Architecture:** Keep subtitle-specific behavior in focused modules under `autovideo/services/subtitles/`, then connect those modules through the online mix task builder and a new `/api/subtitle-template-sets` router. The frontend gets a dedicated subtitle API client and workbench component, while `OnlineRemixWorkbench` only owns task-level subtitle settings.

**Tech Stack:** FastAPI, Pydantic, JSON file storage, Python stdlib ASS generation, FFmpeg subprocess calls, React + Vite + TanStack Query, Vitest, pytest.

---

## Source Spec

- Design spec: `docs/superpowers/specs/2026-06-17-subtitle-system-design.md`
- Original reference project: `/Users/sha/junxincode/Services/100.95.201.23/opt/ai/video-generator`

## File Structure

### Backend Subtitle Modules

- Create `autovideo/services/subtitles/__init__.py`: package exports.
- Create `autovideo/services/subtitles/models.py`: dataclasses and normalization helpers for template sets, render blocks, subtitle events, and render options.
- Create `autovideo/services/subtitles/template_presets.py`: built-in template sets for `bottom`, `highlight`, and `punch`.
- Create `autovideo/services/subtitles/dsl_v2.py`: DSL v2 normalization and downgrade warnings.
- Create `autovideo/services/subtitles/template_store.py`: JSON store at `<AUTOVIDEO_DATA_DIR>/subtitle_templates/subtitle_template_sets.json`, preset overrides, CRUD, favorite selection.
- Create `autovideo/services/subtitles/timeline.py`: timeline item to subtitle event conversion and punctuation splitting.
- Create `autovideo/services/subtitles/template_assignment.py`: semantic role and variant assignment with deterministic fallback.
- Create `autovideo/services/subtitles/keyword_spans.py`: keyword span injection with injectable extractor and safe fallback.
- Create `autovideo/services/subtitles/event_enrichment.py`: merge blocks, variant blocks, tracks, spans, and animations into events.
- Create `autovideo/services/subtitles/ass_renderer.py`: ASS escaping, styles, dialogue events, local span tags, file output.
- Create `autovideo/services/subtitles/preview_renderer.py`: preview ASS generation and optional FFmpeg/libass PNG or short MP4 rendering.
- Create `autovideo/services/subtitles/ffmpeg_burner.py`: FFmpeg ASS burn command building and execution.
- Create `autovideo/services/subtitles/source_masks.py`: local/hybrid source subtitle marker detection and bottom-mask filter helpers.

### Backend Integration

- Modify `autovideo/services/rendering.py`: split base MP4 render from ASS burn, write ASS before FFmpeg, support `output.base.mp4`, source subtitle masking, and render plan status.
- Modify `autovideo/services/online_mix.py`: normalize subtitle options, choose template snapshot, apply font override, pass subtitle config into rendering, persist manifest fields.
- Modify `autovideo/api/app.py`: include subtitle template router and request size handling if needed.
- Create `autovideo/api/routes/subtitle_templates.py`: list/create/update/delete/validate/preview APIs.
- Modify `autovideo/api/routes/online_mix.py`: map subtitle template errors to structured 400 responses.

### Backend Tests

- Create `tests/services/test_subtitle_template_store.py`.
- Create `tests/services/test_subtitle_dsl.py`.
- Create `tests/services/test_subtitle_timeline.py`.
- Create `tests/services/test_ass_renderer.py`.
- Create `tests/services/test_subtitle_rendering_pipeline.py`.
- Create `tests/api/test_subtitle_templates.py`.
- Modify `tests/services/test_rendering.py`.
- Modify `tests/api/test_online_mix.py`.

### Frontend

- Create `frontend/src/api/subtitles.ts`: subtitle API types and fetch helpers.
- Create `frontend/src/components/SubtitleTemplateWorkbench.tsx`: template list, preview, editor, save/restore/favorite controls.
- Modify `frontend/src/components/OnlineRemixWorkbench.tsx`: subtitle task settings and submission options.
- Modify `frontend/src/App.tsx`: active section state, enable `字幕模板`, desktop/mobile navigation semantics.
- Modify `frontend/src/styles.css`: responsive workbench layout, preview ratio, mobile tabs, focus, disabled/loading states.
- Modify `frontend/src/App.test.tsx`: navigation, workbench, subtitle settings, mobile/a11y assertions.

### Documentation

- Modify `README.md`: subtitle template API, UI workflow, online mix options, output artifacts, FFmpeg fallback behavior.

---

## Task 1: Template Models, Presets, DSL, and Store

**Files:**
- Create: `autovideo/services/subtitles/__init__.py`
- Create: `autovideo/services/subtitles/models.py`
- Create: `autovideo/services/subtitles/template_presets.py`
- Create: `autovideo/services/subtitles/dsl_v2.py`
- Create: `autovideo/services/subtitles/template_store.py`
- Test: `tests/services/test_subtitle_template_store.py`
- Test: `tests/services/test_subtitle_dsl.py`

- [ ] **Step 1: Write failing template store tests**

Create `tests/services/test_subtitle_template_store.py` with these tests:

```python
import json

import pytest

from autovideo.core.settings import Settings
from autovideo.services.subtitles import template_store


def _store(tmp_path):
    return template_store.SubtitleTemplateStore(Settings(_env_file=None, data_dir=tmp_path))


def test_list_template_presets_returns_editable_normalized_items(tmp_path):
    store = _store(tmp_path)

    presets = store.list_presets()

    assert presets
    assert presets[0]["id"] == "preset-clean-bottom"
    assert presets[0]["schema_version"] == 2
    assert {block["role"] for block in presets[0]["blocks"]} >= {"bottom", "highlight", "punch"}
    assert presets[0]["is_modified"] is False


def test_create_update_and_delete_custom_template_set(tmp_path):
    store = _store(tmp_path)

    created = store.create_template_set("我的字幕", preset_id="preset-clean-bottom")
    updated = store.update_template_set(
        created["id"],
        {
            "name": "默认字幕",
            "is_favorite": True,
            "blocks": [
                {
                    "id": "bottom-main",
                    "role": "bottom",
                    "style": {"font_family": "PingFang SC", "primary_color": "#FFFFFF"},
                    "spans": [],
                }
            ],
        },
    )

    assert updated["name"] == "默认字幕"
    assert updated["is_favorite"] is True
    assert store.get_template_set(created["id"])["name"] == "默认字幕"
    assert json.loads(store.store_path.read_text(encoding="utf-8"))["items"]

    store.delete_template_set(created["id"])

    with pytest.raises(KeyError):
        store.get_template_set(created["id"])


def test_select_auto_template_set_prefers_favorite_then_sort_key(tmp_path):
    store = _store(tmp_path)
    old = store.create_template_set("旧模板", preset_id="preset-clean-bottom")
    new = store.create_template_set("新模板", preset_id="preset-clean-bottom")
    store.update_template_set(old["id"], {"is_favorite": True, "updated_at": "2026-01-01T00:00:00+00:00"})
    store.update_template_set(new["id"], {"is_favorite": True, "updated_at": "2026-02-01T00:00:00+00:00"})

    selected = store.select_auto_template_set()

    assert selected["id"] == new["id"]


def test_preset_override_preserves_favorite_metadata(tmp_path):
    store = _store(tmp_path)

    updated = store.update_preset("preset-clean-bottom", {"is_favorite": True, "name": "收藏预设"})
    selected = store.select_auto_template_set()

    assert updated["is_favorite"] is True
    assert selected["id"] == "preset-clean-bottom"
```

- [ ] **Step 2: Write failing DSL tests**

Create `tests/services/test_subtitle_dsl.py`:

```python
from autovideo.services.subtitles import dsl_v2


def test_validate_template_set_v2_preserves_supported_fields_and_warns_for_advanced_fields():
    payload = {
        "id": "template-1",
        "name": "动效模板",
        "schema_version": 2,
        "renderer_mode": "ass_plus",
        "is_favorite": True,
        "tracks": [{"id": "main", "kind": "subtitle", "z": 10}],
        "blocks": [
            {
                "id": "bottom-main",
                "role": "bottom",
                "track_id": "main",
                "style": {
                    "font_family": "Inter",
                    "primary_color": "#FFFFFF",
                    "outline_width": 4,
                    "shadow": 3,
                    "font_size_scale": 1.08,
                    "margin_v": 112,
                    "max_width": 0.82,
                    "rotate": -2,
                    "skew": 6,
                },
                "spans": [
                    {
                        "selector": {"type": "keyword", "value": "效率"},
                        "style": {"primary_color": "#FFD54F", "font_scale": 1.15},
                    }
                ],
                "animations": {"in": {"type": "fade", "duration_ms": 120}},
                "mask": {"type": "rounded_rect"},
            }
        ],
        "template_variants": {
            "highlight": [
                {
                    "id": "emphasis",
                    "blocks": [
                        {
                            "id": "highlight-emphasis",
                            "role": "highlight",
                            "style": {"primary_color": "#FFD54F", "font_size_scale": 1.2},
                        }
                    ],
                }
            ]
        },
    }

    result = dsl_v2.validate_template_set_v2(payload)

    assert result["ok"] is True
    assert result["normalized"]["is_favorite"] is True
    assert result["normalized"]["blocks"][0]["role"] == "bottom"
    assert result["normalized"]["templates"]["bottom"]["font_family"] == "Inter"
    assert result["normalized"]["templates"]["bottom"]["font_size_scale"] == 1.08
    assert result["normalized"]["templates"]["bottom"]["margin_v"] == 112
    assert result["normalized"]["template_variants"]["highlight"][0]["id"] == "emphasis"
    assert any("mask" in warning for warning in result["warnings"])
```

- [ ] **Step 3: Run tests to verify red**

Run:

```bash
pytest tests/services/test_subtitle_template_store.py tests/services/test_subtitle_dsl.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'autovideo.services.subtitles'`.

- [ ] **Step 4: Add minimal models and presets**

Create `autovideo/services/subtitles/__init__.py`:

```python
from __future__ import annotations

__all__ = [
    "dsl_v2",
    "template_presets",
    "template_store",
]
```

Create `autovideo/services/subtitles/models.py` with these public constants:

```python
from __future__ import annotations

from typing import Any

TEMPLATE_ROLES = ("bottom", "highlight", "punch")
SCHEMA_VERSION = 2
RENDERER_MODE = "ass_plus"
MAIN_TRACK_ID = "main"
DEFAULT_TRACK = {"id": MAIN_TRACK_ID, "kind": "subtitle", "z": 10}


def deep_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
```

Create `autovideo/services/subtitles/template_presets.py` with three roles in one preset:

```python
from __future__ import annotations

import copy
from typing import Any

from autovideo.services.subtitles.models import DEFAULT_TRACK, RENDERER_MODE, SCHEMA_VERSION


def _block(role: str, y: float, size: int) -> dict[str, Any]:
    return {
        "id": f"{role}-main",
        "role": role,
        "track_id": "main",
        "position": {"x": 0.5, "y": y, "anchor": "center"},
        "style": {
            "font_family": "PingFang SC",
            "font_size": size,
            "primary_color": "#FFFFFF",
            "outline_color": "#111827",
            "outline_width": 3,
            "shadow_color": "#000000",
            "shadow_depth": 2,
        },
        "spans": [
            {
                "selector": {"type": "keyword", "value": ""},
                "style": {"primary_color": "#FFD54F", "font_scale": 1.15},
            }
        ],
        "animations": {"in": {"type": "fade", "duration_ms": 120}},
    }


PRESETS: list[dict[str, Any]] = [
    {
        "id": "preset-clean-bottom",
        "name": "清晰底部字幕",
        "schema_version": SCHEMA_VERSION,
        "renderer_mode": RENDERER_MODE,
        "tracks": [copy.deepcopy(DEFAULT_TRACK)],
        "blocks": [
            _block("bottom", 0.82, 54),
            _block("highlight", 0.72, 60),
            _block("punch", 0.62, 68),
        ],
    }
]


def list_presets() -> list[dict[str, Any]]:
    return [copy.deepcopy(item) for item in PRESETS]
```

- [ ] **Step 5: Implement DSL normalization**

Create `autovideo/services/subtitles/dsl_v2.py` with:

```python
from __future__ import annotations

import copy
from typing import Any

from autovideo.services.subtitles.models import (
    DEFAULT_TRACK,
    RENDERER_MODE,
    SCHEMA_VERSION,
    TEMPLATE_ROLES,
)

KNOWN_TOP_LEVEL_FIELDS = {
    "id",
    "name",
    "created_at",
    "updated_at",
    "is_builtin",
    "is_modified",
    "is_favorite",
    "favorite",
    "preset_id",
    "schema_version",
    "renderer_mode",
    "tracks",
    "blocks",
    "templates",
    "template_variants",
}
ADVANCED_BLOCK_FIELDS = {"mask", "filter", "filters", "blend", "keyframes", "cue_points", "layers"}
SUPPORTED_STYLE_FIELDS = {
    "font_family",
    "font_size",
    "primary_color",
    "accent_color",
    "outline_color",
    "outline_width",
    "shadow_color",
    "shadow_depth",
    "shadow",
    "font_size_scale",
    "font_scale",
    "margin_v",
    "max_width",
    "rotate",
    "skew",
}


def validate_template_set_v2(payload: Any) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        normalized = normalize_template_set_v2(payload, warnings)
        normalized["templates"] = compile_v2_blocks_to_legacy_templates(normalized)
        return {"ok": True, "normalized": normalized, "warnings": warnings}
    except Exception as exc:
        warnings.append(str(exc))
        return {"ok": False, "normalized": None, "warnings": warnings}


def normalize_template_set_v2(payload: Any, warnings: list[str] | None = None) -> dict[str, Any]:
    warning_list = warnings if warnings is not None else []
    raw = copy.deepcopy(payload) if isinstance(payload, dict) else {}
    if not isinstance(payload, dict):
        warning_list.append("payload must be an object")

    normalized: dict[str, Any] = {
        "id": str(raw.get("id") or "").strip(),
        "name": str(raw.get("name") or "").strip(),
        "schema_version": SCHEMA_VERSION,
        "renderer_mode": str(raw.get("renderer_mode") or RENDERER_MODE).strip() or RENDERER_MODE,
        "tracks": _normalize_tracks(raw.get("tracks")),
        "blocks": _normalize_blocks(raw.get("blocks"), warning_list),
    }
    for field in ("created_at", "updated_at", "is_favorite", "favorite"):
        if field in raw:
            normalized[field] = copy.deepcopy(raw[field])
    if "template_variants" in raw:
        normalized["template_variants"] = copy.deepcopy(raw["template_variants"])
    for key in raw:
        if key not in KNOWN_TOP_LEVEL_FIELDS:
            warning_list.append(f"unknown top-level field {key} preserved only as warning")
    return normalized


def _normalize_tracks(raw_tracks: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_tracks, list) or not raw_tracks:
        return [copy.deepcopy(DEFAULT_TRACK)]
    return [track for track in raw_tracks if isinstance(track, dict)] or [copy.deepcopy(DEFAULT_TRACK)]


def _normalize_blocks(raw_blocks: Any, warnings: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw_blocks, list):
        raw_blocks = []
    blocks: list[dict[str, Any]] = []
    for raw_block in raw_blocks:
        if not isinstance(raw_block, dict):
            continue
        role = str(raw_block.get("role") or "").strip().lower()
        if role not in TEMPLATE_ROLES:
            warnings.append(f"unsupported block role {role}")
            continue
        for field in ADVANCED_BLOCK_FIELDS:
            if field in raw_block:
                warnings.append(f"advanced block field {field} is preserved as warning")
        style = {
            str(key): copy.deepcopy(value)
            for key, value in dict(raw_block.get("style") or {}).items()
            if str(key) in SUPPORTED_STYLE_FIELDS
        }
        blocks.append(
            {
                "id": str(raw_block.get("id") or f"{role}-main"),
                "role": role,
                "track_id": str(raw_block.get("track_id") or "main"),
                "position": copy.deepcopy(raw_block.get("position") or {}),
                "style": style,
                "spans": copy.deepcopy(raw_block.get("spans") or []),
                "animations": copy.deepcopy(raw_block.get("animations") or {}),
            }
        )
    return blocks


def compile_v2_blocks_to_legacy_templates(template_set: dict[str, Any]) -> dict[str, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    for role in TEMPLATE_ROLES:
        block = next((item for item in template_set.get("blocks", []) if item.get("role") == role), None)
        style = dict((block or {}).get("style") or {})
        templates[role] = {
            **copy.deepcopy(style),
            "font_family": style.get("font_family", "PingFang SC"),
            "font_size": int(style.get("font_size") or 54),
            "primary_color": style.get("primary_color", "#FFFFFF"),
            "outline_color": style.get("outline_color", "#111827"),
            "outline_width": int(style.get("outline_width") or 3),
            "shadow_color": style.get("shadow_color", "#000000"),
            "shadow_depth": int(style.get("shadow_depth") if style.get("shadow_depth") is not None else style.get("shadow") or 2),
        }
    return templates
```

- [ ] **Step 6: Implement JSON store**

Create `autovideo/services/subtitles/template_store.py` with public class and module wrappers:

```python
from __future__ import annotations

import copy
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autovideo.core.settings import Settings
from autovideo.services.subtitles import dsl_v2, template_presets


class SubtitleTemplateStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store_dir = Path(settings.data_dir) / "subtitle_templates"
        self.store_path = self.store_dir / "subtitle_template_sets.json"

    def list_presets(self) -> list[dict[str, Any]]:
        overrides = self._load().get("preset_overrides", {})
        presets: list[dict[str, Any]] = []
        for preset in template_presets.list_presets():
            preset_id = str(preset["id"])
            item = copy.deepcopy(overrides.get(preset_id, preset))
            item["is_modified"] = preset_id in overrides
            presets.append(_normalize_template_set_item(item))
        return presets

    def list_template_sets(self) -> list[dict[str, Any]]:
        return [_normalize_template_set_item(item) for item in self._load().get("items", [])]

    def get_template_set(self, template_set_id: str) -> dict[str, Any]:
        clean_id = str(template_set_id or "").strip()
        for item in self.list_template_sets() + self.list_presets():
            if item.get("id") == clean_id:
                return copy.deepcopy(item)
        raise KeyError(f"Subtitle template set not found: {template_set_id}")

    def create_template_set(self, name: str, *, preset_id: str | None = None, source_id: str | None = None) -> dict[str, Any]:
        if bool(preset_id) == bool(source_id):
            raise ValueError("preset_id and source_id must be exclusive")
        source = self.get_template_set(preset_id or source_id or "")
        now = _now_iso()
        item = copy.deepcopy(source)
        item.update({"id": f"tmpl-{uuid.uuid4().hex[:12]}", "name": str(name).strip(), "created_at": now, "updated_at": now})
        item.pop("is_builtin", None)
        item.pop("is_modified", None)
        data = self._load()
        data.setdefault("items", []).append(_normalize_template_set_item(item))
        self._write(data)
        return item

    def update_template_set(self, template_set_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        for index, item in enumerate(data.get("items", [])):
            if item.get("id") == template_set_id:
                target = copy.deepcopy(item)
                target.update(copy.deepcopy(patch))
                target["id"] = template_set_id
                target["updated_at"] = str(patch.get("updated_at") or _now_iso())
                data["items"][index] = _normalize_template_set_item(target)
                self._write(data)
                return data["items"][index]
        raise KeyError(f"Subtitle template set not found: {template_set_id}")

    def update_preset(self, preset_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        base = self.get_template_set(preset_id)
        target = copy.deepcopy(base)
        target.update(copy.deepcopy(patch))
        target["id"] = preset_id
        data = self._load()
        data.setdefault("preset_overrides", {})[preset_id] = _normalize_template_set_item(target)
        self._write(data)
        return data["preset_overrides"][preset_id]

    def delete_template_set(self, template_set_id: str) -> None:
        data = self._load()
        before = len(data.get("items", []))
        data["items"] = [item for item in data.get("items", []) if item.get("id") != template_set_id]
        if len(data["items"]) == before:
            raise KeyError(f"Subtitle template set not found: {template_set_id}")
        self._write(data)

    def reset_preset(self, preset_id: str) -> None:
        data = self._load()
        data.setdefault("preset_overrides", {}).pop(preset_id, None)
        self._write(data)

    def select_auto_template_set(self) -> dict[str, Any]:
        custom_sets = self.list_template_sets()
        favorite_sets = [item for item in custom_sets if item.get("is_favorite") or item.get("favorite")]
        candidates = favorite_sets or custom_sets
        if candidates:
            return copy.deepcopy(max(candidates, key=_template_selection_sort_key))
        presets = self.list_presets()
        if presets:
            return copy.deepcopy(presets[0])
        raise KeyError("No subtitle template sets or presets available")

    def _load(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {"items": [], "preset_overrides": {}}
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self.store_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.store_path)


def _normalize_template_set_item(item: dict[str, Any]) -> dict[str, Any]:
    result = dsl_v2.validate_template_set_v2(item)
    if not result["ok"]:
        raise ValueError("; ".join(result["warnings"]))
    normalized = copy.deepcopy(result["normalized"])
    if "template_variants" in item:
        normalized["template_variants"] = copy.deepcopy(item["template_variants"])
    for metadata_key in ("created_at", "updated_at", "is_builtin", "is_modified", "is_favorite", "favorite"):
        if metadata_key in item:
            normalized[metadata_key] = copy.deepcopy(item[metadata_key])
    return normalized


def _template_selection_sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (str(item.get("updated_at") or ""), str(item.get("created_at") or ""), str(item.get("id") or ""))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
```

- [ ] **Step 7: Run tests to verify green**

Run:

```bash
pytest tests/services/test_subtitle_template_store.py tests/services/test_subtitle_dsl.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add autovideo/services/subtitles/__init__.py autovideo/services/subtitles/models.py autovideo/services/subtitles/template_presets.py autovideo/services/subtitles/dsl_v2.py autovideo/services/subtitles/template_store.py tests/services/test_subtitle_template_store.py tests/services/test_subtitle_dsl.py
git commit -m "feat: add subtitle template store"
```

---

## Task 2: Timeline, Assignment, Keyword Spans, Enrichment, and ASS Renderer

**Files:**
- Create: `autovideo/services/subtitles/timeline.py`
- Create: `autovideo/services/subtitles/template_assignment.py`
- Create: `autovideo/services/subtitles/keyword_spans.py`
- Create: `autovideo/services/subtitles/event_enrichment.py`
- Create: `autovideo/services/subtitles/ass_renderer.py`
- Test: `tests/services/test_subtitle_timeline.py`
- Test: `tests/services/test_ass_renderer.py`

- [ ] **Step 1: Write failing timeline tests**

Create `tests/services/test_subtitle_timeline.py`:

```python
from autovideo.services.subtitles.timeline import SubtitleEvent, events_from_render_timeline


def test_events_from_render_timeline_splits_long_punctuation_text_without_breaking_decimal():
    timeline = {
        "items": [
            {
                "shot_index": 1,
                "start_time": 0,
                "end_time": 6,
                "duration": 6,
                "subtitle": "AI 能提升 3.5 倍效率，也能降低重复工作。",
            }
        ]
    }

    events = events_from_render_timeline(timeline)

    assert [event.text for event in events] == ["AI 能提升 3.5 倍效率", "也能降低重复工作"]
    assert events[0].start_ms == 0
    assert events[-1].end_ms == 6000


def test_events_from_render_timeline_uses_narration_when_subtitle_missing():
    events = events_from_render_timeline(
        {
            "items": [
                {
                    "shot_index": 1,
                    "start_time": 0,
                    "end_time": 3,
                    "duration": 3,
                    "narration": "这是旁白",
                }
            ]
        }
    )

    assert events == [
        SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=3000, text="这是旁白", template="bottom")
    ]
```

- [ ] **Step 2: Write failing ASS and enrichment tests**

Create `tests/services/test_ass_renderer.py`:

```python
from pathlib import Path

from autovideo.services.subtitles import ass_renderer, event_enrichment, keyword_spans, template_assignment
from autovideo.services.subtitles.timeline import SubtitleEvent


def _template():
    return {
        "id": "template-1",
        "name": "字幕模板",
        "templates": {
            "bottom": {
                "font_family": "PingFang SC",
                "font_size": 54,
                "font_size_scale": 1.1,
                "primary_color": "#FFFFFF",
                "outline_width": 4,
                "shadow": 3,
                "margin_v": 112,
                "rotate": -2,
            },
            "highlight": {"font_family": "PingFang SC", "font_size": 60, "primary_color": "#FFD54F"},
            "punch": {"font_family": "PingFang SC", "font_size": 68, "primary_color": "#FFFFFF"},
        },
        "blocks": [
            {
                "id": "bottom-main",
                "role": "bottom",
                "track_id": "main",
                "style": {"font_family": "PingFang SC", "font_size": 54, "primary_color": "#FFFFFF"},
                "spans": [{"selector": {"type": "keyword", "value": "AI"}, "style": {"primary_color": "#FFD54F"}}],
                "animations": {"in": {"type": "fade", "duration_ms": 120}},
            }
        ],
        "template_variants": {
            "highlight": [
                {
                    "id": "emphasis",
                    "blocks": [
                        {
                            "id": "highlight-emphasis",
                            "role": "highlight",
                            "track_id": "main",
                            "style": {"font_family": "PingFang SC", "font_size": 60, "primary_color": "#FFD54F"},
                            "spans": [{"selector": {"type": "keyword", "value": "效率"}, "style": {"primary_color": "#00E5FF"}}],
                            "animations": {"in": {"type": "pop_in", "duration_ms": 140}},
                        }
                    ],
                }
            ]
        },
    }


def test_assignment_keyword_enrichment_and_ass_output(tmp_path: Path):
    events = [SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=2000, text="业务团队协作", template="bottom")]

    assigned = template_assignment.assign_template_roles(events, _template(), random_seed=1)
    keyworded = keyword_spans.apply_keyword_spans(
        assigned,
        _template(),
        keyword_extractor=lambda payload, context: [{"index": 1, "terms": ["团队"]}],
        sample_rate=1,
        random_seed=1,
    )
    enriched = event_enrichment.enrich_subtitle_events(keyworded, _template(), (1080, 1920))
    output_path = ass_renderer.write_ass_file(tmp_path / "subtitles.ass", enriched, _template(), (1080, 1920))

    content = output_path.read_text(encoding="utf-8")
    assert "Style: bottom" in content
    assert "PingFang SC" in content
    assert "Style: bottom,PingFang SC,59," in content
    assert ",-2,1,4,3,2,60,60,112,1" in content
    assert "Dialogue: 0,0:00:00.00,0:00:02.00,bottom" in content
    assert "{\\c&H4FD5FF&}团队{\\r}" in content
    assert enriched[0].track_id == "main"
    assert enriched[0].event_animations["in"]["type"] == "fade"


def test_variant_block_is_used_when_assignment_selects_variant(tmp_path: Path):
    events = [SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1000, text="AI 提升效率", template="bottom")]

    assigned = template_assignment.assign_template_roles(events, _template(), random_seed=1)
    enriched = event_enrichment.enrich_subtitle_events(assigned, _template(), (1080, 1920))
    output_path = ass_renderer.write_ass_file(tmp_path / "variant.ass", enriched, _template(), (1080, 1920))

    assert enriched[0].template == "highlight"
    assert enriched[0].template_variant == "emphasis"
    assert enriched[0].event_animations["in"]["type"] == "pop_in"
    assert "{\\c&HFFE500&}效率{\\r}" in output_path.read_text(encoding="utf-8")


def test_keyword_extractor_failure_keeps_events_renderable():
    events = [SubtitleEvent(index=1, shot_index=1, start_ms=0, end_ms=1000, text="AI 办公", template="bottom")]

    result = keyword_spans.apply_keyword_spans(
        events,
        _template(),
        keyword_extractor=lambda payload, context: (_ for _ in ()).throw(RuntimeError("llm failed")),
        sample_rate=1,
        random_seed=1,
    )

    assert result[0].text == "AI 办公"
    assert result[0].keyword_spans == []
```

- [ ] **Step 3: Run tests to verify red**

Run:

```bash
pytest tests/services/test_subtitle_timeline.py tests/services/test_ass_renderer.py -q
```

Expected: fail with import errors for new modules or missing public functions.

- [ ] **Step 4: Implement timeline event model and splitting**

Create `autovideo/services/subtitles/timeline.py` with:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(eq=True)
class SubtitleEvent:
    index: int
    shot_index: int
    start_ms: int
    end_ms: int
    text: str
    template: str = "bottom"
    template_variant: str | None = None
    track_id: str = "main"
    spans: list[dict[str, Any]] = field(default_factory=list)
    keyword_spans: list[dict[str, Any]] = field(default_factory=list)
    event_animations: dict[str, Any] = field(default_factory=dict)


def events_from_render_timeline(timeline: dict[str, Any]) -> list[SubtitleEvent]:
    events: list[SubtitleEvent] = []
    event_index = 1
    for item in timeline.get("items", []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("subtitle") or item.get("narration") or "").strip()
        if not text:
            continue
        start_ms = int(round(float(item.get("start_time") or 0) * 1000))
        end_ms = int(round(float(item.get("end_time") or 0) * 1000))
        parts = _split_subtitle_text(text)
        span = max(end_ms - start_ms, 1)
        per_part = span / max(len(parts), 1)
        for offset, part in enumerate(parts):
            part_start = int(round(start_ms + per_part * offset))
            part_end = end_ms if offset == len(parts) - 1 else int(round(start_ms + per_part * (offset + 1)))
            events.append(
                SubtitleEvent(
                    index=event_index,
                    shot_index=int(item.get("shot_index") or event_index),
                    start_ms=part_start,
                    end_ms=part_end,
                    text=part,
                    template="bottom",
                )
            )
            event_index += 1
    return events


def _split_subtitle_text(text: str) -> list[str]:
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<DOT>", text)
    parts = [
        part.replace("<DOT>", ".").strip(" ，,。！？!?；;")
        for part in re.split(r"[，,。！？!?；;]+", protected)
        if part.strip(" ，,。！？!?；;")
    ]
    return parts or [text.strip()]
```

- [ ] **Step 5: Implement assignment, keyword spans, enrichment, and ASS writer**

Create `template_assignment.py`, `keyword_spans.py`, `event_enrichment.py`, and `ass_renderer.py` with these public functions:

```python
# autovideo/services/subtitles/template_assignment.py
from __future__ import annotations

import copy
import random

from autovideo.services.subtitles.timeline import SubtitleEvent


def assign_template_roles(events: list[SubtitleEvent], template_set: dict, *, random_seed: int | None = None) -> list[SubtitleEvent]:
    copied = copy.deepcopy(events)
    rng = random.Random(random_seed)
    for event in copied:
        text = event.text.strip()
        if any(mark in text for mark in ("！", "!", "立即", "现在", "关键")):
            event.template = "punch"
        elif any(mark in text for mark in ("AI", "效率", "降低", "提升", "自动")):
            event.template = "highlight"
        else:
            event.template = "bottom" if rng.random() >= 0 else "bottom"
        event.template_variant = _first_variant_key(template_set, event.template)
    return copied


def _first_variant_key(template_set: dict, role: str) -> str | None:
    variants = (template_set.get("template_variants") or {}).get(role)
    if isinstance(variants, dict):
        variants = list(variants.values())
    if not isinstance(variants, list) or not variants:
        return None
    first = variants[0]
    if not isinstance(first, dict):
        return None
    return str(first.get("id") or first.get("key") or first.get("name") or "1")
```

```python
# autovideo/services/subtitles/keyword_spans.py
from __future__ import annotations

import copy
import random
from typing import Any, Callable

from autovideo.services.subtitles.timeline import SubtitleEvent

KeywordExtractor = Callable[[list[dict[str, Any]], dict[str, Any]], Any]
DEFAULT_KEYWORD_STYLE = {"primary_color": "#FFD54F", "font_scale": 1.15}


def apply_keyword_spans(
    events: list[SubtitleEvent],
    template_set: dict | None,
    *,
    keyword_extractor: KeywordExtractor | None = None,
    sample_rate: float = 0.2,
    random_seed: int | None = None,
) -> list[SubtitleEvent]:
    copied = copy.deepcopy(events)
    for event in copied:
        event.keyword_spans = []
    selected = _sample_events(copied, sample_rate, random_seed)
    if not selected or keyword_extractor is None:
        return copied
    try:
        raw = keyword_extractor([{"index": event.index, "text": event.text, "template": event.template} for event in selected], {"sample_rate": sample_rate})
    except Exception:
        return copied
    keyword_map = _keyword_map(raw)
    for event in selected:
        terms = [term for term in keyword_map.get(event.index, []) if term in event.text][:2]
        event.keyword_spans = [{"selector": {"type": "keyword", "value": term}, "style": copy.deepcopy(DEFAULT_KEYWORD_STYLE)} for term in terms]
        event.spans.extend(copy.deepcopy(event.keyword_spans))
    return copied


def _sample_events(events: list[SubtitleEvent], sample_rate: float, random_seed: int | None) -> list[SubtitleEvent]:
    eligible = [event for event in events if event.text.strip()]
    if not eligible or sample_rate <= 0:
        return []
    count = min(len(eligible), max(1, int(round(len(eligible) * sample_rate))))
    return sorted(random.Random(random_seed).sample(eligible, count), key=lambda event: event.index)


def _keyword_map(raw: Any) -> dict[int, list[str]]:
    items = raw.get("keywords") if isinstance(raw, dict) else raw
    result: dict[int, list[str]] = {}
    if not isinstance(items, list):
        return result
    for item in items:
        if isinstance(item, dict):
            result[int(item.get("index"))] = [str(term).strip() for term in item.get("terms", []) if str(term).strip()]
    return result
```

```python
# autovideo/services/subtitles/event_enrichment.py
from __future__ import annotations

import copy
from typing import Any

from autovideo.services.subtitles.timeline import SubtitleEvent


def enrich_subtitle_events(events: list[SubtitleEvent], template_set: dict[str, Any] | None, resolution: tuple[int, int]) -> list[SubtitleEvent]:
    copied = copy.deepcopy(events)
    render_blocks = {
        str(block.get("role")): block
        for block in (template_set or {}).get("blocks", [])
        if isinstance(block, dict)
    }
    for event in copied:
        block = _variant_block(template_set or {}, event.template, event.template_variant) or render_blocks.get(event.template)
        if not isinstance(block, dict):
            continue
        event.track_id = str(block.get("track_id") or "main")
        for span in block.get("spans") or []:
            if isinstance(span, dict) and span not in event.spans:
                event.spans.append(copy.deepcopy(span))
        event.event_animations = {**copy.deepcopy(block.get("animations") or {}), **event.event_animations}
    return copied


def _variant_block(template_set: dict[str, Any], role: str, variant_key: str | None) -> dict[str, Any] | None:
    if not variant_key:
        return None
    variants = (template_set.get("template_variants") or {}).get(role)
    if isinstance(variants, dict):
        variants = list(variants.values())
    if not isinstance(variants, list):
        return None
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        key = str(variant.get("id") or variant.get("key") or variant.get("name") or "")
        if key != variant_key:
            continue
        for block in variant.get("blocks") or []:
            if isinstance(block, dict) and str(block.get("role")) == role:
                return copy.deepcopy(block)
    return None
```

```python
# autovideo/services/subtitles/ass_renderer.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from autovideo.services.subtitles.timeline import SubtitleEvent


def write_ass_file(path: Path, events: list[SubtitleEvent], template_set: dict[str, Any], resolution: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_ass(events, template_set, resolution), encoding="utf-8")
    return path


def render_ass(events: list[SubtitleEvent], template_set: dict[str, Any], resolution: tuple[int, int]) -> str:
    width, height = resolution
    styles = _styles(template_set)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        *styles,
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    for event in events:
        lines.append(f"Dialogue: 0,{_ass_time(event.start_ms)},{_ass_time(event.end_ms)},{event.template},,0,0,0,,{_render_event_text(event)}")
    return "\n".join(lines) + "\n"


def _styles(template_set: dict[str, Any]) -> list[str]:
    templates = template_set.get("templates") or {}
    result: list[str] = []
    for role in ("bottom", "highlight", "punch"):
        item = templates.get(role) or {}
        font_size = int((item.get("font_size") or 54) * float(item.get("font_size_scale") or item.get("font_scale") or 1))
        shadow = int(item.get("shadow_depth") if item.get("shadow_depth") is not None else item.get("shadow") or 2)
        margin_v = int(item.get("margin_v") or 130)
        angle = float(item.get("rotate") or 0)
        result.append(
            "Style: "
            f"{role},{item.get('font_family', 'PingFang SC')},{font_size},"
            f"{_ass_color(item.get('primary_color', '#FFFFFF'))},&H000000FF,"
            f"{_ass_color(item.get('outline_color', '#111827'))},&H80000000,0,0,0,0,100,100,0,{angle:g},1,"
            f"{int(item.get('outline_width') or 3)},{shadow},2,60,60,{margin_v},1"
        )
    return result


def _ass_time(ms: int) -> str:
    total_cs = max(0, round(ms / 10))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    seconds, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02}:{seconds:02}.{cs:02}"


def _escape_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def _render_event_text(event: SubtitleEvent) -> str:
    text = _escape_text(event.text)
    for span in event.spans:
        selector = span.get("selector") if isinstance(span, dict) else None
        style = span.get("style") if isinstance(span, dict) else None
        if not isinstance(selector, dict) or not isinstance(style, dict):
            continue
        if selector.get("type") != "keyword":
            continue
        keyword = str(selector.get("value") or "").strip()
        if not keyword or keyword not in event.text:
            continue
        color = style.get("primary_color")
        if not color:
            continue
        escaped_keyword = _escape_text(keyword)
        text = text.replace(escaped_keyword, f"{{\\c{_ass_inline_color(color)}}}{escaped_keyword}{{\\r}}", 1)
    return text


def _ass_inline_color(value: str) -> str:
    clean = str(value or "#FFFFFF").lstrip("#")
    if len(clean) != 6:
        clean = "FFFFFF"
    red, green, blue = clean[0:2], clean[2:4], clean[4:6]
    return f"&H{blue}{green}{red}&"


def _ass_color(value: str) -> str:
    clean = str(value or "#FFFFFF").lstrip("#")
    if len(clean) != 6:
        clean = "FFFFFF"
    red, green, blue = clean[0:2], clean[2:4], clean[4:6]
    return f"&H00{blue}{green}{red}"
```

- [ ] **Step 6: Run tests to verify green**

Run:

```bash
pytest tests/services/test_subtitle_timeline.py tests/services/test_ass_renderer.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add autovideo/services/subtitles/timeline.py autovideo/services/subtitles/template_assignment.py autovideo/services/subtitles/keyword_spans.py autovideo/services/subtitles/event_enrichment.py autovideo/services/subtitles/ass_renderer.py tests/services/test_subtitle_timeline.py tests/services/test_ass_renderer.py
git commit -m "feat: render subtitle events to ass"
```

---

## Task 3: Rendering Pipeline, FFmpeg Burn, Source Subtitle Masks, and Output Matrix

**Files:**
- Create: `autovideo/services/subtitles/ffmpeg_burner.py`
- Create: `autovideo/services/subtitles/source_masks.py`
- Modify: `autovideo/services/rendering.py`
- Test: `tests/services/test_subtitle_rendering_pipeline.py`
- Modify: `tests/services/test_rendering.py`

- [ ] **Step 1: Replace the sidecar-only test with failing burn tests**

In `tests/services/test_rendering.py`, replace `test_ffmpeg_command_keeps_subtitles_as_sidecar_only` with:

```python
def test_ffmpeg_command_burns_ass_when_subtitles_enabled(tmp_path):
    material_path = tmp_path / "clip.mp4"
    ass_path = tmp_path / "subtitles.ass"
    output_path = tmp_path / "output.mp4"
    material_path.write_bytes(b"video")
    ass_path.write_text("[Script Info]\n", encoding="utf-8")

    command = rendering._build_ffmpeg_command(
        ffmpeg_binary="ffmpeg",
        render_items=[({"duration": 1}, {"storage_path": str(material_path), "content_type": "video/mp4"})],
        output_path=output_path,
        aspect_ratio="9:16",
        source_subtitle_masks=[False],
        ass_path=ass_path,
    )

    filter_index = command.index("-filter_complex") + 1
    assert "ass=" in command[filter_index]
    assert "subtitles.ass" in command[filter_index]
    assert argv_has_output(command, output_path)


def test_ffmpeg_command_masks_source_subtitles_before_concat(tmp_path):
    material_path = tmp_path / "clip.mp4"
    output_path = tmp_path / "output.mp4"
    material_path.write_bytes(b"video")

    command = rendering._build_ffmpeg_command(
        ffmpeg_binary="ffmpeg",
        render_items=[({"duration": 1}, {"storage_path": str(material_path), "content_type": "video/mp4"})],
        output_path=output_path,
        aspect_ratio="9:16",
        source_subtitle_masks=[True],
        ass_path=None,
    )

    filter_index = command.index("-filter_complex") + 1
    assert "drawbox=x=0:y=1498:w=1080:h=422:color=black@1:t=fill" in command[filter_index]


def argv_has_output(command: list[str], output_path):
    return command[-1] == str(output_path)
```

- [ ] **Step 2: Add rendering pipeline tests**

Create `tests/services/test_subtitle_rendering_pipeline.py`:

```python
import json
import os

from autovideo.core.settings import Settings
from autovideo.services import rendering


def _fake_ffmpeg(tmp_path):
    log_path = tmp_path / "ffmpeg-argv.json"
    ffmpeg_path = tmp_path / "fake-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"pathlib.Path({str(log_path)!r}).write_text(json.dumps(sys.argv[1:], ensure_ascii=False), encoding='utf-8')\n"
        "pathlib.Path(sys.argv[-1]).write_bytes(b'video')\n",
        encoding="utf-8",
    )
    os.chmod(ffmpeg_path, 0o755)
    return str(ffmpeg_path), log_path


def _failing_fake_ffmpeg(tmp_path):
    ffmpeg_path = tmp_path / "failing-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stderr.write('base render failed')\n"
        "sys.exit(12)\n",
        encoding="utf-8",
    )
    os.chmod(ffmpeg_path, 0o755)
    return str(ffmpeg_path)


def _timeline():
    return {
        "title": "字幕渲染",
        "total_duration": 1,
        "items": [
            {
                "shot_index": 1,
                "start_time": 0,
                "end_time": 1,
                "duration": 1,
                "subtitle": "AI 提升效率",
                "material_id": "material-1",
            }
        ],
    }


def _materials(tmp_path):
    material_path = tmp_path / "caption_clip.mp4"
    material_path.write_bytes(b"video")
    return {"material-1": {"storage_path": str(material_path), "content_type": "video/mp4", "source_type": "upload"}}


def _template():
    return {
        "id": "template-1",
        "name": "字幕模板",
        "templates": {
            "bottom": {"font_family": "PingFang SC", "font_size": 54, "primary_color": "#FFFFFF"},
            "highlight": {"font_family": "PingFang SC", "font_size": 60, "primary_color": "#FFD54F"},
            "punch": {"font_family": "PingFang SC", "font_size": 68, "primary_color": "#FFFFFF"},
        },
        "blocks": [],
    }


def test_render_mix_video_writes_ass_base_video_and_burned_output(tmp_path):
    ffmpeg_path, log_path = _fake_ffmpeg(tmp_path)

    result = rendering.render_mix_video(
        settings=Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path=ffmpeg_path),
        output_dir=tmp_path / "outputs",
        timeline=_timeline(),
        materials_by_id=_materials(tmp_path),
        aspect_ratio="9:16",
        subtitle_enabled=True,
        subtitle_template_set=_template(),
        source_subtitle_masks=[True],
    )

    assert result.status == "subtitle_burned"
    assert result.output_path == tmp_path / "outputs" / "output.mp4"
    assert (tmp_path / "outputs" / "output.base.mp4").is_file()
    assert (tmp_path / "outputs" / "subtitles.ass").is_file()
    assert "ass=" in " ".join(json.loads(log_path.read_text(encoding="utf-8")))


def test_render_mix_video_without_ffmpeg_still_writes_timeline_srt_and_ass(tmp_path):
    result = rendering.render_mix_video(
        settings=Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg"),
        output_dir=tmp_path / "outputs",
        timeline=_timeline(),
        materials_by_id=_materials(tmp_path),
        aspect_ratio="9:16",
        subtitle_enabled=True,
        subtitle_template_set=_template(),
        source_subtitle_masks=[False],
    )

    assert result.output_path is None
    assert result.status == "manifest_only"
    assert result.renderer == "ffmpeg_unavailable"
    assert result.base_video_skipped is True
    assert result.subtitle_burn_skipped is True
    assert (tmp_path / "outputs" / "timeline.json").is_file()
    assert (tmp_path / "outputs" / "subtitles.srt").is_file()
    assert (tmp_path / "outputs" / "subtitles.ass").is_file()
    assert not (tmp_path / "outputs" / "output.base.mp4").exists()


def test_render_mix_video_base_failure_keeps_subtitle_artifacts(tmp_path):
    result = rendering.render_mix_video(
        settings=Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path=_failing_fake_ffmpeg(tmp_path)),
        output_dir=tmp_path / "outputs",
        timeline=_timeline(),
        materials_by_id=_materials(tmp_path),
        aspect_ratio="9:16",
        subtitle_enabled=True,
        subtitle_template_set=_template(),
        source_subtitle_masks=[False],
    )

    assert result.output_path is None
    assert result.status == "base_video_failed"
    assert "base render failed" in result.error_summary
    assert (tmp_path / "outputs" / "timeline.json").is_file()
    assert (tmp_path / "outputs" / "subtitles.srt").is_file()
    assert (tmp_path / "outputs" / "subtitles.ass").is_file()


def test_source_subtitle_masks_follow_material_source_and_markers(tmp_path):
    from autovideo.services.subtitles.source_masks import build_source_subtitle_masks

    captioned = tmp_path / "口播素材" / "clip.mp4"
    clean = tmp_path / "素材" / "clip.mp4"

    assert build_source_subtitle_masks("local", [str(captioned), str(clean)], subtitle_enabled=True) == [True, False]
    assert build_source_subtitle_masks("hybrid", [str(captioned)], subtitle_enabled=True) == [True]
    assert build_source_subtitle_masks("online", [str(captioned)], subtitle_enabled=True) == [False]
    assert build_source_subtitle_masks("local", [str(captioned)], subtitle_enabled=False) == [False]
```

- [ ] **Step 3: Run tests to verify red**

Run:

```bash
pytest tests/services/test_rendering.py tests/services/test_subtitle_rendering_pipeline.py -q
```

Expected: fail because `_build_ffmpeg_command` does not accept `source_subtitle_masks` or `ass_path`, `render_mix_video` does not return a structured result, and source mask helpers do not exist.

- [ ] **Step 4: Implement source mask helpers**

Create `autovideo/services/subtitles/source_masks.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

CAPTIONED_LOCAL_MATERIAL_MARKERS = (
    "口播",
    "字幕",
    "带字",
    "caption",
    "captions",
    "subtitle",
    "subtitled",
    "hard-sub",
    "hardsub",
)
SOURCE_SUBTITLE_MASK_HEIGHT_RATIO = 0.22


def material_path_appears_captioned(file_path: Any) -> bool:
    clean_path = str(file_path or "").strip()
    if not clean_path:
        return False
    path = Path(clean_path)
    searchable = f"{path.parent.name} {path.stem}".casefold()
    return any(marker.casefold() in searchable for marker in CAPTIONED_LOCAL_MATERIAL_MARKERS)


def build_source_subtitle_masks(
    material_source: str,
    material_paths: list[str],
    *,
    subtitle_enabled: bool,
    material_plans: list[list[Any]] | None = None,
) -> list[bool]:
    if not subtitle_enabled or material_source not in {"local", "hybrid"}:
        return [False for _ in material_paths]
    masks: list[bool] = []
    for index, path in enumerate(material_paths):
        planned_paths = material_plans[index] if material_plans and index < len(material_plans) and material_plans[index] else [path]
        masks.append(any(material_path_appears_captioned(item) for item in planned_paths))
    return masks


def drawbox_filter(width: int, height: int) -> str:
    mask_height = max(1, int(round(height * SOURCE_SUBTITLE_MASK_HEIGHT_RATIO)))
    y_pos = max(0, height - mask_height)
    return f"drawbox=x=0:y={y_pos}:w={width}:h={mask_height}:color=black@1:t=fill"
```

- [ ] **Step 5: Modify rendering pipeline**

Update `autovideo/services/rendering.py`:

```python
from dataclasses import dataclass
from autovideo.services.subtitles import ass_renderer, event_enrichment, keyword_spans, template_assignment
from autovideo.services.subtitles.source_masks import drawbox_filter
from autovideo.services.subtitles.timeline import events_from_render_timeline
```

Add this result type near `FfmpegRenderFailedError`:

```python
@dataclass(frozen=True)
class RenderResult:
    output_path: Path | None
    status: str
    renderer: str
    timeline_path: str = "timeline.json"
    subtitles_path: str = "subtitles.srt"
    subtitles_ass_path: str | None = None
    base_output_path: str | None = None
    base_video_skipped: bool = False
    subtitle_burn_skipped: bool = False
    error_summary: str = ""
```

Change `render_mix_video` signature:

```python
def render_mix_video(
    *,
    settings: Settings,
    output_dir: Path,
    timeline: dict[str, Any],
    materials_by_id: dict[str, dict[str, Any]],
    aspect_ratio: str,
    subtitle_enabled: bool = False,
    subtitle_template_set: dict[str, Any] | None = None,
    source_subtitle_masks: list[bool] | None = None,
) -> RenderResult:
```

Inside `render_mix_video`, write timeline artifacts before `shutil.which`, generate ASS when subtitles are enabled, and render through `output.base.mp4` plus burn:

```python
safe_timeline = sanitize_render_timeline(timeline)
output_dir.mkdir(parents=True, exist_ok=True)
write_timeline_artifacts(output_dir, safe_timeline)
ass_path = None
if subtitle_enabled and subtitle_template_set:
    resolution = _resolution_for_aspect_ratio(aspect_ratio)
    events = events_from_render_timeline(safe_timeline)
    events = template_assignment.assign_template_roles(events, subtitle_template_set, random_seed=1)
    events = keyword_spans.apply_keyword_spans(events, subtitle_template_set, random_seed=1)
    events = event_enrichment.enrich_subtitle_events(events, subtitle_template_set, resolution)
    ass_path = ass_renderer.write_ass_file(output_dir / "subtitles.ass", events, subtitle_template_set, resolution)

render_items = _timeline_items_with_materials(safe_timeline, materials_by_id)
ffmpeg_binary = shutil.which(settings.ffmpeg_path)
if ffmpeg_binary is None:
    return RenderResult(
        output_path=None,
        status="manifest_only",
        renderer="ffmpeg_unavailable",
        subtitles_ass_path=ass_path.name if ass_path else None,
        base_video_skipped=True,
        subtitle_burn_skipped=ass_path is not None,
    )

output_path = output_dir / "output.mp4"
base_output_path = output_dir / "output.base.mp4" if ass_path else output_path
command = _build_ffmpeg_command(
    ffmpeg_binary=ffmpeg_binary,
    render_items=render_items,
    output_path=base_output_path,
    aspect_ratio=aspect_ratio,
    source_subtitle_masks=source_subtitle_masks or [False for _ in render_items],
    ass_path=None,
)
```

Run the base render inside a `try` block. Invalid timeline/material validation errors should still raise. FFmpeg process failures should return `base_video_failed` so `create_task` can keep manifest, timeline, SRT, and ASS:

```python
try:
    _run_ffmpeg_command(command, safe_timeline)
except FfmpegRenderFailedError as exc:
    if ass_path is None:
        raise
    return RenderResult(
        output_path=None,
        status="base_video_failed",
        renderer="ffmpeg",
        subtitles_ass_path=ass_path.name if ass_path else None,
        base_output_path=base_output_path.name,
        error_summary=_clean_ffmpeg_stderr(exc.stderr or str(exc)),
    )
```

After base render succeeds, run a second FFmpeg command using `ffmpeg_burner.burn_ass_subtitles`:

```python
if ass_path is not None:
    from autovideo.services.subtitles.ffmpeg_burner import burn_ass_subtitles

    try:
        burn_ass_subtitles(
            ffmpeg_binary=ffmpeg_binary,
            input_path=base_output_path,
            ass_path=ass_path,
            output_path=output_path,
            timeout_seconds=_ffmpeg_timeout_seconds(safe_timeline),
        )
    except FfmpegRenderFailedError as exc:
        return RenderResult(
            output_path=base_output_path,
            status="subtitle_burn_failed",
            renderer="ffmpeg",
            subtitles_ass_path=ass_path.name,
            base_output_path=base_output_path.name,
            error_summary=_clean_ffmpeg_stderr(exc.stderr or str(exc)),
        )
    return RenderResult(
        output_path=output_path,
        status="subtitle_burned",
        renderer="ffmpeg",
        subtitles_ass_path=ass_path.name,
        base_output_path=base_output_path.name,
    )
return RenderResult(output_path=output_path, status="video_rendered", renderer="ffmpeg")
```

Add helper wrappers so the complete behavior is reusable:

```python
def _run_ffmpeg_command(command: list[str], timeline: dict[str, Any]) -> None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=_ffmpeg_timeout_seconds(timeline),
        )
    except subprocess.TimeoutExpired as exc:
        raise FfmpegRenderFailedError("FFmpeg 渲染超时", stderr=str(exc)) from exc
    if completed.returncode != 0:
        raise FfmpegRenderFailedError(
            "FFmpeg 渲染失败",
            stderr=(completed.stderr or completed.stdout or "").strip(),
        )


def _clean_ffmpeg_stderr(stderr: str) -> str:
    return str(stderr or "").strip()[-1200:]


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
```

Change `_build_ffmpeg_command` signature:

```python
def _build_ffmpeg_command(
    *,
    ffmpeg_binary: str,
    render_items: list[tuple[dict[str, Any], dict[str, Any]]],
    output_path: Path,
    aspect_ratio: str,
    source_subtitle_masks: list[bool] | None = None,
    ass_path: Path | None = None,
) -> list[str]:
```

In each per-input filter, append drawbox when the corresponding mask is true:

```python
mask_filter = f",{drawbox_filter(width, height)}" if index < len(source_subtitle_masks or []) and source_subtitle_masks[index] else ""
filters.append(
    f"[{index}:v]"
    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
    f"crop={width}:{height},setsar=1,fps=30,format=yuv420p"
    f"{mask_filter}"
    f"[{label}]"
)
```

When `ass_path` is passed directly to `_build_ffmpeg_command`, append an ASS filter after concat:

```python
concat_filter = f"{''.join(video_labels)}concat=n={len(video_labels)}:v=1:a=0,format=yuv420p"
if ass_path is not None:
    concat_filter += f",ass={_escape_filter_path(ass_path)}"
filters.append(f"{concat_filter}[v]")
```

- [ ] **Step 6: Create FFmpeg burner**

Create `autovideo/services/subtitles/ffmpeg_burner.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from autovideo.services.rendering import FfmpegRenderFailedError


def burn_ass_subtitles(
    *,
    ffmpeg_binary: str,
    input_path: Path,
    ass_path: Path,
    output_path: Path,
    timeout_seconds: float,
) -> Path:
    command = [
        ffmpeg_binary,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"ass={_escape_filter_path(ass_path)}",
        "-an",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise FfmpegRenderFailedError("FFmpeg 字幕烧录超时", stderr=str(exc)) from exc
    if completed.returncode != 0:
        raise FfmpegRenderFailedError("FFmpeg 字幕烧录失败", stderr=(completed.stderr or completed.stdout or "").strip())
    if not output_path.is_file():
        raise FfmpegRenderFailedError("FFmpeg 未生成带字幕输出视频")
    return output_path


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
```

- [ ] **Step 7: Run tests to verify green**

Run:

```bash
pytest tests/services/test_rendering.py tests/services/test_subtitle_rendering_pipeline.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add autovideo/services/subtitles/ffmpeg_burner.py autovideo/services/subtitles/source_masks.py autovideo/services/rendering.py tests/services/test_rendering.py tests/services/test_subtitle_rendering_pipeline.py
git commit -m "feat: burn ass subtitles during rendering"
```

---

## Task 4: Subtitle Template API and Preview Endpoints

**Files:**
- Create: `autovideo/api/routes/subtitle_templates.py`
- Create: `autovideo/services/subtitles/preview_renderer.py`
- Modify: `autovideo/api/app.py`
- Test: `tests/api/test_subtitle_templates.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/api/test_subtitle_templates.py`:

```python
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


def _client(tmp_path):
    return TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path="missing-ffmpeg")))


def test_list_create_update_validate_and_delete_template_set(tmp_path):
    with _client(tmp_path) as client:
        listing = client.get("/api/subtitle-template-sets")
        preset_id = listing.json()["presets"][0]["id"]
        created = client.post("/api/subtitle-template-sets", json={"name": "我的模板", "preset_id": preset_id})
        template_id = created.json()["id"]
        updated = client.put(
            f"/api/subtitle-template-sets/{template_id}",
            json={"name": "默认模板", "is_favorite": True},
        )
        validated = client.post("/api/subtitle-template-sets/validate", json=updated.json())
        deleted = client.delete(f"/api/subtitle-template-sets/{template_id}")

    assert listing.status_code == 200
    assert created.status_code == 201
    assert updated.json()["is_favorite"] is True
    assert validated.json()["ok"] is True
    assert deleted.status_code == 204


def test_preview_reports_ffmpeg_unavailable_without_blocking_template_save(tmp_path):
    with _client(tmp_path) as client:
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/subtitle-template-sets/preview",
            json={"template_set": template, "template_type": "bottom", "aspect_ratio": "9:16", "sample_text": "AI 提升效率"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE"


def test_preset_override_reset_and_timeline_preview_routes(tmp_path):
    ffmpeg_path = _write_preview_fake_ffmpeg(tmp_path)
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path=ffmpeg_path))) as client:
        preset_id = client.get("/api/subtitle-template-sets").json()["presets"][0]["id"]
        overridden = client.put(
            f"/api/subtitle-template-sets/presets/{preset_id}",
            json={"name": "收藏预设", "is_favorite": True},
        )
        listing = client.get("/api/subtitle-template-sets").json()
        timeline_preview = client.post(
            "/api/subtitle-template-sets/preview-timeline",
            json={
                "template_set": overridden.json(),
                "template_type": "bottom",
                "aspect_ratio": "9:16",
                "sample_text": "AI 提升效率",
                "duration_ms": 1200,
            },
        )
        reset = client.delete(f"/api/subtitle-template-sets/presets/{preset_id}")

    assert overridden.status_code == 200
    assert any(item["is_favorite"] for item in listing["presets"] if item["id"] == preset_id)
    assert timeline_preview.status_code == 200
    assert timeline_preview.json()["mime_type"] == "video/mp4"
    assert timeline_preview.json()["duration_ms"] == 1200
    assert reset.status_code == 204


def _write_preview_fake_ffmpeg(tmp_path) -> str:
    ffmpeg_path = tmp_path / "preview-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[-1]).write_bytes(b'preview-media')\n",
        encoding="utf-8",
    )
    ffmpeg_path.chmod(0o755)
    return str(ffmpeg_path)
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
pytest tests/api/test_subtitle_templates.py -q
```

Expected: fail with 404 for `/api/subtitle-template-sets`.

- [ ] **Step 3: Implement preview renderer**

Create `autovideo/services/subtitles/preview_renderer.py` with real FFmpeg/libass-backed output. The fake FFmpeg tests prove command shape and file handling; real FFmpeg smoke in Task 8 verifies decoder behavior.

```python
from __future__ import annotations

import base64
import subprocess
import shutil
from pathlib import Path
from typing import Any

from autovideo.services.subtitles import ass_renderer
from autovideo.services.subtitles.timeline import SubtitleEvent


class SubtitlePreviewRendererUnavailableError(RuntimeError):
    pass


def render_preview_png(
    *,
    ffmpeg_path: str,
    template_set: dict[str, Any],
    template_type: str,
    aspect_ratio: str,
    sample_text: str,
    work_dir: Path,
) -> dict[str, Any]:
    output_path = _render_preview_media(
        ffmpeg_path=ffmpeg_path,
        template_set=template_set,
        template_type=template_type,
        aspect_ratio=aspect_ratio,
        sample_text=sample_text,
        work_dir=work_dir,
        duration_ms=1200,
        output_name="preview.png",
        video=False,
    )
    return {
        "mime_type": "image/png",
        "data": base64.b64encode(output_path.read_bytes()).decode("ascii"),
        "resolution": _resolution_payload(aspect_ratio),
        "warnings": [],
    }


def render_preview_timeline(
    *,
    ffmpeg_path: str,
    template_set: dict[str, Any],
    template_type: str,
    aspect_ratio: str,
    sample_text: str,
    duration_ms: int,
    work_dir: Path,
) -> dict[str, Any]:
    clean_duration_ms = max(500, min(int(duration_ms or 1200), 5000))
    output_path = _render_preview_media(
        ffmpeg_path=ffmpeg_path,
        template_set=template_set,
        template_type=template_type,
        aspect_ratio=aspect_ratio,
        sample_text=sample_text,
        work_dir=work_dir,
        duration_ms=clean_duration_ms,
        output_name="preview.mp4",
        video=True,
    )
    return {
        "mime_type": "video/mp4",
        "data": base64.b64encode(output_path.read_bytes()).decode("ascii"),
        "duration_ms": clean_duration_ms,
        "resolution": _resolution_payload(aspect_ratio),
        "warnings": [],
    }


def _render_preview_media(
    *,
    ffmpeg_path: str,
    template_set: dict[str, Any],
    template_type: str,
    aspect_ratio: str,
    sample_text: str,
    work_dir: Path,
    duration_ms: int,
    output_name: str,
    video: bool,
) -> Path:
    ffmpeg_binary = shutil.which(ffmpeg_path)
    if ffmpeg_binary is None:
        raise SubtitlePreviewRendererUnavailableError("FFmpeg/libass preview renderer is unavailable")
    width, height = _resolution(aspect_ratio)
    work_dir.mkdir(parents=True, exist_ok=True)
    ass_path = work_dir / f"{output_name}.ass"
    output_path = work_dir / output_name
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=duration_ms,
        text=sample_text,
        template=template_type,
    )
    ass_renderer.write_ass_file(ass_path, [event], template_set, (width, height))
    duration_seconds = f"{duration_ms / 1000:.3f}"
    command = [
        ffmpeg_binary,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:d={duration_seconds}",
        "-vf",
        f"ass={_escape_filter_path(ass_path)}",
    ]
    if video:
        command.extend(["-t", duration_seconds, "-movflags", "+faststart", str(output_path)])
    else:
        command.extend(["-frames:v", "1", str(output_path)])
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired as exc:
        raise SubtitlePreviewRendererUnavailableError(f"preview render timeout: {exc}") from exc
    if completed.returncode != 0 or not output_path.exists():
        raise SubtitlePreviewRendererUnavailableError((completed.stderr or completed.stdout or "preview failed").strip())
    return output_path


def _resolution(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "16:9":
        return 1920, 1080
    if aspect_ratio == "1:1":
        return 1080, 1080
    return 1080, 1920


def _resolution_payload(aspect_ratio: str) -> dict[str, int]:
    width, height = _resolution(aspect_ratio)
    return {"width": width, "height": height}


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
```

- [ ] **Step 4: Implement subtitle template router**

Create `autovideo/api/routes/subtitle_templates.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.subtitles.preview_renderer import (
    SubtitlePreviewRendererUnavailableError,
    render_preview_png,
    render_preview_timeline,
)
from autovideo.services.subtitles.template_store import SubtitleTemplateStore

router = APIRouter(prefix="/api/subtitle-template-sets", tags=["subtitle-template-sets"])


class CreateTemplateSetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    preset_id: str | None = None
    source_id: str | None = None


class PreviewRequest(BaseModel):
    template_set: dict[str, Any]
    template_type: str = "bottom"
    aspect_ratio: str = "9:16"
    sample_text: str = "AI 提升效率"
    duration_ms: int = 1200


def _store(settings: Settings) -> SubtitleTemplateStore:
    return SubtitleTemplateStore(settings)


@router.get("")
def list_template_sets(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    store = _store(settings)
    return {"items": store.list_template_sets(), "presets": store.list_presets()}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_template_set(body: CreateTemplateSetRequest, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return _store(settings).create_template_set(body.name, preset_id=body.preset_id, source_id=body.source_id)
    except (KeyError, ValueError) as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "SUBTITLE_TEMPLATE_INVALID", message=str(exc)) from exc


@router.put("/{template_set_id}")
def update_template_set(template_set_id: str, patch: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return _store(settings).update_template_set(template_set_id, patch)
    except (KeyError, ValueError) as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "SUBTITLE_TEMPLATE_INVALID", message=str(exc)) from exc


@router.delete("/{template_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template_set(template_set_id: str, settings: Settings = Depends(get_settings)) -> Response:
    try:
        _store(settings).delete_template_set(template_set_id)
    except KeyError as exc:
        raise structured_error(status.HTTP_404_NOT_FOUND, "SUBTITLE_TEMPLATE_NOT_FOUND") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/presets/{preset_id}")
def update_preset(preset_id: str, patch: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return _store(settings).update_preset(preset_id, patch)
    except (KeyError, ValueError) as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "SUBTITLE_TEMPLATE_INVALID", message=str(exc)) from exc


@router.delete("/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_preset(preset_id: str, settings: Settings = Depends(get_settings)) -> Response:
    _store(settings).reset_preset(preset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/validate")
def validate_template_set(payload: dict[str, Any], settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    from autovideo.services.subtitles import dsl_v2

    return dsl_v2.validate_template_set_v2(payload)


@router.post("/preview")
def preview_template(body: PreviewRequest, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return render_preview_png(
            ffmpeg_path=settings.ffmpeg_path,
            template_set=body.template_set,
            template_type=body.template_type,
            aspect_ratio=body.aspect_ratio,
            sample_text=body.sample_text,
            work_dir=settings.data_dir / "subtitle_previews",
        )
    except SubtitlePreviewRendererUnavailableError as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE", message=str(exc)) from exc


@router.post("/preview-timeline")
def preview_template_timeline(body: PreviewRequest, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return render_preview_timeline(
            ffmpeg_path=settings.ffmpeg_path,
            template_set=body.template_set,
            template_type=body.template_type,
            aspect_ratio=body.aspect_ratio,
            sample_text=body.sample_text,
            duration_ms=body.duration_ms,
            work_dir=settings.data_dir / "subtitle_previews",
        )
    except SubtitlePreviewRendererUnavailableError as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE", message=str(exc)) from exc
```

Modify `autovideo/api/app.py`:

```python
from autovideo.api.routes.subtitle_templates import router as subtitle_templates_router
```

and include before static mounting:

```python
app.include_router(subtitle_templates_router)
```

- [ ] **Step 5: Run tests to verify green**

Run:

```bash
pytest tests/api/test_subtitle_templates.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add autovideo/api/routes/subtitle_templates.py autovideo/services/subtitles/preview_renderer.py autovideo/api/app.py tests/api/test_subtitle_templates.py
git commit -m "feat: add subtitle template api"
```

---

## Task 5: Online Mix Subtitle Options, Snapshot Rules, Font Override, and Manifest

**Files:**
- Modify: `autovideo/services/online_mix.py`
- Modify: `autovideo/api/routes/online_mix.py`
- Modify: `tests/api/test_online_mix.py`

- [ ] **Step 1: Add failing online mix option tests**

First modify the existing `test_online_mix_cleans_unregistered_output_dir_when_ffmpeg_fails` in `tests/api/test_online_mix.py` so it explicitly tests the subtitle-disabled hard failure path. Keep the current assertions for `502`, empty task list, and cleaned output directory, and add this option to the request body:

```python
"options": {"aspect_ratio": "9:16", "subtitle_enabled": False},
```

This preserves the existing cleanup guarantee for hard render exceptions while allowing subtitle-enabled base video failures to keep manifest, timeline, SRT, and ASS artifacts.

Also update legacy tests that assert pre-subtitle render status or exact sanitized options:

- In `test_online_mix_renders_video_and_writes_timeline_when_ffmpeg_available`, set `"options": {"aspect_ratio": "9:16", "subtitle_enabled": False}` and update the assertion to `manifest["render_plan"]["status"] == "video_rendered"`.
- In `test_online_mix_sanitizes_sensitive_task_options`, add `"subtitle_enabled": False` to request options and to the expected sanitized options. This keeps the test focused on secret stripping while accepting the new subtitle option schema.

Append to `tests/api/test_online_mix.py`:

```python
def test_online_mix_persists_subtitle_snapshot_and_font_override(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg-binary"))

    with TestClient(app) as client:
        material = client.post("/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}).json()
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "字幕快照",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "aspect_ratio": "9:16",
                    "subtitle_enabled": True,
                    "subtitle_template_snapshot": template,
                    "subtitle_template_set_id": template["id"],
                    "subtitle_font_family": "Noto Sans CJK SC",
                },
            },
        )
        task = response.json()

    manifest = json.loads((tmp_path / "outputs" / task["id"] / "manifest.json").read_text(encoding="utf-8"))
    snapshot = manifest["subtitle_template_snapshot"]
    assert response.status_code == 201
    assert manifest["subtitle_enabled"] is True
    assert snapshot["id"] == template["id"]
    assert "template_variants" in snapshot
    assert snapshot["templates"]["bottom"]["font_family"] == "Noto Sans CJK SC"
    assert snapshot["blocks"][0]["style"]["font_family"] == "Noto Sans CJK SC"
    assert manifest["render_plan"]["subtitles_ass"] == "subtitles.ass"


def test_online_mix_rejects_snapshot_id_mismatch(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg-binary"))

    with TestClient(app) as client:
        material = client.post("/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}).json()
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "快照不匹配",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "subtitle_enabled": True,
                    "subtitle_template_set_id": "different-id",
                    "subtitle_template_snapshot": template,
                },
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SUBTITLE_TEMPLATE_INVALID"


def test_online_mix_keeps_manifest_and_ass_when_base_video_fails(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, ffmpeg_path=_write_failing_fake_ffmpeg(tmp_path)))

    with TestClient(app) as client:
        material = client.post("/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}).json()
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "保留字幕产物",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "subtitle_enabled": True,
                    "subtitle_template_snapshot": template,
                    "subtitle_template_set_id": template["id"],
                },
            },
        )
        task = response.json()

    output_dir = tmp_path / "outputs" / task["id"]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert response.status_code == 201
    assert manifest["render_plan"]["status"] == "base_video_failed"
    assert (output_dir / "timeline.json").is_file()
    assert (output_dir / "subtitles.srt").is_file()
    assert (output_dir / "subtitles.ass").is_file()


def test_online_mix_manifest_records_captioned_local_source_masks(tmp_path):
    from datetime import UTC, datetime

    from autovideo.storage.database import AutoVideoStore

    settings = Settings(data_dir=tmp_path, ffmpeg_path="missing-ffmpeg")
    store = AutoVideoStore(settings)
    captioned_dir = tmp_path / "字幕素材"
    clean_dir = tmp_path / "clean"
    captioned_dir.mkdir()
    clean_dir.mkdir()
    captioned_path = captioned_dir / "clip.mp4"
    clean_path = clean_dir / "clip.mp4"
    captioned_path.write_bytes(b"captioned")
    clean_path.write_bytes(b"clean")
    now = datetime.now(UTC).isoformat()
    captioned = store.insert_material(
        {
            "id": "captioned-local",
            "original_filename": "clip.mp4",
            "content_type": "video/mp4",
            "size_bytes": captioned_path.stat().st_size,
            "storage_path": str(captioned_path),
            "created_at": now,
            "source_type": "upload",
        }
    )
    clean = store.insert_material(
        {
            "id": "clean-local",
            "original_filename": "clip.mp4",
            "content_type": "video/mp4",
            "size_bytes": clean_path.stat().st_size,
            "storage_path": str(clean_path),
            "created_at": now,
            "source_type": "upload",
        }
    )
    app = create_app(settings)

    with TestClient(app) as client:
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "源字幕遮挡",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_materials": [
                    {"shot_index": 1, "material_id": captioned["id"]},
                    {"shot_index": 2, "material_id": clean["id"]},
                ],
                "options": {
                    "subtitle_enabled": True,
                    "subtitle_template_snapshot": template,
                    "subtitle_template_set_id": template["id"],
                },
            },
        )
        task = response.json()

    output_dir = tmp_path / "outputs" / task["id"]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert response.status_code == 201
    assert manifest["render_plan"]["status"] == "manifest_only"
    assert manifest["render_plan"]["base_video_skipped"] is True
    assert manifest["render_plan"]["subtitle_burn_skipped"] is True
    assert manifest["render_plan"]["source_subtitle_masked"] is True
    assert manifest["render_plan"]["source_subtitle_mask_count"] == 1
    assert manifest["render_plan"]["source_subtitle_masks"] == [True, False]


def _write_failing_fake_ffmpeg(tmp_path) -> str:
    ffmpeg_path = tmp_path / "failing-online-mix-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stderr.write('base render failed')\n"
        "sys.exit(12)\n",
        encoding="utf-8",
    )
    ffmpeg_path.chmod(0o755)
    return str(ffmpeg_path)
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
pytest tests/api/test_online_mix.py::test_online_mix_persists_subtitle_snapshot_and_font_override tests/api/test_online_mix.py::test_online_mix_rejects_snapshot_id_mismatch tests/api/test_online_mix.py::test_online_mix_keeps_manifest_and_ass_when_base_video_fails tests/api/test_online_mix.py::test_online_mix_manifest_records_captioned_local_source_masks -q
```

Expected: fail because online mix does not normalize subtitle options.

- [ ] **Step 3: Add subtitle option normalization helpers**

Modify `autovideo/services/online_mix.py`:

```python
from autovideo.services.subtitles import dsl_v2
from autovideo.services.subtitles.source_masks import build_source_subtitle_masks
from autovideo.services.subtitles.template_store import SubtitleTemplateStore
```

Add:

```python
class SubtitleTemplateInvalidError(ValueError):
    pass


def normalize_subtitle_options(store: AutoVideoStore, options: dict[str, Any]) -> dict[str, Any]:
    subtitle_enabled = bool(options.get("subtitle_enabled", True))
    if not subtitle_enabled:
        return {"subtitle_enabled": False, "subtitle_template_set_id": None, "subtitle_template_snapshot": None, "subtitle_font_family": None}

    template_store = SubtitleTemplateStore(store.settings)
    template_set_id = str(options.get("subtitle_template_set_id") or "").strip()
    snapshot = options.get("subtitle_template_snapshot")
    if isinstance(snapshot, dict):
        snapshot_id = str(snapshot.get("id") or "").strip()
        snapshot_name = str(snapshot.get("name") or "").strip()
        if not snapshot_id or not snapshot_name:
            raise SubtitleTemplateInvalidError("Subtitle template snapshot must include id and name")
        if template_set_id and snapshot_id != template_set_id:
            raise SubtitleTemplateInvalidError("Subtitle template snapshot does not match template set id")
        effective = snapshot
    elif template_set_id:
        effective = template_store.get_template_set(template_set_id)
    else:
        effective = template_store.select_auto_template_set()

    result = dsl_v2.validate_template_set_v2(effective)
    if not result["ok"]:
        raise SubtitleTemplateInvalidError("; ".join(result["warnings"]))
    snapshot = _override_subtitle_template_font_family(result["normalized"], options.get("subtitle_font_family"))
    return {
        "subtitle_enabled": True,
        "subtitle_template_set_id": snapshot["id"],
        "subtitle_template_set_name": snapshot["name"],
        "subtitle_template_snapshot": snapshot,
        "subtitle_font_family": str(options.get("subtitle_font_family") or "").strip() or None,
    }


def _override_subtitle_template_font_family(template_set: dict[str, Any], font_family: Any) -> dict[str, Any]:
    import copy

    clean_font = str(font_family or "").strip()
    snapshot = copy.deepcopy(template_set)
    if not clean_font:
        return snapshot
    for template in (snapshot.get("templates") or {}).values():
        if isinstance(template, dict):
            template["font_family"] = clean_font
    for block in snapshot.get("blocks") or []:
        if isinstance(block, dict):
            block.setdefault("style", {})["font_family"] = clean_font
    for variants in (snapshot.get("template_variants") or {}).values():
        items = variants.values() if isinstance(variants, dict) else variants if isinstance(variants, list) else []
        for variant in items:
            if isinstance(variant, dict) and isinstance(variant.get("template"), dict):
                variant["template"]["font_family"] = clean_font
            if isinstance(variant, dict):
                for block in variant.get("blocks") or []:
                    if isinstance(block, dict):
                        block.setdefault("style", {})["font_family"] = clean_font
    return snapshot
```

- [ ] **Step 4: Connect normalized options to task builder**

In `create_online_mix_task`, compute:

```python
subtitle_options = normalize_subtitle_options(store, options)
sanitized_options = sanitized_online_mix_options({**options, **subtitle_options})
```

Pass `sanitized_options` to `create_task(options=...)`.

Add manifest fields:

```python
"subtitle_enabled": subtitle_options["subtitle_enabled"],
"subtitle_template_set_id": subtitle_options.get("subtitle_template_set_id"),
"subtitle_template_set_name": subtitle_options.get("subtitle_template_set_name"),
"subtitle_template_snapshot": subtitle_options.get("subtitle_template_snapshot"),
"subtitle_font_family": subtitle_options.get("subtitle_font_family"),
```

Pass `subtitle_options` into `_render_online_mix_output_builder`, and then into `render_mix_video`. Use the structured `RenderResult` from Task 3; do not raise for `manifest_only`, `base_video_failed`, or `subtitle_burn_failed`, because `create_task` would delete the output directory on exceptions:

```python
render_result = render_mix_video(
    settings=store.settings,
    output_dir=output_dir,
    timeline=safe_timeline,
    materials_by_id=materials_by_id,
    aspect_ratio=str(options.get("aspect_ratio") or script.get("aspect_ratio") or "9:16"),
    subtitle_enabled=bool(subtitle_options.get("subtitle_enabled")),
    subtitle_template_set=subtitle_options.get("subtitle_template_snapshot"),
    source_subtitle_masks=source_subtitle_masks,
)
```

Build masks before rendering:

```python
material_paths = [str(materials_by_id[str(item["material_id"])]["storage_path"]) for item in manifest_shots]
material_source = "hybrid" if any(item.get("provider") for item in manifest_shots) and any(not item.get("provider") for item in manifest_shots) else "online" if all(item.get("provider") for item in manifest_shots) else "local"
source_subtitle_masks = build_source_subtitle_masks(
    material_source,
    material_paths,
    subtitle_enabled=bool(subtitle_options.get("subtitle_enabled")),
)
```

Set render plans from `render_result`:

```python
output_payload["render_plan"] = {
    "status": render_result.status,
    "renderer": render_result.renderer,
    "output": render_result.output_path.name if render_result.output_path else None,
    "base_output": render_result.base_output_path,
    "timeline": render_result.timeline_path,
    "subtitles": render_result.subtitles_path,
    "subtitles_ass": render_result.subtitles_ass_path,
    "base_video_skipped": render_result.base_video_skipped,
    "subtitle_burn_skipped": render_result.subtitle_burn_skipped,
    "error_summary": render_result.error_summary or None,
    "source_subtitle_masked": any(source_subtitle_masks),
    "source_subtitle_mask_count": sum(1 for value in source_subtitle_masks if value),
    "source_subtitle_masks": source_subtitle_masks,
}
return render_result.output_path
```

- [ ] **Step 5: Map subtitle errors in API route**

Modify `autovideo/api/routes/online_mix.py` imports and exception handling:

```python
from autovideo.services.online_mix import SubtitleTemplateInvalidError
```

Add before generic rendering errors:

```python
except SubtitleTemplateInvalidError as exc:
    raise structured_error(
        status.HTTP_400_BAD_REQUEST,
        "SUBTITLE_TEMPLATE_INVALID",
        message=str(exc),
    ) from exc
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest tests/api/test_online_mix.py::test_online_mix_persists_subtitle_snapshot_and_font_override tests/api/test_online_mix.py::test_online_mix_rejects_snapshot_id_mismatch tests/api/test_online_mix.py::test_online_mix_keeps_manifest_and_ass_when_base_video_fails tests/api/test_online_mix.py::test_online_mix_manifest_records_captioned_local_source_masks -q
```

Expected: all focused tests pass.

- [ ] **Step 7: Run related API tests**

Run:

```bash
pytest tests/api/test_online_mix.py tests/api/test_subtitle_templates.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add autovideo/services/online_mix.py autovideo/api/routes/online_mix.py tests/api/test_online_mix.py
git commit -m "feat: persist subtitle options for online mixes"
```

---

## Task 6: Frontend Subtitle API and Navigation

**Files:**
- Create: `frontend/src/api/subtitles.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add failing frontend tests for navigation and API mocks**

Modify `frontend/src/App.test.tsx` mock section:

```typescript
vi.mock("./api/subtitles", () => ({
  fetchSubtitleTemplateSets: vi.fn(),
  createSubtitleTemplateSet: vi.fn(),
  updateSubtitleTemplateSet: vi.fn(),
  deleteSubtitleTemplateSet: vi.fn(),
  updateSubtitlePresetOverride: vi.fn(),
  resetSubtitlePresetOverride: vi.fn(),
  validateSubtitleTemplateSet: vi.fn(),
  previewSubtitleTemplateSet: vi.fn(),
  previewSubtitleTimeline: vi.fn(),
}));
```

Import:

```typescript
import {
  createSubtitleTemplateSet,
  fetchSubtitleTemplateSets,
  previewSubtitleTemplateSet,
  previewSubtitleTimeline,
  resetSubtitlePresetOverride,
  updateSubtitlePresetOverride,
  updateSubtitleTemplateSet,
  validateSubtitleTemplateSet,
} from "./api/subtitles";
```

In `beforeEach`, add:

```typescript
const cleanBottomPreset = {
  id: "preset-clean-bottom",
  name: "清晰底部字幕",
  schema_version: 2,
  renderer_mode: "ass_plus",
  templates: {
    bottom: { font_family: "PingFang SC", font_size: 54, primary_color: "#FFFFFF" },
    highlight: { font_family: "PingFang SC", font_size: 60, primary_color: "#FFD54F" },
    punch: { font_family: "PingFang SC", font_size: 68, primary_color: "#FFFFFF" },
  },
  blocks: [],
  template_variants: {},
};

vi.mocked(fetchSubtitleTemplateSets).mockResolvedValue({
  items: [],
  presets: [cleanBottomPreset],
});
vi.mocked(createSubtitleTemplateSet).mockResolvedValue({
  ...cleanBottomPreset,
  id: "custom-clean-bottom",
  name: "我的清晰底部字幕",
});
vi.mocked(updateSubtitleTemplateSet).mockResolvedValue({
  ...cleanBottomPreset,
  id: "custom-clean-bottom",
  name: "我的清晰底部字幕",
  is_favorite: true,
});
vi.mocked(updateSubtitlePresetOverride).mockResolvedValue({
  ...cleanBottomPreset,
  is_favorite: true,
});
vi.mocked(resetSubtitlePresetOverride).mockResolvedValue(undefined);
vi.mocked(previewSubtitleTemplateSet).mockResolvedValue({
  mime_type: "image/png",
  data: btoa("preview"),
  resolution: { width: 1080, height: 1920 },
  warnings: [],
});
vi.mocked(previewSubtitleTimeline).mockResolvedValue({
  mime_type: "video/mp4",
  data: btoa("timeline-preview"),
  duration_ms: 1200,
  resolution: { width: 1080, height: 1920 },
  warnings: [],
});
vi.mocked(validateSubtitleTemplateSet).mockResolvedValue({
  ok: true,
  normalized: cleanBottomPreset,
  warnings: [],
});
```

Add test:

```typescript
it("opens the subtitle template workbench from desktop and mobile navigation", async () => {
  const user = userEvent.setup();
  renderApp();

  await user.click(await screen.findByRole("link", { name: "字幕模板" }));

  expect(screen.getByRole("heading", { name: "字幕模板" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "字幕模板" })).toHaveAttribute("aria-current", "page");

  await user.click(screen.getByRole("link", { name: "混剪工作台" }));
  await user.click(screen.getByRole("link", { name: "字幕" }));

  expect(screen.getByRole("heading", { name: "字幕模板" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "字幕" })).toHaveAttribute("aria-current", "page");
});
```

- [ ] **Step 2: Run test to verify red**

Run:

```bash
cd frontend && npm test -- --run App.test.tsx
```

Expected: fail because `./api/subtitles` and clickable subtitle navigation do not exist.

- [ ] **Step 3: Create subtitle API client**

Create `frontend/src/api/subtitles.ts`:

```typescript
export interface SubtitleTemplateSet {
  id: string;
  name: string;
  schema_version?: number;
  renderer_mode?: string;
  is_favorite?: boolean;
  favorite?: boolean;
  templates: Record<string, Record<string, unknown>>;
  blocks: Array<Record<string, unknown>>;
  tracks?: Array<Record<string, unknown>>;
  template_variants?: Record<string, unknown>;
}

export interface SubtitleTemplateSetList {
  items: SubtitleTemplateSet[];
  presets: SubtitleTemplateSet[];
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(
      typeof payload === "object" &&
        payload !== null &&
        "detail" in payload &&
        typeof payload.detail === "object" &&
        payload.detail !== null &&
        "code" in payload.detail
        ? String(payload.detail.code)
        : `HTTP_${response.status}`,
    );
  }
  return response.json() as Promise<T>;
}

export async function fetchSubtitleTemplateSets(): Promise<SubtitleTemplateSetList> {
  return readJson(await fetch("/api/subtitle-template-sets"));
}

export async function createSubtitleTemplateSet(input: {
  name: string;
  preset_id?: string;
  source_id?: string;
}): Promise<SubtitleTemplateSet> {
  return readJson(
    await fetch("/api/subtitle-template-sets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function updateSubtitleTemplateSet(input: {
  id: string;
  patch: Partial<SubtitleTemplateSet>;
}): Promise<SubtitleTemplateSet> {
  return readJson(
    await fetch(`/api/subtitle-template-sets/${input.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input.patch),
    }),
  );
}

export async function deleteSubtitleTemplateSet(id: string): Promise<void> {
  const response = await fetch(`/api/subtitle-template-sets/${id}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
}

export async function updateSubtitlePresetOverride(input: {
  id: string;
  patch: Partial<SubtitleTemplateSet>;
}): Promise<SubtitleTemplateSet> {
  return readJson(
    await fetch(`/api/subtitle-template-sets/presets/${input.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input.patch),
    }),
  );
}

export async function resetSubtitlePresetOverride(id: string): Promise<void> {
  const response = await fetch(`/api/subtitle-template-sets/presets/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
}

export async function validateSubtitleTemplateSet(
  input: Partial<SubtitleTemplateSet>,
): Promise<{ ok: boolean; normalized: SubtitleTemplateSet | null; warnings: string[] }> {
  return readJson(
    await fetch("/api/subtitle-template-sets/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function previewSubtitleTemplateSet(input: {
  template_set: SubtitleTemplateSet;
  template_type: string;
  aspect_ratio: string;
  sample_text: string;
}): Promise<{ mime_type: string; data: string; resolution: { width: number; height: number }; warnings: string[] }> {
  return readJson(
    await fetch("/api/subtitle-template-sets/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function previewSubtitleTimeline(input: {
  template_set: SubtitleTemplateSet;
  template_type: string;
  aspect_ratio: string;
  sample_text: string;
  duration_ms: number;
}): Promise<{
  mime_type: string;
  data: string;
  duration_ms: number;
  resolution: { width: number; height: number };
  warnings: string[];
}> {
  return readJson(
    await fetch("/api/subtitle-template-sets/preview-timeline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}
```

- [ ] **Step 4: Enable active section navigation**

Modify `frontend/src/App.tsx`:

```typescript
import { useState } from "react";
import { SubtitleTemplateWorkbench } from "./components/SubtitleTemplateWorkbench";
```

Add `id` fields:

```typescript
const navItems = [
  { id: "remix", label: "混剪工作台", shortLabel: "混剪", icon: Clapperboard, enabled: true },
  { id: "materials", label: "素材库", shortLabel: "素材", icon: FolderOpen, enabled: false },
  { id: "subtitles", label: "字幕模板", shortLabel: "字幕", icon: Captions, enabled: true },
  { id: "bgm", label: "BGM 管理", shortLabel: "BGM", icon: Music, enabled: false },
  { id: "voices", label: "音色中心", shortLabel: "音色", icon: Volume2, enabled: false },
  { id: "extract", label: "功能提取处理", shortLabel: "提取", icon: Sparkles, enabled: false },
  { id: "tasks", label: "任务与输出", shortLabel: "任务", icon: SquarePlay, enabled: false },
  { id: "settings", label: "系统设置", shortLabel: "设置", icon: Settings, enabled: false },
];
```

Use state:

```typescript
const [activeSection, setActiveSection] = useState("remix");
```

Render enabled items as links:

```tsx
<a
  aria-current={activeSection === item.id ? "page" : undefined}
  className={activeSection === item.id ? "active" : ""}
  href={`#${item.id}`}
  onClick={(event) => {
    event.preventDefault();
    setActiveSection(item.id);
  }}
  key={item.label}
>
```

Switch content:

```tsx
{activeSection === "remix" ? (
  <section className="content-grid" id="remix">
    <OnlineRemixWorkbench />
    <RuntimeStatus />
  </section>
) : (
  <section className="content-grid single-column" id="subtitles">
    <SubtitleTemplateWorkbench />
  </section>
)}
```

- [ ] **Step 5: Create temporary workbench shell**

Create `frontend/src/components/SubtitleTemplateWorkbench.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";

import { fetchSubtitleTemplateSets } from "../api/subtitles";

export function SubtitleTemplateWorkbench() {
  const templates = useQuery({
    queryKey: ["subtitle-template-sets"],
    queryFn: fetchSubtitleTemplateSets,
  });

  return (
    <article
      aria-label="字幕模板"
      className="panel subtitle-template-workbench"
      data-mobile-layout="stacked-template-preview-editor"
    >
      <div className="panel-heading">
        <h2>字幕模板</h2>
        <div className="status-inline" aria-live="polite">
          <span>{templates.isLoading ? "正在加载模板" : `可用模板 ${(templates.data?.items.length ?? 0) + (templates.data?.presets.length ?? 0)} 个`}</span>
        </div>
      </div>
    </article>
  );
}
```

- [ ] **Step 6: Run test to verify green**

Run:

```bash
cd frontend && npm test -- --run App.test.tsx
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/subtitles.ts frontend/src/App.tsx frontend/src/components/SubtitleTemplateWorkbench.tsx frontend/src/App.test.tsx
git commit -m "feat: enable subtitle template navigation"
```

---

## Task 7: Frontend Template Workbench, Mix Subtitle Settings, Mobile and A11y

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/SubtitleTemplateWorkbench.tsx`
- Modify: `frontend/src/components/OnlineRemixWorkbench.tsx`
- Modify: `frontend/src/api/onlineRemix.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add failing workbench and task option tests**

Add mocked subtitle API constants near the existing API mocks:

```typescript
const mockedCreateSubtitleTemplateSet = vi.mocked(createSubtitleTemplateSet);
const mockedUpdateSubtitleTemplateSet = vi.mocked(updateSubtitleTemplateSet);
const mockedUpdateSubtitlePresetOverride = vi.mocked(updateSubtitlePresetOverride);
const mockedPreviewSubtitleTemplateSet = vi.mocked(previewSubtitleTemplateSet);
const mockedPreviewSubtitleTimeline = vi.mocked(previewSubtitleTimeline);
const mockedValidateSubtitleTemplateSet = vi.mocked(validateSubtitleTemplateSet);
```

Append to `frontend/src/App.test.tsx`:

```typescript
it("creates a custom subtitle template and marks a preset as default", async () => {
  const user = userEvent.setup();
  renderApp();

  await user.click(await screen.findByRole("link", { name: "字幕模板" }));

  expect(await screen.findByRole("button", { name: "设为默认" })).toBeInTheDocument();
  expect(screen.getByLabelText("示例文本")).toBeInTheDocument();
  expect(screen.getAllByLabelText("字体")).toHaveLength(3);
  expect(screen.getAllByLabelText("主色")).toHaveLength(3);
  expect(screen.getByRole("group", { name: "底部字幕" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "强调字幕" })).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "冲击字幕" })).toBeInTheDocument();
  expect(screen.getByLabelText("预览画幅")).toHaveValue("9:16");
  expect(screen.getAllByLabelText("字号比例")).toHaveLength(3);
  expect(screen.getAllByLabelText("描边宽度")).toHaveLength(3);
  expect(screen.getAllByLabelText("阴影强度")).toHaveLength(3);
  expect(screen.getAllByLabelText("垂直位置")).toHaveLength(3);
  expect(screen.getAllByLabelText("最大宽度")).toHaveLength(3);
  expect(screen.getAllByLabelText("旋转")).toHaveLength(3);
  expect(screen.getAllByLabelText("倾斜")).toHaveLength(3);
  expect(screen.getByLabelText("局部关键词")).toBeInTheDocument();
  expect(screen.getByLabelText("局部高亮色")).toBeInTheDocument();
  expect(screen.getByTestId("subtitle-preview-frame")).toHaveStyle({ aspectRatio: "9 / 16" });

  await user.selectOptions(screen.getByLabelText("预览画幅"), "16:9");
  expect(screen.getByTestId("subtitle-preview-frame")).toHaveStyle({ aspectRatio: "16 / 9" });
  await user.click(screen.getByRole("button", { name: "设为默认" }));
  await user.click(screen.getByRole("button", { name: "从预设新建" }));

  expect(mockedCreateSubtitleTemplateSet).toHaveBeenCalledWith({
    name: "我的清晰底部字幕",
    preset_id: "preset-clean-bottom",
  });
  expect(mockedUpdateSubtitlePresetOverride).toHaveBeenCalledWith({
    id: "preset-clean-bottom",
    patch: { is_favorite: true },
  });
});


it("shows subtitle validation warnings near the editor", async () => {
  const user = userEvent.setup();
  mockedValidateSubtitleTemplateSet.mockResolvedValueOnce({
    ok: false,
    normalized: null,
    warnings: ["主色格式无效"],
  });
  renderApp();

  await user.click(await screen.findByRole("link", { name: "字幕模板" }));
  await user.click(screen.getByRole("button", { name: "校验模板" }));

  expect(mockedValidateSubtitleTemplateSet).toHaveBeenCalledWith(
    expect.objectContaining({ id: "preset-clean-bottom" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("主色格式无效");
});


it("renders precise image and timeline previews from the selected template", async () => {
  const user = userEvent.setup();
  renderApp();

  await user.click(await screen.findByRole("link", { name: "字幕模板" }));
  await user.clear(screen.getByLabelText("示例文本"));
  await user.type(screen.getByLabelText("示例文本"), "AI 自动完成重复工作");
  await user.click(screen.getByRole("button", { name: "精准预览" }));
  await user.click(screen.getByRole("button", { name: "时间线预览" }));

  expect(mockedPreviewSubtitleTemplateSet).toHaveBeenCalledWith(
    expect.objectContaining({
      template_type: "bottom",
      aspect_ratio: "9:16",
      sample_text: "AI 自动完成重复工作",
    }),
  );
  expect(mockedPreviewSubtitleTimeline).toHaveBeenCalledWith(
    expect.objectContaining({
      template_type: "bottom",
      duration_ms: 1200,
    }),
  );
  expect(await screen.findByRole("img", { name: "字幕精准预览" })).toHaveAttribute(
    "src",
    expect.stringContaining("data:image/png;base64,"),
  );
  expect(screen.getByTestId("subtitle-timeline-preview")).toHaveAttribute(
    "src",
    expect.stringContaining("data:video/mp4;base64,"),
  );
});


it("keeps subtitle workbench keyboard, loading, error, and mobile semantics accessible", async () => {
  const user = userEvent.setup();
  let resolvePreview: (value: Awaited<ReturnType<typeof previewSubtitleTemplateSet>>) => void;
  mockedPreviewSubtitleTemplateSet.mockReturnValueOnce(
    new Promise((resolve) => {
      resolvePreview = resolve;
    }),
  );
  renderApp();

  await user.click(await screen.findByRole("link", { name: "字幕模板" }));
  const precisePreview = screen.getByRole("button", { name: "精准预览" });
  await user.click(precisePreview);
  expect(precisePreview).toBeDisabled();
  resolvePreview!({
    mime_type: "image/png",
    data: btoa("preview"),
    resolution: { width: 1080, height: 1920 },
    warnings: [],
  });
  expect(await screen.findByRole("img", { name: "字幕精准预览" })).toBeInTheDocument();

  mockedPreviewSubtitleTemplateSet.mockRejectedValueOnce(
    new Error("SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE"),
  );
  await user.click(screen.getByRole("button", { name: "精准预览" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("预览渲染不可用");
  expect(screen.getByRole("region", { name: "字幕模板列表" })).toHaveAttribute(
    "data-mobile-layout",
    "horizontal-scroll-on-mobile",
  );
  expect(screen.getByRole("button", { name: "清晰底部字幕" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  screen.getByRole("button", { name: "精准预览" }).focus();
  await user.tab();
  expect(document.activeElement).toHaveAccessibleName("时间线预览");
});


it("submits subtitle options when creating online mix task", async () => {
  const user = userEvent.setup();
  mockedGenerateScript.mockResolvedValue({
    id: "script-1",
    title: "AI 办公",
    topic: "AI 办公",
    aspect_ratio: "9:16",
    duration_seconds: 5,
    provider: "heuristic",
    created_at: "2026-06-14T00:00:00+00:00",
    shots: [{ index: 1, duration: 5, narration: "旁白", subtitle: "字幕", visual_description: "office", keywords: ["office"] }],
  });
  mockedCreateOnlineMixTask.mockResolvedValue({ id: "task-1", title: "AI 办公", output: { download_url: "/api/tasks/task-1/output" } });
  renderApp();

  await user.type(await screen.findByLabelText("视频主题"), "AI 办公");
  await user.click(screen.getByRole("button", { name: "生成脚本" }));
  await user.selectOptions(await screen.findByLabelText("字幕模板"), "preset-clean-bottom");
  await user.selectOptions(screen.getByLabelText("字幕字体"), "Noto Sans CJK SC");
  expect(screen.getByText("当前模板：清晰底部字幕")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "去字幕模板页编辑" }));
  expect(await screen.findByRole("heading", { name: "字幕模板" })).toBeInTheDocument();
  await user.click(screen.getByRole("link", { name: "混剪工作台" }));
  await user.click(screen.getByRole("button", { name: "创建任务" }));

  expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
    expect.objectContaining({
      options: expect.objectContaining({
        subtitle_enabled: true,
        subtitle_template_set_id: "preset-clean-bottom",
        subtitle_font_family: "Noto Sans CJK SC",
      }),
    }),
  );
});
```

- [ ] **Step 2: Run tests to verify red**

Run:

```bash
cd frontend && npm test -- --run App.test.tsx
```

Expected: fail because editor controls and online mix subtitle settings are not present.

- [ ] **Step 3: Expand subtitle API types**

Modify `frontend/src/api/subtitles.ts`:

```typescript
export async function deleteSubtitleTemplateSet(id: string): Promise<void> {
  const response = await fetch(`/api/subtitle-template-sets/${id}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
}

export async function updateSubtitlePresetOverride(input: {
  id: string;
  patch: Partial<SubtitleTemplateSet>;
}): Promise<SubtitleTemplateSet> {
  return readJson(
    await fetch(`/api/subtitle-template-sets/presets/${input.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input.patch),
    }),
  );
}

export async function resetSubtitlePresetOverride(id: string): Promise<void> {
  const response = await fetch(`/api/subtitle-template-sets/presets/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`HTTP_${response.status}`);
  }
}

export async function validateSubtitleTemplateSet(
  input: Partial<SubtitleTemplateSet>,
): Promise<{ ok: boolean; normalized: SubtitleTemplateSet | null; warnings: string[] }> {
  return readJson(
    await fetch("/api/subtitle-template-sets/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function previewSubtitleTemplateSet(input: {
  template_set: SubtitleTemplateSet;
  template_type: string;
  aspect_ratio: string;
  sample_text: string;
}): Promise<{ mime_type: string; data: string; resolution: { width: number; height: number }; warnings: string[] }> {
  return readJson(
    await fetch("/api/subtitle-template-sets/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function previewSubtitleTimeline(input: {
  template_set: SubtitleTemplateSet;
  template_type: string;
  aspect_ratio: string;
  sample_text: string;
  duration_ms: number;
}): Promise<{
  mime_type: string;
  data: string;
  duration_ms: number;
  resolution: { width: number; height: number };
  warnings: string[];
}> {
  return readJson(
    await fetch("/api/subtitle-template-sets/preview-timeline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}
```

- [ ] **Step 4: Implement workbench editor controls**

Replace `frontend/src/components/SubtitleTemplateWorkbench.tsx` with a stateful workbench that uses real mutations:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CopyPlus, Play, RotateCcw, WandSparkles } from "lucide-react";
import { useMemo, useState } from "react";

import {
  SubtitleTemplateSet,
  createSubtitleTemplateSet,
  fetchSubtitleTemplateSets,
  previewSubtitleTemplateSet,
  previewSubtitleTimeline,
  resetSubtitlePresetOverride,
  updateSubtitlePresetOverride,
  updateSubtitleTemplateSet,
  validateSubtitleTemplateSet,
} from "../api/subtitles";

function isPreset(template: SubtitleTemplateSet | undefined): boolean {
  return Boolean(template?.id.startsWith("preset-"));
}

function styleValue(template: SubtitleTemplateSet | undefined, role: string, key: string, fallback: string): string {
  const style = template?.templates?.[role] ?? {};
  return String(style[key] ?? fallback);
}

function stylePatch(template: SubtitleTemplateSet | undefined, role: string, patch: Record<string, unknown>): Partial<SubtitleTemplateSet> {
  const nextBlocks = (template?.blocks ?? []).map((block) =>
    block.role === role
      ? {
          ...block,
          style: {
            ...(typeof block.style === "object" && block.style !== null ? block.style : {}),
            ...patch,
          },
        }
      : block,
  );
  return {
    templates: {
      ...(template?.templates ?? {}),
      [role]: {
        ...(template?.templates?.[role] ?? {}),
        ...patch,
      },
    },
    blocks: nextBlocks,
  };
}

function previewErrorText(error: unknown): string {
  const code = error instanceof Error ? error.message : "";
  return code === "SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE" ? "预览渲染不可用" : "预览生成失败";
}

export function SubtitleTemplateWorkbench() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sampleText, setSampleText] = useState("AI 自动完成重复工作");
  const [previewAspectRatio, setPreviewAspectRatio] = useState("9:16");
  const [keyword, setKeyword] = useState("AI");
  const [keywordColor, setKeywordColor] = useState("#FFD54F");
  const templates = useQuery({
    queryKey: ["subtitle-template-sets"],
    queryFn: fetchSubtitleTemplateSets,
  });
  const allTemplates = useMemo(
    () => [...(templates.data?.items ?? []), ...(templates.data?.presets ?? [])],
    [templates.data],
  );
  const selected = allTemplates.find((item) => item.id === (selectedId ?? templates.data?.presets[0]?.id));
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["subtitle-template-sets"] });

  const createFromPreset = useMutation({
    mutationFn: () =>
      createSubtitleTemplateSet({
        name: `我的${selected?.name ?? "字幕模板"}`,
        preset_id: selected?.id,
      }),
    onSuccess: (template) => {
      setSelectedId(template.id);
      invalidate();
    },
  });
  const saveTemplate = useMutation({
    mutationFn: (patch: Partial<SubtitleTemplateSet>) =>
      updateSubtitleTemplateSet({ id: String(selected?.id), patch }),
    onSuccess: invalidate,
  });
  const markDefault = useMutation({
    mutationFn: () =>
      isPreset(selected)
        ? updateSubtitlePresetOverride({ id: String(selected?.id), patch: { is_favorite: true } })
        : updateSubtitleTemplateSet({ id: String(selected?.id), patch: { is_favorite: true } }),
    onSuccess: invalidate,
  });
  const resetPreset = useMutation({
    mutationFn: () => resetSubtitlePresetOverride(String(selected?.id)),
    onSuccess: invalidate,
  });
  const validateTemplate = useMutation({
    mutationFn: () => validateSubtitleTemplateSet(selected as SubtitleTemplateSet),
  });
  const precisePreview = useMutation({
    mutationFn: () =>
      previewSubtitleTemplateSet({
        template_set: selected as SubtitleTemplateSet,
        template_type: "bottom",
        aspect_ratio: previewAspectRatio,
        sample_text: sampleText,
      }),
  });
  const timelinePreview = useMutation({
    mutationFn: () =>
      previewSubtitleTimeline({
        template_set: selected as SubtitleTemplateSet,
        template_type: "bottom",
        aspect_ratio: previewAspectRatio,
        sample_text: sampleText,
        duration_ms: 1200,
      }),
  });

  const imagePreviewSrc = precisePreview.data
    ? `data:${precisePreview.data.mime_type};base64,${precisePreview.data.data}`
    : "";
  const timelinePreviewSrc = timelinePreview.data
    ? `data:${timelinePreview.data.mime_type};base64,${timelinePreview.data.data}`
    : "";

  return (
    <article
      aria-label="字幕模板"
      className="panel subtitle-template-workbench"
      data-mobile-layout="stacked-template-preview-editor"
    >
      <div className="panel-heading">
        <h2>字幕模板</h2>
        <div className="status-inline" aria-live="polite">
          <span>{templates.isLoading ? "正在加载模板" : `可用模板 ${allTemplates.length} 个`}</span>
        </div>
      </div>
      <div className="subtitle-workbench-grid">
        <section
          aria-label="字幕模板列表"
          className="subtitle-template-list"
          data-mobile-layout="horizontal-scroll-on-mobile"
        >
          {allTemplates.map((item) => (
            <button
              aria-selected={selected?.id === item.id}
              key={item.id}
              type="button"
              onClick={() => setSelectedId(item.id)}
            >
              <span>{item.name}</span>
              {item.is_favorite || item.favorite ? <strong>默认</strong> : null}
            </button>
          ))}
          <button disabled={!selected || createFromPreset.isPending} type="button" onClick={() => createFromPreset.mutate()}>
            <CopyPlus aria-hidden="true" size={16} />
            从预设新建
          </button>
          <button disabled={!selected || markDefault.isPending} type="button" onClick={() => markDefault.mutate()}>
            <Check aria-hidden="true" size={16} />
            设为默认
          </button>
          <button
            disabled={!isPreset(selected) || resetPreset.isPending}
            type="button"
            onClick={() => resetPreset.mutate()}
          >
            <RotateCcw aria-hidden="true" size={16} />
            还原预设
          </button>
        </section>

        <section className="subtitle-preview-panel" aria-label="字幕预览">
          <label>
            <span>示例文本</span>
            <input value={sampleText} onChange={(event) => setSampleText(event.target.value)} />
          </label>
          <label>
            <span>预览画幅</span>
            <select value={previewAspectRatio} onChange={(event) => setPreviewAspectRatio(event.target.value)}>
              <option value="9:16">9:16</option>
              <option value="16:9">16:9</option>
            </select>
          </label>
          <label>
            <span>局部关键词</span>
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} />
          </label>
          <label>
            <span>局部高亮色</span>
            <input value={keywordColor} onChange={(event) => setKeywordColor(event.target.value)} />
          </label>
          <div
            className="subtitle-preview-frame"
            data-testid="subtitle-preview-frame"
            style={{ aspectRatio: previewAspectRatio === "16:9" ? "16 / 9" : "9 / 16" }}
          >
            <span>{sampleText}</span>
          </div>
          <div className="button-row">
            <button
              disabled={!selected || validateTemplate.isPending}
              type="button"
              onClick={() => validateTemplate.mutate()}
            >
              <Check aria-hidden="true" size={16} />
              校验模板
            </button>
            <button
              disabled={!selected || isPreset(selected) || saveTemplate.isPending}
              type="button"
              onClick={() =>
                saveTemplate.mutate({
                  blocks: (selected?.blocks ?? []).map((block) =>
                    block.role === "bottom"
                      ? {
                          ...block,
                          spans: [
                            ...(Array.isArray(block.spans) ? block.spans : []),
                            {
                              selector: { type: "keyword", value: keyword },
                              style: { primary_color: keywordColor },
                            },
                          ],
                        }
                      : block,
                  ),
                })
              }
            >
              保存局部高亮
            </button>
            <button
              disabled={!selected || precisePreview.isPending}
              type="button"
              onClick={() => precisePreview.mutate()}
            >
              <WandSparkles aria-hidden="true" size={16} />
              精准预览
            </button>
            <button
              disabled={!selected || timelinePreview.isPending}
              type="button"
              onClick={() => timelinePreview.mutate()}
            >
              <Play aria-hidden="true" size={16} />
              时间线预览
            </button>
          </div>
          {imagePreviewSrc ? <img alt="字幕精准预览" src={imagePreviewSrc} /> : null}
          {timelinePreviewSrc ? (
            <video controls data-testid="subtitle-timeline-preview" src={timelinePreviewSrc}>
              <track kind="captions" />
            </video>
          ) : null}
          {validateTemplate.data?.warnings.length ? (
            <p role="alert">{validateTemplate.data.warnings.join("；")}</p>
          ) : null}
          {precisePreview.isError ? <p role="alert">{previewErrorText(precisePreview.error)}</p> : null}
        </section>

        <section className="subtitle-editor-panel" aria-label="字幕块编辑">
          {[
            ["bottom", "底部字幕"],
            ["highlight", "强调字幕"],
            ["punch", "冲击字幕"],
          ].map(([role, label]) => (
            <fieldset key={role}>
              <legend>{label}</legend>
              <label>
                <span>字体</span>
                <select
                  disabled={!selected || isPreset(selected) || saveTemplate.isPending}
                  value={styleValue(selected, role, "font_family", "PingFang SC")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { font_family: event.target.value }))
                  }
                >
                  <option value="PingFang SC">PingFang SC</option>
                  <option value="Noto Sans CJK SC">Noto Sans CJK SC</option>
                </select>
              </label>
              <label>
                <span>主色</span>
                <input
                  disabled={!selected || isPreset(selected) || saveTemplate.isPending}
                  value={styleValue(selected, role, "primary_color", "#FFFFFF")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { primary_color: event.target.value }))
                  }
                />
              </label>
              <label>
                <span>字号比例</span>
                <input
                  disabled={!selected || isPreset(selected) || saveTemplate.isPending}
                  inputMode="decimal"
                  value={styleValue(selected, role, "font_size_scale", "1")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { font_size_scale: Number(event.target.value) || 1 }))
                  }
                />
              </label>
              <label>
                <span>描边宽度</span>
                <input
                  disabled={!selected || isPreset(selected) || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "outline_width", "2")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { outline_width: Number(event.target.value) || 0 }))
                  }
                />
              </label>
              <label>
                <span>阴影强度</span>
                <input
                  disabled={!selected || isPreset(selected) || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "shadow", "0")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { shadow: Number(event.target.value) || 0 }))
                  }
                />
              </label>
              <label>
                <span>垂直位置</span>
                <input
                  disabled={!selected || isPreset(selected) || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "margin_v", "96")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { margin_v: Number(event.target.value) || 0 }))
                  }
                />
              </label>
              <label>
                <span>最大宽度</span>
                <input
                  disabled={!selected || isPreset(selected) || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "max_width", "0.86")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { max_width: Number(event.target.value) || 0.86 }))
                  }
                />
              </label>
              <label>
                <span>旋转</span>
                <input
                  disabled={!selected || isPreset(selected) || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "rotate", "0")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { rotate: Number(event.target.value) || 0 }))
                  }
                />
              </label>
              <label>
                <span>倾斜</span>
                <input
                  disabled={!selected || isPreset(selected) || saveTemplate.isPending}
                  inputMode="numeric"
                  value={styleValue(selected, role, "skew", "0")}
                  onChange={(event) =>
                    saveTemplate.mutate(stylePatch(selected, role, { skew: Number(event.target.value) || 0 }))
                  }
                />
              </label>
            </fieldset>
          ))}
        </section>
      </div>
    </article>
  );
}
```

- [ ] **Step 5: Add online mix subtitle settings**

Modify `frontend/src/App.tsx` so the mix workbench can open the subtitle workbench without depending on hover or a disabled navigation item:

```tsx
<OnlineRemixWorkbench onOpenSubtitleTemplates={() => setActiveSection("subtitles")} />
```

Modify `frontend/src/components/OnlineRemixWorkbench.tsx`:

```typescript
import { fetchSubtitleTemplateSets } from "../api/subtitles";
```

Change the component signature:

```typescript
interface OnlineRemixWorkbenchProps {
  onOpenSubtitleTemplates?: () => void;
}

export function OnlineRemixWorkbench({ onOpenSubtitleTemplates }: OnlineRemixWorkbenchProps) {
```

Add state:

```typescript
const [subtitleEnabled, setSubtitleEnabled] = useState(true);
const [subtitleTemplateSetId, setSubtitleTemplateSetId] = useState("");
const [subtitleFontFamily, setSubtitleFontFamily] = useState("");
const subtitleTemplates = useQuery({
  queryKey: ["subtitle-template-sets"],
  queryFn: fetchSubtitleTemplateSets,
});
```

Add the selected template summary:

```typescript
const subtitleTemplateItems = (subtitleTemplates.data?.items ?? []).concat(
  subtitleTemplates.data?.presets ?? [],
);
const selectedSubtitleTemplate =
  subtitleTemplateItems.find((template) => template.id === subtitleTemplateSetId) ??
  subtitleTemplateItems.find((template) => template.is_favorite || template.favorite) ??
  subtitleTemplateItems[0];
```

In task options:

```typescript
options: {
  aspect_ratio: script.aspect_ratio,
  resolution: "1080p",
  subtitle_enabled: subtitleEnabled,
  subtitle_template_set_id: subtitleEnabled ? subtitleTemplateSetId || null : null,
  subtitle_font_family: subtitleEnabled ? subtitleFontFamily || null : null,
},
```

Render settings after material provider select:

```tsx
<fieldset className="subtitle-settings">
  <legend>字幕设置</legend>
  <label className="switch-row">
    <input
      checked={subtitleEnabled}
      onChange={(event) => setSubtitleEnabled(event.target.checked)}
      type="checkbox"
    />
    <span>启用字幕</span>
  </label>
  <label>
    <span>字幕模板</span>
    <select
      disabled={!subtitleEnabled || subtitleTemplates.isLoading}
      value={subtitleTemplateSetId}
      onChange={(event) => setSubtitleTemplateSetId(event.target.value)}
    >
      <option value="">自动选择默认模板</option>
      {subtitleTemplateItems.map((template) => (
        <option key={template.id} value={template.id}>
          {template.name}
        </option>
      ))}
    </select>
  </label>
  <label>
    <span>字幕字体</span>
    <select
      disabled={!subtitleEnabled}
      value={subtitleFontFamily}
      onChange={(event) => setSubtitleFontFamily(event.target.value)}
    >
      <option value="">跟随字幕模板</option>
      <option value="PingFang SC">PingFang SC</option>
      <option value="Noto Sans CJK SC">Noto Sans CJK SC</option>
    </select>
  </label>
  {subtitleEnabled && selectedSubtitleTemplate ? (
    <p className="subtitle-template-summary">当前模板：{selectedSubtitleTemplate.name}</p>
  ) : null}
  <button type="button" onClick={onOpenSubtitleTemplates}>
    去字幕模板页编辑
  </button>
</fieldset>
```

- [ ] **Step 6: Add responsive styles**

Modify `frontend/src/styles.css`:

```css
.content-grid.single-column {
  grid-template-columns: 1fr;
}

.subtitle-workbench-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 320px;
  gap: 16px;
}

.subtitle-template-list,
.subtitle-preview-panel,
.subtitle-editor-panel,
.subtitle-settings {
  display: grid;
  gap: 12px;
}

.subtitle-template-list button,
.subtitle-preview-panel button,
.subtitle-preview-panel input,
.subtitle-preview-panel select,
.subtitle-editor-panel input,
.subtitle-editor-panel select,
.subtitle-settings input,
.subtitle-settings select {
  min-height: 44px;
}

.subtitle-template-list button,
.subtitle-preview-panel button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.subtitle-template-list button[aria-selected="true"] {
  border-color: var(--accent);
  color: var(--accent-strong);
  font-weight: 700;
}

.subtitle-template-list button:focus-visible,
.subtitle-preview-panel button:focus-visible,
.subtitle-editor-panel input:focus-visible,
.subtitle-editor-panel select:focus-visible,
.subtitle-settings input:focus-visible,
.subtitle-settings select:focus-visible {
  outline: 3px solid var(--accent);
  outline-offset: 2px;
}

.subtitle-template-list button:disabled,
.subtitle-preview-panel button:disabled,
.subtitle-editor-panel input:disabled,
.subtitle-editor-panel select:disabled,
.subtitle-settings input:disabled,
.subtitle-settings select:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.subtitle-preview-frame {
  aspect-ratio: 9 / 16;
  width: min(100%, 280px);
  display: grid;
  place-items: end center;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #111827;
  color: #ffffff;
  padding: 20px;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.subtitle-settings {
  grid-column: 1 / -1;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
}

.subtitle-template-summary {
  margin: 0;
  color: var(--muted);
  font-size: 0.92rem;
}

.subtitle-preview-panel img,
.subtitle-preview-panel video {
  width: min(100%, 280px);
  border-radius: 8px;
  border: 1px solid var(--line);
}

.switch-row {
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 10px;
}

@media (max-width: 1024px) {
  .subtitle-workbench-grid {
    grid-template-columns: 1fr;
  }

  .subtitle-template-list {
    grid-auto-flow: column;
    grid-auto-columns: minmax(152px, max-content);
    overflow-x: auto;
    padding-bottom: 4px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .subtitle-template-workbench *,
  .subtitle-settings * {
    animation-duration: 1ms !important;
    transition-duration: 1ms !important;
  }
}
```

- [ ] **Step 7: Run frontend tests and build**

Run:

```bash
cd frontend && npm test -- --run App.test.tsx
cd frontend && npm run build
```

Expected: tests and build pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/subtitles.ts frontend/src/components/SubtitleTemplateWorkbench.tsx frontend/src/components/OnlineRemixWorkbench.tsx frontend/src/api/onlineRemix.ts frontend/src/styles.css frontend/src/App.test.tsx
git commit -m "feat: add subtitle controls to frontend"
```

---

## Task 8: Documentation, Full Verification, and Smoke Test

**Files:**
- Modify: `README.md`
- Test: existing backend and frontend test suites

- [ ] **Step 1: Update README**

Modify `README.md` current stage and API sections. Include this content under current stage:

```markdown
- 字幕模板管理 API 和字幕模板工作台
- 线上混剪任务支持 `subtitle_enabled`、`subtitle_template_set_id`、`subtitle_template_snapshot` 和 `subtitle_font_family`
- 字幕启用时任务目录保留 `subtitles.ass`；FFmpeg 可用时烧录为最终 `output.mp4`
- local/hybrid 素材疑似自带字幕时会遮挡底部源字幕区域，避免和生成字幕叠加
```

Update output artifact paragraph:

```markdown
线上混剪任务会在 FFmpeg 可用时输出 `output.mp4`，并在同一任务目录保留 `manifest.json`、`timeline.json`、`subtitles.srt` 和启用字幕时的 `subtitles.ass`；启用字幕时还会保留 `output.base.mp4` 便于排查烧录前的视频。FFmpeg 不可用时仍会保留 manifest、timeline、SRT 和 ASS 字幕文件，并在 `manifest.render_plan` 中记录 `base_video_skipped` 和 `subtitle_burn_skipped`。
```

Add API bullet:

```markdown
- `GET /api/subtitle-template-sets`：返回自定义模板组和内置预设。
- `POST /api/subtitle-template-sets`：从预设或已有模板复制创建自定义模板组。
- `PUT /api/subtitle-template-sets/{id}`：保存模板组字段、DSL v2 blocks、`is_favorite` 默认模板标记。
- `DELETE /api/subtitle-template-sets/{id}`：删除自定义模板组；内置预设不能通过该接口删除。
- `PUT /api/subtitle-template-sets/presets/{id}`：保存内置预设的本地覆盖项，例如默认模板标记。
- `DELETE /api/subtitle-template-sets/presets/{id}`：清除内置预设覆盖项并恢复出厂预设。
- `POST /api/subtitle-template-sets/validate`：校验并归一字幕模板。
- `POST /api/subtitle-template-sets/preview`：生成精准预览；FFmpeg/libass 不可用时返回 `SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE`。
- `POST /api/subtitle-template-sets/preview-timeline`：生成 0.5-5 秒时间线预览短视频，返回 base64 MP4。
```

- [ ] **Step 2: Run full backend tests**

Run:

```bash
pytest
```

Expected: all tests pass.

- [ ] **Step 3: Run full frontend tests and build**

Run:

```bash
cd frontend && npm test -- --run
cd frontend && npm run build
```

Expected: all tests and build pass.

- [ ] **Step 4: Run FFmpeg smoke when available**

Run:

```bash
python - <<'PY'
import shutil
from pathlib import Path
print(shutil.which("ffmpeg") or "FFMPEG_NOT_FOUND")
PY
```

If output is a path, run a one-shot API smoke with real FFmpeg:

```bash
python - <<'PY'
from fastapi.testclient import TestClient
from tempfile import TemporaryDirectory
from pathlib import Path
from autovideo.api.app import create_app
from autovideo.core.settings import Settings

script = {
    "id": "script-smoke",
    "title": "AI 办公",
    "topic": "AI 办公",
    "aspect_ratio": "9:16",
    "duration_seconds": 1,
    "provider": "heuristic",
    "created_at": "2026-06-17T00:00:00+00:00",
    "shots": [{"index": 1, "duration": 1, "narration": "AI 提升效率", "subtitle": "AI 提升效率", "visual_description": "office", "keywords": ["AI"]}],
}

with TemporaryDirectory() as tmp:
    app = create_app(Settings(_env_file=None, data_dir=Path(tmp), ffmpeg_path="ffmpeg"))
    with TestClient(app) as client:
        material = client.post("/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}).json()
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "smoke",
                "script": script,
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {"subtitle_enabled": True, "subtitle_template_snapshot": template, "subtitle_template_set_id": template["id"]},
            },
        )
        print(response.status_code)
        print(response.json().get("detail", response.json()).get("code", "OK"))
PY
```

Expected: either `201` for a valid generated test clip or a documented FFmpeg decode failure if fake bytes are not accepted. If decode fails, record that automated tests with fake FFmpeg covered command behavior and real FFmpeg rejected the synthetic input.

- [ ] **Step 5: Verify mobile layout with browser automation**

Run the frontend dev server:

```bash
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
```

Use Playwright or in-app browser inspection at widths `375`, `768`, and `1024`. Verify:

```javascript
document.documentElement.scrollWidth <= window.innerWidth
```

Expected at each width:

- The enabled `混剪` and `字幕` mobile tabs are visible without horizontal scrolling.
- Template preview keeps `9 / 16` ratio.
- Buttons and inputs are at least `44px` high.
- Focus ring is visible when tabbing through controls.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: document subtitle system"
```

---

## Final Verification Before PR

- [ ] Run backend suite:

```bash
pytest
```

- [ ] Run frontend suite:

```bash
cd frontend && npm test -- --run
```

- [ ] Run frontend build:

```bash
cd frontend && npm run build
```

- [ ] Confirm staged and committed files:

```bash
git status --short
git log --oneline origin/main..HEAD
```

- [ ] Run the repository-required local review loop before push:

Use `superpowers:requesting-code-review` with:

- Spec: `docs/superpowers/specs/2026-06-17-subtitle-system-design.md`
- Plan: `docs/superpowers/plans/2026-06-17-subtitle-system.md`
- Uncommitted diff if any: `git diff HEAD --`
- Branch diff: `git diff origin/main..HEAD`
- Test output summaries from the three commands above

Only push and create or update a PR after local review has no actionable findings.
