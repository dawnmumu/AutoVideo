# Task 3 Report: Material Processing, Raw Files, Segments, And Cleanup Guards

## Status

- Task status: DONE
- Commit: `7d486ce` (`feat: process local material files`)

## Scope Delivered

- Added `material_raw_files` / `material_segments` schema and store helpers in [`autovideo/storage/database.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/autovideo/storage/database.py).
- Added [`MaterialProcessingService`](/Users/sha/.codex/worktrees/ed23/AutoVideo/autovideo/services/material_processing.py) for local source scanning, managed raw copies, segment generation hooks, local-segment material row creation, guarded raw deletion, and guarded library clearing.
- Updated [`MaterialWorkerService`](/Users/sha/.codex/worktrees/ed23/AutoVideo/autovideo/services/material_worker.py) so `run_job(job_id)` atomically claims the exact queued job before processing and finishes it with counts/status.
- Added focused RED/GREEN coverage in [`tests/services/test_material_processing.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/tests/services/test_material_processing.py) and extended [`tests/services/test_material_worker_jobs.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/tests/services/test_material_worker_jobs.py).
- No HTTP API, matcher flow, or frontend UI was added in this task.

## TDD Evidence

### RED

Command:

```bash
PYENV_VERSION=3.12.13 pytest tests/services/test_material_processing.py tests/services/test_material_worker_jobs.py -q
```

Observed failure:

- `ModuleNotFoundError: No module named 'autovideo.services.material_processing'`
- `tests/services/test_material_worker_jobs.py` also failed import for `MaterialFfmpegUnavailableError`
- Exit code: `2`

This was the expected missing-implementation failure after adding the Task 3 tests.

### GREEN

Command:

```bash
PYENV_VERSION=3.12.13 pytest tests/services/test_material_processing.py tests/services/test_material_worker_jobs.py -q
```

Observed result:

- `19 passed, 1 warning in 0.10s`
- Warning only: upstream `StarletteDeprecationWarning` from `fastapi.testclient`
- Exit code: `0`

## Required Verification

Command:

```bash
PYENV_VERSION=3.12.13 pytest tests/services/test_material_processing.py tests/services/test_material_worker_jobs.py -q
```

Observed result:

- `19 passed, 1 warning in 0.10s`
- Warning only: upstream `StarletteDeprecationWarning` from `fastapi.testclient`
- Exit code: `0`

Additional check:

```bash
git diff --check
```

Observed result:

- No whitespace or patch-format errors
- Exit code: `0`

## Behavior Checklist Against Brief

- Raw files and segments persist only managed relative paths; no external absolute source path is returned from the new store rows.
- Processing scans read-only external source roots and only writes managed artifacts under `data/materials/raw` and `data/materials/segments`.
- File symlinks must resolve inside the allowed root; directory symlinks are skipped during traversal.
- `delete_raw_file()` and `clear_library()` preflight managed-root guards before deleting files or marking DB rows deleted.
- Successful raw deletion also removes matching `materials` rows only for `source_type='local_segment'` and `source_provider='local_material_worker'`.
- `run_job(job_id)` claims the exact queued job atomically via Task 2 helpers before processing and does not direct-update a queued row to `running`.
- Worker success/failure now depends on processed segment counts, and missing FFmpeg is surfaced as `MATERIAL_FFMPEG_UNAVAILABLE`.

## Changed Files

- [`autovideo/storage/database.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/autovideo/storage/database.py)
- [`autovideo/services/material_processing.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/autovideo/services/material_processing.py)
- [`autovideo/services/material_worker.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/autovideo/services/material_worker.py)
- [`tests/services/test_material_processing.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/tests/services/test_material_processing.py)
- [`tests/services/test_material_worker_jobs.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/tests/services/test_material_worker_jobs.py)

## Self-Review

- Re-checked the implementation against [`/Users/sha/.codex/worktrees/ed23/AutoVideo/.superpowers/sdd/task-3-brief.md`](/Users/sha/.codex/worktrees/ed23/AutoVideo/.superpowers/sdd/task-3-brief.md) and the local material worker design/plan docs.
- Verified the final test command after commit, not only before commit.
- Verified patch hygiene with `git diff --check`.
- No scope bleed into API routes, matcher logic, or frontend surfaces.

## Concerns

- No functional blocker in delivered Task 3 scope.
- I did not run an independent review subagent in this subtask environment because no review-dispatch tool was surfaced here; review was manual against the brief, diff, and required tests.

---

## Review Fix Follow-Up (2026-06-25)

### Scope

- Fixed the missing managed-root preflight for `delete_raw_file()` and `clear_library()`.
- Fixed `MaterialWorkerService.run_job()` so failed raw files are not double-counted in progress.
- Added regression tests only on Task 3 surfaces.

### Root Cause

- `delete_raw_file()` validated raw path and segment files first, but only validated the derived segment directory after unlinking segment files. A corrupted `raw_file_id` could therefore trigger partial deletion before returning `MATERIAL_LIBRARY_CLEAR_FAILED`.
- `clear_library()` preflighted raw paths and segment file paths for all rows, but did not preflight each computed segment directory before entering the delete loop. A later corrupted row could fail after earlier safe rows had already been deleted.
- `run_job()` used `raw_files_total + failed_total` for progress even though `raw_files_total` already includes failed raw files.

### TDD Evidence

#### RED

Command:

```bash
PYENV_VERSION=3.12.13 pytest tests/services/test_material_processing.py tests/services/test_material_worker_jobs.py -q
```

Observed failure:

- `test_delete_raw_file_rejects_segment_directory_escape_before_any_deletion` failed because the segment file had already been deleted before the escape was detected.
- `test_clear_library_validates_every_segment_dir_before_deleting_anything` failed because an earlier safe raw file had already been deleted before the later escape was detected.
- `test_run_job_fails_when_no_segments_were_produced` failed because `progress_current/progress_total` were `2/2` instead of `1/1`.
- Exit code: `1`

#### GREEN

Command:

```bash
PYENV_VERSION=3.12.13 pytest tests/services/test_material_processing.py tests/services/test_material_worker_jobs.py -q
```

Observed result:

- `21 passed, 1 warning in 0.11s`
- Warning only: upstream `StarletteDeprecationWarning` from `fastapi.testclient`
- Exit code: `0`

### Fix Summary

- Added `_plan_raw_cleanup()` in [`autovideo/services/material_processing.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/autovideo/services/material_processing.py) so raw path, every segment path, and the computed segment directory are all validated before any unlink, `rmtree`, material-row deletion, or `deleted_at` marking occurs.
- Updated `delete_raw_file()` to operate only on the fully validated plan.
- Updated `clear_library()` to preflight every row completely before entering the deletion loop, so any escape now returns `MATERIAL_LIBRARY_CLEAR_FAILED` as a no-op.
- Updated the worker progress calculation in [`autovideo/services/material_worker.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/autovideo/services/material_worker.py) from `raw_files_total + failed_total` to `raw_files_total`.
- Added regression coverage in [`tests/services/test_material_processing.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/tests/services/test_material_processing.py) for corrupted `raw_file_id` / segment-dir escape and `clear_library()` all-or-nothing preflight behavior, plus the failed-job progress assertion in [`tests/services/test_material_worker_jobs.py`](/Users/sha/.codex/worktrees/ed23/AutoVideo/tests/services/test_material_worker_jobs.py).

### Verification

- `git diff --check` passed.
- `PYENV_VERSION=3.12.13 pytest tests/services/test_material_processing.py tests/services/test_material_worker_jobs.py -q` passed.
