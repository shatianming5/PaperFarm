# Round 6 Deep Audit: Remote Modules + System Reliability

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all verified bugs (P0/P1/P2) found by deep audit of remote/network modules and full system reliability scan.

**Architecture:** Priority-based batch fixing: P0 crash fixes first, then P1 behavior corrections, then P2 hardening, with comprehensive test coverage.

**Tech Stack:** Python 3.14, pytest, unittest.mock, asyncio

---

## Verified Issues (Cross-validated by audit + source review)

### P0 — Crash (4 confirmed real)

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `hub_cmd.py:134-147` | `torch.cuda.get_device_properties(0)` only catches `ImportError`; `RuntimeError`/`IndexError` unhandled | Catch `Exception` in torch block |
| 2 | `worker.py:373-409` | GPU telemetry thread `join(timeout=2)` may not stop thread; resource leak | Increase timeout, add logging if thread still alive |
| 3 | `headless.py:179-249,291-374` | Agent resolve fails → finally references undefined vars → `NameError` | Initialize agent vars to `None` before try, check in finally |
| 4 | `legacy_bootstrap.py:704-721+` | `on_prepare_event` callback exceptions propagate uncaught | Wrap in try/except |

### P1 — Wrong Behavior (6 high priority)

| # | File | Issue | Fix |
|---|------|-------|-----|
| 5 | `config.py:109-117` | `int(exp.get("timeout", 600) or 600)` treats `timeout: 0` as 600 | Use explicit None check instead of `or` |
| 6 | `hub_cmd.py:133` | GPU requirement comparison is case-sensitive | `.lower()` before compare |
| 7 | `worker.py:258-265` | `_load_detached_state` doesn't catch `UnicodeDecodeError` | Add to except tuple |
| 8 | `legacy_gpu.py:236-246` | TTL reaping: malformed `started_at` → age=None → never reaped | Default to 0 age on parse failure |
| 9 | `legacy_bootstrap.py:580-591` | `_run_prepare_command` timeout doesn't kill subprocess | Kill process on timeout |
| 10 | `worker.py:1332-1340` | GPU allocation not released if workspace isolation fails in some paths | Ensure release in finally |

### P2 — Hardening (best-effort)

| # | File | Issue | Fix |
|---|------|-------|-----|
| 11 | `legacy_gpu.py:102` | `status_file.read_text()` missing `encoding="utf-8"` | Add encoding param |
| 12 | `worker_plugins.py:115-116` | `except Exception:` silently swallows errors without logging | Add logger.warning |
| 13 | `config.py:129-154` | `bool()` conversion on non-bool types (empty list/string) | Explicit True/False check |
| 14 | `hub_cmd.py:163,199` | Negative exit codes from signal termination | `max(returncode, 1)` |
| 15 | `worker.py:316-326` | Saturation context file not read-locked | Document or add lock |
| 16 | `legacy_bootstrap.py:270-278` | `_expected_paths_status` resolves symlinks (info leak) | Document intended behavior |

## Test Plan

- Each fix gets at least 1 dedicated test
- Mock external deps (torch, subprocess, SSH, HTTP)
- Test file: `tests/test_round6_deep_audit.py`
- Target: 728+ existing tests pass + 30-40 new tests

## Execution Order

1. P0 fixes (4 items) → commit
2. P1 fixes (6 items) → commit
3. P2 hardening (6 items) → commit
4. Write all tests → commit
5. Full test suite verification → done
