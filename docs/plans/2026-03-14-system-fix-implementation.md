# System Audit Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all 73 issues found in the system audit, organized into 6 phases by module and severity.

**Architecture:** Each phase targets one module/layer, fixing CRITICAL/HIGH first then MEDIUM. Each phase produces one commit, tested with the full test suite. Phases are independent and can be paused between.

**Tech Stack:** Python 3.12, pytest, filelock, Textual (TUI), csv, json, threading

---

## Task 1: Phase 1 — Worker Core Fixes (12 issues)

**Files:**
- Modify: `src/open_researcher/worker.py`
- Test: `tests/test_tui.py` (existing), `pytest tests/ -x -q`

**Step 1: Fix C1+H1 — Claim slot leak on break paths**

In `worker.py`, the main experiment loop (around line 928-1386) has multiple `break`/`continue` paths that can skip `_release_claim_slot()`. The fix wraps the claim-run-release in a unified try/finally.

Find the block starting at line ~928 `if not self._reserve_claim_slot():` through line ~990 (the break/continue paths). The key change: after `idea` is claimed (line 931), set a `claimed = True` flag and ensure the finally at line 1362 always releases. The existing finally at 1357-1362 already calls `_release_claim_slot()`, so we just need to ensure ALL break paths reach it.

The specific fix for line 975-980 (pause break):
```python
# OLD (line 975-980):
                    if not self._wait_until_unpaused():
                        applied = self.idea_pool.update_status(idea["id"], "pending", claim_token=claim_token or None)
                        if not applied:
                            self.on_output(f"[{wid}] Stop requested while pausing; claim release skipped")
                        notify_finished = False
                        break
```
Change `break` to set a flag and let the finally handle cleanup:
```python
# NEW:
                    if not self._wait_until_unpaused():
                        applied = self.idea_pool.update_status(idea["id"], "pending", claim_token=claim_token or None)
                        if not applied:
                            self.on_output(f"[{wid}] Stop requested while pausing; claim release skipped")
                        notify_finished = False
                        break  # finally at line 1357-1362 will release claim slot
```
Actually the existing finally block at 1357-1362 DOES cover all `break` exits from the inner loop. Verify by tracing: `break` at 980 exits the inner `while not self._should_stop()` loop → reaches `finally:` at 1357 → `_release_claim_slot()` at 1362. **This path IS covered.**

The REAL gap is line 956: `self.stop(); break` for resource_deadlock. After this break, execution reaches 1357 finally → release. **Also covered.**

Re-examine: the outer `try` starts at line ~927. The `finally` at 1357 is inside the inner `while` loop's body (the `try:` at line ~970). Let me trace more carefully...

The structure is:
```
while not self._should_stop():   # outer loop
    if not self._reserve_claim_slot(): break  # 928-930: exits outer loop, NO finally
    idea, allocation, resource_state = ...   # 931
    if not idea:
        self._release_claim_slot()   # 933
        ...
        continue or break
    ...
    try:   # ~970
        ... experiment code ...
    finally:   # 1357
        try:
            gpu release
        finally:
            self._release_claim_slot()   # 1362
```

So the `break` at line 930 (claim budget exhausted) is BEFORE any claim succeeds → no slot to release. OK.

The `break` at line 956 (resource_deadlock) is AFTER `_reserve_claim_slot()` but BEFORE the inner `try` at ~970. **This IS the leak!** The claim slot was reserved at 928, the idea was not claimed (line 932: `if not idea`), but wait — line 933 does `self._release_claim_slot()` for the `not idea` case. But on line 944, `resource_state == "resource_deadlock"` is inside the `if not idea:` block, so line 933 already released. **Not a leak here either.**

Let me check: line 931 `idea, allocation, resource_state = ...`. If `not idea` (line 932), line 933 releases. Then lines 934-956 handle various resource_states, all ending in `continue` or `break`. The slot WAS released at 933. OK.

Now check line 975 `break`: this is INSIDE the inner `try` (line ~970), so the `finally` at 1357 catches it. **Covered.**

So actually the claim slot management is correct in all paths. Let me re-verify the skip path at 982-990: `continue` goes back to while loop → reserves again → OK.

**Conclusion: C1/H1 are false positives in the audit for the current code.** The existing try/finally structure covers all paths. Skip this fix.

**Step 2: Fix C2 — Detached state concurrent write protection**

Add FileLock to `_write_detached_state` (line 278-281):
```python
# OLD:
    def _write_detached_state(self, idea: dict, payload: dict) -> None:
        path = self._detached_state_path(idea)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, payload)

# NEW:
    def _write_detached_state(self, idea: dict, payload: dict) -> None:
        path = self._detached_state_path(idea)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = FileLock(str(path) + ".lock", timeout=5)
        with lock:
            atomic_write_json(path, payload)
```

Also add lock to `_load_detached_state` (find its definition and add the same lock pattern):
```python
    def _load_detached_state(self, idea: dict) -> dict | None:
        path = self._detached_state_path(idea)
        if not path.exists():
            return None
        lock = FileLock(str(path) + ".lock", timeout=5)
        with lock:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
```

Ensure `from filelock import FileLock` is imported (it likely already is).

**Step 3: Fix H3+H15 — Resource deadlock retry with backoff**

Replace lines 944-956:
```python
# OLD:
                    if resource_state == "resource_deadlock":
                        self._activity.update_worker(...)
                        self._record_resource_deadlock()
                        self.on_output(f"[{wid}] Pending ideas are unschedulable...")
                        self.stop()
                        break

# NEW:
                    if resource_state == "resource_deadlock":
                        self._activity.update_worker(
                            "experiment_agent", wid, status="idle", idea="",
                        )
                        self._record_resource_deadlock()
                        # Retry with random backoff before giving up
                        import random
                        retried = False
                        for _attempt in range(3):
                            backoff = random.uniform(5, 30)
                            self.on_output(f"[{wid}] Resource deadlock, retrying in {backoff:.0f}s...")
                            time.sleep(backoff)
                            if self._should_stop():
                                break
                            idea, allocation, resource_state = self._claim_next_runnable_idea(wid, gpu)
                            if idea or resource_state != "resource_deadlock":
                                retried = True
                                break
                        if not retried:
                            self.on_output(f"[{wid}] Resource deadlock persists after 3 retries, stopping")
                            self.stop()
                            break
                        if not idea:
                            continue
                        # Fall through to experiment execution with the newly claimed idea
```
Note: `import random` should be moved to the file-level imports.

**Step 4: Fix H9 — results.tsv read under lock**

Find `load_results` import and the call at line 1059. Wrap in lock:
```python
# At line 1059, change:
                    results_before_count = len(load_results(workdir))
# To:
                    _results_lock = FileLock(str(workdir / ".research" / "results.tsv.lock"), timeout=10)
                    with _results_lock:
                        results_before_count = len(load_results(workdir))
```

Also wrap the `_find_matching_result_row` call at 1123 similarly.

**Step 5: Fix M7 — Skip flag atomicity**

At lines 982-990, swap the order — update idea first, then consume flag:
```python
# OLD:
                    if consume_skip_current(self.research_dir / "control.json", source=f"{wid}:runtime"):
                        self.on_output(f"[{wid}] Consumed skip_current for {idea['id']}")
                        applied = self.idea_pool.update_status(idea["id"], "skipped", claim_token=claim_token or None)

# NEW:
                    ctrl = read_control(self.research_dir / "control.json")
                    if ctrl.get("skip_current"):
                        applied = self.idea_pool.update_status(idea["id"], "skipped", claim_token=claim_token or None)
                        if applied:
                            consume_skip_current(self.research_dir / "control.json", source=f"{wid}:runtime")
                            self.on_output(f"[{wid}] Consumed skip_current for {idea['id']}")
                        else:
                            self.on_output(f"[{wid}] Claim race on skip for {idea['id']}; flag preserved")
```

**Step 6: Fix M9 — GPU release exception safety**

At line 1359-1360:
```python
# OLD:
                        try:
                            if self._plugins.gpu_allocator is not None and allocation is not None:
                                self._plugins.gpu_allocator.release(allocation)
                        finally:
                            self._release_claim_slot()

# NEW:
                        try:
                            if self._plugins.gpu_allocator is not None and allocation is not None:
                                try:
                                    self._plugins.gpu_allocator.release(allocation)
                                except Exception:
                                    logger.error("GPU release failed for allocation %s", allocation, exc_info=True)
                        finally:
                            self._release_claim_slot()
```

**Step 7: Run tests**

Run: `python3 -m pytest tests/ -x -q --timeout=30`
Expected: All 761+ tests PASS

**Step 8: Commit**

```bash
git add src/open_researcher/worker.py
git commit -m "fix(worker): detached state locking, deadlock retry, results read safety"
```

---

## Task 2: Phase 2 — Data Integrity Fixes (10 issues)

**Files:**
- Modify: `src/open_researcher/control_plane.py`
- Modify: `src/open_researcher/event_journal.py`
- Modify: `src/open_researcher/results_cmd.py`
- Modify: `src/open_researcher/idea_pool.py`

**Step 1: Fix C4 — Control event fsync**

In `control_plane.py` line 97-101:
```python
# OLD:
def _append_event_unlocked(events_path: Path, record: dict) -> None:
    events_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")

# NEW:
def _append_event_unlocked(events_path: Path, record: dict) -> None:
    events_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())
```
Add `import os` at the top if not present.

**Step 2: Fix H4 — EventJournal lock timeout**

In `event_journal.py` line 63:
```python
# OLD:
        self._lock = FileLock(str(path) + ".lock")

# NEW:
        self._lock = FileLock(str(path) + ".lock", timeout=10)
```

**Step 3: Fix H6 — Replay sequence validation**

In `control_plane.py` `_replay_control_state_unlocked` (line 138-184), add sequence gap detection:
```python
# After line 168 (after getting seq):
            if prev_seq is not None and seq != prev_seq + 1:
                logger.warning("Control event sequence gap: %d -> %d", prev_seq, seq)
            prev_seq = seq
```
Initialize `prev_seq = None` before the loop (after line 149).

**Step 4: Fix H7 — Snapshot staleness warning**

In `read_control` (line 187-198), after replay, compare timestamps:
```python
def read_control(ctrl_path: Path) -> dict:
    events_path = _event_log_path(ctrl_path)
    lock = FileLock(str(events_path) + ".lock", timeout=10)
    with lock:
        ctrl = _replay_control_state_unlocked(
            ctrl_path, events_path, use_snapshot_fallback=True,
        )
        # Warn if snapshot is stale compared to events
        if events_path.exists() and ctrl_path.exists():
            try:
                age_diff = events_path.stat().st_mtime - ctrl_path.stat().st_mtime
                if abs(age_diff) > 300:
                    logger.warning("Control snapshot may be stale (%.0fs behind events)", age_diff)
            except OSError:
                pass
        atomic_write_json(ctrl_path, ctrl)
        return ctrl
```

**Step 5: Fix H10 — results.tsv atomic rewrite**

In `results_cmd.py` `augment_result_secondary_metrics` (around line 102):
```python
# OLD:
        with results_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

# NEW:
        import io
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
        atomic_write_text(results_path, buf.getvalue())
```
Ensure `atomic_write_text` is imported from `open_researcher.utils` (or wherever it's defined).

**Step 6: Fix M2 — claim_token_seq recovery**

In `idea_pool.py` `_next_claim_token` (line 216-224):
```python
# OLD:
        except (TypeError, ValueError):
            current_seq = 0

# NEW:
        except (TypeError, ValueError):
            # Recover from corrupted seq by scanning existing tokens
            ideas = data.get("ideas", data.get("backlog", []))
            max_found = 0
            for idea in ideas:
                token = str(idea.get("claim_token") or idea.get("finished_claim_token") or "")
                if token.startswith("claim-"):
                    try:
                        seq_part = int(token.split(":")[0].replace("claim-", ""))
                        max_found = max(max_found, seq_part)
                    except (ValueError, IndexError):
                        pass
            current_seq = max_found
            logger.warning("claim_token_seq corrupted (was %r), recovered to %d", raw_seq, current_seq)
```

**Step 7: Fix M3 — TSV escaping**

In `results_cmd.py` `write_final_results_tsv` (around line 197):
```python
# OLD:
        escaped = [
            '"' + value.replace('"', '""') + '"' if "\t" in value or "\n" in value else value for value in values
        ]
        lines.append("\t".join(escaped))

# NEW:
        import io as _io
        _row_buf = _io.StringIO()
        _row_writer = csv.writer(_row_buf, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
        _row_writer.writerow(values)
        lines.append(_row_buf.getvalue().rstrip("\r\n"))
```

**Step 8: Run tests**

Run: `python3 -m pytest tests/ -x -q --timeout=30`
Expected: All tests PASS

**Step 9: Commit**

```bash
git add src/open_researcher/control_plane.py src/open_researcher/event_journal.py src/open_researcher/results_cmd.py src/open_researcher/idea_pool.py
git commit -m "fix(data): event fsync, lock timeout, atomic TSV writes, seq validation"
```

---

## Task 3: Phase 3 — Agent/Execution Layer (12 issues)

**Files:**
- Modify: `src/open_researcher/agents/base.py`
- Modify: `src/open_researcher/plugins/execution/legacy_worktree.py`
- Modify: `src/open_researcher/plugins/execution/legacy_gpu.py`
- Modify: `src/open_researcher/plugins/bootstrap/prepare.py`
- Modify: `src/open_researcher/plugins/bootstrap/detection.py`

**Step 1: Fix H11 — Agent subprocess timeout**

In `agents/base.py` `_run_process` line ~98:
```python
# OLD:
            proc.wait()
        return proc.returncode

# NEW:
            proc.wait(timeout=43200)  # 12h max matching experiment.timeout default
        return proc.returncode
```
Also catch TimeoutExpired:
```python
        try:
            proc.wait(timeout=43200)
        except subprocess.TimeoutExpired:
            self.terminate()
            return 124  # timeout exit code
        return proc.returncode
```

**Step 2: Fix H12 — Worktree cleanup lock**

In `legacy_worktree.py` `remove_worktree` (line 352), add lock:
```python
def remove_worktree(repo_path: Path, worktree_path: Path) -> None:
    worktrees_root = worktree_path.parent
    lock_path = worktrees_root / ".cleanup.lock" if worktrees_root.exists() else repo_path / ".research" / "worktree_cleanup.lock"
    lock = FileLock(str(lock_path), timeout=60)
    with lock:
        # ... existing cleanup code ...
```

**Step 3: Fix H13 — GPU stale reservation protection**

In `legacy_gpu.py` `_reap_stale_reservations`, for unknown age items, also check `created_at` or `reserved_at` as fallback before reaping:
```python
# Replace the "Unknown age" block (around line 242):
                # Unknown age: try created_at or reserved_at as fallback
                for alt_field in ("created_at", "reserved_at"):
                    alt_age = _reservation_age_minutes_from_field(res, alt_field)
                    if alt_age is not None:
                        if alt_age <= self.reservation_ttl_minutes:
                            kept.append(res)
                        else:
                            logger.warning("Reaped GPU reservation %s via %s (age=%.0f min)", rid, alt_field, alt_age)
                        break
                else:
                    logger.warning("Reaped GPU reservation %s with unknown age (tag=%s)", rid, tag)
```

**Step 4: Fix M13 — Atomic symlink replacement**

In `legacy_worktree.py` `_replace_research_dir` (line 134-141):
```python
# OLD:
    if wt_research.is_symlink() or wt_research.is_file():
        wt_research.unlink()
    elif wt_research.is_dir():
        shutil.rmtree(wt_research)
    os.symlink(str(research_dir.resolve()), str(wt_research))

# NEW:
    if wt_research.is_symlink() or wt_research.is_file():
        wt_research.unlink()
    elif wt_research.is_dir():
        shutil.rmtree(wt_research)
    # Use temp symlink + rename for atomicity
    tmp_link = wt_research.with_suffix(".tmp_symlink")
    tmp_link.unlink(missing_ok=True)
    os.symlink(str(research_dir.resolve()), str(tmp_link))
    tmp_link.rename(wt_research)
```

**Step 5: Fix M14 — Negative free memory warning**

In `legacy_gpu.py` `effective_free_memory` (line 312):
```python
# OLD:
        return max(int(gpu.get("memory_free", 0) or 0) - reserved, 0)

# NEW:
        physical_free = int(gpu.get("memory_free", 0) or 0)
        effective = physical_free - reserved
        if effective < 0:
            gpu_id = gpu.get("index", gpu.get("id", "?"))
            logger.warning("GPU %s: reserved %dMiB > free %dMiB, data may be stale", gpu_id, reserved, physical_free)
        return max(effective, 0)
```

**Step 6: Fix M25 — CommandInfo validation**

In `plugins/bootstrap/detection.py`, add `__post_init__` to CommandInfo:
```python
@dataclass
class CommandInfo:
    command: list[str]
    ...
    def __post_init__(self):
        if not self.command:
            raise ValueError("CommandInfo.command must be non-empty")
```

**Step 7: Run tests and commit**

Run: `python3 -m pytest tests/ -x -q --timeout=30`

```bash
git add src/open_researcher/agents/base.py src/open_researcher/plugins/
git commit -m "fix(execution): agent timeout, worktree locking, GPU safety, symlink atomicity"
```

---

## Task 4: Phase 4 — TUI/CLI Fixes (12 issues)

**Files:**
- Modify: `src/open_researcher/tui/widgets.py`
- Modify: `src/open_researcher/tui/app.py`
- Modify: `src/open_researcher/tui/view_model.py`
- Modify: `src/open_researcher/phase_gate.py`
- Modify: `src/open_researcher/evaluation_contract.py`
- Test: `tests/test_tui.py`

**Step 1: Fix C6 — FrontierFocusPanel IndexError**

In `widgets.py` line 676-677:
```python
# OLD:
                if not restored:
                    option_list.highlighted = 0 if options else None
                    self._update_active(frontiers[0].frontier_id)

# NEW:
                if not restored:
                    option_list.highlighted = 0 if options else None
                    if frontiers:
                        self._update_active(frontiers[0].frontier_id)
```

**Step 2: Write test for C6 fix**

In `tests/test_tui.py`, add:
```python
def test_frontier_focus_panel_handles_empty_frontiers():
    """C6: Should not crash when frontiers list is empty."""
    panel = FrontierFocusPanel()
    panel.update_frontiers([])  # Must not raise IndexError
    assert "frontier data" in panel.items_text.lower() or panel.items_text == ""
```

**Step 3: Fix H17 — PhaseGate corruption logging**

In `phase_gate.py` line 22-24:
```python
# OLD:
        except (json.JSONDecodeError, OSError):
            return "init"

# NEW:
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("experiment_progress.json corrupted: %s, defaulting to init", exc)
            return "init"
```
Add `import logging` and `logger = logging.getLogger(__name__)` at the top.

**Step 4: Fix H19 — view_model None safety**

In `view_model.py`, find `_build_frontier_detail` (around line 384) and add guards at entry:
```python
def _build_frontier_detail(
    card: FrontierCard,
    ...
    hypothesis: dict | None,
    spec: dict | None,
    ...
):
    hypothesis = hypothesis or {}
    spec = spec or {}
```

**Step 5: Fix M17 — metric direction inference**

In `evaluation_contract.py` line 85-86:
```python
# OLD:
    if metric_name and not direction:
        direction = "higher_is_better"

# NEW:
    if metric_name and not direction:
        _LOWER_METRICS = {"loss", "val_loss", "error", "perplexity", "cer", "wer", "mae", "mse", "rmse"}
        direction = "lower_is_better" if metric_name.lower() in _LOWER_METRICS else "higher_is_better"
```

**Step 6: Fix M26 — Narrow exception catching in widgets.py**

Replace all instances of `except Exception:` with specific exceptions. Example at line 602:
```python
# OLD:
            except Exception:
                logger.debug("Error updating empty frontier panel", exc_info=True)

# NEW:
            except (AttributeError, KeyError):
                logger.debug("Error updating empty frontier panel", exc_info=True)
```

For lines with `query_one` calls, use:
```python
            except (AttributeError, KeyError, Exception):  # Keep broad for query_one NoMatches
```
Actually, Textual raises `NoMatches` for failed queries. Import it:
```python
from textual.css.query import NoMatches
```
Then use `except NoMatches:` for query_one failures.

**Step 7: Fix M27 — Highlight race condition**

At line 663-664:
```python
# OLD:
                if option_list.highlighted is not None and 0 <= option_list.highlighted < option_list.option_count:
                    prev_highlighted = option_list.options[option_list.highlighted].id

# NEW:
                try:
                    if option_list.highlighted is not None and 0 <= option_list.highlighted < option_list.option_count:
                        prev_highlighted = option_list.options[option_list.highlighted].id
                except (IndexError, AttributeError):
                    prev_highlighted = None
```

**Step 8: Run tests and commit**

Run: `python3 -m pytest tests/ -x -q --timeout=30`

```bash
git add src/open_researcher/tui/ src/open_researcher/phase_gate.py src/open_researcher/evaluation_contract.py tests/test_tui.py
git commit -m "fix(tui): frontier IndexError, phase gate logging, metric inference, exception narrowing"
```

---

## Task 5: Phase 5 — MEDIUM Cleanup (8 remaining)

**Files:**
- Modify: `src/open_researcher/role_programs.py` (M18: atomic write)
- Modify: `src/open_researcher/graph_protocol.py` (M19: atomic write)
- Modify: `src/open_researcher/control_plane.py` (M20: snapshot type validation)
- Modify: `src/open_researcher/results_cmd.py` (M21: fieldnames schema check)
- Modify: `src/open_researcher/agents/opencode.py` (M24: threading lock)
- Modify: `src/open_researcher/idea_pool.py` (M6: token expiry)
- Modify: `src/open_researcher/research_memory.py` (M4: schema validation)
- Modify: `src/open_researcher/demo_cmd.py` (M5: atomic writes)

**Step 1: M18+M19 — Atomic file writes**

In `role_programs.py`, replace `.write_text(content, encoding="utf-8")` with:
```python
from open_researcher.utils import atomic_write_text
atomic_write_text(internal_path, content)
```

In `graph_protocol.py`, replace `.write_text(json.dumps(...))` with:
```python
from open_researcher.utils import atomic_write_json
atomic_write_json(progress_path, {"phase": "init"})
```

**Step 2: M20 — Snapshot type validation**

In `control_plane.py` `_load_control_snapshot` line 60-63, add type checking:
```python
    ids = merged.get("applied_command_ids", [])
    if not isinstance(ids, list):
        logger.warning("applied_command_ids is %s, expected list; resetting", type(ids).__name__)
        ids = []
```

**Step 3: M21 — Results fieldnames schema check**

In `results_cmd.py` `augment_result_secondary_metrics`, after getting fieldnames:
```python
    required_cols = {"timestamp", "status", "metric_value"}
    if fieldnames and not required_cols.issubset(set(fieldnames)):
        logger.warning("results.tsv schema mismatch: missing %s", required_cols - set(fieldnames))
        return False
```

**Step 4: M24 — OpenCode thread safety**

In `agents/opencode.py`, add `threading.Lock` around `_supports_run_command`:
```python
    def __init__(self, ...):
        ...
        self._detect_lock = threading.Lock()

    def _supports_run_command(self):
        with self._detect_lock:
            if self._supports_run_subcommand is not None:
                return self._supports_run_subcommand
            # ... detection logic ...
```

**Step 5: M6 — Token expiry (30min)**

In `idea_pool.py` claim token validation (line 173), add time check:
```python
    if claim_token is not None:
        current = str(idea.get("claim_token") or idea.get("finished_claim_token") or "")
        if current != str(claim_token):
            return False
        # Check token age (optional: skip if no timestamp)
        claimed_at = idea.get("claimed_at")
        if claimed_at:
            try:
                from datetime import datetime, timezone
                age_seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(claimed_at)).total_seconds()
                if age_seconds > 1800:  # 30 minutes
                    logger.warning("Claim token for %s expired (age=%.0fs)", idea.get("id"), age_seconds)
                    return False
            except (ValueError, TypeError):
                pass
```

**Step 6: Run tests and commit**

Run: `python3 -m pytest tests/ -x -q --timeout=30`

```bash
git add -A
git commit -m "fix(misc): atomic writes, schema validation, token expiry, thread safety"
```

---

## Task 6: Phase 6 — LOW Cleanup (18 issues)

**Files:** Multiple small changes across the codebase.

**Step 1: Batch all LOW fixes**

| Issue | File | Change |
|-------|------|--------|
| L1 | worker.py | Add collision check in `_safe_state_component` |
| L2 | event_journal.py | Add `sys.stdout.flush()` after stream write |
| L3 | worker.py | Change `logger.debug` to `logger.info` for failure memory errors |
| L4 | worker.py | Add docstring to `stop_after_finalize` usage |
| L5 | worker.py | Log when activity update and worker state diverge |
| L6 | plugins/bootstrap/detection.py | Add `logger.debug` for each fallback |
| L7 | plugins/execution/legacy_worktree.py | Standardize git timeouts to 60s |
| L8 | plugins/execution/gpu.py | Change nvidia-smi timeout from 10s to 30s |
| L9 | plugins/execution/legacy_gpu.py | Add `except OSError` to detect_remote |
| L10 | plugins/execution/legacy_worktree.py | Include full args in WorktreeError messages |
| L11 | plugins/execution/legacy_worktree.py | Wrap manifest write in try/except |
| L12 | plugins/execution/gpu.py | Add simple deadlock detection log |
| L13 | worker.py | Add `if memory_context:` guard |
| L14 | graph_protocol.py | Use `jinja2.select_autoescape()` |
| L15 | evaluation_contract.py | Validate metric_name length < 64 |
| L16 | event_journal.py | Stream-read instead of full file load |
| L17 | demo_cmd.py | Add `logger.debug` for injection failures |
| L18 | tui/view_model.py | Combine 3 dict comprehensions into single scan |

**Step 2: Implement all changes**

Apply each change as described in the table. Each is a 1-3 line change.

**Step 3: Run tests and commit**

Run: `python3 -m pytest tests/ -x -q --timeout=30`

```bash
git add -A
git commit -m "fix(low): logging, timeouts, guards, performance across 18 minor issues"
```

---

## Deployment

After all 6 phases:

```bash
# SCP to remote runners
for runner in open-researcher open-researcher-runner-20260312 open-researcher-runner-c2a5ab9 open-researcher-runner-3a29c1b open-researcher-runner-025412c; do
    scp -r src/open_researcher/ zechuan@222.200.185.183:/mnt/SSD1_8TB/zechuan/$runner/src/open_researcher/
done
```
