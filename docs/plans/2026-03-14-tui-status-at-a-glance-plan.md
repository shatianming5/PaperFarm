# TUI "全局状态一目了然" 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 改造 TUI Command 页，让用户一眼看清当前活动、进度和指标变化。

**Architecture:** 替换 SessionChromeBar 为 ActivityBar（根据 6 种状态切换显示），扩展 StatsBar 吸收配置信息，压缩左列 idle 角色和已完成 bootstrap。进度条引入高水位机制防止倒退。

**Tech Stack:** Textual (Python TUI), Rich markup, dataclass

---

### Task 1: view_model.py — SessionChrome 新增字段 + 进度计算

**Files:**
- Modify: `src/open_researcher/tui/view_model.py` (SessionChrome dataclass + build_dashboard_state)

**Step 1: 给 SessionChrome 添加 last_result 字段**

在 SessionChrome dataclass 末尾添加：

```python
    # Last experiment result (for idle display)
    last_result_frontier_id: str = ""
    last_result_verdict: str = ""
    last_result_metric: float | None = None
    last_result_description: str = ""
```

**Step 2: 在 build_dashboard_state 中填充 last_result 字段**

在构造 SessionChrome 之前，从 rows 提取最后一个结果：

```python
# Extract last result for ActivityBar idle display
_last_frontier_id = ""
_last_verdict = ""
_last_metric: float | None = None
_last_description = ""
if rows:
    _last_row = rows[-1]
    _last_verdict = str(_last_row.get("status", "")).strip()
    _last_description = _short_text(str(_last_row.get("description", "")).strip(), limit=60)
    try:
        _last_metric = float(_last_row.get("metric_value", ""))
    except (TypeError, ValueError):
        pass
    _secondary = _last_row.get("secondary_metrics")
    if isinstance(_secondary, str):
        try:
            _secondary = json.loads(_secondary)
        except (json.JSONDecodeError, TypeError):
            _secondary = {}
    if isinstance(_secondary, dict):
        _trace = _secondary.get("_open_researcher_trace")
        if isinstance(_trace, dict):
            _last_frontier_id = str(_trace.get("frontier_id", "")).strip()
```

然后在 SessionChrome 构造器中加入这 4 个字段。

**Step 3: 运行测试验证**

Run: `python3 -m pytest tests/ -x -q --timeout=30 -k "test_build_dashboard or test_session"`
Expected: PASS

**Step 4: Commit**

```
feat(view_model): add last_result fields to SessionChrome
```

---

### Task 2: widgets.py — StatsBar 扩展为 2 行

**Files:**
- Modify: `src/open_researcher/tui/widgets.py` (StatsBar.update_stats)

**Step 1: 修改 update_stats 签名，接收 token/cost 参数**

```python
def update_stats(
    self,
    state: dict,
    phase: str = "",
    paused: bool = False,
    data_errors: list[str] | None = None,
    tokens_used: int = 0,
    token_budget: int = 0,
    estimated_cost: float = 0.0,
) -> None:
```

**Step 2: 在 update_stats 中构建第 2 行**

在现有 `right` 列表拼接完成后，新增第 2 行：

```python
line1 = "  ".join(left) + sep + "  ".join(right)

# Line 2: token/cost info (merged from old SessionChromeBar)
line2_parts: list[str] = []
if tokens_used > 0:
    if token_budget > 0:
        ratio = tokens_used / token_budget
        line2_parts.append(
            f"[{C_DIM}]tokens[/] [{C_TEXT}]{tokens_used:,}[/]"
            f"/[{C_TEXT}]{token_budget:,}[/] ({ratio:.0%})"
        )
    else:
        line2_parts.append(f"[{C_DIM}]tokens[/] [{C_TEXT}]{tokens_used:,}[/]")
    if estimated_cost > 0:
        line2_parts.append(f"[{C_DIM}]est.[/] [{C_SECONDARY}]${estimated_cost:.2f}[/]")
if data_errors:
    line2_parts.append(f"[{C_ERROR}]data errors: {', '.join(data_errors)}[/]")

if line2_parts:
    self.stats_text = line1 + "\n" + "  ".join(line2_parts)
else:
    self.stats_text = line1
```

**Step 3: 修改 app.py 中调用 update_stats 的地方，传递 token/cost 参数**

在 `_apply_refresh_data` 中：

```python
self.query_one("#stats-bar", StatsBar).update_stats(
    state,
    phase=self.app_phase,
    paused=dashboard.session.paused,
    data_errors=data_errors or [],
    tokens_used=dashboard.session.tokens_used,
    token_budget=dashboard.session.token_budget,
    estimated_cost=dashboard.session.estimated_cost,
)
```

**Step 4: 运行测试**

Run: `python3 -m pytest tests/ -x -q --timeout=30`
Expected: PASS

**Step 5: Commit**

```
feat(StatsBar): expand to 2 lines with token/cost info
```

---

### Task 3: widgets.py — SessionChromeBar → ActivityBar 重写

**Files:**
- Modify: `src/open_researcher/tui/widgets.py` (SessionChromeBar class)

**Step 1: 重写 update_chrome 方法**

将 `update_chrome(self, chrome: SessionChrome)` 改为接收活动状态参数：

```python
def update_chrome(
    self,
    chrome: SessionChrome,
    *,
    active_role: RoleStatus | None = None,
    phase: str = "",
    completed: int = 0,
    total: int = 0,
) -> None:
```

**Step 2: 实现 6 种状态的显示逻辑**

```python
def update_chrome(
    self,
    chrome: SessionChrome,
    *,
    active_role: RoleStatus | None = None,
    phase: str = "",
    completed: int = 0,
    total: int = 0,
) -> None:
    metric_name = escape(chrome.primary_metric or "metric")

    # 进度条
    def _progress_line(completed: int, total: int, suffix: str = "") -> str:
        bar_width = 24
        if total > 0:
            filled = min(int(bar_width * completed / max(total, 1)), bar_width)
            bar = f"[{C_PRIMARY}]{'█' * filled}[/][{C_DIM}]{'░' * (bar_width - filled)}[/]"
            return f"  {bar}  [{C_TEXT}]{completed}/{total}[/]{' ' + suffix if suffix else ''}"
        return f"  [{C_DIM}]No experiments yet[/]"

    # 指标行
    def _metric_line() -> str:
        baseline = _format_metric(chrome.baseline_value)
        current = _format_metric(chrome.current_value)
        best = _format_metric(chrome.best_value)
        delta = ""
        if chrome.baseline_value is not None and chrome.current_value is not None:
            d = chrome.current_value - chrome.baseline_value
            improved = d < 0 if chrome.direction == "lower_is_better" else d > 0
            color = C_SUCCESS if improved else C_CORAL
            arrow = "▼" if d < 0 else "▲"
            delta = f" [{color}]({arrow}{abs(d):.4f})[/]"
        return (
            f"  [{C_DIM}]{metric_name}:[/] "
            f"[{C_DIM}]baseline[/] [{C_INFO}]{baseline}[/] → "
            f"[{C_DIM}]current[/] [{C_SECONDARY}]{current}[/]{delta}  "
            f"[{C_DIM}]best[/] [bold {C_BEST}]{best}[/]"
        )

    # 状态 F: Paused (优先级最高)
    if chrome.paused:
        line1 = f"[bold {C_CORAL}]⏸ PAUSED[/] [{C_DIM}]— Press [bold {C_INFO}]r[/] to resume[/]"
        last = self._last_result_line(chrome)
        lines = [line1, last, _progress_line(completed, total)]
        self.chrome_text = "\n".join(lines)
        return

    # 状态 C: Scouting
    if phase == "scouting":
        detail = escape((active_role.detail if active_role else "") or "Analyzing repository structure and evaluation path")
        lines = [
            f"[bold {C_PRIMARY}]Scout Agent[/] [{C_DIM}]— Analyzing repository[/]",
            f"  [{C_TEXT}]{detail}[/]",
        ]
        self.chrome_text = "\n".join(lines)
        return

    # 状态 D: Preparing
    if phase == "preparing":
        detail = escape((active_role.detail if active_role else "") or "Installing dependencies and running smoke test")
        lines = [
            f"[bold {C_WARNING}]Repo Prepare[/] [{C_DIM}]— Setting up environment[/]",
            f"  [{C_TEXT}]{detail}[/]",
        ]
        self.chrome_text = "\n".join(lines)
        return

    # 状态 E: Reviewing
    if phase == "reviewing":
        lines = [
            f"[bold {C_SKY}]Review Gate[/] [{C_DIM}]— Waiting for operator confirmation[/]",
            f"  [{C_DIM}]Approve the research plan to start experimenting[/]",
        ]
        self.chrome_text = "\n".join(lines)
        return

    # 状态 A: 有 agent 活跃
    if active_role and active_role.status != "idle":
        role_label = escape(active_role.label)
        frontier = escape(active_role.frontier_id or "")
        detail = escape(active_role.detail or "")
        status_chip = _chip(
            active_role.status.replace("_", " "),
            fg="#08111a",
            bg=_status_color(active_role.status),
        )
        line1 = f"[bold {C_TEXT}]▶ {role_label}[/]  {status_chip}"
        if frontier:
            line1 += f"  [{C_PRIMARY}]{frontier}[/]"
        lines = [line1]
        if detail:
            lines.append(f"  [{C_TEXT}]{detail}[/]")
        lines.append(_progress_line(completed, total))
        lines.append(_metric_line())
        self.chrome_text = "\n".join(lines)
        return

    # 状态 B: 所有 agent idle
    last = self._last_result_line(chrome)
    lines = [last, _progress_line(completed, total, "Idle — waiting for next cycle")]
    self.chrome_text = "\n".join(lines)

@staticmethod
def _last_result_line(chrome: SessionChrome) -> str:
    """Format the last experiment result for idle/paused display."""
    if not chrome.last_result_verdict:
        return f"[{C_DIM}]No experiments completed yet[/]"
    verdict = chrome.last_result_verdict
    color = C_SUCCESS if verdict == "keep" else (C_WARNING if verdict == "discard" else C_ERROR)
    icon = "✓" if verdict == "keep" else ("▸" if verdict == "discard" else "✗")
    frontier = escape(chrome.last_result_frontier_id or "?")
    metric = _format_metric(chrome.last_result_metric)
    delta = ""
    if chrome.last_result_metric is not None and chrome.baseline_value is not None:
        d = chrome.last_result_metric - chrome.baseline_value
        improved = d < 0 if chrome.direction == "lower_is_better" else d > 0
        delta_color = C_SUCCESS if improved else C_CORAL
        arrow = "▼" if d < 0 else "▲"
        delta = f" [{delta_color}](vs baseline {arrow}{abs(d):.4f})[/]"
    return f"[{color}]{icon} Last: {frontier} {verdict}[/]  [{C_INFO}]{metric}[/]{delta}"
```

**Step 3: 修改 app.py 中的 update_chrome 调用**

在 `_apply_refresh_data` 中替换原来的调用：

```python
# Find the active role
active_role = None
for role in dashboard.roles:
    if role.status != "idle":
        active_role = role
        break

# Progress with high-water mark
completed = dashboard.session.keep + dashboard.session.discard + dashboard.session.crash
self._progress_total_high_water = max(
    getattr(self, "_progress_total_high_water", 0),
    completed + dashboard.graph.frontier_runnable,
    len(rows),
)
progress_total = self._progress_total_high_water

self.query_one("#session-chrome", SessionChromeBar).update_chrome(
    dashboard.session,
    active_role=active_role,
    phase=self.app_phase,
    completed=completed,
    total=progress_total,
)
```

**Step 4: 在 app.py 顶部 imports 添加 RoleStatus（如尚未导入）**

需要确认 RoleStatus 是否已在 app.py 的 view_model import 中。如果没有，添加到 view_model import 行。

**Step 5: 运行测试**

Run: `python3 -m pytest tests/ -x -q --timeout=30`
Expected: PASS

**Step 6: Commit**

```
feat(ActivityBar): replace SessionChromeBar with phase-aware activity display
```

---

### Task 4: widgets.py — RoleActivityPanel 压缩 idle 角色

**Files:**
- Modify: `src/open_researcher/tui/widgets.py` (RoleActivityPanel.update_roles)

**Step 1: 修改 update_roles 中的角色渲染逻辑**

将 idle 角色压缩为单行：

```python
def update_roles(self, roles: list[RoleStatus], *, paused: bool = False, skip_current: bool = False) -> None:
    if not roles:
        self.roles_text = _empty_state("role activity")
        return

    header_bits = [f"[bold {C_TEXT}]Role Activity[/]"]
    if paused:
        header_bits.append(_chip("Paused", fg="#08111a", bg=C_CORAL))
    if skip_current:
        header_bits.append(_chip("Skip", fg="#08111a", bg=C_WARNING))
    lines = ["  ".join(header_bits)]

    for role in roles:
        if role.status == "idle":
            # Compressed single-line for idle roles
            lines.append(f"[{C_DIM}]· {escape(role.label)}  [idle][/]")
            continue

        # Full display for active roles
        color = _status_color(role.status)
        status_chip = _chip(_role_label(role.status), fg="#08111a", bg=color)
        meta = []
        if role.frontier_id:
            meta.append(f"[{C_PRIMARY}]{escape(role.frontier_id)}[/]")
        if role.execution_id:
            meta.append(f"[{C_DIM}]{escape(role.execution_id)}[/]")
        if role.worker_count:
            meta.append(f"[{C_INFO}]{role.worker_count} worker(s)[/]")
        detail = escape(role.detail or "working")
        lines.append(f"[bold {C_TEXT}]▶ {escape(role.label)}[/]  {status_chip}")
        if meta:
            lines.append(f"  {'  '.join(meta)}")
        lines.append(f"  [{C_TEXT}]{detail}[/]")
        lines.append("")

    self.roles_text = "\n".join(lines).rstrip()
```

**Step 2: 运行测试**

Run: `python3 -m pytest tests/ -x -q --timeout=30`
Expected: PASS

**Step 3: Commit**

```
feat(RoleActivityPanel): compress idle roles to single line
```

---

### Task 5: widgets.py — BootstrapStatusPanel 完成后折叠

**Files:**
- Modify: `src/open_researcher/tui/widgets.py` (BootstrapStatusPanel.update_summary)

**Step 1: 在 update_summary 开头添加折叠判断**

```python
def update_summary(self, summary: BootstrapSummary) -> None:
    # Fold to single line when bootstrap is completed
    if summary.status in ("completed", "resolved", "cached"):
        self.summary_text = (
            f"[bold {C_TEXT}]Bootstrap[/]  "
            f"{_chip(summary.status, fg='#08111a', bg=C_SUCCESS)}"
        )
        return

    # ... rest of existing code unchanged ...
```

**Step 2: 运行测试**

Run: `python3 -m pytest tests/ -x -q --timeout=30`
Expected: PASS

**Step 3: Commit**

```
feat(BootstrapStatusPanel): fold to one line when completed
```

---

### Task 6: styles.css — ActivityBar 样式微调

**Files:**
- Modify: `src/open_researcher/tui/styles.css`

**Step 1: 确保 hero-card 样式适用于 ActivityBar**

SessionChromeBar 已经使用 `classes="hero-card"`，CSS 不变。如果需要微调 ActivityBar 的内边距或边框：

```css
/* 无需修改 — hero-card 已正确覆盖 */
```

此步骤可能不需要任何改动，因为 SessionChromeBar 的 CSS class (`hero-card`) 保持不变。

**Step 2: Commit (如有改动)**

```
style: adjust ActivityBar hero-card styling
```

---

### Task 7: 全量测试 + 远程部署

**Step 1: 运行全量测试**

Run: `python3 -m pytest tests/ -x -q --timeout=30`
Expected: 760 passed

**Step 2: 同步到远程服务器**

```bash
scp src/open_researcher/tui/view_model.py zechuan@222.200.185.183:/mnt/SSD1_8TB/zechuan/open-researcher/src/open_researcher/tui/view_model.py
scp src/open_researcher/tui/widgets.py zechuan@222.200.185.183:/mnt/SSD1_8TB/zechuan/open-researcher/src/open_researcher/tui/widgets.py
scp src/open_researcher/tui/app.py zechuan@222.200.185.183:/mnt/SSD1_8TB/zechuan/open-researcher/src/open_researcher/tui/app.py
```

**Step 3: 最终 Commit + Push**

```
feat: TUI status-at-a-glance — ActivityBar, StatsBar, compressed roles
```
