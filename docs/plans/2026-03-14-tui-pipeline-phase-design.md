# TUI 信息架构优化：Phase Strip + Pipeline Flow

> 日期: 2026-03-14
> 状态: 已批准

## 问题

上一轮改造（ActivityBar + StatsBar 2行 + idle压缩 + Bootstrap折叠）解决了"没有全局状态"的问题，但用户仍感觉"不够一目了然"。深度分析发现 4 个根因：

1. **阶段切换不明显** — scouting → preparing → reviewing → experimenting 切换仅靠文字变化，无视觉反馈
2. **缺少全局进展感** — 只有 "4/10 experiments" 局部进度，没有阶段位置感和 cycle 概念
3. **Agent 之间关系不清** — Manager、Critic、Experiment 并列显示，看不出工作流转关系
4. **信息重复/碎片化** — 进度/指标在 ActivityBar、ExperimentStatusPanel、ExecutionSummaryPanel 三处重复

**根因：TUI 按「组件类型」组织，而非按「用户问题层次」组织。**

## 设计决策

| 决策 | 选择 |
|------|------|
| 阶段显示方式 | 新增 Phase Step Indicator 组件（1行横条） |
| Agent 关系展示 | RoleActivityPanel 改为纵向 Pipeline Flow（带箭头） |
| ExperimentStatusPanel | 保留但简化，去除与 ActivityBar 重复的 phase 逻辑 |
| Phase Strip 位置 | StatsBar 下方，ActivityBar 上方 |

## 改造后的 Command Tab 布局

```
┌─ StatsBar (2行) ───────────────────────────────────────────────┐
│ [Research] OPEN RESEARCHER  research-v1  main  3K 2D 1C  0.85 │
│                               tokens 15K/50K  est.$2.50  14:32│
├─ PhaseStripBar (新增, 1行) ────────────────────────────────────┤
│   ✓ Scout ─── ✓ Prepare ─── ✓ Review ─── ● Experiment         │
├─ ActivityBar ──────────────────────────────────────────────────┤
│ ▶ Experiment Agent  ─  frontier-003                            │
│   "Testing learning rate warmup schedule"                      │
│   ████████████░░░░░░░░░░  4/10 experiments  ~12min             │
│   loss: baseline 1.00 → current 0.92 (▼0.08)  best 0.85       │
├─ 左列                         │ 右列                           │
│ ┌─ Agent Pipeline ────────┐   │ ┌─ Frontier列表 ──┬─ 详情 ──┐ │
│ │   Manager     [idle]    │   │ │ P1 frontier-003 │ Detail  │ │
│ │        ↓                │   │ │ P2 frontier-001 │         │ │
│ │   Experiment  [▶ RUN]   │   │ │ P3 frontier-004 │         │ │
│ │               f-003     │   │ │                 │         │ │
│ │        ↓                │   │ └─────────────────┴─────────┘ │
│ │   Critic      [idle]    │   │                                │
│ └─────────────────────────┘   │                                │
│ ┌─ Bootstrap [✓ completed] ─┐ │                                │
│ └────────────────────────────┘│                                │
│ ┌─ Graph Summary ──────────┐  │                                │
│ └────────────────────────────┘│                                │
└────────────────────────────────┴────────────────────────────────┘
```

## 各组件改造细节

### 1. PhaseStripBar — 新增组件

一行横条，显示研究流程的四个阶段：

```
  ✓ Scout ─── ✓ Prepare ─── ✓ Review ─── ● Experiment
```

**状态映射：**

| app_phase | Scout | Prepare | Review | Experiment |
|-----------|-------|---------|--------|------------|
| scouting | ● 高亮 | ○ 灰色 | ○ 灰色 | ○ 灰色 |
| preparing | ✓ 成功 | ● 高亮 | ○ 灰色 | ○ 灰色 |
| reviewing | ✓ 成功 | ✓ 成功 | ● 高亮 | ○ 灰色 |
| experimenting | ✓ 成功 | ✓ 成功 | ✓ 成功 | ● 高亮 |

**特殊状态：**
- Paused: 当前阶段显示 `⏸` + 珊瑚色
- 连接线：使用 `───` dim 灰色

**样式：**
- 高亮阶段用 `C_PRIMARY` (#8bd5ff)
- 已完成用 `C_SUCCESS` (#7dd4b0)
- 未到达用 `C_DIM` (#8899ab)
- Paused 用 `C_CORAL` (#ff8f70)

### 2. RoleActivityPanel → Agent Pipeline（纵向流水线）

**改前：**
```
Role Activity
▶ Experiment Agent  [RUNNING]
  frontier-003  exec-456
  Testing LR warmup
· Manager    [idle]
· Critic     [idle]
```

**改后：**
```
Agent Pipeline
  Manager     [idle]
       ↓
  Experiment  [▶ RUNNING]
              frontier-003
       ↓
  Critic      [idle]
```

**规则：**
- 固定顺序：Manager → Experiment → Critic（按实际工作流）
- 活跃 agent: 名称加粗 + 状态芯片 + frontier_id（如有）
- Idle agent: 灰色一行 `名称  [idle]`
- 箭头 `↓` 用 dim 灰色
- 活跃 agent 的 detail 不再单独显示（已在 ActivityBar 中展示，避免重复）

### 3. ExperimentStatusPanel — 简化

**去除的内容：**
- Scouting/Preparing/Reviewing 的 phase 展示逻辑（交给 PhaseStripBar + ActivityBar）

**保留的内容：**
- 当前活跃实验的 frontier_id + execution_id
- 进度条（与 ActivityBar 不同视角：这里用彩色条，ActiveBar 用文字进度）
- Role label

**Idle 状态简化为：**
```
Execution Focus  [IDLE]
Waiting for next cycle.
```

## 不改的部分

- StatsBar — 保持 2 行，不变
- ActivityBar (SessionChromeBar) — 保持 6 状态不变
- FrontierFocusPanel / FrontierDetailPanel — 保持不变
- BootstrapStatusPanel — 保持折叠行为不变
- ResearchGraphSummaryPanel — 保持不变
- LineageTimelinePanel — 保持不变
- MetricChart / RecentExperiments — 保持不变
- ExecutionSummaryPanel — 保持不变
- 所有快捷键 — 保持不变

## 涉及文件

| 文件 | 改动 |
|------|------|
| `widgets.py` | 新增 PhaseStripBar 类；RoleActivityPanel 改为 Pipeline Flow；ExperimentStatusPanel 简化 |
| `app.py` | compose() 添加 PhaseStripBar；_apply_refresh_data 传 phase 给 PhaseStripBar |
| `styles.css` | PhaseStripBar 样式（背景色、padding、margin） |
