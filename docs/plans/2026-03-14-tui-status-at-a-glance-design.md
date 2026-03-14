# TUI "全局状态一目了然" 设计方案

> 日期: 2026-03-14
> 状态: 待批准

## 问题

用户打开 TUI 的 Command 页后，无法一眼看清：
1. **现在在干嘛** — 哪个 agent 活跃、在做哪个 frontier
2. **进度到哪了** — 做了几个实验、还剩多少
3. **效果如何** — 指标是否在改善

原因：SessionChromeBar 显示的是配置信息（protocol/mode/branch），活跃 agent 藏在左列 RoleActivityPanel 中三个角色并列，需要用户自己找。

## 设计决策

| 决策 | 选择 |
|------|------|
| ActivityBar 位置 | 替换 SessionChromeBar |
| 原配置信息去向 | 合并到 StatsBar |
| Idle 状态显示 | 上一次实验结果 |
| 左列优化 | Bootstrap 完成后折叠；RoleActivity 只高亮活跃 agent |

## 改造后的布局

```
┌─ StatsBar (顶部固定，扩展) ──────────────────────────────────────────┐
│ [Research] OPEN RESEARCHER  research-v1  main │ 3K 2D 1C  best=0.85 │
│                                    tokens 15K/50K  est.$2.50  14:32 │
├─ ActivityBar (替换 SessionChromeBar) ────────────────────────────────┤
│ ▶ Experiment Agent  ─  frontier-003                                 │
│   "Testing learning rate warmup schedule"                           │
│   ████████████░░░░░░░░░░  4/10 experiments  ~12min                  │
│   loss: baseline 1.00 → current 0.92 (▼0.08)  best 0.85            │
├─ 左列                          │ 右列                               │
│ ┌─ RoleActivity ─────────┐     │ ┌─ Frontier列表 ──┬─ 详情 ────┐   │
│ │ ▶ Experiment [RUNNING]  │     │ │ P1 frontier-003 │ Detail... │   │
│ │   frontier-003          │     │ │ P2 frontier-001 │           │   │
│ │ · Manager    [idle]     │     │ │ P3 frontier-004 │           │   │
│ │ · Critic     [idle]     │     │ │                 │           │   │
│ └────────────────────────┘     │ └─────────────────┴───────────┘   │
│ ┌─ Bootstrap [✓ completed] ─┐  │                                    │
│ └────────────────────────────┘ │                                    │
│ ┌─ Graph Summary ──────────┐   │                                    │
│ └────────────────────────────┘ │                                    │
└─────────────────────────────────────────────────────────────────────┘
```

## 各组件改造细节

### 1. StatsBar — 扩展为 2 行

**第 1 行（不变）：** 相位徽章 + 项目名 + protocol + branch + 结果计数 + 最佳值
**第 2 行（新增）：** token 用量 + 预估成本 + 数据刷新时间 + PAUSED 标记

合并原 SessionChromeBar 中的 token/cost 信息。

### 2. ActivityBar — 替换 SessionChromeBar

根据当前状态显示不同内容：

#### 状态 A：有 agent 活跃（最常见）
```
▶ Experiment Agent  ─  frontier-003
  "Testing learning rate warmup schedule"
  ████████████░░░░░░░░░░  4/10 experiments  ~12min
  loss: baseline 1.00 → current 0.92 (▼0.08)  best 0.85
```

- 第 1 行：活跃角色名 + frontier_id
- 第 2 行：hypothesis_summary 或 spec_summary（描述在做什么）
- 第 3 行：进度条 + completed/total + 预估剩余时间
- 第 4 行：指标概览（baseline → current + delta + best）

#### 状态 B：所有 agent idle
```
✓ Last: frontier-002 kept  loss=0.88 (vs baseline ▼0.12)
  ████████████░░░░░░░░░░  4/10 experiments  Idle — waiting for next cycle
```

- 第 1 行：上次实验结果（frontier + verdict + metric + delta）
- 第 2 行：总体进度 + idle 提示

#### 状态 C：Scouting 阶段
```
🔍 Scout Agent — Analyzing repository structure and evaluation path
  Scanning docs, configs, and training scripts...
```

#### 状态 D：Preparing 阶段
```
⚙ Repo Prepare — Installing dependencies and running smoke test
  install [✓]  data [✓]  smoke [▶ running...]
```

#### 状态 E：Reviewing 阶段
```
⏸ Review Gate — Waiting for operator confirmation
  Press [r] to approve and start experimenting
```

#### 状态 F：Paused
```
⏸ PAUSED — Press [r] to resume
  Last: frontier-002 kept  loss=0.88  4/10 experiments
```

### 3. RoleActivityPanel — 压缩 idle 角色

**活跃角色（status != idle）：** 保持原格式（2-3 行详情）
**Idle 角色：** 压缩为一行灰色文字 `· Manager [idle]`

示例：
```
Role Activity
▶ Experiment Agent  [RUNNING]
  frontier-003  exec-456  1 worker(s)
  Evaluating training run with modified LR schedule
· Manager    [idle]
· Critic     [idle]
```

### 4. BootstrapStatusPanel — 完成后折叠

- `status in ("completed", "resolved", "cached")` → 显示为一行：`Bootstrap [✓ completed]`
- 其他状态 → 保持当前多行格式不变

### 5. 进度条计算修正

当前问题：`total = max(completed + runnable, len(rows), len(frontiers))` 会导致进度倒退。

修正为：
```python
# total 只能单调增加
self._progress_total_high_water = max(
    self._progress_total_high_water,
    completed + dashboard.graph.frontier_runnable,
    len(rows),
)
total = self._progress_total_high_water
```

## 不改的部分

- FrontierFocusPanel / FrontierDetailPanel — 保持不变
- ResearchGraphSummaryPanel — 保持不变
- LineageTimelinePanel — 保持不变
- Execution / Logs / Docs 标签页 — 保持不变
- HotkeyBar — 保持不变
- 所有快捷键 — 保持不变

## 涉及文件

| 文件 | 改动 |
|------|------|
| `widgets.py` | StatsBar 扩展、SessionChromeBar → ActivityBar 重写、RoleActivityPanel 压缩 idle、BootstrapStatusPanel 折叠 |
| `app.py` | `_apply_refresh_data` 传参调整、进度高水位 |
| `view_model.py` | SessionChrome 新增字段（last_result、progress 估算） |
| `styles.css` | ActivityBar 样式 |
