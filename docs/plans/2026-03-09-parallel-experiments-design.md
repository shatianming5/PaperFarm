# Parallel Experiment Execution Design

> Date: 2026-03-09

## Summary

重构 Experiment Agent 为 Master + Sub-agent 架构，支持多 idea 并发跑在不同 GPU 上，以及单 idea 多卡 DDP 训练。同时修复 TUI 显示问题，改用实时日志流。

## Architecture

```
Idea Agent (1 process)          Experiment Master Agent (claude/codex)
  │                                │
  │ 生成 idea → idea_pool.json     │ 读 idea pool + GPU 状态
  │ 分析实验结果                    │ 决定分配策略
  │                                │
  │                                ├─ worktree-001/: claude -p "idea-001, GPU=0"
  │                                ├─ worktree-002/: claude -p "idea-002, GPU=1,2 DDP"
  │                                ├─ worktree-003/: claude -p "idea-003, GPU=3"
  │                                │
  │                                │ 等待完成 → 收集结果 → 合并/丢弃 → 循环
```

### Key Decisions

1. **Master + Sub-agent pattern**: 一个 Master Agent 做调度决策，spawn sub-agent 执行
2. **Git Worktree 隔离**: 每个并发实验在独立 worktree 中，不冲突
3. **Master 限制**: 只有 Claude Code 和 Codex 支持 sub-agent（可通过 Bash 调用子进程）
4. **智能 GPU 分配**: Master Agent 根据 idea 数量 / 优先级 / gpu_hint 决定分配

### GPU Allocation Strategy

idea_pool.json 新增 `gpu_hint` 字段：
- `"auto"` (默认): Master 自行决定
- `1`: 单卡
- `2`, `4`, `8`: 指定卡数
- `"all"`: 所有可用 GPU

Master 决策逻辑（在 prompt 中指导，非硬编码）：
- pending ideas >= 可用 GPU: 每 idea 1 卡，最大并行
- pending ideas < 可用 GPU: 高优先级 idea 分更多卡
- 有 gpu_hint: 尊重标注
- 单 idea 多卡: 指示 sub-agent 用 torchrun/DDP

### Worker Lifecycle

1. Master 发现空闲 GPU + pending idea
2. `git worktree add .research/worktrees/w-{idea_id} -b exp/{idea_id}`
3. 复制 `.research/` 共享文件到 worktree（或 symlink）
4. 生成 worker prompt 文件（含 idea 描述 + GPU 分配 + 评估方法）
5. `CUDA_VISIBLE_DEVICES=X claude -p "$(cat worker_prompt.md)"` in worktree dir
6. Worker 完成 → Master 检查结果:
   - 好: `git merge exp/{idea_id}`, 记录 results.tsv
   - 差: 丢弃 worktree
7. 清理: `git worktree remove`, 释放 GPU, 更新 idea pool

### Shared State (file-locked)

- `idea_pool.json`: Master 负责 claim/update（sub-agent 不直接写）
- `activity.json`: Master 写入 `workers` 数组记录各 worker 状态
- `results.tsv`: Master 负责追加
- `control.json`: 全局暂停/恢复

### activity.json Format

```json
{
  "idea_agent": {"status": "analyzing", "detail": "..."},
  "experiment_master": {
    "status": "scheduling",
    "workers": [
      {"id": "w-001", "idea": "idea-001", "gpus": [0], "status": "evaluating", "started_at": "..."},
      {"id": "w-002", "idea": "idea-002", "gpus": [1, 2], "status": "coding", "started_at": "..."}
    ],
    "gpu_total": 4,
    "gpu_active": 3
  }
}
```

## TUI Redesign

### Problems with Current TUI

1. `AgentPanel` extends `Widget` — no scrolling, long content clipped
2. Only shows last 5 log lines, truncated to 70 chars
3. Thread safety: list append from agent threads, read from main thread
4. activity.json dependency: panels show "idle" if agent doesn't write it
5. No real-time log streaming

### New Layout

```
┌─ Open Researcher | 12 exp | 8 kept | best val_loss=1.234 ─────────┐
├─ Idea Pool (3 pending / 15 total) ────────────────────────────────┤
│ >> #003 Cosine annealing warmup  [RUNNING GPU:0]                  │
│ >> #005 Gradient accumulation    [RUNNING GPU:1,2 DDP]            │
│    #008 Knowledge distillation   [pending] pri:3                  │
│ -- #001 Baseline                 [kept 1.8821]                    │
├─ Idea Agent ──────────────────┬─ Experiment Master ───────────────┤
│ (RichLog - 实时滚动日志流)    │ Workers: 3/4 GPU active          │
│                               │ GPU 0: idea-003 [evaluating]     │
│ > analyzing repo structure... │ GPU 1,2: idea-005 [coding] DDP   │
│ > found 3 optimization...    │ GPU 3: idea-007 [evaluating]     │
│ > generating idea-008...     │                                   │
│ > wrote idea_pool.json       │ (RichLog - master agent 日志)     │
│                               │ > spawned worker w-003 on GPU 0  │
│                               │ > idea-003 val_loss=1.75 ✓       │
├───────────────────────────────┴───────────────────────────────────┤
│ [p]ause [r]esume [s]kip [a]dd idea [g]pu [l]og [q]uit           │
└───────────────────────────────────────────────────────────────────┘
```

### Widget Changes

- **AgentPanel → RichLog**: 用 Textual 的 `RichLog` 替代自定义 `Widget`，支持实时滚动
- **Thread-safe output**: 用 `app.call_from_thread()` 安全地从 agent 线程更新 UI
- **Experiment Panel split**: 上半部分是 worker 状态列表（从 activity.json 读取），下半部分是 Master agent 的实时日志
- **Idea Pool**: 增加 GPU 分配信息显示

## File Changes

| File | Change |
|------|--------|
| `gpu_manager.py` | `allocate_group(n)` 分配 N 张连续 GPU |
| `idea_pool.py` | 新增 `gpu_hint` 字段, `claim_idea()` 原子操作 |
| `experiment_program.md.j2` | 重写为 Master 调度指令 |
| 新增 `worker_prompt.md.j2` | Sub-agent 的执行指令模板 |
| `run_cmd.py` | Master agent 线程 + output 汇总 |
| `tui/widgets.py` | AgentPanel → RichLog, 新增 WorkerStatusPanel |
| `tui/app.py` | call_from_thread, 多 worker activity 读取 |
| `activity.py` | 支持 `workers` 数组格式 |
| `tui/styles.css` | 布局调整适配新组件 |

## Compatibility

- Master 模式仅支持 Claude Code 和 Codex（有 sub-agent 能力）
- 单 agent 模式 (`open-researcher run`) 不受影响，保持向后兼容
- 无 GPU 环境（CPU only）: Master 检测到 0 GPU，退化为串行执行
