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
