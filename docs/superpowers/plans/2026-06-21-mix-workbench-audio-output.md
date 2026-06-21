# Mix Workbench Audio Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AutoVideo online remix tasks synthesize selected narration and mix selected BGM into the final `output.mp4`.

**Architecture:** Keep the existing video render and subtitle burn sequence intact, then add a focused `autovideo/services/audio_mix.py` layer that prepares Edge TTS narration clips, resolves BGM snapshots, and runs a second FFmpeg pass to write audio into the final MP4. `online_mix.py` passes normalized voice and BGM options into that layer and records the returned safe status in `render_plan`.

**Tech Stack:** FastAPI, pytest, React, TypeScript, Vitest, FFmpeg, Edge TTS provider abstraction.

---

## File Structure

- Create: `autovideo/services/audio_mix.py`
  - Owns narration clip synthesis, BGM path resolution, FFmpeg audio mix command construction, command execution, and safe status payloads.
- Modify: `autovideo/services/online_mix.py`
  - Add `AudioMixFailedError`, pass voice/BGM options into output builder, invoke audio mix after `render_mix_video`, and update manifest fields.
- Modify: `autovideo/api/routes/online_mix.py`
  - Catch `AudioMixFailedError` and return structured `502 AUDIO_MIX_FAILED`.
- Modify: `tests/services/test_audio_mix.py`
  - Cover command shape, path safety, skipped state, and failure mapping.
- Modify: `tests/api/test_online_mix.py`
  - Cover final task manifest and API failure cleanup using fake FFmpeg and fake Edge TTS provider.
- Modify: `frontend/src/components/OnlineRemixWorkbench.tsx`
  - Update compact status text so users know selected narration and BGM are mixed into output.
- Modify: `README.md`
  - Replace previous config-only caveats with final audio output behavior.

## Tasks

### Task 1: Audio Mix Service Contract

**Files:**
- Create: `tests/services/test_audio_mix.py`
- Create: `autovideo/services/audio_mix.py`

- [ ] Write failing tests for `audio_mix.build_audio_mix_status()` skipped state and for `resolve_bgm_audio()` refusing paths outside `data/bgm/tracks`.
- [ ] Run `pytest tests/services/test_audio_mix.py -q`; expected failure is import error because `autovideo.services.audio_mix` does not exist.
- [ ] Implement `AudioMixFailedError`, `build_audio_mix_status()`, `resolve_bgm_audio()`, `_safe_bgm_tracks_dir()`, and `_sanitize_audio_error_summary()`.
- [ ] Run `pytest tests/services/test_audio_mix.py -q`; expected pass for skipped/path-safety tests.

### Task 2: FFmpeg Audio Command

**Files:**
- Modify: `tests/services/test_audio_mix.py`
- Modify: `autovideo/services/audio_mix.py`

- [ ] Add a failing test that calls `_build_audio_mix_command()` with one narration clip and one BGM file and asserts the command has the video input, `-stream_loop -1` for BGM, `adelay`, `volume=0.12`, `amix`, `-map 0:v:0`, and `-map [aout]`.
- [ ] Run `pytest tests/services/test_audio_mix.py -k audio_mix_command -q`; expected failure is missing `_build_audio_mix_command`.
- [ ] Implement `_build_audio_mix_command()` with deterministic input ordering: base video input first, narration clips next, BGM last.
- [ ] Run `pytest tests/services/test_audio_mix.py -q`; expected pass.

### Task 3: Narration Synthesis And Mix Execution

**Files:**
- Modify: `tests/services/test_audio_mix.py`
- Modify: `autovideo/services/audio_mix.py`

- [ ] Add a failing async test for `prepare_narration_clips()` using a fake provider; assert it writes one MP3 per non-empty narration, uses selected `voice_id`, and records `start_time`.
- [ ] Add a failing test for `mix_audio_into_video()` using a fake FFmpeg executable; assert it writes a temporary output and replaces final `output.mp4`.
- [ ] Run `pytest tests/services/test_audio_mix.py -q`; expected failure is missing functions.
- [ ] Implement `prepare_narration_clips()`, `mix_audio_into_video()`, `_run_audio_mix_command()`, timeout handling, and atomic replace.
- [ ] Run `pytest tests/services/test_audio_mix.py -q`; expected pass.

### Task 4: Online Mix Integration

**Files:**
- Modify: `tests/api/test_online_mix.py`
- Modify: `autovideo/services/online_mix.py`
- Modify: `autovideo/api/routes/online_mix.py`

- [ ] Add a failing API test that creates a manual online mix task with `voice_id` and BGM, using fake Edge TTS provider and fake FFmpeg; assert `manifest["render_plan"]["audio_mix"]["status"] == "mixed"`, `voiceover_clip_count == 1`, `bgm_status == "mixed"`, `bgm_mix_status == "mixed"`, and output download is `video/mp4`.
- [ ] Add a failing API test where the second FFmpeg pass fails; assert status `502`, code `AUDIO_MIX_FAILED`, no task is listed, and `outputs` is empty.
- [ ] Run `pytest tests/api/test_online_mix.py -k "audio_mix or AUDIO_MIX" -q`; expected failure is missing integration.
- [ ] Update `_render_online_mix_output_builder()` to accept `voice_options` and `bgm_options`, call `apply_audio_mix()` after video rendering succeeds, merge returned status into `render_plan`, and update `output_payload["bgm_mix_status"]`.
- [ ] Add `AudioMixFailedError` mapping in `online_mix.py` and route-level `AUDIO_MIX_FAILED` response.
- [ ] Run `pytest tests/api/test_online_mix.py -k "audio_mix or AUDIO_MIX" -q`; expected pass.

### Task 5: Docs And UI Text

**Files:**
- Modify: `frontend/src/components/OnlineRemixWorkbench.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `README.md`

- [ ] Add a failing frontend test asserting the online remix workbench contains concise text that selected narration and BGM are mixed into the final output.
- [ ] Run `cd frontend && npm test -- --run src/App.test.tsx -t "audio output"`.
- [ ] Update workbench helper text without changing layout or adding a new panel.
- [ ] Update README to say final MP4 includes selected Edge TTS narration and BGM; remove outdated caveats that say final video has not mixed those tracks.
- [ ] Run `cd frontend && npm test -- --run src/App.test.tsx -t "audio output"` and `pytest tests/web/test_frontend_build.py -q`.

### Task 6: Verification

**Files:**
- No new files.

- [ ] Run `pytest tests/services/test_audio_mix.py tests/services/test_rendering.py tests/api/test_online_mix.py -q`.
- [ ] Run `pytest tests/api/test_bgm.py tests/services/test_voice_center.py -q`.
- [ ] Run `cd frontend && npm test -- --run src/App.test.tsx`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run local review loop before commit, then fix any actionable findings and rerun impacted tests.
