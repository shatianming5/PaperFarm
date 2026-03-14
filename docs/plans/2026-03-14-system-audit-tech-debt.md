# 系统全面审计：技术债清单

> 日期: 2026-03-14
> 状态: 已审计，待修复
> 审计范围: 核心编排层、数据完整性层、Agent 执行层、TUI/CLI 层

---

## 概述

对 open-researcher 本地系统进行了四路并行全面审计，共发现 **73 个潜在问题**：
- CRITICAL: 6 个
- HIGH: 19 个
- MEDIUM: 30 个
- LOW: 18 个

---

## 一、CRITICAL（必须立即修复）

### C1. Worker Claim Slot 泄漏 — 暂停后 break 路径
- **文件**: `src/open_researcher/worker.py:975-980`
- **问题**: 当 `_wait_until_unpaused()` 返回 False（stop requested），代码执行 `break` 退出循环。但 claim slot 在 line 928 已预留，而 break 绕过了所有 `_release_claim_slot()` 调用点（line 933, 1362, 1385）。
- **后果**: worker 永久饥饿，max_claims 计数器不一致。
- **修复方案**: 在 break 前添加 `self._release_claim_slot()`，或将整个 claim 逻辑包裹在 try/finally 中。

### C2. Detached State 无锁并发写
- **文件**: `src/open_researcher/worker.py:278-281, 543`
- **问题**: `_write_detached_state()` 使用 `atomic_write_json()` 但无 FileLock 保护。多 worker 可并发写同一 idea 的 detached state 文件。
- **后果**: 读到部分更新的状态，错过状态转换，PID 判断错误。
- **修复方案**: 为 detached state 文件操作添加 FileLock。

### C3. Detached 运行监控非原子读取
- **文件**: `src/open_researcher/worker.py:513-591`
- **问题**: 监控循环（0.5s 轮询）中，先读 detached_state，再检查进程存活，再查找 matched_row——三步非原子。进程可能在检查间隙退出。
- **后果**: 使用错误的 exit code 做决策，结果丢失。
- **修复方案**: 将状态读取和进程检查包裹在同一个锁内，或使用快照一致性。

### C4. 控制事件写入无 fsync
- **文件**: `src/open_researcher/control_plane.py:97-102`
- **问题**: `_append_event_unlocked()` 写入控制事件后无 `flush()` 或 `os.fsync()`，进程崩溃时事件丢失。
- **后果**: pause/resume/skip 事件可能丢失，重启后状态不一致。
- **修复方案**: 在 `handle.write(line + "\n")` 后添加 `handle.flush()` 和 `os.fsync(handle.fileno())`。

### C5. EventJournal 序列号 TOCTOU 竞态
- **文件**: `src/open_researcher/event_journal.py:36-86`
- **问题**: `_next_seq_unlocked()` 在锁内计算，但如果两个线程同时进入 `emit()`，序列号可能重复。
- **后果**: 事件回放时出现重复序列号，状态重建错误。
- **修复方案**: 确保序列号生成和事件写入在同一个锁的同一个 critical section 内完成。

### C6. FrontierFocusPanel 空列表 IndexError
- **文件**: `src/open_researcher/tui/widgets.py:676`
- **问题**: `update_frontiers()` 中 `frontiers` 为空时访问 `frontiers[0]`。
- **后果**: 无 frontier 时 TUI 直接崩溃。
- **修复方案**: 添加 `if frontiers:` 守卫。

---

## 二、HIGH（高风险，应尽快修复）

### H1. Claim Slot 早期 break 未释放
- **文件**: `worker.py:975-980`
- **问题**: 同 C1，claim slot 在多个 break 路径中未释放。
- **修复**: 统一 try/finally 模式。

### H2. Claim Token 更新失败无验证
- **文件**: `worker.py:1294-1299`
- **问题**: `update_status("pending")` 失败后只记日志 "claim release skipped"，不验证实际状态。
- **后果**: idea_pool 状态不一致，多 worker 竞争同一 idea。

### H3. 资源死锁无重试
- **文件**: `worker.py:944-956`
- **问题**: 检测到 `resource_deadlock` 后直接 `self.stop()` 永久关闭 worker，无延迟重试。
- **后果**: 长时间任务完成后无 worker 可用，实验永久卡住。

### H4. EventJournal FileLock 无超时
- **文件**: `event_journal.py:63`
- **问题**: `emit()` 中 FileLock 使用默认无限等待。锁持有者崩溃时其他进程永久阻塞。
- **修复**: 设置合理超时（如 10s），与 control_plane.py 一致。

### H5. 锁文件残留无清理机制
- **文件**: `.research/*.lock`
- **问题**: 进程崩溃后锁文件残留，无年龄验证或自动清理。
- **修复**: 启动时检查锁文件年龄，过期自动清理。

### H6. 控制状态回放无序列连续性验证
- **文件**: `control_plane.py:138-184`
- **问题**: `_replay_control_state_unlocked()` 不检查序列号连续性，静默跳过损坏行。
- **后果**: 跳过的事件导致重建出错误的控制状态。

### H7. Snapshot 回退使用过期数据
- **文件**: `control_plane.py:187-198`
- **问题**: events.jsonl 被截断时回退到 control.json 快照，但无时间戳对比。
- **后果**: 1 小时前的 "paused=True" 快照被当作当前状态，实验不恢复。

### H8. 序列号碰撞风险
- **文件**: `event_journal.py:36-54`
- **问题**: 文件截断后 `next_seq_unlocked()` 基于剩余最后一条记录计算，可能与已删除记录碰撞。

### H9. results.tsv 读取无锁 (TOCTOU)
- **文件**: `worker.py:1059, 1123, 1171`
- **问题**: `load_results()` 无锁读取，并发写入时 `results_before_count` 过期，匹配逻辑出错。

### H10. results.tsv 重写非原子
- **文件**: `results_cmd.py:102-105`
- **问题**: `augment_result_secondary_metrics()` 用 `csv.DictWriter` 直接写入，崩溃导致文件损坏。
- **修复**: 改用 `atomic_write_text()`。

### H11. Agent 子进程无超时
- **文件**: `agents/base.py:61-99`
- **问题**: `_run_process()` 中 `proc.wait()` 无超时，agent 挂起时 worker 线程永久阻塞。

### H12. Worktree 清理竞态
- **文件**: `plugins/execution/legacy_worktree.py:352-390`
- **问题**: 移除 worktree 与其他 worker 使用 `.worktrees/` 之间无同步。
- **后果**: 孤儿 worktree 目录累积占用磁盘。

### H13. GPU 陈旧预留错误移除
- **文件**: `plugins/execution/legacy_gpu.py:230-260`
- **问题**: 缺少 `started_at` 的合法预留被当作陈旧移除。
- **后果**: 正在运行的实验 GPU 资源被释放。

### H14. Detached 进程监控竞态
- **文件**: `worker.py:472-591`
- **问题**: 超时检查使用 monotonic time，但 detached state 文件写入延迟导致 deadline 计算偏差。

### H15. 资源死锁活锁
- **文件**: `worker.py:944-955`
- **问题**: 多 worker 同时检测到死锁后全部 stop，但无机制防止立即重新启动和再次死锁。

### H16. TUI 静默吞掉 RuntimeError
- **文件**: `tui/app.py:338-341`
- **问题**: `call_from_thread` 中 catch RuntimeError 无法区分 app 关闭和真实线程错误。

### H17. PhaseGate JSON 损坏静默回退
- **文件**: `phase_gate.py:17-24`
- **问题**: `experiment_progress.json` 损坏时返回 "init"，丢失已完成的阶段状态。

### H18. Bootstrap 超时未正确处理
- **文件**: `plugins/bootstrap/prepare.py:45-59`
- **问题**: `subprocess.TimeoutExpired` 异常未被捕获，导致准备阶段意外崩溃。

### H19. view_model 多个可选参数无 None 校验
- **文件**: `tui/view_model.py:373-378`
- **问题**: hypothesis/spec 为 None 时下游代码可能崩溃。

---

## 三、MEDIUM（中等风险）

### M1. activity.json active_workers 计数竞态
- **文件**: `activity.py:43-76`
- **问题**: 两个 worker 同时 `update_worker()` 时 active_workers 可能不一致。

### M2. idea_pool claim_token_seq 类型损坏
- **文件**: `idea_pool.py:216-224`
- **问题**: seq 损坏为字符串时 fallback 为 0，可能产生重复 token。

### M3. TSV 手动转义不完整
- **文件**: `results_cmd.py:197-203`
- **问题**: 不处理 `\r` 和边界引号。应改用 csv 模块的 `QUOTE_MINIMAL`。

### M4. research_memory 图吸收无 schema 验证
- **文件**: `research_memory.py:59-130`
- **问题**: malformed evidence/claim_updates 被静默跳过。

### M5. demo_cmd 多处非原子写入
- **文件**: `demo_cmd.py:177-185, 223, 240-249`
- **问题**: 7 处 `.write_text()` 无原子保护。

### M6. Claim token 无过期机制
- **文件**: `idea_pool.py:173-175`
- **问题**: 崩溃 worker 的 token 永不失效，1 小时后仍能操作。

### M7. skip_current 标志与 idea 更新非原子
- **文件**: `worker.py:982-990`
- **问题**: flag 已清除但 idea 更新失败，skip 信号丢失。

### M8. 暂停检查仅在实验开始前
- **文件**: `worker.py:975`
- **问题**: 运行中不检查暂停状态，用户 pause 后当前实验仍继续。

### M9. GPU 释放异常时资源泄漏
- **文件**: `worker.py:1359-1360`
- **问题**: `gpu_allocator.release()` 异常后 GPU 永远显示 "busy"。

### M10. GPU 遥测线程 daemon 无保证清理
- **文件**: `worker.py:401-410`
- **问题**: `thread.join(timeout=5)` 超时后线程被放弃，持续占用资源。

### M11. Workspace 清理异常后 idea 回 pending
- **文件**: `worker.py:1335-1340`
- **问题**: `WorkspaceIsolationError` 后 fatal error 被记录但 idea 正常释放回 pending。

### M12. Agent terminate 僵尸进程
- **文件**: `agents/base.py:106-116`
- **问题**: `proc.wait(timeout=5)` 对僵尸进程可能无效。

### M13. Worktree symlink 替换非原子
- **文件**: `plugins/execution/legacy_worktree.py:134-141`
- **问题**: 删除旧目录和创建 symlink 之间崩溃导致无 `.research/` 目录。

### M14. GPU effective_free_memory 可能返回负值
- **文件**: `plugins/execution/legacy_gpu.py:312-317`
- **问题**: 陈旧预留数据导致 reserved > free，`max(0, ...)` 掩盖不一致。

### M15. 失败记忆无上限增长
- **文件**: `worker.py:993-1001`
- **问题**: 每次实验都追加，无清理机制，长期运行后文件膨胀。

### M16. 模板渲染缺少变量验证
- **文件**: `init_cmd.py:71-90`
- **问题**: Jinja2 模板可能引用不存在的变量，静默渲染为空。

### M17. 评估合约 metric direction 默认值不安全
- **文件**: `evaluation_contract.py:85-86`
- **问题**: 默认 "higher_is_better" 对 loss 等指标不正确。

### M18. role_programs 模板写入非原子
- **文件**: `role_programs.py:66-74`
- **问题**: `.write_text()` 无原子保护。

### M19. graph_protocol experiment_progress 写入非原子
- **文件**: `graph_protocol.py:24-26`
- **问题**: `experiment_progress.json` 非原子写入。

### M20. control_plane snapshot 恢复无验证
- **文件**: `control_plane.py:35-64`
- **问题**: 截断文件恢复后不验证 `applied_command_ids` 类型。

### M21. results_cmd fieldnames schema 无验证
- **文件**: `results_cmd.py:80-88`
- **问题**: 只检查 empty，不验证列名是否匹配预期 schema。

### M22. GPU 远程检测 SSH 超时静默失败
- **文件**: `plugins/execution/legacy_gpu.py:218-228`
- **问题**: SSH 超时后返回空列表，已有预留状态丢失。

### M23. GPU 幽灵预留无 TTL 时永不清理
- **文件**: `plugins/execution/legacy_gpu.py:262-296`
- **问题**: `reservation_ttl_minutes=0` 时离线 GPU 预留永不清理。

### M24. Agent opencode 并发检测竞态
- **文件**: `agents/opencode.py:48-67`
- **问题**: `_supports_run_command()` 缓存无线程安全保护。

### M25. Bootstrap CommandInfo 无字段验证
- **文件**: `plugins/bootstrap/detection.py:84-91`
- **问题**: command 列表可以为空，下游执行时才报错。

### M26. widgets.py ~12 处 `except Exception` 捕获过宽
- **文件**: `tui/widgets.py:602,678,731,821,1212,...`
- **问题**: 掩盖真实 bug，应捕获具体异常类型。

### M27. FrontierFocusPanel highlight 竞态
- **文件**: `tui/widgets.py:662-676`
- **问题**: highlighted index 在检查和访问之间可能改变。

### M28. status_cmd HTML 注释检测逻辑不完整
- **文件**: `status_cmd.py:33`
- **问题**: `<!--` 无 `-->` 闭合时误判为无内容。

### M29. view_model 类型转换链不安全
- **文件**: `tui/view_model.py:292-297, 305`
- **问题**: `.get()` 链中 None 处理不一致。

### M30. results_cmd 表头验证过于严格
- **文件**: `results_cmd.py:40-42`
- **问题**: 列顺序不同即返回空，无恢复尝试。

---

## 四、LOW（低风险）

### L1. Detached state 路径 sanitization 碰撞
- **文件**: `worker.py:250-251`

### L2. EventJournal stdout 刷新不保证
- **文件**: `event_journal.py:83-85`

### L3. 失败记忆记录异常仅 debug 日志
- **文件**: `worker.py:1330-1333`

### L4. stop_after_finalize 语义不清晰
- **文件**: `worker.py:548-550, 1235, 1371`

### L5. Activity 更新与 worker 状态不一致
- **文件**: `worker.py:935-940`

### L6. Python env 检测无日志
- **文件**: `plugins/bootstrap/detection.py:51-80`

### L7. Git 操作超时不一致
- **文件**: `plugins/execution/legacy_worktree.py:162-228`
- rev-parse 30s, diff 120s, checkout 无超时

### L8. GPU 检测超时过短
- **文件**: `plugins/execution/gpu.py:20-50`
- nvidia-smi 10s 超时在高负载下可能不够。

### L9. OSError 未在 GPU 远程检测中捕获
- **文件**: `plugins/execution/legacy_gpu.py:218-228`

### L10. Worktree git 错误上下文丢失
- **文件**: `plugins/execution/legacy_worktree.py:404-418`

### L11. Worktree manifest 写入异常未捕获
- **文件**: `plugins/execution/legacy_worktree.py:331-342`

### L12. GPU Allocator 无死锁检测
- **文件**: `plugins/execution/gpu.py:53-92`

### L13. 失败记忆 null check 不完整
- **文件**: `worker.py:997-1013`

### L14. 模板注入风险（理论）
- **文件**: `graph_protocol.py:18-21`

### L15. 评估合约 metric_name 未验证
- **文件**: `evaluation_contract.py:42-55`

### L16. EventJournal 全文件读入内存
- **文件**: `event_journal.py:100-115`
- 大文件时内存膨胀。

### L17. Demo 模式日志注入静默失败
- **文件**: `demo_cmd.py:283-286`

### L18. view_model 重复字典查找
- **文件**: `tui/view_model.py:543-555`
- 性能问题，同数据扫描 3 次。

---

## 修复优先级建议

### 第一批（紧急）— 影响运行中实验
1. C1 + H1: Claim slot 泄漏 → try/finally 统一
2. C6: FrontierFocusPanel IndexError → 添加空列表守卫
3. H10: results.tsv 非原子重写 → 改用 atomic_write_text
4. H4: EventJournal 锁超时 → 设置 10s timeout
5. C2: Detached state 加锁

### 第二批（高优）— 数据完整性
6. C4: 控制事件 fsync
7. C5: 序列号原子性
8. H6 + H7: 控制状态回放验证
9. H9: results.tsv 读锁
10. H5: 锁文件清理机制

### 第三批（中优）— 健壮性
11. H3 + H15: 资源死锁重试
12. H11: Agent 子进程超时
13. M26: widgets.py 异常捕获细化
14. M15: 失败记忆上限
15. M6: Claim token 过期机制

### 第四批（低优）— 代码质量
16. 其余 MEDIUM 和 LOW 项
