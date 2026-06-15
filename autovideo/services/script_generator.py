from __future__ import annotations

import json
import math
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


SYSTEM_PROMPT = """你是 AutoVideo 的专业短视频分镜脚本编剧。用户会给你一个产品、主题或已写好的脚本文案，你需要生成一份结构化的分镜脚本。

要求：
1. 每个镜头包含：旁白文本、字幕文本、画面描述、搜索关键词、delivery 朗读控制
2. 旁白要简洁有力，适合 TTS 朗读；如果用户提供 script_text，尽量保留用户原文表达
3. 字幕用于屏幕烧录显示，默认可等于旁白，也允许比旁白更短或表达不同
4. 画面描述要具体，便于素材匹配和线上免费视频搜索
5. 关键词用于搜索相关素材，返回 3-5 个简洁词或短语
6. 所有镜头时长之和要接近目标总时长
7. 主题生成时采用：开场吸引 → 痛点/需求 → 产品亮点(1-3个) → 行动号召

请严格按以下 JSON 格式输出，不要包含任何其他文字：
{
  "title": "视频标题",
  "total_duration": 总时长秒数,
  "shots": [
    {
      "index": 1,
      "duration": 秒数,
      "narration": "旁白文本",
      "subtitle": "字幕文本",
      "visual_description": "画面描述",
      "keywords": ["关键词1", "关键词2", "关键词3"],
      "delivery": {
        "style": "natural",
        "emotion": null,
        "emotion_scale": 3,
        "speech_rate": 0,
        "loudness_rate": 0,
        "pause_profile": "normal"
      }
    }
  ]
}"""

CUSTOM_SCRIPT_SYSTEM_PROMPT = """你是一个专业的短视频分镜编辑助手。用户会给你一份已经写好的脚本、口播稿或文案，请你把它整理成适合视频生成的结构化分镜脚本。

要求：
1. 尽量保留用户原有文案语气和表达，不要偏题
2. 自动拆分为 6-12 个短镜头，镜头节奏适合短视频
3. 每个镜头必须包含：旁白文本、字幕文本、画面描述、搜索关键词、时长、delivery 朗读控制
4. 如果原文缺少画面信息，你要补充适合检索素材的视觉描述
5. subtitle 用于屏幕字幕，默认可等于 narration，也可以为了可读性更短或与旁白不同
6. 时长要按原文自然节奏估算，不要为了凑固定时长而压缩内容
7. 只输出 JSON，不要输出解释

请严格按以下 JSON 格式输出，不要包含任何其他文字：
{
  "title": "视频标题",
  "total_duration": 总时长秒数,
  "shots": [
    {
      "index": 1,
      "duration": 秒数,
      "narration": "旁白文本",
      "subtitle": "字幕文本",
      "visual_description": "画面描述",
      "keywords": ["关键词1", "关键词2"],
      "delivery": {
        "style": "natural",
        "emotion": null,
        "emotion_scale": 3,
        "speech_rate": 0,
        "loudness_rate": 0,
        "pause_profile": "normal"
      }
    }
  ]
}"""

PLAIN_TEXT_ENRICH_SYSTEM_PROMPT = """你是短视频分镜补全助手。用户会给你一个标题/主题，以及一组已经定稿的旁白句子。

你的任务只是在不改动原句的前提下，为每一句补充屏幕字幕、画面描述和关键词。

硬性要求：
1. narration 必须与用户提供的原句逐字一致，不能改写、合并、拆分、增删。
2. subtitle 用于屏幕字幕，可以等于 narration，也可以为了可读性更短或与旁白不同。
3. 每句都要补充一个具体的 visual_description，便于检索视频素材。
4. 每句都要补充 3-5 个 keywords。
5. keywords 要优先提炼：标题主题词、场景词、人物/物体词、动作词、结果词。
6. keywords 不能只是把整句旁白原样拆碎，不要给相邻句返回几乎完全一样的一组词。
7. 关键词要适合视频素材搜索，尽量使用简洁短词或短短语。
8. 每句都要返回 delivery 朗读控制。
9. 只输出 JSON，不要输出解释。

请严格按以下 JSON 格式输出：
{
  "title": "视频标题",
  "shots": [
    {
      "index": 1,
      "narration": "原句",
      "subtitle": "屏幕字幕",
      "visual_description": "画面描述",
      "keywords": ["关键词1", "关键词2", "关键词3"],
      "delivery": {
        "style": "natural",
        "emotion": null,
        "emotion_scale": 3,
        "speech_rate": 0,
        "loudness_rate": 0,
        "pause_profile": "normal"
      }
    }
  ]
}"""

SHOT_HEADER_RE = re.compile(r"^镜头\s*(\d+)(?:\s*[（(]([0-9]+(?:\.[0-9]+)?)\s*秒[）)])?\s*$")
TIME_SEPARATOR_RE = r"[:：]"
TIME_TOKEN_RE = rf"(?:[0-9]+(?:{TIME_SEPARATOR_RE}[0-9]{{1,2}}){{1,3}}(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"
TIME_RANGE_HEADER_RE = re.compile(
    rf"^({TIME_TOKEN_RE})\s*(?:-|~|–|—)\s*({TIME_TOKEN_RE})\s*秒?(?:(?:\s*[|｜]\s*|\s+)(.*?))?\s*$"
)
NUMBER_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)")
KEYWORD_SPLIT_RE = re.compile(r"[，,、/\s|]+")
STRONG_PAUSE_RE = re.compile(r"[。！？!?；;]")
WEAK_PAUSE_RE = re.compile(r"[，,、：:]")
NON_SPOKEN_RE = re.compile(r"[。！？!?；;，,、：:\s“”\"'‘’（）()【】《》<>]")
SPOKEN_CONTENT_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaffA-Za-z0-9\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]"
)
SENTENCE_SPLIT_RE = re.compile(r"[^。！？!?；;\n]+(?:[。！？!?；;]+|$)")
KEYWORD_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,16}")

GENERIC_KEYWORD_STOPWORDS = {
    "自定义脚本视频",
    "视频脚本",
    "脚本视频",
    "视频",
    "画面",
    "镜头",
    "素材",
    "内容",
    "展示",
    "介绍",
    "场景",
    "相关",
    "相关画面",
    "一下",
    "一种",
    "一些",
    "这个",
    "那个",
    "这里",
    "现在",
    "真的",
    "非常",
    "已经",
    "就是",
    "可以",
    "我们",
    "你们",
    "他们",
    "自己",
}

PLACEHOLDER_TITLES = {
    "自定义脚本视频",
    "视频脚本",
    "脚本视频",
    "自定义脚本",
}

QUESTION_KEYWORD_HINTS = {
    "什么",
    "怎么",
    "为什么",
    "为何",
    "吗",
    "呢",
    "是不是",
    "有没有",
}

LOW_SIGNAL_KEYWORD_PREFIXES = (
    "首先",
    "然后",
    "接着",
    "最后",
    "我们来",
    "我说",
    "你说",
    "你会",
    "你脑子",
    "大家来",
)


class NarrationDelivery(BaseModel):
    style: str = "natural"
    emotion: str | None = None
    emotion_scale: float = Field(3.0, ge=1.0, le=5.0)
    speech_rate: int = Field(0, ge=-50, le=100)
    loudness_rate: int = Field(0, ge=-50, le=100)
    pitch: int | None = Field(None, ge=-12, le=12)
    pause_profile: str = "normal"
    voice_instruction: str | None = None
    context_reference: str | None = None
    voice_tag: str | None = None
    ssml: str | None = None


class SceneShot(BaseModel):
    index: int
    duration: float = Field(..., gt=0)
    narration: str
    subtitle: str = ""
    visual_description: str
    keywords: list[str] = Field(default_factory=list)
    delivery: NarrationDelivery | None = Field(default_factory=NarrationDelivery)


class VideoScript(BaseModel):
    title: str
    total_duration: float
    shots: list[SceneShot]


class ScriptTextInvalidError(ValueError):
    pass


def has_spoken_content(text: str) -> bool:
    return bool(SPOKEN_CONTENT_RE.search(str(text or "")))


def _count_spoken_content_chars(text: str) -> int:
    return len(SPOKEN_CONTENT_RE.findall(str(text or "")))


def extract_json_content(content: str) -> str:
    cleaned = (content or "").strip()
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
    return cleaned


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        number = float(value)
    except Exception:
        return default
    if not math.isfinite(number):
        return default
    return number


def _parse_strict_finite_number(value: Any, *, field: str) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            token = value.strip().replace("：", ":")
            if not re.fullmatch(TIME_TOKEN_RE, value.strip()):
                raise ValueError
            if ":" not in token:
                number = float(token)
            else:
                parts = token.split(":")
                if len(parts) not in (2, 3, 4) or any(part == "" for part in parts):
                    raise ValueError
                values = [float(part) for part in parts]
                if any(not math.isfinite(item) or item < 0 for item in values):
                    raise ValueError
                if len(values) == 2:
                    minutes, seconds = values
                    number = minutes * 60 + seconds
                elif len(values) == 3:
                    hours, minutes, seconds = values
                    number = hours * 3600 + minutes * 60 + seconds
                else:
                    hours, minutes, seconds, _frames = values
                    number = hours * 3600 + minutes * 60 + seconds
        else:
            raise ValueError
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"镜头 {field} 必须是有限数字") from exc

    if not math.isfinite(number):
        raise ValueError(f"镜头 {field} 必须是有限数字")
    return number


def _parse_positive_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("必须是正整数")
    if isinstance(value, int):
        resolved = value
    elif isinstance(value, float) and value.is_integer():
        resolved = int(value)
    elif isinstance(value, str) and re.fullmatch(r"[1-9]\d*", value.strip()):
        resolved = int(value.strip())
    else:
        raise ValueError("必须是正整数")
    if resolved <= 0:
        raise ValueError("必须是正整数")
    return resolved


def format_seconds(value: float) -> str:
    rounded = round(float(value or 0), 1)
    if abs(rounded - int(rounded)) < 0.05:
        return str(int(rounded))
    return f"{rounded:.1f}".rstrip("0").rstrip(".")


def _split_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = [str(item).strip() for item in value]
    elif isinstance(value, str):
        parts = [part.strip() for part in KEYWORD_SPLIT_RE.split(value)]
    else:
        parts = []

    seen: set[str] = set()
    results: list[str] = []
    for part in parts:
        if not part or part in seen:
            continue
        seen.add(part)
        results.append(part)
    return results[:6]


def _extract_plain_sentences(script_text: str) -> list[str]:
    normalized = (script_text or "").replace("\r\n", "\n").replace("\r", "\n")
    sentences: list[str] = []

    for block in normalized.split("\n"):
        cleaned_block = block.strip()
        if not cleaned_block:
            continue
        for match in SENTENCE_SPLIT_RE.finditer(cleaned_block):
            sentence = match.group(0).strip()
            if sentence and has_spoken_content(sentence):
                sentences.append(sentence)

    return sentences


def _normalize_keyword_text(value: Any) -> str:
    text = str(value or "").strip()
    text = text.strip(" ,，。、；;！？!?()（）[]【】“”\"'《》<>")
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_compare_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"[\s,，。、；;！？!?()（）\[\]【】“”\"'《》<>:：\-]+", "", text)


def _is_placeholder_title(value: Any) -> bool:
    normalized = _normalize_compare_text(value)
    return normalized in {_normalize_compare_text(item) for item in PLACEHOLDER_TITLES}


def _is_low_signal_keyword_token(value: Any) -> bool:
    token = _normalize_keyword_text(value)
    compare_token = _normalize_compare_text(token)
    if not token or not compare_token:
        return True
    if len(compare_token) < 2 or len(compare_token) > 24:
        return True
    if compare_token.isdigit():
        return True
    if token in GENERIC_KEYWORD_STOPWORDS or _is_placeholder_title(token):
        return True
    if any(hint in compare_token for hint in QUESTION_KEYWORD_HINTS):
        return True
    low_signal_prefixes = tuple(_normalize_compare_text(item) for item in LOW_SIGNAL_KEYWORD_PREFIXES)
    return compare_token.startswith(low_signal_prefixes)


def _extract_keyword_candidates(text: str) -> list[str]:
    if not text:
        return []

    quoted_terms = re.findall(r"[“\"'「『](.{1,12}?)[”\"'」』]", str(text))
    normalized = (
        str(text)
        .replace("：", " ")
        .replace(":", " ")
        .replace("？", " ")
        .replace("?", " ")
        .replace("！", " ")
        .replace("!", " ")
        .replace("“", " ")
        .replace("”", " ")
        .replace('"', " ")
        .replace("'", " ")
        .replace("（", " ")
        .replace("）", " ")
        .replace("(", " ")
        .replace(")", " ")
    )

    candidates: list[str] = []
    candidates.extend(quoted_terms)
    candidates.extend(part for part in KEYWORD_SPLIT_RE.split(normalized))
    candidates.extend(match.group(0) for match in KEYWORD_TOKEN_RE.finditer(normalized))

    results: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        token = _normalize_keyword_text(item)
        if not token or token in seen:
            continue
        if token.lower() in {"http", "https"} or _is_low_signal_keyword_token(token):
            continue
        compare_token = _normalize_compare_text(token)
        seen.add(token)
        seen.add(compare_token)
        results.append(token)
    return results


def _is_low_quality_visual_description(
    visual_description: str,
    narration: str,
    title: str = "",
) -> bool:
    visual = _normalize_compare_text(visual_description)
    narration_text = _normalize_compare_text(narration)
    title_text = _normalize_compare_text(title)

    if not visual:
        return True
    if visual == narration_text:
        return True
    if title_text and visual in {title_text, f"{title_text}相关画面"}:
        return True
    return len(visual) < 6


def _is_low_quality_keywords(
    keywords: Any,
    narration: str,
    title: str = "",
) -> bool:
    parsed_keywords = [_normalize_keyword_text(item) for item in _split_keywords(keywords)]
    parsed_keywords = [item for item in parsed_keywords if item]
    if len(parsed_keywords) < 2:
        return True

    narration_text = _normalize_compare_text(narration)
    title_text = _normalize_compare_text(title)
    direct_phrase_hits = 0
    meaningful_keywords = 0

    for item in parsed_keywords:
        normalized_item = _normalize_compare_text(item)
        if not normalized_item:
            continue
        if _is_placeholder_title(item):
            return True
        if normalized_item == title_text and _is_placeholder_title(title):
            return True
        if item not in GENERIC_KEYWORD_STOPWORDS:
            meaningful_keywords += 1
        if normalized_item and normalized_item in narration_text:
            direct_phrase_hits += 1

    if meaningful_keywords < 2:
        return True
    return direct_phrase_hits >= max(2, len(parsed_keywords) - 1)


def _build_fallback_visual_description(title: str, narration: str) -> str:
    focus_terms = _extract_keyword_candidates(title)
    if not focus_terms:
        focus_terms = _extract_keyword_candidates(narration)

    primary = focus_terms[0] if focus_terms else ""
    secondary = focus_terms[1] if len(focus_terms) > 1 else ""

    if primary and secondary:
        return f"{primary}相关场景，{secondary}动作特写"
    if primary:
        return f"{primary}相关场景，人物反应特写"
    if title and not _is_placeholder_title(title):
        return f"{title}相关场景"
    return "人物场景与动作特写"


def build_search_keywords(
    title: str,
    narration: str,
    visual_description: str = "",
    seed_keywords: Any | None = None,
) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()

    def add_candidates(items: list[str]) -> None:
        for item in items:
            token = _normalize_keyword_text(item)
            if not token or token in seen:
                continue
            if _is_low_signal_keyword_token(token):
                continue
            seen.add(token)
            results.append(token)
            if len(results) >= 5:
                return

    if seed_keywords:
        add_candidates(_split_keywords(seed_keywords))
        if len(results) >= 2:
            return results[:5]
    if len(results) < 5 and title and not _is_placeholder_title(title):
        add_candidates([title])
    if len(results) < 5:
        add_candidates(_extract_keyword_candidates(title))
    if len(results) < 5:
        add_candidates(_extract_keyword_candidates(visual_description))
    if len(results) < 5:
        add_candidates(_extract_keyword_candidates(narration))

    if not results:
        fallback_title = _normalize_keyword_text(title)
        if 2 <= len(fallback_title) <= 12:
            results.append(fallback_title)
        else:
            results.extend(["产品", "展示"])

    return results[:5]


def _resolve_subtitle(value: Any, narration: str) -> str:
    if isinstance(value, dict):
        raw = (
            value.get("subtitle")
            or value.get("subtitle_text")
            or value.get("caption")
            or value.get("on_screen_text")
            or value.get("description")
            or value.get("shot_description")
        )
    else:
        raw = getattr(value, "subtitle", None)
        if raw is None:
            raw = getattr(value, "subtitle_text", None)
        if raw is None:
            raw = getattr(value, "caption", None)
        if raw is None:
            raw = getattr(value, "on_screen_text", None)
    return str(raw if raw is not None else narration or "").strip()


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _guess_keywords(*texts: str) -> list[str]:
    title = texts[-1] if texts else ""
    narration = texts[0] if texts else ""
    visual_description = texts[1] if len(texts) > 1 else ""
    return build_search_keywords(title, narration, visual_description)


def build_delivery_for_narration(narration: str, style: str | None = None) -> NarrationDelivery:
    text = (narration or "").strip()
    resolved_style = (style or "").strip() or "natural"
    emotion = None
    emotion_scale = 3.0
    speech_rate = 0
    loudness_rate = 0
    pause_profile = "normal"

    dramatic_terms = ("反转", "真相", "崩了", "震惊", "关键", "必须")
    gentle_terms = ("安心", "温柔", "慢慢", "陪你")

    if resolved_style == "energetic":
        speech_rate = 12
        loudness_rate = 8
        emotion = "happy"
        emotion_scale = 3.5
    elif resolved_style == "professional":
        speech_rate = -6
        emotion = "neutral"
    elif resolved_style == "dramatic" or any(term in text for term in dramatic_terms):
        resolved_style = "dramatic"
        speech_rate = 6
        loudness_rate = 10
        emotion = "surprised"
        emotion_scale = 4.0
        pause_profile = "dramatic"
    elif resolved_style == "gentle" or any(term in text for term in gentle_terms):
        resolved_style = "gentle"
        speech_rate = -8
        loudness_rate = -6
        emotion = "neutral"

    return NarrationDelivery(
        style=resolved_style,
        emotion=emotion,
        emotion_scale=emotion_scale,
        speech_rate=speech_rate,
        loudness_rate=loudness_rate,
        pause_profile=pause_profile,
    )


def estimate_narration_duration(text: str) -> float:
    cleaned = (text or "").strip()
    if not cleaned:
        return 1.5

    strong_pause = len(STRONG_PAUSE_RE.findall(cleaned))
    weak_pause = len(WEAK_PAUSE_RE.findall(cleaned))
    spoken_chars = _count_spoken_content_chars(cleaned)

    base_duration = spoken_chars / 4.2
    duration = base_duration + (strong_pause * 0.45) + (weak_pause * 0.18) + 0.8
    return round(max(duration, 1.5), 1)


def _resolve_shot_duration(shot: SceneShot) -> float:
    explicit = _safe_float(getattr(shot, "duration", 0), 0.0)
    if explicit > 0:
        return round(max(explicit, 1.0), 1)
    return estimate_narration_duration(getattr(shot, "narration", ""))


def _calculate_total_duration(shot_durations: list[float]) -> float:
    if not shot_durations:
        return 0.0
    return round(sum(shot_durations), 1)


def normalize_script(
    title: str,
    shots: list[SceneShot],
    target_duration: float | None = None,
    *,
    scale_to_target: bool = True,
    preserve_indexes: bool = False,
) -> VideoScript:
    valid_shots = [
        shot
        for shot in shots
        if (shot.narration or "").strip()
        and has_spoken_content((shot.narration or "").strip())
    ]
    if not valid_shots:
        raise ValueError("脚本中没有可用镜头")

    resolved_title = (title or "").strip() or "视频脚本"
    base_durations = [_resolve_shot_duration(shot) for shot in valid_shots]
    normalized_target = _safe_float(target_duration, 0.0)

    if scale_to_target and normalized_target > 0:
        source_total = sum(base_durations) or len(base_durations)
        shot_durations = [
            max(round(item * normalized_target / source_total, 1), 1.0)
            for item in base_durations
        ]
        duration_delta = round(normalized_target - sum(shot_durations), 1)
        if shot_durations:
            shot_durations[-1] = max(round(shot_durations[-1] + duration_delta, 1), 1.0)
    else:
        shot_durations = base_durations[:]

    normalized_shots: list[SceneShot] = []
    for index, (shot, duration_value) in enumerate(zip(valid_shots, shot_durations), start=1):
        narration = (shot.narration or "").strip()
        subtitle = _resolve_subtitle(shot, narration) or narration
        visual_description = (shot.visual_description or "").strip() or narration or f"{resolved_title} 相关画面"
        keywords = build_search_keywords(
            resolved_title,
            narration,
            visual_description,
            shot.keywords,
        )
        shot_index = int(getattr(shot, "index", 0) or index) if preserve_indexes else index
        normalized_shots.append(
            SceneShot(
                index=shot_index,
                duration=duration_value,
                narration=narration,
                subtitle=subtitle,
                visual_description=visual_description,
                keywords=keywords,
                delivery=shot.delivery or build_delivery_for_narration(narration),
            )
        )

    return VideoScript(
        title=resolved_title,
        total_duration=_calculate_total_duration([shot.duration for shot in normalized_shots]),
        shots=normalized_shots,
    )


def _enrich_plain_text_script_with_llm(parts: list[str], topic: str) -> VideoScript | None:
    return None


def _build_plain_text_script_heuristic(parts: list[str], topic: str) -> VideoScript:
    resolved_topic = (topic or "").strip() or "自定义脚本视频"
    shots: list[SceneShot] = []

    for index, part in enumerate(parts, start=1):
        visual_description = _build_fallback_visual_description(resolved_topic, part)
        shots.append(
            SceneShot(
                index=index,
                duration=estimate_narration_duration(part),
                narration=part,
                subtitle=part,
                visual_description=visual_description,
                keywords=build_search_keywords(
                    resolved_topic,
                    part,
                    visual_description,
                ),
                delivery=build_delivery_for_narration(part),
            )
        )

    return normalize_script(resolved_topic, shots, scale_to_target=False)


def _repair_structured_script_metadata(
    script: VideoScript,
    topic: str | None = None,
    *,
    force: bool = False,
) -> VideoScript:
    if not script.shots:
        return script

    resolved_title = (topic or "").strip() or (script.title or "").strip() or "自定义脚本视频"
    needs_repair = force or any(
        _is_low_quality_visual_description(shot.visual_description, shot.narration, resolved_title)
        or _is_low_quality_keywords(shot.keywords, shot.narration, resolved_title)
        for shot in script.shots
    )
    if not needs_repair:
        return normalize_script(script.title or resolved_title, script.shots, scale_to_target=False)

    fallback_shots: list[SceneShot] = []
    final_title = (script.title or resolved_title).strip() or resolved_title
    for index, shot in enumerate(script.shots, start=1):
        use_existing_visual = not (
            force
            or _is_low_quality_visual_description(
                shot.visual_description,
                shot.narration,
                final_title,
            )
        )
        visual_description = (shot.visual_description or "").strip() if use_existing_visual else ""
        if not visual_description:
            visual_description = _build_fallback_visual_description(final_title, shot.narration)

        seed_keywords = None if (
            force or _is_low_quality_keywords(shot.keywords, shot.narration, final_title)
        ) else shot.keywords
        fallback_shots.append(
            SceneShot(
                index=index,
                duration=_resolve_shot_duration(shot),
                narration=shot.narration,
                subtitle=_resolve_subtitle(shot, shot.narration),
                visual_description=visual_description,
                keywords=build_search_keywords(
                    final_title,
                    shot.narration,
                    visual_description,
                    seed_keywords,
                ),
                delivery=shot.delivery or build_delivery_for_narration(shot.narration),
            )
        )

    return normalize_script(final_title, fallback_shots, scale_to_target=False)


def build_script_from_data(
    data: dict[str, Any],
    *,
    fallback_title: str,
    target_duration: float | None = None,
    scale_to_target: bool = False,
    strict: bool = False,
) -> VideoScript:
    shots_data = data.get("shots")
    if not isinstance(shots_data, list) or not shots_data:
        raise ValueError("脚本缺少 shots")

    parsed_shots: list[SceneShot] = []
    for index, item in enumerate(shots_data, start=1):
        if not isinstance(item, dict):
            if strict:
                raise ValueError("镜头必须是对象")
            continue

        _validate_explicit_text_fields(
            item,
            "narration",
            "voiceover",
            "voice_over",
            "audio_cue",
            "subtitle",
            "caption",
            "description",
            "shot_description",
            "visual_description",
            "visual",
            "scene",
            strict=strict,
        )
        _validate_explicit_number_fields(
            item,
            "duration",
            "start_time",
            "end_time",
            strict=strict,
        )
        narration = _first_text(item, "narration", "voiceover", "voice_over", "audio_cue")
        if not narration:
            if strict:
                raise ValueError("镜头缺少可朗读旁白")
            continue
        if strict and not has_spoken_content(narration):
            raise ValueError("镜头缺少可朗读旁白")
        subtitle = _resolve_subtitle(item, narration)
        visual_description = _first_text(
            item,
            "visual_description",
            "description",
            "shot_description",
            "visual",
            "scene",
        )
        raw_duration = item.get("duration")
        if isinstance(raw_duration, bool):
            raise ValueError("镜头 duration 不能是 bool")
        duration = (
            _parse_time_range_value(raw_duration)
            if isinstance(raw_duration, str)
            else _safe_float(raw_duration, 0.0)
        )
        duration = duration or 0.0
        if duration <= 0:
            raw_start_time = item.get("start_time")
            raw_end_time = item.get("end_time")
            start_time = (
                _parse_time_range_value(raw_start_time)
                if isinstance(raw_start_time, str)
                else _safe_float(raw_start_time, 0.0)
            )
            end_time = (
                _parse_time_range_value(raw_end_time)
                if isinstance(raw_end_time, str)
                else _safe_float(raw_end_time, 0.0)
            )
            start_time = start_time or 0.0
            end_time = end_time or 0.0
            if end_time > start_time:
                duration = round(end_time - start_time, 1)
        raw_keywords = item.get("keywords")
        if strict:
            _validate_keywords(raw_keywords, present="keywords" in item)
        elif isinstance(raw_keywords, list) and any(not isinstance(keyword, str) for keyword in raw_keywords):
            raise ValueError("镜头 keywords 必须是字符串列表")
        keywords = _split_keywords(raw_keywords)
        delivery = item.get("delivery")
        if isinstance(delivery, NarrationDelivery):
            delivery_model = delivery
        elif isinstance(delivery, dict):
            delivery_model = NarrationDelivery(**delivery)
        elif strict and "delivery" in item and delivery is not None:
            raise ValueError("镜头 delivery 必须是对象")
        else:
            delivery_model = build_delivery_for_narration(narration)

        parsed_shots.append(
            SceneShot(
                index=_parse_positive_int(item.get("index") or item.get("shot_id") or index),
                duration=duration or estimate_narration_duration(narration),
                narration=narration,
                subtitle=subtitle,
                visual_description=visual_description,
                keywords=keywords,
                delivery=delivery_model,
            )
        )

    _validate_explicit_number_fields(
        data,
        "total_duration",
        strict=strict,
    )
    explicit_total = _safe_float(data.get("total_duration"), 0.0)
    normalize_target = (
        target_duration
        if scale_to_target and _safe_float(target_duration, 0.0) > 0
        else explicit_total
    )
    return normalize_script(
        str(data.get("title") or fallback_title or "视频脚本"),
        parsed_shots,
        normalize_target,
        scale_to_target=bool(normalize_target and normalize_target > 0),
    )


def _validate_explicit_text_fields(
    item: dict[str, Any],
    *fields: str,
    strict: bool,
) -> None:
    if not strict:
        return
    for field in fields:
        value = item.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"镜头 {field} 必须是字符串")


def _validate_keywords(value: Any, *, present: bool) -> None:
    if not present or value is None:
        return
    if isinstance(value, str):
        return
    if isinstance(value, list) and all(isinstance(keyword, str) for keyword in value):
        return
    raise ValueError("镜头 keywords 必须是字符串或字符串列表")


def _validate_explicit_number_fields(
    item: dict[str, Any],
    *fields: str,
    strict: bool,
) -> None:
    if not strict:
        return
    for field in fields:
        value = item.get(field)
        if value is None:
            continue
        _parse_strict_finite_number(value, field=field)


def try_parse_json_script(
    script_text: str,
    *,
    fallback_title: str,
    scale_to_target: bool = False,
    target_duration: float | None = None,
) -> VideoScript | None:
    try:
        data = json.loads(extract_json_content(script_text))
    except Exception:
        return None

    if not isinstance(data, dict) or not data.get("shots"):
        return None

    return build_script_from_data(
        data,
        fallback_title=fallback_title,
        target_duration=target_duration,
        scale_to_target=scale_to_target,
    )


def _is_no_usable_script_error(exc: ValueError) -> bool:
    return str(exc) in {"脚本中没有可用内容", "脚本中没有可用镜头"}


def _parse_duration_line(value: str) -> float | None:
    match = NUMBER_RE.search(value or "")
    return _safe_float(match.group(1), 0.0) if match else None


def _parse_time_range_value(value: str) -> float | None:
    token = (value or "").strip().replace("：", ":")
    if not token:
        return None
    if ":" not in token:
        return _safe_float(token, 0.0)

    parts = token.split(":")
    if len(parts) not in (2, 3, 4) or any(part == "" for part in parts):
        return None
    try:
        values = [float(part) for part in parts]
    except ValueError:
        return None
    if any(item < 0 for item in values):
        return None
    if len(values) == 2:
        minutes, seconds = values
        return minutes * 60 + seconds
    if len(values) == 3:
        hours, minutes, seconds = values
        return hours * 3600 + minutes * 60 + seconds
    hours, minutes, seconds, _frames = values
    return hours * 3600 + minutes * 60 + seconds


def parse_editor_script(
    script_text: str,
    *,
    fallback_title: str,
) -> VideoScript | None:
    title = (fallback_title or "").strip() or "视频脚本"
    explicit_total: float | None = None
    shots: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_field: str | None = None
    skip_implicit_until_next_header = False

    def field_value(value: str) -> str:
        return value.split("：", 1)[1].strip() if "：" in value else value.split(":", 1)[1].strip()

    narration_prefixes = ("旁白：", "旁白:", "口播：", "口播:")
    subtitle_prefixes = ("字幕：", "字幕:", "屏幕字幕：", "屏幕字幕:")
    visual_prefixes = ("画面：", "画面:", "镜头画面：", "镜头画面:")
    keyword_prefixes = ("关键词：", "关键词:")
    implicit_shot_prefixes = narration_prefixes + subtitle_prefixes + visual_prefixes + keyword_prefixes

    def new_current(duration: float = 0.0) -> dict[str, Any]:
        return {
            "duration": duration,
            "narration": "",
            "subtitle": "",
            "visual_description": "",
            "keywords": [],
        }

    def flush_current() -> None:
        nonlocal current
        if not current:
            return
        narration = str(current.get("narration") or "").strip()
        if narration and has_spoken_content(narration):
            shots.append(current)
        current = None

    for raw_line in script_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith(("标题：", "标题:")):
            title = field_value(line)
            continue

        if line.startswith(("总时长：", "总时长:", "时长：", "时长:")):
            explicit_total = _parse_duration_line(line)
            continue

        shot_match = SHOT_HEADER_RE.match(line)
        if shot_match:
            flush_current()
            skip_implicit_until_next_header = False
            current = {
                "index": int(shot_match.group(1)),
                "duration": _safe_float(shot_match.group(2), 0.0),
                "narration": "",
                "subtitle": "",
                "visual_description": "",
                "keywords": [],
            }
            current_field = None
            continue

        time_range_match = TIME_RANGE_HEADER_RE.match(line)
        if time_range_match:
            flush_current()
            start_seconds = _parse_time_range_value(time_range_match.group(1))
            end_seconds = _parse_time_range_value(time_range_match.group(2))
            if start_seconds is None or end_seconds is None or end_seconds <= start_seconds:
                current = None
                current_field = None
                skip_implicit_until_next_header = True
                continue
            skip_implicit_until_next_header = False
            current = new_current(round(end_seconds - start_seconds, 1))
            current["_time_start"] = start_seconds
            current["_time_end"] = end_seconds
            current_field = None
            continue

        if line.startswith(("屏幕字幕结尾：", "屏幕字幕结尾:", "字幕结尾：", "字幕结尾:")):
            current_field = "ignored"
            continue

        if current is None and not skip_implicit_until_next_header and line.startswith(implicit_shot_prefixes):
            current = new_current()
            current_field = None

        if current is None:
            continue

        if line.startswith(narration_prefixes):
            current["narration"] = field_value(line)
            current_field = "narration"
            continue

        if line.startswith(subtitle_prefixes):
            current["subtitle"] = field_value(line)
            current_field = "subtitle"
            continue

        if line.startswith(visual_prefixes):
            current["visual_description"] = field_value(line)
            current_field = "visual_description"
            continue

        if line.startswith(keyword_prefixes):
            current["keywords"] = _split_keywords(field_value(line))
            current_field = "keywords"
            continue

        if current_field in {"narration", "subtitle", "visual_description"}:
            current[current_field] = f"{current[current_field]} {line}".strip()
        elif current_field == "keywords":
            current["keywords"] = _split_keywords(" ".join(current.get("keywords", [])) + " " + line)

    flush_current()

    if not shots:
        return None

    parsed_shots: list[SceneShot] = []
    time_range_start: float | None = None
    time_range_end: float | None = None
    for index, item in enumerate(shots, start=1):
        narration = str(item.get("narration") or "").strip()
        if not narration or not has_spoken_content(narration):
            continue
        shot_time_start = item.get("_time_start")
        shot_time_end = item.get("_time_end")
        if isinstance(shot_time_start, (int, float)) and isinstance(shot_time_end, (int, float)):
            time_range_start = (
                float(shot_time_start)
                if time_range_start is None
                else min(time_range_start, float(shot_time_start))
            )
            time_range_end = (
                float(shot_time_end)
                if time_range_end is None
                else max(time_range_end, float(shot_time_end))
            )
        parsed_shots.append(
            SceneShot(
                index=int(item.get("index") or index),
                duration=_safe_float(item.get("duration"), 0.0) or estimate_narration_duration(narration),
                narration=narration,
                subtitle=str(item.get("subtitle") or narration).strip(),
                visual_description=str(item.get("visual_description") or "").strip(),
                keywords=_split_keywords(item.get("keywords")),
                delivery=build_delivery_for_narration(narration),
            )
        )

    if not parsed_shots:
        return None

    inferred_total = None
    if explicit_total is None and time_range_start is not None and time_range_end is not None:
        inferred_total = round(max(time_range_end - time_range_start, 0.0), 1)
    normalize_target = explicit_total if explicit_total is not None else inferred_total

    return normalize_script(
        title,
        parsed_shots,
        normalize_target,
        scale_to_target=bool(normalize_target and normalize_target > 0),
        preserve_indexes=True,
    )


def _build_plain_text_script(script_text: str, topic: str) -> VideoScript:
    parts = [
        part.strip(" -•\t")
        for part in _extract_plain_sentences(script_text)
        if part.strip(" -•\t")
    ]
    if not parts:
        raise ScriptTextInvalidError("脚本中没有可用内容")

    semantic_script = _enrich_plain_text_script_with_llm(parts, topic)
    if semantic_script:
        return semantic_script

    return _build_plain_text_script_heuristic(parts, topic)


def generate_fallback_script(
    topic: str,
    duration: int,
    selling_points: list[str] | None = None,
) -> VideoScript:
    resolved_topic = (topic or "").strip()
    resolved_selling_points = [
        str(item).strip()
        for item in (selling_points or [])
        if str(item).strip()
    ]
    seg = max(round(duration / 4, 1), 1.0)
    first_narration = f"你还在为{resolved_topic}烦恼吗？" if resolved_topic else "你还在为这个问题烦恼吗？"
    highlight_text = "、".join(resolved_selling_points[:3])
    second_narration = (
        f"试试这款{resolved_topic}，{highlight_text}，效果超乎想象"
        if resolved_topic and highlight_text
        else f"试试这款{resolved_topic}，效果超乎想象"
        if resolved_topic
        else f"试试这款产品，{highlight_text}，效果超乎想象"
        if highlight_text
        else "试试这款产品，效果超乎想象"
    )
    feature_keywords = [resolved_topic, *resolved_selling_points] if resolved_topic else resolved_selling_points
    return VideoScript(
        title=resolved_topic or "视频脚本",
        total_duration=duration,
        shots=[
            SceneShot(
                index=1,
                duration=seg,
                narration=first_narration,
                subtitle=first_narration,
                visual_description="产品特写",
                keywords=_guess_keywords(resolved_topic or "产品", "特写"),
                delivery=build_delivery_for_narration(first_narration),
            ),
            SceneShot(
                index=2,
                duration=seg,
                narration=second_narration,
                subtitle=second_narration,
                visual_description="使用场景",
                keywords=build_search_keywords(
                    resolved_topic or "产品",
                    second_narration,
                    "使用场景",
                    feature_keywords,
                ),
                delivery=build_delivery_for_narration(second_narration),
            ),
            SceneShot(
                index=3,
                duration=seg,
                narration="天然成分，温和不刺激，适合日常使用",
                subtitle="天然成分，温和不刺激，适合日常使用",
                visual_description="成分展示",
                keywords=_guess_keywords("天然成分", "温和", "展示"),
                delivery=build_delivery_for_narration("天然成分，温和不刺激，适合日常使用"),
            ),
            SceneShot(
                index=4,
                duration=seg,
                narration="点击下方链接，立即体验！",
                subtitle="点击下方链接，立即体验！",
                visual_description="品牌收尾和行动号召",
                keywords=_guess_keywords("品牌", "购买", "行动号召"),
                delivery=build_delivery_for_narration("点击下方链接，立即体验！"),
            ),
        ],
    )


def optimize_script_text(
    script_text: str,
    topic: str | None = None,
    max_single_duration: float | None = None,
) -> dict[str, Any]:
    cleaned_script = (script_text or "").strip()
    resolved_topic = (topic or "").strip() or "自定义脚本视频"
    if not cleaned_script:
        raise ValueError("脚本不能为空")

    try:
        script = try_parse_json_script(
            cleaned_script,
            fallback_title=resolved_topic,
        )
        if not script:
            script = parse_editor_script(
                cleaned_script,
                fallback_title=resolved_topic,
            )
        if not script:
            script = _build_plain_text_script(cleaned_script, resolved_topic)
        else:
            script = _repair_structured_script_metadata(script, resolved_topic, force=False)
    except ScriptTextInvalidError:
        raise
    except ValueError as exc:
        if _is_no_usable_script_error(exc):
            raise ScriptTextInvalidError("脚本中没有可用内容") from exc
        raise

    analysis = analyze_script(script, max_single_duration)
    return {
        "script": script,
        "script_text": format_script_for_editor(script),
        "analysis": analysis,
    }


def _split_script_for_preview(
    script: VideoScript,
    max_single_duration: float | None = None,
) -> list[dict[str, Any]]:
    if not script.shots:
        return []

    max_limit = _safe_float(max_single_duration, 0.0)
    segments: list[dict[str, Any]] = []
    current_shots: list[SceneShot] = []
    current_durations: list[float] = []
    current_start = 1

    for index, shot in enumerate(script.shots, start=1):
        shot_duration = _resolve_shot_duration(shot)
        proposed_durations = current_durations + [shot_duration]
        proposed_total = round(sum(proposed_durations), 1)

        if current_shots and max_limit > 0 and proposed_total > max_limit + 0.05:
            segments.append(
                {
                    "segment_index": len(segments) + 1,
                    "shot_range_start": current_start,
                    "shot_range_end": current_start + len(current_shots) - 1,
                    "shot_count": len(current_shots),
                    "duration": round(sum(current_durations), 1),
                }
            )
            current_shots = []
            current_durations = []
            current_start = index

        current_shots.append(shot)
        current_durations.append(shot_duration)

    if current_shots:
        segments.append(
            {
                "segment_index": len(segments) + 1,
                "shot_range_start": current_start,
                "shot_range_end": current_start + len(current_shots) - 1,
                "shot_count": len(current_shots),
                "duration": round(sum(current_durations), 1),
            }
        )

    return segments


def analyze_script(
    script: VideoScript,
    max_single_duration: float | None = None,
) -> dict[str, Any]:
    segments = _split_script_for_preview(script, max_single_duration)
    return {
        "title": script.title,
        "shot_count": len(script.shots),
        "total_duration": round(float(script.total_duration or 0), 1),
        "max_single_duration": _safe_float(max_single_duration, 0.0) or None,
        "segment_count": len(segments) or 1,
        "segments": segments,
    }


def analyze_script_text(
    script_text: str,
    topic: str | None = None,
    max_single_duration: float | None = None,
) -> dict[str, Any]:
    cleaned_script = (script_text or "").strip()
    resolved_topic = (topic or "").strip() or "自定义脚本视频"
    if not cleaned_script:
        raise ValueError("自定义脚本不能为空")

    try:
        script = try_parse_json_script(
            cleaned_script,
            fallback_title=resolved_topic,
        )
        if not script:
            script = parse_editor_script(
                cleaned_script,
                fallback_title=resolved_topic,
            )
        if not script:
            script = _build_plain_text_script(cleaned_script, resolved_topic)
        else:
            script = _repair_structured_script_metadata(script, resolved_topic, force=False)
    except ScriptTextInvalidError:
        raise
    except ValueError as exc:
        if _is_no_usable_script_error(exc):
            raise ScriptTextInvalidError("脚本中没有可用内容") from exc
        raise

    return {
        "script": script,
        "script_text": format_script_for_editor(script),
        "analysis": analyze_script(script, max_single_duration),
    }


def format_script_for_editor(script: VideoScript) -> str:
    lines = [
        f"标题：{script.title}",
        f"总时长：{format_seconds(script.total_duration)}秒",
        "",
    ]

    for shot in script.shots:
        lines.extend(
            [
                f"镜头{shot.index}（{format_seconds(shot.duration)}秒）",
                f"旁白：{shot.narration}",
                f"字幕：{shot.subtitle or shot.narration}",
                f"画面：{shot.visual_description}",
                f"关键词：{'、'.join(shot.keywords)}",
                "",
            ]
        )

    return "\n".join(lines).strip()


def script_to_response(
    script: VideoScript,
    payload: dict[str, Any],
    *,
    provider: str,
    script_text: str | None = None,
    analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    topic = str(payload.get("topic") or script.title or "").strip()
    aspect_ratio = str(payload.get("aspect_ratio") or "9:16")
    duration_seconds = int(round(float(script.total_duration or payload.get("duration_seconds") or 30)))
    response = {
        "id": uuid.uuid4().hex,
        "title": script.title,
        "topic": topic,
        "aspect_ratio": aspect_ratio,
        "duration_seconds": duration_seconds,
        "total_duration": script.total_duration,
        "shots": [shot.model_dump(mode="json") for shot in script.shots],
        "provider": provider,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if script_text is not None:
        response["script_text"] = script_text
    if analysis is not None:
        response["analysis"] = analysis
    return response


_build_delivery_for_narration = build_delivery_for_narration
_build_script_from_data = build_script_from_data
_parse_editor_script = parse_editor_script
_normalize_script = normalize_script
repair_structured_script_metadata = _repair_structured_script_metadata
