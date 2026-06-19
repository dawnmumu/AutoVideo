import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, get_ident

import pytest

from autovideo.core.settings import Settings
from autovideo.services.subtitles import template_store

TARGET_PRESET_ID = "bold_yellow"


def _store(tmp_path):
    return template_store.SubtitleTemplateStore(Settings(_env_file=None, data_dir=tmp_path))


def test_list_template_presets_returns_editable_normalized_items(tmp_path):
    store = _store(tmp_path)

    presets = store.list_presets()

    assert presets
    assert len(presets) == 20
    assert presets[0]["id"] == TARGET_PRESET_ID
    assert presets[-1]["id"] == "duo_language_stack"
    assert presets[0]["schema_version"] == 2
    assert {block["role"] for block in presets[0]["blocks"]} >= {"bottom", "highlight", "punch"}
    assert presets[0]["is_modified"] is False
    assert presets[0]["templates"]["bottom"]["font_family"] == "Noto Sans CJK SC"
    assert presets[0]["templates"]["bottom"]["font_weight"] == 800
    assert presets[1]["templates"]["bottom"]["font_weight"] == 700
    assert presets[1]["templates"]["bottom"]["italic"] is False
    assert presets[1]["templates"]["bottom"]["letter_spacing"] == 0
    assert presets[1]["templates"]["bottom"]["line_spacing"] == 1.15
    assert presets[1]["templates"]["bottom"]["margin_l"] == 60
    assert presets[1]["templates"]["bottom"]["margin_r"] == 60
    assert presets[1]["templates"]["bottom"]["margin_v"] == 80
    assert presets[1]["templates"]["bottom"]["max_chars_per_line"] == 16
    assert presets[1]["templates"]["bottom"]["max_lines"] == 3
    assert presets[1]["templates"]["bottom"]["fade_in_ms"] == 80
    assert presets[1]["templates"]["bottom"]["fade_out_ms"] == 80
    assert presets[0]["templates"]["punch"]["font_size_scale"] == 1.16
    assert presets[2]["templates"]["highlight"]["position"] == "bottom"
    assert presets[2]["templates"]["highlight"]["y_percent"] == 60
    assert presets[3]["templates"]["punch"]["angle"] == -4
    assert presets[3]["templates"]["punch"]["rotate"] == -4
    assert presets[7]["blocks"][0]["position"]["anchor"] == "left"
    assert presets[17]["templates"]["bottom"]["skew_x_deg"] == 10
    assert presets[17]["templates"]["bottom"]["skew_y_deg"] == -3
    assert presets[17]["templates"]["bottom"]["max_width_ratio"] == 0.58
    assert presets[0]["blocks"][2]["spans"][0]["selector"] == {"type": "range", "start": 0, "end": 2}


def test_create_update_and_delete_custom_template_set(tmp_path):
    store = _store(tmp_path)

    created = store.create_template_set("我的字幕", preset_id=TARGET_PRESET_ID)
    updated = store.update_template_set(
        created["id"],
        {
            "name": "更新字幕",
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

    assert updated["name"] == "更新字幕"
    assert updated["is_favorite"] is True
    assert store.get_template_set(created["id"])["name"] == "更新字幕"
    assert json.loads(store.store_path.read_text(encoding="utf-8"))["items"]

    store.delete_template_set(created["id"])

    with pytest.raises(KeyError):
        store.get_template_set(created["id"])


def test_select_auto_template_set_ignores_favorite_and_uses_sort_key(tmp_path):
    store = _store(tmp_path)
    old = store.create_template_set("旧模板", preset_id=TARGET_PRESET_ID)
    new = store.create_template_set("新模板", preset_id=TARGET_PRESET_ID)
    store.update_template_set(old["id"], {"is_favorite": True, "updated_at": "2026-01-01T00:00:00+00:00"})
    store.update_template_set(new["id"], {"is_favorite": False, "updated_at": "2026-02-01T00:00:00+00:00"})

    selected = store.select_auto_template_set()

    assert selected["id"] == new["id"]


def test_preset_override_preserves_favorite_metadata_without_affecting_auto_selection(tmp_path):
    store = _store(tmp_path)

    updated = store.update_preset("clean_white", {"is_favorite": True, "name": "收藏预设"})
    selected = store.select_auto_template_set()

    assert updated["is_favorite"] is True
    assert selected["id"] == TARGET_PRESET_ID


def test_with_template_variants_collects_custom_sets_and_all_default_presets(tmp_path):
    store = _store(tmp_path)
    custom = store.create_template_set("我的随机字幕", preset_id=TARGET_PRESET_ID)

    enriched = store.with_template_variants(store.select_auto_template_set())

    for role in ("bottom", "highlight", "punch"):
        role_variants = enriched["template_variants"][role]
        variant_ids = {variant["id"] for variant in role_variants}
        assert custom["id"] in variant_ids
        assert TARGET_PRESET_ID in variant_ids
        assert "duo_language_stack" in variant_ids
        assert len(role_variants) >= 21
        assert all(isinstance(variant.get("blocks"), list) for variant in role_variants)
        assert all(isinstance(variant.get("template"), dict) for variant in role_variants)


def test_corrupt_store_json_raises_domain_error_without_overwriting(tmp_path):
    store = _store(tmp_path)
    store.store_path.parent.mkdir(parents=True)
    store.store_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(template_store.SubtitleTemplateStoreError, match="Invalid subtitle template store JSON"):
        store.list_template_sets()

    assert store.store_path.read_text(encoding="utf-8") == "{not-json"


def test_create_template_set_serializes_same_path_mutations(tmp_path, monkeypatch):
    setup_store = _store(tmp_path)
    source = setup_store.create_template_set("源模板", preset_id=TARGET_PRESET_ID)
    original_load = template_store.SubtitleTemplateStore._load
    per_thread_loads = {}
    ready = Event()
    state_lock = Lock()
    mutation_loads = 0

    def slow_second_load(self):
        nonlocal mutation_loads
        data = original_load(self)
        thread_id = get_ident()

        with state_lock:
            per_thread_loads[thread_id] = per_thread_loads.get(thread_id, 0) + 1
            should_wait = per_thread_loads[thread_id] >= 2
            if should_wait:
                mutation_loads += 1
                if mutation_loads == 2:
                    ready.set()

        if should_wait:
            ready.wait(timeout=0.2)

        return data

    monkeypatch.setattr(template_store.SubtitleTemplateStore, "_load", slow_second_load)

    store_a = _store(tmp_path)
    store_b = _store(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(store_a.create_template_set, "并发模板 A", source_id=source["id"]),
            executor.submit(store_b.create_template_set, "并发模板 B", source_id=source["id"]),
        ]
        created = [future.result() for future in futures]

    items = _store(tmp_path).list_template_sets()

    assert {item["id"] for item in created}.issubset({item["id"] for item in items})
    assert len(items) == 3


def test_store_rejects_invalid_dsl_validation_result(tmp_path, monkeypatch):
    store = _store(tmp_path)

    monkeypatch.setattr(
        template_store.dsl_v2,
        "validate_template_set_v2",
        lambda item: {"ok": False, "normalized": None, "warnings": ["payload must be an object"]},
    )

    with pytest.raises(template_store.SubtitleTemplateStoreError, match="Invalid subtitle template set"):
        store._normalize_template_set_item({"id": "bad-template"})


def test_invalid_template_variants_are_normalized_before_persisting(tmp_path):
    store = _store(tmp_path)
    created = store.create_template_set("变体模板", preset_id=TARGET_PRESET_ID)

    updated = store.update_template_set(created["id"], {"template_variants": ["bad"]})
    persisted = json.loads(store.store_path.read_text(encoding="utf-8"))["items"][0]

    assert updated["template_variants"] == {}
    assert isinstance(persisted["template_variants"], dict)
    assert persisted["template_variants"] == {}
