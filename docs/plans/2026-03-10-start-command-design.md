# Start Command Design — Zero-Config Repo Analysis + TUI Confirmation

**Date**: 2026-03-10
**Status**: Approved

## Problem

当前启动流程摩擦太大：
1. `init` 生成模板 → 2. 手动编辑 `config.yaml` → 3. `run` 启动 Agent
- Agent 的 Phase 1-3（理解项目、文献搜索、设计评估）在后台静默执行，用户看不到过程也没有确认环节
- 用户需要理解模板结构并手动配置指标、方向等

## Solution

新增 `start` 命令，实现三阶段流程：**Scout → Review → Research**

### 用户体验

```bash
# 最简用法（零配置）
open-researcher start

# 指定 Agent + 双 Agent 模式
open-researcher start --agent claude-code --multi

# 指定标签
open-researcher start --tag mar10
```

TUI 启动后弹出目标输入框，用户可输入研究目标（如"减少 val_loss"）或留空让 Agent 自主判断。

### 三阶段流程

```
start → auto init → 启动 TUI → 目标输入弹窗
    │
    ▼
Phase 1: Scout（外部 Agent 执行 scout_program.md）
  产出：
    - project-understanding.md（项目理解）
    - research-strategy.md（研究方向/策略/约束）
    - evaluation.md（评估指标 + 方法）
    - config.yaml（填充 metrics 部分）
  不产出 ideas。
  TUI 实时显示 Agent 日志和分析进度。
    │
    ▼
Phase 2: Review（TUI ReviewScreen）
  展示 Scout 产出，用户可以：
    - [e] 编辑研究策略
    - [m] 编辑评估指标
    - [r] 要求重新分析
    - [Enter] 确认并开始研究
    - [q] 退出
    │
    ▼
Phase 3: Research（现有 Idea Agent + Experiment Agent）
  Idea Agent 读取确认后的策略文件，生成具体 ideas。
  Experiment Agent 执行实验。
  TUI 切换到正常仪表板（5 标签页）。
```

### TUI 状态机

```
GOAL_INPUT → SCOUTING → REVIEWING → EXPERIMENTING
                ↑            │
                └────────────┘  (用户要求重新分析)
```

### TUI Review Screen 布局

```
┌─────────────────────────────────────────────────────────────────┐
│  ✅ Repository Analysis Complete                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📋 Project Understanding                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ (Scout Agent 的项目理解摘要)                              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  🧭 Research Strategy                              [e] edit     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Direction: ...                                          │    │
│  │ Focus areas: ...                                        │    │
│  │ Constraints: ...                                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  🎯 Evaluation Plan                                [m] edit     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Metric: val_loss (lower_is_better)                      │    │
│  │ Command: python train.py --eval-only                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  [Enter] Confirm & Start    [e] Edit Strategy                   │
│  [m] Edit Metrics    [r] Re-analyze    [q] Quit                 │
└─────────────────────────────────────────────────────────────────┘
```

### 与现有命令的关系

| 命令 | 角色 | 变化 |
|------|------|------|
| `start` | **新增** — 推荐入口 | 新命令 |
| `init` | 保留 — 细粒度控制 | 新增 scout_program.md 生成 |
| `run` | 保留 — 跳过 Scout | 不变 |

`start` = auto `init` + Scout Agent + TUI Review + `run --multi`

### Scout Agent 产出

| 文件 | 内容 | Review 中可编辑 |
|------|------|----------------|
| `project-understanding.md` | 项目架构、入口、现有评估 | 只读 |
| `research-strategy.md` | 研究方向、关注领域、约束 | ✅ |
| `evaluation.md` | 主指标、评估命令、基线方法 | ✅ |
| `config.yaml` | metrics 部分填充 | ✅ |

### scout_program.md.j2 模板

```markdown
# Scout Program — Repository Analysis

{% if goal %}
## Research Goal (from user)
{{ goal }}
{% endif %}

## Your Task
Analyze this repository and produce a research strategy.
Do NOT generate specific experiment ideas — that's the job of the Idea Agent.

## Phase 1: Understand the Project
- Read codebase structure, key files, tests, documentation
- Identify: purpose, architecture, entry points, existing benchmarks
- Write to `.research/project-understanding.md`

## Phase 2: Research Related Work
- Search for relevant papers and optimization techniques (if web search available)
- Identify the state of the art and common improvement patterns
- Write to `.research/literature.md`

## Phase 3: Define Research Strategy
- Based on project understanding and related work, define:
  1. Research direction (what to optimize)
  2. Focus areas (2-4 specific areas to explore)
  3. Constraints (what NOT to change)
- Write to `.research/research-strategy.md`

## Phase 4: Design Evaluation
- Define the primary metric (name + direction)
- Define the evaluation command
- Estimate reasonable experiment duration
- Write to `.research/evaluation.md`
- Update `.research/config.yaml` metrics section

## Output Requirements
When done, these files must exist and be filled:
- .research/project-understanding.md
- .research/research-strategy.md
- .research/evaluation.md
- .research/config.yaml (metrics filled)
```

### idea_program.md.j2 修改

在开头新增：

```markdown
## Research Context
Read these files to understand the confirmed research strategy:
- .research/project-understanding.md
- .research/research-strategy.md
- .research/evaluation.md

Generate specific, implementable ideas that align with the
confirmed research direction, focus areas, and constraints.
```

## Code Changes

| 模块 | 变化 | 说明 |
|------|------|------|
| `cli.py` | 修改 | 新增 `start` 命令 |
| `start_cmd.py` | **新建** | start 命令逻辑 |
| `templates/scout_program.md.j2` | **新建** | Scout Agent 指南 |
| `templates/research-strategy.md.j2` | **新建** | 策略空模板 |
| `templates/idea_program.md.j2` | 修改 | 加读取策略文件 |
| `tui/app.py` | 修改 | 新增 app_state 状态机 |
| `tui/modals.py` | 修改 | 新增 GoalInputModal |
| `tui/screens/review.py` | **新建** | ReviewScreen |
| `run_cmd.py` | 修改 | 抽取共用逻辑 |
| `init_cmd.py` | 修改 | 新增 scout 模板生成 |

### 不变的模块

- `agents/*` — Scout 复用同一个 Agent 适配器
- `idea_pool.py`, `worker.py`, `worktree.py` — 不变
- `program.md.j2` — 不变（run 命令用）
- `experiment_program.md.j2` — 不变
