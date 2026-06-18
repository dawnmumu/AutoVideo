from __future__ import annotations

from collections.abc import Iterable
import copy
import json
import os
import secrets
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autovideo.core.settings import Settings
from autovideo.services.subtitles import dsl_v2, template_presets
from autovideo.services.subtitles.models import TEMPLATE_ROLES

METADATA_KEYS = (
    "created_at",
    "updated_at",
    "is_builtin",
    "is_modified",
    "is_favorite",
    "favorite",
)

_STORE_LOCKS_GUARD = threading.Lock()
_STORE_LOCKS: dict[Path, threading.RLock] = {}


class SubtitleTemplateStoreError(RuntimeError):
    pass


class SubtitleTemplateStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store_path = settings.resolved_data_dir / "subtitle_templates" / "subtitle_template_sets.json"

    def list_presets(self) -> list[dict[str, Any]]:
        data = self._load()
        overrides = data["preset_overrides"]
        presets: list[dict[str, Any]] = []

        for preset in template_presets.list_presets():
            preset_id = preset["id"]
            merged = self._merge_dicts(preset, overrides.get(preset_id, {}))
            merged["is_builtin"] = True
            merged["is_modified"] = preset_id in overrides
            presets.append(self._normalize_template_set_item(merged))

        return presets

    def list_template_sets(self) -> list[dict[str, Any]]:
        return [self._normalize_template_set_item(item) for item in self._load()["items"] if isinstance(item, dict)]

    def get_template_set(self, template_id: str) -> dict[str, Any]:
        for item in self.list_template_sets():
            if item.get("id") == template_id:
                return copy.deepcopy(item)

        for preset in self.list_presets():
            if preset.get("id") == template_id:
                return copy.deepcopy(preset)

        raise KeyError(template_id)

    def create_template_set(
        self,
        name: str,
        *,
        preset_id: str | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        if (preset_id is None) == (source_id is None):
            raise ValueError("Exactly one of preset_id or source_id is required")

        with self._mutation_lock():
            source = self._get_preset(preset_id) if preset_id else self.get_template_set(source_id or "")
            now = _utc_now()
            item = copy.deepcopy(source)
            item["id"] = f"tmpl-{secrets.token_hex(6)}"
            item["name"] = name
            item["created_at"] = now
            item["updated_at"] = now
            item.pop("is_builtin", None)
            item.pop("is_modified", None)
            if preset_id:
                item["preset_id"] = preset_id

            normalized = self._normalize_template_set_item(item)
            data = self._load()
            data["items"].append(normalized)
            self._write(data)
            return copy.deepcopy(normalized)

    def update_template_set(self, template_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._mutation_lock():
            data = self._load()
            for index, item in enumerate(data["items"]):
                if isinstance(item, dict) and item.get("id") == template_id:
                    merged = self._merge_dicts(item, patch)
                    merged["id"] = template_id
                    if "updated_at" not in patch:
                        merged["updated_at"] = _utc_now()
                    normalized = self._normalize_template_set_item(merged)
                    data["items"][index] = normalized
                    self._write(data)
                    return copy.deepcopy(normalized)

        raise KeyError(template_id)

    def update_preset(self, preset_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._mutation_lock():
            current = self._get_preset(preset_id)
            merged = self._merge_dicts(current, patch)
            merged["id"] = preset_id
            merged["is_builtin"] = True
            merged["is_modified"] = True
            if "updated_at" not in patch:
                merged["updated_at"] = _utc_now()

            normalized = self._normalize_template_set_item(merged)
            data = self._load()
            data["preset_overrides"][preset_id] = normalized
            self._write(data)
            return copy.deepcopy(normalized)

    def delete_template_set(self, template_id: str) -> None:
        with self._mutation_lock():
            data = self._load()
            filtered = [item for item in data["items"] if not (isinstance(item, dict) and item.get("id") == template_id)]
            if len(filtered) == len(data["items"]):
                raise KeyError(template_id)
            data["items"] = filtered
            self._write(data)

    def reset_preset(self, preset_id: str) -> dict[str, Any]:
        with self._mutation_lock():
            self._get_preset_base(preset_id)
            data = self._load()
            data["preset_overrides"].pop(preset_id, None)
            self._write(data)
            return self._get_preset_base(preset_id)

    def with_template_variants(self, template_set: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_template_set_item(template_set)
        normalized["template_variants"] = self._build_template_variant_pool(normalized)
        return normalized

    def select_auto_template_set(self) -> dict[str, Any]:
        custom = self.list_template_sets()
        favorite_custom = [item for item in custom if _is_favorite(item)]
        if favorite_custom:
            return copy.deepcopy(_sort_for_selection(favorite_custom)[0])
        if custom:
            return copy.deepcopy(_sort_for_selection(custom)[0])

        presets = self.list_presets()
        favorite_presets = [item for item in presets if _is_favorite(item)]
        if favorite_presets:
            return copy.deepcopy(_sort_for_selection(favorite_presets)[0])
        if presets:
            return copy.deepcopy(presets[0])

        raise KeyError("No subtitle templates available")

    def _load(self) -> dict[str, Any]:
        if not self.store_path.exists():
            return {"items": [], "preset_overrides": {}}

        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SubtitleTemplateStoreError(f"Invalid subtitle template store JSON: {self.store_path}") from exc

        if not isinstance(data, dict):
            raise SubtitleTemplateStoreError(f"Subtitle template store must contain a JSON object: {self.store_path}")

        items = data.get("items") if isinstance(data.get("items"), list) else []
        overrides = data.get("preset_overrides") if isinstance(data.get("preset_overrides"), dict) else {}
        return {"items": items, "preset_overrides": overrides}

    def _write(self, data: dict[str, Any]) -> None:
        payload = {
            "items": data.get("items") if isinstance(data.get("items"), list) else [],
            "preset_overrides": data.get("preset_overrides") if isinstance(data.get("preset_overrides"), dict) else {},
        }
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = Path(f"{self.store_path}.{secrets.token_hex(8)}.tmp")
        try:
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(temp_path, self.store_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _get_preset(self, preset_id: str | None) -> dict[str, Any]:
        if preset_id is None:
            raise KeyError(preset_id)
        for preset in self.list_presets():
            if preset.get("id") == preset_id:
                return copy.deepcopy(preset)
        raise KeyError(preset_id)

    def _get_preset_base(self, preset_id: str) -> dict[str, Any]:
        for preset in template_presets.list_presets():
            if preset.get("id") == preset_id:
                item = copy.deepcopy(preset)
                item["is_builtin"] = True
                item["is_modified"] = False
                return self._normalize_template_set_item(item)
        raise KeyError(preset_id)

    def _normalize_template_set_item(self, item: dict[str, Any]) -> dict[str, Any]:
        result = dsl_v2.validate_template_set_v2(item)
        if not result.get("ok") or not isinstance(result.get("normalized"), dict):
            warnings = "; ".join(result.get("warnings") or [])
            detail = f": {warnings}" if warnings else ""
            raise SubtitleTemplateStoreError(f"Invalid subtitle template set{detail}")

        normalized = result["normalized"]

        for key in METADATA_KEYS:
            if key in item:
                normalized[key] = copy.deepcopy(item[key])
        if isinstance(item.get("template_variants"), dict):
            normalized["template_variants"] = copy.deepcopy(item["template_variants"])

        return normalized

    def _mutation_lock(self) -> threading.RLock:
        return _store_lock_for_path(self.store_path)

    def _build_template_variant_pool(self, base_template_set: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        pool: dict[str, list[dict[str, Any]]] = {role: [] for role in TEMPLATE_ROLES}
        seen: dict[str, set[str]] = {role: set() for role in TEMPLATE_ROLES}

        _append_existing_variant_pool(pool, seen, base_template_set.get("template_variants"))
        _append_template_set_variants(pool, seen, base_template_set)
        for candidate in self.list_template_sets():
            _append_template_set_variants(pool, seen, candidate)
        for candidate in self.list_presets():
            _append_template_set_variants(pool, seen, candidate)

        return pool

    @staticmethod
    def _merge_dicts(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = copy.deepcopy(base)
        for key, value in patch.items():
            merged[key] = copy.deepcopy(value)
        return merged


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _store_lock_for_path(path: Path) -> threading.RLock:
    with _STORE_LOCKS_GUARD:
        lock = _STORE_LOCKS.get(path)
        if lock is None:
            lock = threading.RLock()
            _STORE_LOCKS[path] = lock
        return lock


def _is_favorite(item: dict[str, Any]) -> bool:
    return bool(item.get("is_favorite") or item.get("favorite"))


def _append_existing_variant_pool(
    pool: dict[str, list[dict[str, Any]]],
    seen: dict[str, set[str]],
    raw_variants: Any,
) -> None:
    if not isinstance(raw_variants, dict):
        return

    for role in TEMPLATE_ROLES:
        raw_items = raw_variants.get(role)
        if isinstance(raw_items, dict):
            raw_items = raw_items.values()
        if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Iterable):
            continue

        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            _append_template_variant(
                pool,
                seen,
                role,
                raw_item.get("id") or raw_item.get("key") or raw_item.get("name"),
                raw_item.get("name"),
                raw_item.get("template"),
                raw_item.get("blocks"),
            )


def _append_template_set_variants(
    pool: dict[str, list[dict[str, Any]]],
    seen: dict[str, set[str]],
    template_set: dict[str, Any],
) -> None:
    result = dsl_v2.validate_template_set_v2(template_set)
    normalized = result.get("normalized")
    if not result.get("ok") or not isinstance(normalized, dict):
        return

    template_set_id = str(normalized.get("id") or normalized.get("name") or "").strip()
    if not template_set_id:
        template_set_id = f"template-set-{sum(len(items) for items in pool.values()) + 1}"
    template_set_name = str(normalized.get("name") or template_set_id).strip()
    templates = normalized.get("templates") if isinstance(normalized.get("templates"), dict) else {}
    blocks = normalized.get("blocks") if isinstance(normalized.get("blocks"), list) else []

    for role in TEMPLATE_ROLES:
        role_blocks = [copy.deepcopy(block) for block in blocks if isinstance(block, dict) and block.get("role") == role]
        template = templates.get(role)
        _append_template_variant(pool, seen, role, template_set_id, template_set_name, template, role_blocks)


def _append_template_variant(
    pool: dict[str, list[dict[str, Any]]],
    seen: dict[str, set[str]],
    role: str,
    variant_id: Any,
    variant_name: Any,
    template: Any,
    blocks: Any,
) -> None:
    clean_id = str(variant_id or "").strip()
    if not clean_id or clean_id in seen[role]:
        return

    clean_blocks = copy.deepcopy(blocks) if isinstance(blocks, list) else []
    clean_template = copy.deepcopy(template) if isinstance(template, dict) else None
    if not clean_blocks and clean_template is not None:
        clean_blocks = [_legacy_template_block(role, clean_template)]
    if not clean_blocks and clean_template is None:
        return

    seen[role].add(clean_id)
    item: dict[str, Any] = {
        "id": clean_id,
        "name": str(variant_name or clean_id).strip(),
        "blocks": clean_blocks,
    }
    if clean_template is not None:
        item["template"] = clean_template
    pool[role].append(item)


def _legacy_template_block(role: str, template: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"{role}-{str(template.get('id') or 'variant')}",
        "role": role,
        "track_id": "main",
        "position": _position_for_template(template),
        "style": copy.deepcopy(template),
        "spans": [],
        "animations": {},
    }


def _position_for_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "x": _percent_to_ratio(template.get("x_percent"), 0.5),
        "y": _percent_to_ratio(template.get("y_percent"), _fallback_y_for_position(template.get("position"))),
        "anchor": _anchor_from_alignment(template.get("alignment")),
    }


def _percent_to_ratio(value: Any, fallback: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return fallback
    return max(0, min(1, float(value) / 100))


def _fallback_y_for_position(value: Any) -> float:
    position = str(value or "").strip()
    if position == "upper":
        return 0.25
    if position == "center":
        return 0.5
    return 0.78


def _anchor_from_alignment(value: Any) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in {"left", "center", "right"} else "center"


def _sort_for_selection(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (str(item.get("updated_at") or ""), str(item.get("created_at") or ""), str(item.get("id") or "")),
        reverse=True,
    )
