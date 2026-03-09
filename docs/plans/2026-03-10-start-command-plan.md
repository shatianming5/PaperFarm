# Start Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `start` command that provides a zero-config, one-command experience: auto-init → Scout Agent analyzes repo → TUI Review → Idea+Experiment Agents run.

**Architecture:** New `start` command orchestrates three phases: (1) Bootstrap (auto-init + TUI launch + goal input modal), (2) Scout Agent runs `scout_program.md` to produce strategy/evaluation docs, (3) TUI switches to ReviewScreen for user confirmation, then transitions to normal experiment mode via existing Idea+Experiment agent flow.

**Tech Stack:** Python, Typer (CLI), Textual (TUI), Jinja2 (templates), pytest (tests)

---

### Task 1: Scout Program Template

**Files:**
- Create: `src/open_researcher/templates/scout_program.md.j2`
- Test: `tests/test_init.py` (add test)

**Step 1: Write the failing test**

Add to `tests/test_init.py`:

```python
def test_scout_program_template():
    """scout_program.md.j2 should render with goal variable."""
    from jinja2 import Environment, PackageLoader

    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    tmpl = env.get_template("scout_program.md.j2")

    # With goal
    result = tmpl.render(tag="test", goal="reduce val_loss")
    assert "reduce val_loss" in result
    assert "research-strategy.md" in result
    assert "evaluation.md" in result
    assert "project-understanding.md" in result
    assert "Do NOT generate specific experiment ideas" in result

    # Without goal
    result_no_goal = tmpl.render(tag="test", goal="")
    assert "Research Goal" not in result_no_goal
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_init.py::test_scout_program_template -v`
Expected: FAIL — template not found

**Step 3: Write the template**

Create `src/open_researcher/templates/scout_program.md.j2`:

```markdown
# Scout Program — Repository Analysis

You are a **Scout Agent**. Your job is to analyze this repository and produce a research strategy.
Do NOT generate specific experiment ideas — that is the Idea Agent's job.

{% if goal %}
## Research Goal (from user)
{{ goal }}

Use this goal to guide your analysis. Focus your strategy on achieving this objective.
{% endif %}

## Your Output Files

- **Write**: `.research/project-understanding.md` — project analysis
- **Write**: `.research/literature.md` — related work and techniques
- **Write**: `.research/research-strategy.md` — research direction, focus areas, constraints
- **Write**: `.research/evaluation.md` — primary metric, evaluation command, baseline method
- **Update**: `.research/config.yaml` — fill in `metrics.primary.name` and `metrics.primary.direction`
- **Write**: `.research/activity.json` — update `scout_agent` key with your status

## Status Updates

Before each action, update your status in `.research/activity.json`:
```json
{"scout_agent": {"status": "<phase>", "detail": "<what you're doing>", "updated_at": "<ISO timestamp>"}}
```

Valid statuses: `analyzing`, `searching`, `strategizing`, `idle`

## Phase 1: Understand the Project

1. Read the codebase: source files, tests, documentation, README
2. Identify: purpose, architecture, entry points, existing benchmarks/evaluations
3. Write your analysis to `.research/project-understanding.md`
4. Update status: `{"status": "analyzing", "detail": "reading codebase"}`

## Phase 2: Research Related Work

1. If web search is available (`config.yaml: research.web_search: true`):
   - Search 3-5 technical queries related to the project
   - Identify state of the art and common improvement patterns
2. Write findings to `.research/literature.md`
3. Update status: `{"status": "searching", "detail": "searching related work"}`

## Phase 3: Define Research Strategy

Based on project understanding and related work, define:

1. **Research direction** — what to optimize and why
2. **Focus areas** — 2-4 specific areas to explore (e.g., "learning rate scheduling", "architecture modifications")
3. **Constraints** — what NOT to change (e.g., "do not change model architecture")

Write to `.research/research-strategy.md` with this structure:
```markdown
## Research Direction
<What to optimize and why>

## Focus Areas
1. <Area 1>
2. <Area 2>
3. <Area 3>

## Constraints
- <Constraint 1>
- <Constraint 2>
```

Update status: `{"status": "strategizing", "detail": "defining research strategy"}`

## Phase 4: Design Evaluation

1. Define the primary metric (name + direction: higher_is_better or lower_is_better)
2. Define the evaluation command (how to measure the metric)
3. Estimate reasonable experiment duration
4. Write to `.research/evaluation.md`
5. Update `.research/config.yaml`: set `metrics.primary.name` and `metrics.primary.direction`
6. Update status: `{"status": "idle", "detail": "analysis complete"}`

## Rules

- Do NOT generate specific experiment ideas — that is the Idea Agent's job
- Do NOT modify code or run experiments
- Always update `activity.json` before each action
- Keep all outputs specific and actionable
- If web search is unavailable, rely on codebase analysis alone
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_init.py::test_scout_program_template -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/open_researcher/templates/scout_program.md.j2 tests/test_init.py
git commit -m "feat: add scout_program.md.j2 template for repo analysis phase"
```

---

### Task 2: Research Strategy Template

**Files:**
- Create: `src/open_researcher/templates/research-strategy.md.j2`
- Test: `tests/test_init.py` (add test)

**Step 1: Write the failing test**

Add to `tests/test_init.py`:

```python
def test_research_strategy_template():
    """research-strategy.md.j2 should render as empty scaffold."""
    from jinja2 import Environment, PackageLoader

    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    tmpl = env.get_template("research-strategy.md.j2")
    result = tmpl.render(tag="test")
    assert "Research Direction" in result
    assert "Focus Areas" in result
    assert "Constraints" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_init.py::test_research_strategy_template -v`
Expected: FAIL

**Step 3: Write the template**

Create `src/open_researcher/templates/research-strategy.md.j2`:

```markdown
# Research Strategy

<!-- Scout Agent fills this file during the analysis phase. -->

## Research Direction

<!-- What to optimize and why. -->

## Focus Areas

<!-- 2-4 specific areas to explore. -->
1.
2.
3.

## Constraints

<!-- What NOT to change during experiments. -->
-
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_init.py::test_research_strategy_template -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/open_researcher/templates/research-strategy.md.j2 tests/test_init.py
git commit -m "feat: add research-strategy.md.j2 template"
```

---

### Task 3: Add Scout Templates to init_cmd.py

**Files:**
- Modify: `src/open_researcher/init_cmd.py:44-57` (add to template list)
- Test: `tests/test_init.py` (add test)

**Step 1: Write the failing test**

Add to `tests/test_init.py`:

```python
def test_init_creates_scout_and_strategy_files(init_dir):
    """init should create scout_program.md and research-strategy.md."""
    assert (init_dir / "scout_program.md").is_file()
    assert (init_dir / "research-strategy.md").is_file()

    scout = (init_dir / "scout_program.md").read_text()
    assert "Scout Program" in scout

    strategy = (init_dir / "research-strategy.md").read_text()
    assert "Research Direction" in strategy
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_init.py::test_init_creates_scout_and_strategy_files -v`
Expected: FAIL — files don't exist

**Step 3: Add templates to init_cmd.py**

In `src/open_researcher/init_cmd.py`, add two entries to the template list (after line 53):

```python
    for template_name, output_name in [
        ("program.md.j2", "program.md"),
        ("config.yaml.j2", "config.yaml"),
        ("project-understanding.md.j2", "project-understanding.md"),
        ("evaluation.md.j2", "evaluation.md"),
        ("literature.md.j2", "literature.md"),
        ("ideas.md.j2", "ideas.md"),
        ("idea_program.md.j2", "idea_program.md"),
        ("experiment_program.md.j2", "experiment_program.md"),
        ("scout_program.md.j2", "scout_program.md"),                # NEW
        ("research-strategy.md.j2", "research-strategy.md"),        # NEW
    ]:
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_init.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/open_researcher/init_cmd.py tests/test_init.py
git commit -m "feat: generate scout_program.md and research-strategy.md during init"
```

---

### Task 4: Modify idea_program.md.j2 to Read Strategy Files

**Files:**
- Modify: `src/open_researcher/templates/idea_program.md.j2:1-11` (add context section)
- Test: `tests/test_init.py` (add test)

**Step 1: Write the failing test**

Add to `tests/test_init.py`:

```python
def test_idea_program_reads_strategy_files():
    """idea_program.md.j2 should instruct agent to read strategy files."""
    from jinja2 import Environment, PackageLoader

    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    tmpl = env.get_template("idea_program.md.j2")
    result = tmpl.render(tag="test")
    assert "research-strategy.md" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_init.py::test_idea_program_reads_strategy_files -v`
Expected: FAIL — "research-strategy.md" not found in output

**Step 3: Add strategy context to idea_program.md.j2**

In `src/open_researcher/templates/idea_program.md.j2`, add after line 10 (after the existing "Read" file list):

Replace the `## Your Files` section (lines 5-10) with:

```markdown
## Your Files

- **Read/Write**: `.research/idea_pool.json` — the shared idea pool
- **Read**: `.research/results.tsv` — experiment results (written by Experiment Agent)
- **Write**: `.research/activity.json` — update `idea_agent` key with your current status
- **Read**: `.research/literature.md`, `.research/project-understanding.md`
- **Read**: `.research/research-strategy.md` — confirmed research direction and constraints

## Research Context

Before generating ideas, read `.research/research-strategy.md` to understand:
- The confirmed research direction and focus areas
- Constraints on what should NOT be changed
Generate ideas that align with this strategy. If the file is empty or missing, determine the strategy yourself.
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_init.py::test_idea_program_reads_strategy_files -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/open_researcher/templates/idea_program.md.j2 tests/test_init.py
git commit -m "feat: idea_program reads research-strategy.md for context"
```

---

### Task 5: GoalInputModal

**Files:**
- Modify: `src/open_researcher/tui/modals.py` (add new modal class)
- Test: `tests/test_tui_modals.py` (new test file)

**Step 1: Write the failing test**

Create `tests/test_tui_modals.py`:

```python
"""Tests for TUI modal screens."""


def test_goal_input_modal_import():
    """GoalInputModal should be importable."""
    from open_researcher.tui.modals import GoalInputModal

    modal = GoalInputModal()
    assert modal is not None


def test_goal_input_modal_is_modal_screen():
    """GoalInputModal should be a ModalScreen returning str or None."""
    from textual.screen import ModalScreen

    from open_researcher.tui.modals import GoalInputModal

    modal = GoalInputModal()
    assert isinstance(modal, ModalScreen)
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_tui_modals.py -v`
Expected: FAIL — ImportError

**Step 3: Implement GoalInputModal**

Add to `src/open_researcher/tui/modals.py` (after `AddIdeaModal`, before `GPUStatusModal`):

```python
class GoalInputModal(ModalScreen[str | None]):
    """Modal for entering an optional research goal before Scout analysis."""

    BINDINGS = [("escape", "skip", "Skip")]

    def compose(self) -> ComposeResult:
        with Vertical(id="goal-dialog"):
            yield Label("What would you like to optimize?")
            yield Static("Enter a research goal, or press Enter to let the agent decide.", id="goal-hint")
            yield Input(placeholder="e.g., reduce val_loss, improve throughput...", id="goal-input")
            yield Button("Start Analysis", variant="primary", id="btn-start")
            yield Button("Skip (no goal)", id="btn-skip")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            goal = self.query_one("#goal-input", Input).value.strip()
            self.dismiss(goal if goal else None)
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        goal = event.value.strip()
        self.dismiss(goal if goal else None)

    def action_skip(self) -> None:
        self.dismiss(None)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_tui_modals.py -v`
Expected: PASS

**Step 5: Add CSS for GoalInputModal**

Append to `src/open_researcher/tui/styles.css`:

```css
GoalInputModal {
    align: center middle;
}

GoalInputModal > #goal-dialog {
    width: 70;
    height: auto;
    border: thick $primary;
    background: $surface;
    padding: 1 2;
}

GoalInputModal #goal-hint {
    color: $text-muted;
    margin: 0 0 1 0;
}
```

**Step 6: Commit**

```bash
git add src/open_researcher/tui/modals.py src/open_researcher/tui/styles.css tests/test_tui_modals.py
git commit -m "feat: add GoalInputModal for research goal input"
```

---

### Task 6: ReviewScreen

**Files:**
- Create: `src/open_researcher/tui/review.py`
- Modify: `src/open_researcher/tui/styles.css` (add styles)
- Test: `tests/test_review_screen.py` (new test file)

**Step 1: Write the failing test**

Create `tests/test_review_screen.py`:

```python
"""Tests for the Review screen."""

import json
from pathlib import Path


def test_review_screen_import():
    """ReviewScreen should be importable."""
    from open_researcher.tui.review import ReviewScreen

    assert ReviewScreen is not None


def test_review_screen_is_screen():
    """ReviewScreen should be a Textual Screen."""
    from textual.screen import Screen

    from open_researcher.tui.review import ReviewScreen

    assert issubclass(ReviewScreen, Screen)


def test_review_screen_loads_files(tmp_path):
    """ReviewScreen should load strategy, evaluation, and understanding files."""
    from open_researcher.tui.review import load_review_data

    research = tmp_path / ".research"
    research.mkdir()
    (research / "project-understanding.md").write_text("# Understanding\nThis is a test project.")
    (research / "research-strategy.md").write_text("## Research Direction\nOptimize training.")
    (research / "evaluation.md").write_text("## Primary Metric\nval_loss (lower_is_better)")
    (research / "config.yaml").write_text("metrics:\n  primary:\n    name: val_loss\n    direction: lower_is_better\n")

    data = load_review_data(research)
    assert "test project" in data["understanding"]
    assert "Optimize training" in data["strategy"]
    assert "val_loss" in data["evaluation"]
    assert data["metric_name"] == "val_loss"
    assert data["metric_direction"] == "lower_is_better"


def test_review_screen_handles_missing_files(tmp_path):
    """ReviewScreen should handle missing files gracefully."""
    from open_researcher.tui.review import load_review_data

    research = tmp_path / ".research"
    research.mkdir()

    data = load_review_data(research)
    assert data["understanding"] == ""
    assert data["strategy"] == ""
    assert data["evaluation"] == ""
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_review_screen.py -v`
Expected: FAIL — ImportError

**Step 3: Implement ReviewScreen**

Create `src/open_researcher/tui/review.py`:

```python
"""Review screen — displays Scout Agent analysis for user confirmation."""

from pathlib import Path

import yaml
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Label, Static, TextArea


def load_review_data(research_dir: Path) -> dict:
    """Load Scout output files for review."""
    def _read(name: str) -> str:
        p = research_dir / name
        if p.exists():
            try:
                return p.read_text()
            except OSError:
                return ""
        return ""

    # Parse metric info from config.yaml
    metric_name = ""
    metric_direction = ""
    config_path = research_dir / "config.yaml"
    if config_path.exists():
        try:
            raw = yaml.safe_load(config_path.read_text()) or {}
            primary = raw.get("metrics", {}).get("primary", {})
            metric_name = primary.get("name", "")
            metric_direction = primary.get("direction", "")
        except (yaml.YAMLError, OSError):
            pass

    return {
        "understanding": _read("project-understanding.md"),
        "strategy": _read("research-strategy.md"),
        "evaluation": _read("evaluation.md"),
        "metric_name": metric_name,
        "metric_direction": metric_direction,
    }


class ReviewScreen(Screen):
    """Full-screen review of Scout Agent analysis results."""

    BINDINGS = [
        ("enter", "confirm", "Confirm & Start"),
        ("e", "edit_strategy", "Edit Strategy"),
        ("m", "edit_metrics", "Edit Metrics"),
        ("r", "reanalyze", "Re-analyze"),
        ("q", "cancel", "Quit"),
    ]

    def __init__(self, research_dir: Path):
        super().__init__()
        self.research_dir = research_dir
        self._data = load_review_data(research_dir)

    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="review-container"):
            yield Label("Analysis Complete — Review Research Plan", id="review-title")

            yield Label("Project Understanding", id="section-understanding")
            yield Static(
                self._data["understanding"][:500] or "(No analysis yet)",
                id="understanding-content",
            )

            yield Label("Research Strategy  [e] edit", id="section-strategy")
            yield Static(
                self._data["strategy"] or "(No strategy defined)",
                id="strategy-content",
            )

            yield Label("Evaluation Plan  [m] edit", id="section-evaluation")
            metric_info = ""
            if self._data["metric_name"]:
                metric_info = f"Metric: {self._data['metric_name']} ({self._data['metric_direction']})\n\n"
            yield Static(
                metric_info + (self._data["evaluation"] or "(No evaluation defined)"),
                id="evaluation-content",
            )

        with Vertical(id="review-actions"):
            yield Button("Confirm & Start Research", variant="primary", id="btn-confirm")
            yield Button("Re-analyze", id="btn-reanalyze")
            yield Button("Quit", id="btn-quit")

        yield Static(
            "[Enter] Confirm  [e] Edit Strategy  [m] Edit Metrics  [r] Re-analyze  [q] Quit",
            id="review-footer",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self.dismiss("confirm")
        elif event.button.id == "btn-reanalyze":
            self.dismiss("reanalyze")
        elif event.button.id == "btn-quit":
            self.dismiss("quit")

    def action_confirm(self) -> None:
        self.dismiss("confirm")

    def action_reanalyze(self) -> None:
        self.dismiss("reanalyze")

    def action_cancel(self) -> None:
        self.dismiss("quit")

    def action_edit_strategy(self) -> None:
        """Open strategy file in an editable TextArea overlay."""
        strategy_path = self.research_dir / "research-strategy.md"
        content = self._data["strategy"]

        def _on_save(new_content: str | None) -> None:
            if new_content is not None:
                strategy_path.write_text(new_content)
                self._data["strategy"] = new_content
                try:
                    self.query_one("#strategy-content", Static).update(new_content)
                except Exception:
                    pass

        self.app.push_screen(EditDocScreen(content, "Research Strategy"), _on_save)

    def action_edit_metrics(self) -> None:
        """Open evaluation file in an editable TextArea overlay."""
        eval_path = self.research_dir / "evaluation.md"
        content = self._data["evaluation"]

        def _on_save(new_content: str | None) -> None:
            if new_content is not None:
                eval_path.write_text(new_content)
                self._data["evaluation"] = new_content
                try:
                    self.query_one("#evaluation-content", Static).update(new_content)
                except Exception:
                    pass

        self.app.push_screen(EditDocScreen(content, "Evaluation Plan"), _on_save)


class EditDocScreen(Screen[str | None]):
    """Simple full-screen text editor for a document."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, content: str, title: str):
        super().__init__()
        self._content = content
        self._title = title

    def compose(self) -> ComposeResult:
        yield Label(f"Editing: {self._title}", id="edit-title")
        yield TextArea(self._content, id="edit-area")
        with Vertical(id="edit-buttons"):
            yield Button("Save", variant="primary", id="btn-save")
            yield Button("Cancel", id="btn-edit-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            text = self.query_one("#edit-area", TextArea).text
            self.dismiss(text)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_review_screen.py -v`
Expected: PASS

**Step 5: Add CSS for ReviewScreen**

Append to `src/open_researcher/tui/styles.css`:

```css
ReviewScreen {
    background: $surface;
}

#review-container {
    height: 1fr;
    overflow-y: auto;
    padding: 1 2;
}

#review-title {
    text-style: bold;
    color: $success;
    margin: 0 0 1 0;
}

#section-understanding, #section-strategy, #section-evaluation {
    text-style: bold;
    margin: 1 0 0 0;
}

#understanding-content, #strategy-content, #evaluation-content {
    margin: 0 0 1 2;
    color: $text;
}

#review-actions {
    dock: bottom;
    height: auto;
    padding: 1 2;
    layout: horizontal;
}

#review-footer {
    dock: bottom;
    height: 1;
    background: $primary-background;
    color: $text-muted;
    padding: 0 1;
}

EditDocScreen {
    background: $surface;
}

#edit-title {
    dock: top;
    height: 1;
    text-style: bold;
    padding: 0 1;
}

#edit-area {
    height: 1fr;
}

#edit-buttons {
    dock: bottom;
    height: auto;
    layout: horizontal;
    padding: 0 1;
}
```

**Step 6: Commit**

```bash
git add src/open_researcher/tui/review.py src/open_researcher/tui/styles.css tests/test_review_screen.py
git commit -m "feat: add ReviewScreen for Scout analysis confirmation"
```

---

### Task 7: App State Machine in ResearchApp

**Files:**
- Modify: `src/open_researcher/tui/app.py:31-82` (add state management)
- Test: `tests/test_app_state.py` (new test file)

**Step 1: Write the failing test**

Create `tests/test_app_state.py`:

```python
"""Tests for app state machine."""

from pathlib import Path


def test_app_state_default():
    """ResearchApp should default to EXPERIMENTING state."""
    from open_researcher.tui.app import ResearchApp

    # Create minimal research dir
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        research = tmp_path / ".research"
        research.mkdir()
        (research / "idea_pool.json").write_text('{"ideas": []}')
        (research / "activity.json").write_text('{}')

        app = ResearchApp(tmp_path)
        assert app.app_phase == "experimenting"


def test_app_state_scouting():
    """ResearchApp should support scouting state."""
    from open_researcher.tui.app import ResearchApp

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        research = tmp_path / ".research"
        research.mkdir()
        (research / "idea_pool.json").write_text('{"ideas": []}')
        (research / "activity.json").write_text('{}')

        app = ResearchApp(tmp_path, initial_phase="scouting")
        assert app.app_phase == "scouting"
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_app_state.py -v`
Expected: FAIL — `initial_phase` not accepted

**Step 3: Add state to ResearchApp**

In `src/open_researcher/tui/app.py`, modify the `__init__` method:

```python
    def __init__(self, repo_path: Path, multi: bool = False, on_ready=None, initial_phase: str = "experimenting"):
        super().__init__()
        self.repo_path = repo_path
        self.research_dir = repo_path / ".research"
        self.multi = multi
        self.pool = IdeaPool(self.research_dir / "idea_pool.json")
        self.activity = ActivityMonitor(self.research_dir)
        self._on_ready = on_ready
        self.app_phase = initial_phase  # "scouting" | "reviewing" | "experimenting"
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_app_state.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/open_researcher/tui/app.py tests/test_app_state.py
git commit -m "feat: add app_phase state to ResearchApp"
```

---

### Task 8: start_cmd.py — Core Start Logic

**Files:**
- Create: `src/open_researcher/start_cmd.py`
- Test: `tests/test_start_cmd.py` (new test file)

**Step 1: Write the failing test**

Create `tests/test_start_cmd.py`:

```python
"""Tests for the start command."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(tmp_path), capture_output=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(tmp_path), capture_output=True)
    return tmp_path


def test_do_start_auto_inits(tmp_path):
    """start should auto-create .research/ if it doesn't exist."""
    from open_researcher.start_cmd import do_start_init

    _make_git_repo(tmp_path)
    research = do_start_init(tmp_path, tag="test")
    assert research.is_dir()
    assert (research / "scout_program.md").is_file()
    assert (research / "config.yaml").is_file()


def test_do_start_skips_init_if_exists(tmp_path):
    """start should not re-init if .research/ already exists."""
    from open_researcher.start_cmd import do_start_init

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text("mode: autonomous\n")
    (research / "scout_program.md").write_text("# scout")

    result = do_start_init(tmp_path, tag="test")
    assert result == research
    # Original files should be untouched
    assert (research / "config.yaml").read_text() == "mode: autonomous\n"


def test_render_scout_with_goal(tmp_path):
    """Scout program should include goal when provided."""
    from open_researcher.start_cmd import render_scout_program

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()

    render_scout_program(research, tag="test", goal="reduce val_loss")
    content = (research / "scout_program.md").read_text()
    assert "reduce val_loss" in content


def test_render_scout_without_goal(tmp_path):
    """Scout program should work without goal."""
    from open_researcher.start_cmd import render_scout_program

    _make_git_repo(tmp_path)
    research = tmp_path / ".research"
    research.mkdir()

    render_scout_program(research, tag="test", goal=None)
    content = (research / "scout_program.md").read_text()
    assert "Research Goal" not in content
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_start_cmd.py -v`
Expected: FAIL — ImportError

**Step 3: Implement start_cmd.py**

Create `src/open_researcher/start_cmd.py`:

```python
"""Start command — zero-config launch with Scout analysis + TUI review."""

import threading
from datetime import date
from pathlib import Path

from jinja2 import Environment, PackageLoader
from rich.console import Console

from open_researcher.agents import detect_agent, get_agent
from open_researcher.config import load_config

console = Console()


def render_scout_program(research_dir: Path, tag: str, goal: str | None) -> None:
    """Render scout_program.md with optional goal."""
    env = Environment(loader=PackageLoader("open_researcher", "templates"))
    template = env.get_template("scout_program.md.j2")
    content = template.render(tag=tag, goal=goal or "")
    (research_dir / "scout_program.md").write_text(content)


def do_start_init(repo_path: Path, tag: str | None = None) -> Path:
    """Auto-initialize .research/ if needed, return research dir path."""
    research = repo_path / ".research"

    if research.is_dir():
        console.print("[dim]Using existing .research/ directory.[/dim]")
        return research

    # Run full init
    from open_researcher.init_cmd import do_init

    if tag is None:
        tag = date.today().strftime("%b%d").lower()

    do_init(repo_path, tag=tag)
    return research


def _resolve_agent(agent_name: str | None, agent_configs: dict | None = None):
    """Resolve agent by name or auto-detect."""
    configs = agent_configs or {}
    if agent_name:
        try:
            return get_agent(agent_name, config=configs.get(agent_name))
        except KeyError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise SystemExit(1)
    agent = detect_agent(configs=configs)
    if agent is None:
        console.print(
            "[red]Error:[/red] No supported AI agent found.\n"
            "Install one of: claude (Claude Code), codex, aider, opencode\n"
            "Or specify with: --agent <name>"
        )
        raise SystemExit(1)
    console.print(f"[green]Auto-detected agent:[/green] {agent.name}")
    return agent


def do_start(
    repo_path: Path,
    agent_name: str | None = None,
    tag: str | None = None,
    multi: bool = False,
    idea_agent_name: str | None = None,
    exp_agent_name: str | None = None,
) -> None:
    """Execute the start command: auto-init → Scout → Review → Experiment."""
    from open_researcher.run_cmd import (
        _launch_agent_thread,
        _make_safe_output,
    )
    from open_researcher.tui.app import ResearchApp
    from open_researcher.tui.modals import GoalInputModal
    from open_researcher.tui.review import ReviewScreen
    from open_researcher.watchdog import TimeoutWatchdog

    # Phase 0: Bootstrap — auto init
    if tag is None:
        tag = date.today().strftime("%b%d").lower()
    research = do_start_init(repo_path, tag=tag)
    cfg = load_config(research)

    # Resolve agents
    scout_agent = _resolve_agent(agent_name, cfg.agent_config)
    if multi or idea_agent_name or exp_agent_name:
        idea_agent = _resolve_agent(idea_agent_name or agent_name, cfg.agent_config)
        exp_agent = _resolve_agent(exp_agent_name or agent_name, cfg.agent_config)
    else:
        idea_agent = None
        exp_agent = None

    # State
    stop = threading.Event()
    exit_codes: dict[str, int] = {}
    on_output_ref: list = []

    def _on_goal_result(goal: str | None) -> None:
        """Called when user submits or skips the goal input."""
        # Re-render scout program with goal
        render_scout_program(research, tag=tag, goal=goal)

        # Save goal to file for reference
        if goal:
            (research / "goal.md").write_text(f"# Research Goal\n\n{goal}\n")

        # Update app phase
        app.app_phase = "scouting"

        # Launch Scout Agent in background thread
        on_output = _make_safe_output(app.append_log, research / "run.log")
        on_output_ref.append(on_output)

        done_scout = threading.Event()

        def _after_scout():
            done_scout.wait()
            code = exit_codes.get("scout", -1)
            if code != 0:
                app.call_from_thread(
                    app.notify, f"Scout Agent failed (code={code}). Check logs.", severity="error"
                )
            # Switch to review screen
            app.app_phase = "reviewing"
            app.call_from_thread(_show_review)

        def _show_review():
            def _on_review(result: str | None) -> None:
                if result == "confirm":
                    app.app_phase = "experimenting"
                    _start_experiment_agents()
                elif result == "reanalyze":
                    app.app_phase = "scouting"
                    _run_scout()
                else:
                    app.exit()

            app.push_screen(ReviewScreen(research), _on_review)

        _launch_agent_thread(
            scout_agent, repo_path, on_output, done_scout, exit_codes, "scout",
            program_file="scout_program.md",
        )
        threading.Thread(target=_after_scout, daemon=True).start()

    def _run_scout():
        """Re-run scout agent (for re-analyze flow)."""
        on_output = on_output_ref[0] if on_output_ref else _make_safe_output(app.append_log, research / "run.log")
        done_scout = threading.Event()

        def _after_scout():
            done_scout.wait()
            app.app_phase = "reviewing"
            app.call_from_thread(_show_review_again)

        def _show_review_again():
            def _on_review(result: str | None) -> None:
                if result == "confirm":
                    app.app_phase = "experimenting"
                    _start_experiment_agents()
                elif result == "reanalyze":
                    app.app_phase = "scouting"
                    _run_scout()
                else:
                    app.exit()

            app.push_screen(ReviewScreen(research), _on_review)

        _launch_agent_thread(
            scout_agent, repo_path, on_output, done_scout, exit_codes, "scout",
            program_file="scout_program.md",
        )
        threading.Thread(target=_after_scout, daemon=True).start()

    def _start_experiment_agents():
        """Transition to experiment phase — launch idea + experiment agents."""
        from open_researcher.crash_counter import CrashCounter
        from open_researcher.phase_gate import PhaseGate
        from open_researcher.run_cmd import _has_pending_ideas, _read_latest_status, _set_paused

        on_output = on_output_ref[0] if on_output_ref else _make_safe_output(app.append_log, research / "run.log")

        watchdog = TimeoutWatchdog(cfg.timeout, on_timeout=lambda: None)

        if multi and idea_agent and exp_agent:
            # Dual-agent mode
            crash_counter = CrashCounter(cfg.max_crashes)
            phase_gate = PhaseGate(research, cfg.mode)

            def _alternating():
                cycle = 0
                while not stop.is_set():
                    cycle += 1
                    on_output(f"[system] === Cycle {cycle}: Starting Idea Agent ===")
                    try:
                        code = idea_agent.run(
                            repo_path, on_output=on_output, program_file="idea_program.md"
                        )
                    except Exception as exc:
                        on_output(f"[idea] Agent error: {exc}")
                        code = 1
                    exit_codes["idea"] = code

                    if not _has_pending_ideas(research):
                        on_output("[system] No pending ideas. Stopping.")
                        break

                    exp_run = 0
                    while not stop.is_set():
                        exp_run += 1
                        watchdog.reset()
                        try:
                            code = exp_agent.run(
                                repo_path, on_output=on_output, program_file="experiment_program.md"
                            )
                        except Exception as exc:
                            on_output(f"[exp] Agent error: {exc}")
                            code = 1
                        watchdog.stop()
                        exit_codes["exp"] = code

                        status = _read_latest_status(research)
                        if status and crash_counter.record(status):
                            on_output(f"[system] Crash limit reached. Pausing.")
                            _set_paused(research, f"Crash limit: {cfg.max_crashes}")
                            stop.set()
                            break

                        phase = phase_gate.check()
                        if phase:
                            on_output(f"[system] Phase transition to '{phase}'.")
                            _set_paused(research, f"Phase: {phase}")
                            break

                        if not _has_pending_ideas(research):
                            break
                        on_output("[exp] Pending ideas remain, restarting...")

                    if stop.is_set():
                        break

                watchdog.stop()
                on_output("[system] All cycles finished.")

            threading.Thread(target=_alternating, daemon=True).start()
        else:
            # Single-agent mode — use program.md
            agent = scout_agent  # Reuse the same agent
            watchdog_single = TimeoutWatchdog(cfg.timeout, on_timeout=lambda: agent.terminate())
            watchdog_single.start()
            done = threading.Event()
            _launch_agent_thread(agent, repo_path, on_output, done, exit_codes, "agent",
                               program_file="program.md")

    def start_app():
        """Called on app mount — show goal input modal."""
        app.call_from_thread(
            lambda: app.push_screen(GoalInputModal(), _on_goal_result)
        )

    app = ResearchApp(repo_path, multi=bool(multi or idea_agent_name), on_ready=start_app, initial_phase="scouting")
    try:
        app.run()
    finally:
        stop.set()
        if on_output_ref and hasattr(on_output_ref[0], 'close'):
            on_output_ref[0].close()
        scout_agent.terminate()
        if idea_agent:
            idea_agent.terminate()
        if exp_agent:
            exp_agent.terminate()

    # Print summary
    for key, name in [("scout", "Scout"), ("idea", "Idea Agent"), ("exp", "Experiment Agent"), ("agent", "Agent")]:
        code = exit_codes.get(key)
        if code is not None:
            if code == 0:
                console.print(f"[green]{name} completed successfully.[/green]")
            else:
                console.print(f"[red]{name} exited with code {code}.[/red]")
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_start_cmd.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/open_researcher/start_cmd.py tests/test_start_cmd.py
git commit -m "feat: add start_cmd.py with Scout → Review → Experiment flow"
```

---

### Task 9: Register start Command in cli.py

**Files:**
- Modify: `src/open_researcher/cli.py` (add start command)
- Test: `tests/test_cli.py` (add test)

**Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_start_without_git():
    """start should fail without git repo."""
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["start"])
        assert result.exit_code == 1


def test_start_help():
    """start --help should show the command."""
    result = runner.invoke(app, ["start", "--help"])
    assert result.exit_code == 0
    assert "start" in result.stdout.lower() or "Start" in result.stdout
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_cli.py::test_start_help -v`
Expected: FAIL — "start" command not registered

**Step 3: Add start command to cli.py**

In `src/open_researcher/cli.py`, add after the `run` command (before `if __name__`):

```python
@app.command()
def start(
    agent: str = typer.Option(None, help="Agent to use (claude-code, codex, aider, opencode)."),
    tag: str = typer.Option(None, help="Experiment tag (e.g. mar10). Defaults to today's date."),
    multi: bool = typer.Option(False, "--multi", help="Enable dual-agent mode (Idea + Experiment)."),
    idea_agent: str = typer.Option(None, "--idea-agent", help="Agent for idea generation (multi mode)."),
    exp_agent: str = typer.Option(None, "--exp-agent", help="Agent for experiments (multi mode)."),
):
    """Zero-config start: auto-init, analyze repo, confirm plan, then run experiments."""
    from open_researcher.start_cmd import do_start

    do_start(
        repo_path=Path.cwd(),
        agent_name=agent,
        tag=tag,
        multi=multi,
        idea_agent_name=idea_agent,
        exp_agent_name=exp_agent,
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/open_researcher/cli.py tests/test_cli.py
git commit -m "feat: register start command in CLI"
```

---

### Task 10: Integration — Run All Tests

**Step 1: Run full test suite**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 2: Verify no import errors**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -c "from open_researcher.start_cmd import do_start; from open_researcher.tui.review import ReviewScreen; from open_researcher.tui.modals import GoalInputModal; print('All imports OK')"`
Expected: "All imports OK"

**Step 3: Verify CLI help**

Run: `cd /Users/shatianming/Downloads/open-researcher && python -m open_researcher --help`
Expected: `start` command visible in help output

**Step 4: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: resolve integration issues for start command"
```

---

## Summary

| Task | Description | New/Modified Files |
|------|-------------|-------------------|
| 1 | Scout program template | `templates/scout_program.md.j2` |
| 2 | Research strategy template | `templates/research-strategy.md.j2` |
| 3 | Add scout templates to init | `init_cmd.py` |
| 4 | Idea program reads strategy | `templates/idea_program.md.j2` |
| 5 | GoalInputModal | `tui/modals.py` |
| 6 | ReviewScreen | `tui/review.py` |
| 7 | App state machine | `tui/app.py` |
| 8 | start_cmd.py | `start_cmd.py` |
| 9 | CLI registration | `cli.py` |
| 10 | Integration test | All files |
