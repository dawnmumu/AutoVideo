# AutoVideo 混剪工作台最终音频合成设计

日期：2026-06-21

## 背景

混剪工作台已经可以选择 Microsoft Edge TTS 旁白音色，也可以选择 BGM 曲目、分类和音量。当前这些字段只保存到任务 `options` 与 `manifest.json`，渲染层仍使用 `concat=n=...:v=1:a=0` 和 `-an` 生成无音轨 MP4，README 也明确写着最终视频未混入 TTS 旁白和 BGM。

本次目标是把已选择的旁白和 BGM 真正合成到最终输出视频，避免用户下载到“配置里有音频、成片没有声音”的结果。

## 目标

1. 有 `voice_id` 且脚本镜头包含 `narration` 时，按镜头生成 Edge TTS 旁白音频。
2. 启用 BGM 且任务已解析到具体 `bgm_snapshot` 时，把对应 BGM 以 `bgm_volume` 混入成片。
3. 旁白按镜头 `start_time` 对齐，BGM 循环或裁剪到视频总时长。
4. 最终任务主输出仍为 `output.mp4`，但文件包含请求的旁白和 BGM 音轨。
5. `manifest.json` 的 `render_plan` 明确记录音频合成状态、旁白片段数、BGM 状态和最终输出文件。
6. 失败时返回结构化错误，不静默产出缺音频视频。
7. README 和工作台文案同步说明最终输出会包含已选择的旁白和 BGM。

## 非目标

1. 不实现自动 ducking、响度标准化、淡入淡出、多轨手动调音台或节拍点分析。
2. 不接入 Fish Speech 音色复刻。
3. 不引入权限管理、团队素材库或用户隔离。
4. 不修改素材下载、字幕模板、BGM 管理 CRUD 和任务列表安全输出语义。

## 方案

新增 `autovideo/services/audio_mix.py`，只负责音频准备和混音封装：

1. `prepare_narration_clips(...)`：读取 render timeline 和 `voice_options`，对有旁白的镜头调用 `VoiceCenterService` 的 Edge TTS provider 生成每段 MP3，并写出带 `start_time`、`duration`、`filename` 的片段清单。
2. `resolve_bgm_audio(...)`：从 `bgm_snapshot.filename` 解析 `data/bgm/tracks/<filename>`，校验路径仍在 BGM tracks 目录内。
3. `mix_audio_into_video(...)`：输入当前视频、旁白片段、BGM 文件和总时长，构造 FFmpeg 命令输出临时 MP4，成功后原子替换 `output.mp4`。
4. `apply_audio_mix(...)`：组合以上步骤，返回可写入 `render_plan.audio_mix` 的安全状态。

渲染链路保持现有视频/字幕处理顺序：先生成无音频或带字幕烧录的视频，再调用音频合成。这样字幕失败的回退语义不变；只有当最终可下载视频存在时才做音频混合。

## 错误策略

如果用户请求了旁白或 BGM，音频合成失败时任务创建失败并清理未登记输出目录，路由返回 `502 AUDIO_MIX_FAILED`。`render_plan.error_summary` 只保留脱敏摘要，不暴露本地路径、token 或配置值。

如果没有选择音色且没有启用 BGM，则跳过音频合成，保持现有视频输出。

## Manifest 设计

成功合成示例：

```json
{
  "render_plan": {
    "status": "video_rendered",
    "renderer": "ffmpeg",
    "output": "output.mp4",
    "audio_mix": {
      "status": "mixed",
      "voiceover_status": "mixed",
      "voiceover_clip_count": 2,
      "bgm_status": "mixed",
      "bgm_volume": 0.12,
      "output": "output.mp4"
    }
  },
  "bgm_mix_status": "mixed"
}
```

跳过示例：

```json
{
  "audio_mix": {
    "status": "skipped",
    "voiceover_status": "not_requested",
    "voiceover_clip_count": 0,
    "bgm_status": "not_requested"
  }
}
```

## 前端与移动端

现有旁白音色和 BGM 选择器已满足可见 label、触控高度和移动端单列要求，本次不重做选择器。只调整工作台和 README 中的阶段说明：创建任务时所选旁白和 BGM 会进入最终 MP4；任务失败时沿用现有错误列表与重试按钮。

## 验收标准

1. 选择旁白音色并创建混剪任务后，FFmpeg 命令包含旁白音频输入、延迟/混音滤镜和音频 map。
2. 启用 BGM 并创建混剪任务后，FFmpeg 命令包含 BGM 输入、循环/裁剪和音量设置。
3. 同时选择旁白和 BGM 时，最终输出仍为 `output.mp4`，manifest 中 `audio_mix.status` 为 `mixed`。
4. 未选择旁白和未启用 BGM 时不会调用音频混合命令。
5. 音频混合失败时 API 返回 `AUDIO_MIX_FAILED`，输出目录被清理，不登记失败任务。
6. README 不再声明最终视频未混入 TTS/BGM。
