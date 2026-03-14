# 系统审计修复设计：6 Phase 混合模式

> 日期: 2026-03-14
> 状态: 已批准
> 依赖: docs/plans/2026-03-14-system-audit-tech-debt.md

## 目标

修复系统审计中发现的全部 73 个问题（6 CRITICAL + 19 HIGH + 30 MEDIUM + 18 LOW），按「模块内严重度优先」的混合模式组织为 6 个 Phase，每个 Phase 独立提交、独立测试。

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 组织方式 | 混合模式（模块内按严重度） | 减少上下文切换，同时保证高危先修 |
| Phase 数量 | 6 个 | 前 4 个按模块（worker→数据→执行→TUI），后 2 个收尾 |
| 测试策略 | 每 Phase 全量跑 `pytest tests/` | 确保无回归 |
| 提交策略 | 每 Phase 一个 commit | 便于回滚 |

---

## Phase 1: Worker 核心修复（12 个问题）

**目标文件**: `src/open_researcher/worker.py`
**问题编号**: C1, C2, C3, H1, H2, H3, H9, H15, M7, M8, M9, M10

### 修复清单

#### C1 + H1: Claim slot 泄漏
**现状**: 暂停后 break、早期 break 等路径绕过 `_release_claim_slot()`。
**方案**: 将整个 claim-run-release 逻辑重构为 try/finally 模式：
```python
claimed = False
try:
    idea, claim_token, resource_state = self._claim_next_runnable_idea(...)
    if idea:
        claimed = True
        # ... run experiment ...
finally:
    if claimed:
        self._release_claim_slot()
```
所有 break/continue 路径都经过 finally。

#### C2: Detached state 无锁写
**方案**: 为 detached state 文件添加 FileLock：
```python
lock = FileLock(str(state_path) + ".lock", timeout=5)
with lock:
    atomic_write_json(state_path, state)
```
同时在 `_monitor_detached_run` 中读取时也加锁。

#### C3: 监控循环非原子读取
**方案**: 合并状态读取和进程存活检查为单次快照：
```python
with lock:
    state = json.loads(state_path.read_text())
    pid = state.get("pid")
    alive = _check_pid(pid) if pid else False
# 后续决策基于此快照
```

#### H2: Claim token 更新失败无验证
**方案**: `update_status` 失败后重读 idea 状态：
```python
applied = self.idea_pool.update_status(idea_id, "pending", claim_token)
if not applied:
    current = self.idea_pool.get_idea(idea_id)
    logger.warning("claim release failed, idea now: %s", current.get("status"))
```

#### H3 + H15: 资源死锁重试 + 活锁防护
**方案**: 死锁时随机退避重试而非立即 stop：
```python
if resource_state == "resource_deadlock":
    for attempt in range(3):
        backoff = random.uniform(5, 30)
        time.sleep(backoff)
        idea, claim_token, resource_state = self._claim_next_runnable_idea(...)
        if resource_state != "resource_deadlock":
            break
    else:
        self.stop()  # 3 次都失败才停
```

#### H9: results.tsv 读无锁
**方案**: 读取时也获取 lock：
```python
lock = FileLock(str(results_path) + ".lock", timeout=10)
with lock:
    rows = load_results(workdir)
```

#### M7: skip 标志非原子
**方案**: 先更新 idea 状态，成功后再消费 flag：
```python
applied = self.idea_pool.update_status(idea["id"], "skipped", claim_token=...)
if applied:
    consume_skip_current(...)
```

#### M8: 运行中不检查暂停
**方案**: 在 `_monitor_detached_run` 的轮询循环中每 10s 检查 pause：
```python
if iterations % 20 == 0:  # 每 20 * 0.5s = 10s
    if is_paused(self._research_dir):
        logger.info("Paused during experiment, waiting...")
        _wait_until_unpaused()
```

#### M9: GPU 释放异常泄漏
**方案**: try/except 包裹，异常时标记 orphaned：
```python
try:
    self._plugins.gpu_allocator.release(allocation)
except Exception:
    logger.error("GPU release failed for %s, marking orphaned", allocation)
```

#### M10: 遥测线程清理
**方案**: join 超时后再次 set event，5s 后检查：
```python
stop_event.set()
thread.join(timeout=5)
if thread.is_alive():
    stop_event.set()  # 双重确保
    thread.join(timeout=2)
```

---

## Phase 2: 数据完整性层（10 个问题）

**目标文件**: `control_plane.py`, `event_journal.py`, `results_cmd.py`, `idea_pool.py`, `activity.py`
**问题编号**: C4, C5, H4, H5, H6, H7, H8, H10, M1, M2

### 修复清单

#### C4: 控制事件 fsync
```python
with events_path.open("a", encoding="utf-8") as handle:
    handle.write(line + "\n")
    handle.flush()
    os.fsync(handle.fileno())
```

#### C5: 序列号原子性
将 `_next_seq_unlocked()` 调用和写入合并，确保在同一个 lock scope 内：
```python
with self._lock:
    seq = self._next_seq_unlocked()
    # 立即写入，不释放锁
    line = json.dumps(record)
    with self.path.open("a") as f:
        f.write(line + "\n")
```

#### H4: EventJournal 锁超时
```python
self._lock = FileLock(str(self.path) + ".lock", timeout=10)
```

#### H5: 锁文件残留清理
启动时调用 `_cleanup_stale_locks(research_dir)`：
```python
def _cleanup_stale_locks(research_dir: Path, max_age_hours: float = 1.0):
    for lock_file in research_dir.glob("*.lock"):
        age = time.time() - lock_file.stat().st_mtime
        if age > max_age_hours * 3600:
            lock_file.unlink(missing_ok=True)
```

#### H6: 回放序列验证
```python
if prev_seq is not None and seq != prev_seq + 1:
    logger.warning("event seq gap: %d -> %d", prev_seq, seq)
```

#### H7: Snapshot 过期检测
```python
events_mtime = events_path.stat().st_mtime if events_path.exists() else 0
snapshot_mtime = snapshot_path.stat().st_mtime if snapshot_path.exists() else 0
if abs(events_mtime - snapshot_mtime) > 300:
    logger.warning("snapshot may be stale (%.0fs behind events)", events_mtime - snapshot_mtime)
```

#### H8: 序列号碰撞检查
写入前读最后一行验证 seq 不重复。

#### H10: results.tsv 原子重写
```python
content = io.StringIO()
writer = csv.DictWriter(content, fieldnames=fieldnames, delimiter="\t")
writer.writeheader()
writer.writerows(rows)
atomic_write_text(results_path, content.getvalue())
```

#### M1: activity active_workers 计算
确认 `_do()` 回调在 FileLock scope 内执行（已有 `_locked_update` 包裹，验证无遗漏）。

#### M2: claim_token_seq 类型恢复
```python
except (TypeError, ValueError):
    # 扫描现有 ideas 确定最大 seq
    max_seq = max((int(re.search(r'(\d+)', str(i.get('claim_token',''))).group(1))
                   for i in ideas if i.get('claim_token')), default=0)
    current_seq = max_seq
    logger.warning("claim_token_seq corrupted, recovered to %d", current_seq)
```

---

## Phase 3: Agent/执行层（12 个问题）

**目标文件**: `agents/base.py`, `plugins/execution/legacy_worktree.py`, `plugins/execution/legacy_gpu.py`, `plugins/bootstrap/prepare.py`, `plugins/bootstrap/detection.py`
**问题编号**: H11, H12, H13, H14, H18, M11, M12, M13, M14, M15, M22, M25

### 修复清单

#### H11: Agent 子进程超时
在 `_run_process` 中为 `proc.wait()` 设置 timeout，匹配 config.experiment.timeout。

#### H12: Worktree 清理加锁
```python
worktrees_lock = FileLock(str(worktrees_root / ".lock"), timeout=30)
with worktrees_lock:
    # remove worktree
```

#### H13: GPU 预留保护
不删 `kind=user_pin`；无 `started_at` 用 `created_at` 或 `reserved_at` fallback。

#### H14: 监控 deadline 修正
用 detached state 的 `started_at` 时间戳计算 deadline。

#### H18: Bootstrap 超时捕获
```python
try:
    subprocess.run(cmd, timeout=timeout, ...)
except subprocess.TimeoutExpired:
    return PrepareResult(success=False, error=f"Command timed out after {timeout}s")
```

#### M11: Workspace 异常标记 skipped
```python
except WorkspaceIsolationError:
    self.idea_pool.update_status(idea_id, "skipped", reason="workspace_error")
```

#### M12: 僵尸进程清理
terminate 后调用 `os.waitpid(pid, os.WNOHANG)` 清理。

#### M13: Symlink 原子替换
```python
tmp_link = target.with_suffix(".tmp_symlink")
tmp_link.symlink_to(source)
tmp_link.rename(target)  # atomic on same filesystem
```

#### M14: 负值内存警告
```python
free = max(0, total_free - reserved)
if total_free < reserved:
    logger.warning("GPU %s: reserved %dMiB > free %dMiB, triggering refresh", gpu_id, reserved, total_free)
```

#### M15: 失败记忆上限
添加 `max_entries` 配置（默认 500），超出时按时间 LRU 淘汰。

#### M22: SSH 超时保留旧状态
超时时 merge 旧 reservations 而非清空。

#### M25: CommandInfo 校验
`__post_init__` 中检查 `self.command` 非空。

---

## Phase 4: TUI/CLI 层（12 个问题）

**目标文件**: `tui/widgets.py`, `tui/app.py`, `tui/view_model.py`, `status_cmd.py`, `demo_cmd.py`, `evaluation_contract.py`
**问题编号**: C6, H16, H17, H19, M5, M16, M17, M26, M27, M28, M29, M30

### 修复清单

#### C6: FrontierFocusPanel IndexError
```python
if frontiers:
    self._update_active(frontiers[0].frontier_id)
```

#### H16: RuntimeError 区分
```python
except RuntimeError as exc:
    if not self._closing:
        logger.error("Unexpected thread error: %s", exc)
```

#### H17: PhaseGate 损坏日志
```python
except (json.JSONDecodeError, OSError) as exc:
    logger.error("experiment_progress.json corrupted: %s, resetting to init", exc)
    return "init"
```

#### H19: view_model None 防护
统一在 `_build_frontier_detail` 入口处规范化：
```python
hypothesis = hypothesis or {}
spec = spec or {}
```

#### M26: 异常捕获细化
将 `except Exception` 替换为 `except (NoMatches, AttributeError, KeyError)`。

#### M27: highlight 竞态
```python
try:
    prev_highlighted = option_list.options[option_list.highlighted].id
except (IndexError, AttributeError):
    prev_highlighted = None
```

#### M28: HTML 注释检测
修正逻辑为：检查是否全部内容都在 `<!-- -->` 内。

#### M29: 类型安全 helper
```python
def _safe_str(val, default: str = "") -> str:
    return str(val).strip() if val is not None else default
```

#### M30: 表头验证宽松化
检查关键列名存在即可，不要求完全匹配。

#### M5: demo_cmd 原子写
所有 `.write_text()` 改为 `atomic_write_text()`。

#### M16: 模板严格模式
```python
env = jinja2.Environment(..., undefined=jinja2.StrictUndefined)
```

#### M17: metric direction 推断
```python
KNOWN_LOWER = {"loss", "val_loss", "error", "perplexity", "cer", "wer"}
if name.lower() in KNOWN_LOWER:
    direction = "lower_is_better"
```

---

## Phase 5: MEDIUM 收尾（8 个剩余）

**问题编号**: M3, M4, M6, M18, M19, M20, M21, M24

| 问题 | 文件 | 修复 |
|------|------|------|
| M3 | results_cmd.py | TSV 转义改用 `csv.QUOTE_MINIMAL` |
| M4 | research_memory.py | 添加 evidence/claims schema 验证 |
| M6 | idea_pool.py | Claim token 添加 30min 过期检查 |
| M18 | role_programs.py | `.write_text()` → `atomic_write_text()` |
| M19 | graph_protocol.py | `.write_text()` → `atomic_write_json()` |
| M20 | control_plane.py | snapshot 加载后验证 `applied_command_ids` 类型 |
| M21 | results_cmd.py | fieldnames 检查 required columns 子集 |
| M24 | agents/opencode.py | `_supports_run_command` 加 `threading.Lock` |

---

## Phase 6: LOW 收尾（18 个）

**问题编号**: L1-L18

全部 LOW 问题批量处理：
- L1: 路径 sanitization 添加碰撞检测
- L2: stdout journal 显式 flush
- L3: 失败记忆异常提升到 info 级别
- L4: stop_after_finalize 添加 docstring
- L5: activity 更新添加 consistency check
- L6: Python env 检测添加 debug 日志
- L7: git 操作统一 60s 超时
- L8: nvidia-smi 超时延长到 30s
- L9: GPU 远程检测添加 OSError 捕获
- L10: git 错误保留完整 args 上下文
- L11: manifest 写入添加 try/except
- L12: GPU allocator 添加简单死锁检测
- L13: failure_memory null check 补全
- L14: 模板上下文 auto_escape
- L15: metric_name 长度/字符验证
- L16: EventJournal 改为流式读取
- L17: demo 日志注入添加 debug 日志
- L18: view_model 查找合并为单次扫描

---

## 测试与部署

每个 Phase 完成后：
1. `pytest tests/ -x -q` 全量通过
2. 单独 git commit：`fix(phase-N): <summary>`
3. SCP 同步到远端所有 runner 版本
