# TUI Visual Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the plain black-and-white TUI with a colorful, structured interface that shows agent phases, idea progress, and structured logs.

**Architecture:** Replace DataTable-based IdeaPoolTable and plain-text AgentStatusWidget with custom Rich-rendered widgets. Add log line classification with Rich markup coloring. Add scroll-lock and minimize functionality to the log panel.

**Tech Stack:** Textual framework, Rich Text markup, Textual ProgressBar, ScrollableContainer

---

### Task 1: Rewrite widgets.py — StatsBar, ExperimentStatusPanel, IdeaListPanel, HotkeyBar

**Files:**
- Modify: `src/open_researcher/tui/widgets.py` (full rewrite)
- Test: `tests/test_tui.py` (update all tests)

**Step 1: Write failing tests for new widgets**

Replace `tests/test_tui.py` entirely:

```python
"""Tests for Textual TUI components."""

from open_researcher.tui.widgets import (
    ExperimentStatusPanel,
    HotkeyBar,
    IdeaListPanel,
    StatsBar,
)


def test_stats_bar_colored_output():
    bar = StatsBar()
    state = {
        "total": 7,
        "keep": 3,
        "discard": 2,
        "crash": 1,
        "best_value": 1.47,
        "primary_metric": "val_loss",
    }
    bar.update_stats(state)
    text = bar.stats_text
    assert "3 kept" in text
    assert "2 disc" in text
    assert "1.47" in text


def test_stats_bar_empty():
    bar = StatsBar()
    bar.update_stats({"total": 0})
    assert "waiting" in bar.stats_text


def test_experiment_status_panel_running():
    panel = ExperimentStatusPanel()
    activity = {
        "status": "running",
        "detail": "implementing code changes",
        "idea": "idea-003",
        "updated_at": "2026-03-09T12:00:00",
    }
    panel.update_status(activity, completed=3, total=10)
    text = panel.status_text
    assert "RUNNING" in text
    assert "idea-003" in text
    assert "3" in text and "10" in text


def test_experiment_status_panel_idle():
    panel = ExperimentStatusPanel()
    panel.update_status(None, completed=0, total=0)
    assert "IDLE" in panel.status_text


def test_experiment_status_panel_baseline():
    panel = ExperimentStatusPanel()
    activity = {"status": "establishing_baseline", "detail": "running baseline"}
    panel.update_status(activity, completed=0, total=5)
    assert "BASELINE" in panel.status_text or "baseline" in panel.status_text


def test_idea_list_panel_renders():
    panel = IdeaListPanel()
    ideas = [
        {"id": "idea-001", "description": "Add dropout", "status": "done",
         "priority": 1, "result": {"metric_value": 1.23, "verdict": "kept"}},
        {"id": "idea-002", "description": "Batch norm", "status": "running",
         "priority": 2, "result": None},
        {"id": "idea-003", "description": "LR warmup", "status": "pending",
         "priority": 3, "result": None},
    ]
    panel.update_ideas(ideas)
    text = panel.ideas_text
    # Running should appear first (sorted)
    lines = text.strip().split("\n")
    assert len(lines) == 3
    # Check running idea has ▶ icon
    assert "▶" in text
    # Check done/kept has ✓
    assert "✓" in text
    # Check pending has ·
    assert "·" in text


def test_idea_list_panel_empty():
    panel = IdeaListPanel()
    panel.update_ideas([])
    assert "No ideas" in panel.ideas_text


def test_hotkey_bar_includes_minimize():
    bar = HotkeyBar()
    rendered = bar.render()
    assert "m" in rendered
    assert "q" in rendered
```

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_tui.py -v`
Expected: ImportError for ExperimentStatusPanel, IdeaListPanel

**Step 3: Implement new widgets**

Replace `src/open_researcher/tui/widgets.py` with:

```python
"""Custom Textual widgets for Open Researcher TUI."""

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


class StatsBar(Static):
    """Top status bar with colored experiment summary."""

    stats_text = reactive("")

    def render(self) -> Text:
        if not self.stats_text:
            return Text("● Open Researcher — starting...", style="dim")
        return Text.from_markup(self.stats_text)

    def update_stats(self, state: dict) -> None:
        total = state.get("total", 0)
        keep = state.get("keep", 0)
        discard = state.get("discard", 0)
        crash = state.get("crash", 0)
        best = state.get("best_value")
        pm = state.get("primary_metric", "")
        branch = state.get("branch", "")

        if total == 0:
            self.stats_text = "[dim]● Open Researcher — waiting for experiments...[/dim]"
            return

        parts = ["[bold]● Open Researcher[/bold]"]
        if branch:
            parts.append(f"[cyan]{branch}[/cyan]")
        parts.append(f"[bold]{total}[/bold] exp")
        counts = []
        if keep:
            counts.append(f"[green]{keep} kept[/green]")
        if discard:
            counts.append(f"[red]{discard} disc[/red]")
        if crash:
            counts.append(f"[yellow]{crash} crash[/yellow]")
        if counts:
            parts.append(" ".join(counts))
        if best is not None:
            parts.append(f"best [bold cyan]{pm}={best:.4f}[/bold cyan]")
        self.stats_text = " │ ".join(parts)


class ExperimentStatusPanel(Static):
    """Prominent panel showing experiment agent phase and progress."""

    status_text = reactive("  -- [IDLE] waiting to start...")
    _progress_ratio = reactive(0.0)

    def render(self) -> Text:
        return Text.from_markup(self.status_text)

    def update_status(
        self, activity: dict | None, completed: int = 0, total: int = 0
    ) -> None:
        if not activity:
            self.status_text = "  [dim]-- \\[IDLE] waiting to start...[/dim]"
            self._progress_ratio = 0.0
            return

        status = activity.get("status", "idle")
        detail = activity.get("detail", "")
        idea = activity.get("idea", "")

        # Phase styling
        phase_styles = {
            "detecting_environment": ("⟳", "cyan", "SETUP"),
            "establishing_baseline": ("⟳", "yellow", "BASELINE"),
            "running": ("▶", "green", "RUNNING"),
            "evaluating": ("⏱", "blue", "EVALUATING"),
            "idle": ("--", "dim", "IDLE"),
            "paused": ("⏸", "yellow", "PAUSED"),
            "analyzing": (">>", "cyan", "ANALYZING"),
            "generating": ("✦", "magenta", "GENERATING"),
            "searching": ("..", "cyan", "SEARCHING"),
        }
        icon, color, label = phase_styles.get(status, ("*", "white", status.upper()))

        lines = [f"  [{color}]{icon} \\[{label}][/{color}]"]
        if idea:
            lines[0] += f" [bold]{idea}[/bold]"
        if detail:
            lines.append(f"    [dim]{detail}[/dim]")

        # Progress bar (text-based)
        if total > 0:
            ratio = completed / total
            bar_width = 20
            filled = int(ratio * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            lines.append(
                f"    [{color}]{bar}[/{color}]  {completed}/{total} ideas"
            )
            self._progress_ratio = ratio

        self.status_text = "\n".join(lines)


class IdeaListPanel(Static):
    """Custom panel rendering each idea as a colored line."""

    ideas_text = reactive("  No ideas yet")

    def render(self) -> Text:
        return Text.from_markup(self.ideas_text)

    def update_ideas(self, ideas: list[dict]) -> None:
        if not ideas:
            self.ideas_text = "  [dim]No ideas yet[/dim]"
            return

        status_order = {"running": 0, "pending": 1, "done": 2, "skipped": 3}
        sorted_ideas = sorted(
            ideas,
            key=lambda i: (
                status_order.get(i["status"], 9),
                i.get("priority", 99),
            ),
        )

        lines = []
        for idea in sorted_ideas:
            sid = idea["status"]
            iid = idea["id"].replace("idea-", "#")
            desc = idea["description"][:72]
            result = idea.get("result")
            verdict = ""
            val = ""

            if result:
                v = result.get("metric_value")
                if v is not None:
                    val = f"{v:.4f}"
                verdict = result.get("verdict", "")

            if sid == "running":
                line = f"  [bold yellow]▶ {iid}  {desc:<72s}  {'--':>8s}  running[/bold yellow]"
            elif sid == "pending":
                line = f"  [dim]· {iid}  {desc:<72s}  {'--':>8s}  pending[/dim]"
            elif sid == "done" and verdict == "kept":
                line = f"  [green]✓ {iid}  {desc:<72s}  {val:>8s}  kept[/green]"
            elif sid == "done" and verdict == "discarded":
                line = f"  [red]✗ {iid}  {desc:<72s}  {val:>8s}  disc[/red]"
            elif sid == "skipped":
                line = f"  [dim]– {iid}  {desc:<72s}  {'--':>8s}  skip[/dim]"
            else:
                line = f"  [dim]? {iid}  {desc:<72s}  {val:>8s}  {sid}[/dim]"

            lines.append(line)

        self.ideas_text = "\n".join(lines)


class HotkeyBar(Static):
    """Bottom bar showing available keyboard shortcuts."""

    def render(self) -> Text:
        t = Text()
        keys = [
            ("p", "ause"),
            ("r", "esume"),
            ("s", "kip"),
            ("a", "dd idea"),
            ("l", "og"),
            ("m", "in/max"),
            ("q", "uit"),
        ]
        for i, (key, rest) in enumerate(keys):
            if i > 0:
                t.append("  ", style="dim")
            t.append(f"[{key}]", style="bold cyan")
            t.append(rest, style="dim")
        return t
```

**Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_tui.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add src/open_researcher/tui/widgets.py tests/test_tui.py
git commit -m "feat: rewrite TUI widgets with Rich colored rendering"
```

---

### Task 2: Update app.py — new compose layout, log lock/minimize, [m] binding

**Files:**
- Modify: `src/open_researcher/tui/app.py`
- Modify: `tests/test_run.py` (if needed for import changes)

**Step 1: Write failing test for log minimize**

Add to `tests/test_tui.py`:

```python
def test_app_has_minimize_binding():
    from open_researcher.tui.app import ResearchApp
    binding_keys = [b.key for b in ResearchApp.BINDINGS]
    assert "m" in binding_keys
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tui.py::test_app_has_minimize_binding -v`
Expected: FAIL (no "m" binding)

**Step 3: Implement updated app.py**

Key changes to `src/open_researcher/tui/app.py`:

1. Import new widget names: `ExperimentStatusPanel`, `IdeaListPanel` instead of old ones
2. Update `compose()`:
   ```python
   def compose(self) -> ComposeResult:
       yield StatsBar(id="stats-bar")
       yield ExperimentStatusPanel(id="exp-status")
       with ScrollableContainer(id="idea-scroll"):
           yield IdeaListPanel(id="idea-list")
       yield RichLog(id="agent-log", wrap=True, markup=True)  # markup=True for colors
       yield HotkeyBar(id="hotkey-bar")
   ```
3. Add `"m"` binding for `action_toggle_log`
4. Add `_log_minimized` state variable
5. `action_toggle_log()`: toggle `#agent-log` height between `1fr` and `3`
6. Update `_refresh_data()` to use new widget classes and pass progress info:
   ```python
   # Refresh experiment status with progress
   ideas = self.pool.all_ideas()
   completed = sum(1 for i in ideas if i["status"] in ("done", "skipped"))
   total = len(ideas)
   self.query_one("#exp-status", ExperimentStatusPanel).update_status(active, completed, total)

   # Refresh idea list
   self.query_one("#idea-list", IdeaListPanel).update_ideas(ideas)
   ```
7. Update `append_log` to use `RichLog.write(Text.from_markup(line))` since `markup=True`

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -x -q`
Expected: All pass

**Step 5: Commit**

```bash
git add src/open_researcher/tui/app.py tests/test_tui.py
git commit -m "feat: update TUI app with new widgets, log minimize, markup support"
```

---

### Task 3: Rewrite styles.css for new layout

**Files:**
- Modify: `src/open_researcher/tui/styles.css`

**Step 1: Rewrite CSS**

```css
Screen {
    background: $surface;
}

#stats-bar {
    dock: top;
    height: 1;
    background: $primary-background;
    color: $text;
    padding: 0 1;
}

#exp-status {
    height: auto;
    min-height: 2;
    max-height: 5;
    border: solid $accent;
    padding: 0 1;
}

#idea-scroll {
    height: auto;
    max-height: 14;
    border: solid $primary;
    overflow-y: auto;
}

#idea-list {
    height: auto;
    padding: 0 1;
}

#agent-log {
    height: 1fr;
    border: solid $primary;
}

#agent-log.minimized {
    height: 3;
    max-height: 3;
}

#hotkey-bar {
    dock: bottom;
    height: 1;
    background: $primary-background;
    color: $text-muted;
    padding: 0 1;
}

/* Modal styles (unchanged) */
AddIdeaModal {
    align: center middle;
}

AddIdeaModal > #dialog {
    width: 60;
    height: auto;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

GPUStatusModal {
    align: center middle;
}

GPUStatusModal > #gpu-dialog {
    width: 80;
    height: auto;
    max-height: 80%;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

LogScreen {
    background: $surface;
}

LogScreen #log-content {
    height: 1fr;
    overflow-y: scroll;
    padding: 0 1;
}

LogScreen #log-footer {
    dock: bottom;
    height: 1;
    background: $primary-background;
    padding: 0 1;
}
```

**Step 2: Run tests**

Run: `python3 -m pytest tests/ -x -q`
Expected: All pass

**Step 3: Commit**

```bash
git add src/open_researcher/tui/styles.css
git commit -m "feat: rewrite TUI CSS with colored borders and minimizable log"
```

---

### Task 4: Log line classification and phase separators in _make_safe_output

**Files:**
- Modify: `src/open_researcher/run_cmd.py` (the `_make_safe_output` function)
- Test: `tests/test_run.py`

**Step 1: Write failing test for log coloring**

Add to `tests/test_run.py`:

```python
def test_make_safe_output_colors_diff_lines(tmp_path):
    from open_researcher.run_cmd import _make_safe_output

    captured = []
    log_file = tmp_path / "test.log"
    cb = _make_safe_output(captured.append, log_file)

    # Simulate post-prompt output
    cb("user")
    cb("thinking")  # ends prompt filtering

    # Now real output
    cb("assistant")  # should become separator
    cb("diff --git a/foo.py b/foo.py")
    cb("+added line")
    cb("-removed line")
    cb("@@ -1,3 +1,4 @@")
    cb("step 200: val loss 1.34")
    cb("ERROR: something broke")
    cb("plain text")

    # Check that lines contain Rich markup
    assert any("[bold" in line for line in captured)  # diff header or separator
    assert any("[green]" in line for line in captured)  # added line
    assert any("[red]" in line for line in captured)  # removed line or error


def test_make_safe_output_phase_separator(tmp_path):
    from open_researcher.run_cmd import _make_safe_output

    captured = []
    log_file = tmp_path / "test.log"
    cb = _make_safe_output(captured.append, log_file)

    cb("user")
    cb("thinking")
    # Should produce a thinking separator
    assert any("Thinking" in line for line in captured)

    cb("some thought")
    cb("assistant")
    # Should produce an acting separator
    assert any("Acting" in line for line in captured)
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_run.py::test_make_safe_output_colors_diff_lines -v`
Expected: FAIL

**Step 3: Implement log line classifier**

Replace `_make_safe_output` in `src/open_researcher/run_cmd.py`:

```python
def _classify_line(line: str, phase: str) -> str:
    """Add Rich markup to a log line based on its content."""
    stripped = line.strip()

    # System messages
    if stripped.startswith("[exp]") or stripped.startswith("[idea]"):
        return f"[bold cyan]{line}[/bold cyan]"

    # Diff coloring
    if stripped.startswith("diff --git"):
        return f"[bold white]{line}[/bold white]"
    if stripped.startswith("file update:"):
        return f"[bold magenta]{line}[/bold magenta]"
    if stripped.startswith("@@"):
        return f"[yellow]{line}[/yellow]"
    if stripped.startswith("+") and not stripped.startswith("+++"):
        return f"[green]{line}[/green]"
    if stripped.startswith("-") and not stripped.startswith("---"):
        return f"[red]{line}[/red]"

    # Training output
    if "step " in stripped and ("loss" in stripped or "iter" in stripped):
        return f"[cyan]{line}[/cyan]"

    # Errors
    if "error" in stripped.lower() or "traceback" in stripped.lower():
        return f"[bold red]{line}[/bold red]"

    # Thinking phase → dim italic
    if phase == "thinking":
        return f"[dim italic]{line}[/dim italic]"

    # Default
    return f"[dim]{line}[/dim]"


def _make_safe_output(app_log_fn, log_path: Path):
    """Create output callback with log coloring and phase separators."""
    state = {"filtering": False, "prompt_done": False, "phase": "acting"}

    def on_output(line: str):
        # 1. Always write raw line to log file
        try:
            with open(log_path, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass

        # 2. Filter prompt echo
        stripped = line.strip()
        if not state["prompt_done"]:
            if stripped == "user":
                state["filtering"] = True
                return
            if state["filtering"] and stripped in ("thinking", "assistant"):
                state["filtering"] = False
                state["prompt_done"] = True
                # Show phase separator
                if stripped == "thinking":
                    state["phase"] = "thinking"
                    try:
                        app_log_fn("[dim]───── 💭 Thinking ─────[/dim]")
                    except Exception:
                        pass
                else:
                    state["phase"] = "acting"
                    try:
                        app_log_fn("[bold]───── ✦ Acting ─────[/bold]")
                    except Exception:
                        pass
                return
            if state["filtering"]:
                return

        # 3. Phase transitions (after prompt is done)
        if stripped == "thinking":
            state["phase"] = "thinking"
            try:
                app_log_fn("[dim]───── 💭 Thinking ─────[/dim]")
            except Exception:
                pass
            return
        if stripped == "assistant":
            state["phase"] = "acting"
            try:
                app_log_fn("[bold]───── ✦ Acting ─────[/bold]")
            except Exception:
                pass
            return
        if stripped in ("user", ""):
            return

        # 4. Classify and color the line
        colored = _classify_line(line, state["phase"])
        try:
            app_log_fn(colored)
        except Exception:
            pass

    return on_output
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/test_run.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/open_researcher/run_cmd.py tests/test_run.py
git commit -m "feat: add log line coloring and phase separators to TUI output"
```

---

### Task 5: Final integration and verification

**Files:**
- All modified files from Tasks 1-4
- Fix any remaining import references

**Step 1: Fix any stale imports**

Check for any remaining references to old widget names (`IdeaPoolTable`, `AgentStatusWidget`):
- `src/open_researcher/tui/app.py` imports
- `tests/test_tui.py` imports
- Any other files referencing old names

**Step 2: Run full test suite**

Run: `python3 -m pytest tests/ -x -q`
Expected: All pass

**Step 3: Run linter**

Run: `python3 -m ruff check src/ tests/`
Expected: Clean

**Step 4: Commit and push**

```bash
git add -A
git commit -m "feat: TUI visual overhaul — colored widgets, log coloring, phase separators"
git push
```
