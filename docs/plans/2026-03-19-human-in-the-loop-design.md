# Human-in-the-Loop Checkpoint Design

> **Date**: 2026-03-19
> **Status**: Approved
> **Scope**: v2 research loop (open_researcher_v2 + paperfarm TUI)

## Problem

The v2 research loop is fully autonomous: scout analyzes, manager proposes hypotheses, critic approves, experiment executes — no human decision point exists. Users can only pause/resume/skip but cannot:

- Confirm research direction after scout
- Approve/reject hypotheses after manager
- Adjust frontier priority or inject their own ideas
- Override AI result judgments after experiments
- Redirect research mid-session

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Automation level | Checkpoint mode | Balance control vs efficiency; configurable per-checkpoint |
| Default checkpoints | All 4 enabled | Maximum control; users can disable individually |
| User capabilities | Approve/reject + priority + inject ideas | Full control without over-engineering |
| UI form | Modal screens (Textual Screen push/pop) | Clear focus, prevents accidental skipping |
| Coordination mechanism | State file polling (activity.json) | Consistent with existing pause/skip; works headless + remote |
| Backward compatibility | `mode: autopilot` default | Existing users unaffected |

---

## 1. State Protocol

### activity.json Extension

New field in `control`:

```json
{
  "phase": "manager",
  "round": 1,
  "workers": [],
  "control": {
    "paused": false,
    "skip_current": false,
    "awaiting_review": null
  }
}
```

When a checkpoint triggers, SkillRunner writes:

```json
"awaiting_review": {
  "type": "direction_confirm",
  "requested_at": "2026-03-19T14:30:00Z"
}
```

### Review Types

| type | Trigger | Modal Content |
|------|---------|---------------|
| `direction_confirm` | After scout completes | Show research direction, baseline, editable constraints |
| `hypothesis_review` | After manager completes | Show hypotheses + frontier list, approve/reject/reorder |
| `frontier_review` | After critic preflight | Show reviewed frontier, approve/reject/reorder/inject |
| `result_review` | After critic post-run (end of round) | Show results with delta, override AI keep/discard |

### User Decision Storage

User decisions are written directly to the relevant state files, not to activity.json:

- **Approve/reject frontier items**: modify `graph.json → frontier[].status`
- **Adjust priority**: modify `graph.json → frontier[].priority`
- **Inject idea**: append to `graph.json → frontier[]` with `status: "approved"`, `selection_reason_code: "human_injected"`
- **Override result**: append to `graph.json → claim_updates[]` with `reviewer: "human"`
- **Edit goal/constraints**: write `.research/user_constraints.md`

### ResearchState New Methods

Added to **both** `src/open_researcher_v2/state.py` and `src/paperfarm/state.py` (TUI imports from paperfarm):

```python
def set_awaiting_review(self, review: dict | None) -> None:
    """Set control.awaiting_review in activity.json."""

def get_awaiting_review(self) -> dict | None:
    """Read control.awaiting_review from activity.json."""

def clear_awaiting_review(self) -> None:
    """Set control.awaiting_review = null."""
```

### _DEFAULT_ACTIVITY Update

```python
_DEFAULT_ACTIVITY = {
    "phase": "idle",
    "round": 0,
    "workers": [],
    "control": {"paused": False, "skip_current": False, "awaiting_review": None},  # NEW field
}
```

### summary() Update

`summary()` must include `awaiting_review` so TUI `_poll_state` can detect it:

```python
def summary(self) -> dict[str, Any]:
    # ... existing fields ...
    activity = self.load_activity()
    return {
        # ... existing ...
        "awaiting_review": activity.get("control", {}).get("awaiting_review"),  # NEW
    }
```

---

## 2. SkillRunner Checkpoint Mechanism

### Checkpoint Insertion

After each skill step completes, SkillRunner checks if a review is needed:

```python
def run_one_round(self, round_num):
    for step in loop_steps:
        if self.state.is_paused(): return -2
        if self.state.consume_skip(): return -1
        rc = self._run_skill(step.name, step.skill)
        if rc != 0: return rc
        # Checkpoint check
        review_type = self._checkpoint_type(step.name, round_num)
        if review_type:
            self._await_review(review_type)
    return 0
```

### Checkpoint Mapping

```python
def _checkpoint_type(self, step_name, round_num):
    config = self.state.load_config()
    checkpoints = config.get("interaction", {}).get("checkpoints", {})
    mode = config.get("interaction", {}).get("mode", "autopilot")

    if mode != "checkpoint":
        return None

    if step_name == "scout" and checkpoints.get("after_scout", True):
        return "direction_confirm"
    if step_name == "manager" and checkpoints.get("after_manager", True):
        return "hypothesis_review"
    if step_name == "critic" and self._is_preflight_critic():
        if checkpoints.get("after_critic_preflight", True):
            return "frontier_review"
    if step_name == "critic" and self._is_postrun_critic():
        if checkpoints.get("after_round", True):
            return "result_review"
    return None
```

### _await_review Implementation

```python
def _await_review(self, review_type: str):
    self.state.set_awaiting_review({
        "type": review_type,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    })
    self.state.append_log({"event": "review_requested", "review_type": review_type})

    config = self.state.load_config()  # NOTE: use state.load_config(), not self._config
    timeout = config.get("interaction", {}).get("review_timeout_minutes", 0)
    deadline = time.monotonic() + timeout * 60 if timeout > 0 else None

    while True:
        if self.state.get_awaiting_review() is None:
            # Normal exit: user completed or skipped review
            self.state.append_log({"event": "review_completed", "review_type": review_type})
            break
        if self.state.is_paused():
            # Pause takes priority — don't log review_completed
            break
        if deadline and time.monotonic() > deadline:
            self.state.clear_awaiting_review()
            self.state.append_log({"event": "review_timeout", "review_type": review_type})
            break  # NOTE: no review_completed logged for timeout
        time.sleep(1.0)
```

### Bootstrap Scout Checkpoint

```python
def run_bootstrap(self):
    for step in bootstrap_steps:
        rc = self._run_skill(step, f"{step}.md")
        if rc != 0: return rc
        # Only check checkpoint for the actual step name, not hardcoded "scout"
        review_type = self._checkpoint_type(step, 0)
        if review_type:
            self._await_review(review_type)
    return 0
```

### Distinguishing Two Critics

The protocol runs critic twice per round (preflight + post-run). Track with a per-round counter:

```python
# In __init__:
self._critic_call_count_this_round = 0

# In run_one_round, at start of loop body:
#   Reset counter at round start: self._critic_call_count_this_round = 0
# After each _run_skill call where step.name == "critic":
#   self._critic_call_count_this_round += 1

def _is_preflight_critic(self):
    return self._critic_call_count_this_round == 1

def _is_postrun_critic(self):
    return self._critic_call_count_this_round == 2
```

Full `run_one_round` with counter management:

```python
def run_one_round(self, round_num):
    self._critic_call_count_this_round = 0  # Reset each round
    for step in loop_steps:
        if self.state.is_paused(): return -2
        if self.state.consume_skip(): return -1
        rc = self._run_skill(step.name, step.skill)
        if rc != 0: return rc
        if step.name == "critic":
            self._critic_call_count_this_round += 1
        review_type = self._checkpoint_type(step.name, round_num)
        if review_type:
            self._await_review(review_type)
    return 0
```

---

## 3. TUI Modal System

### Architecture

Textual `Screen` stack: `app.push_screen(modal)` overlays, `app.pop_screen()` returns.

```
ResearchApp (main)
  ↓ _poll_state detects awaiting_review
  ↓ app.push_screen(ReviewScreen)

ReviewScreen (overlay)
  ├── Title bar: review type
  ├── Content: type-specific data
  ├── Action bar: keybindings
  └── User action → write graph.json → clear_awaiting_review → pop_screen
```

### _poll_state Trigger

```python
async def _poll_state(self):
    data = await asyncio.get_event_loop().run_in_executor(None, self._read_state_sync)
    # ... existing widget updates ...

    review = data["summary"].get("awaiting_review")
    if review and not self._review_shown:
        self._review_shown = True
        try:
            screen = self._make_review_screen(review, data)
            self.push_screen(screen, callback=self._on_review_done)
        except Exception:
            self._review_shown = False  # Reset on push failure

def _on_review_done(self, result):
    self._review_shown = False
```

### TUI Quit While Awaiting Review

When user presses `q` during a review wait, `action_quit` must clean up:

```python
def action_quit(self):
    # Clear pending review so SkillRunner unblocks and can exit cleanly
    if self.state.get_awaiting_review():
        self.state.clear_awaiting_review()
        self.state.append_log({"event": "review_skipped", "review_type": "quit"})
    self._review_shown = False  # Reset so re-launch doesn't get stuck
    super().action_quit()
```

### 4 Modal Screens

#### DirectionConfirmScreen (after scout)

```
┌─────────── Research Direction ───────────────────┐
│                                                   │
│  Project: code-perf                               │
│  Baseline: 1,954,065 ops/sec (higher is better)  │
│                                                   │
│  Strategy (from .research/research-strategy.md):  │
│  ┌───────────────────────────────────────────┐    │
│  │ 1. Optimize parser bottleneck              │    │
│  │ 2. Reduce memory allocation overhead       │    │
│  └───────────────────────────────────────────┘    │
│                                                   │
│  Additional constraints:                          │
│  ┌───────────────────────────────────────────┐    │
│  │ (type to add)                              │    │
│  └───────────────────────────────────────────┘    │
│                                                   │
│  [Enter] Confirm & Continue    [Esc] Skip review  │
└───────────────────────────────────────────────────┘
```

**Data**: `config.yaml` metrics, `.research/research-strategy.md`, `.research/project-understanding.md`
**Actions**: `Enter` writes constraints to `user_constraints.md` + clears review. `Esc` skips.

#### HypothesisReviewScreen (after manager)

```
┌──────────── Hypothesis Review (Round 1) ─────────────┐
│                                                       │
│  Manager proposed 3 hypotheses:                       │
│                                                       │
│    ✓  H-001  Reduce benchmark loop overhead           │
│    ✓  H-002  Switch to ujson parser                   │
│    ✗  H-003  Rewrite core in Cython                   │
│                                                       │
│  Frontier items:                                      │
│                                                       │
│  #  ID     P  Description                     Keep?   │
│  1  F-001  3  Optimize loop overhead          [✓]     │
│  2  F-002  2  Test ujson as alternative        [✓]     │
│  3  F-003  1  Rewrite parser in Cython         [ ]     │
│                                                       │
│  [↑↓] Navigate  [Space] Toggle  [+/-] Priority       │
│  [Enter] Confirm    [a] Approve all    [Esc] Skip     │
└───────────────────────────────────────────────────────┘
```

**Data**: `graph.json → hypotheses[]`, `graph.json → frontier[]`
**Actions**: `Space` toggle approve/reject, `+/-` adjust priority, `a` approve all, `Enter` confirm, `Esc` skip.

#### FrontierReviewScreen (after critic preflight)

Same layout as HypothesisReviewScreen, plus:
- Shows critic's approve/reject decisions
- `i` key opens sub-modal for injecting custom frontier items

#### ResultReviewScreen (end of round)

```
┌──────────── Round 1 Results ─────────────────────────┐
│                                                       │
│  Frontier   Value        Δ Base    AI Says    You     │
│  F-001      1,980,537    +1.4%    keep       [✓]     │
│  F-002      1,850,200    -5.3%    discard    [✓]     │
│  F-003      2,105,000    +7.7%    keep       [✓]     │
│                                                       │
│  Best: 2,105,000 (F-003, +7.7% vs baseline)          │
│                                                       │
│  Constraints for next round:                          │
│  ┌───────────────────────────────────────────┐        │
│  │ (type to add)                              │        │
│  └───────────────────────────────────────────┘        │
│                                                       │
│  [Space] Override AI  [Enter] Next round  [q] Stop    │
└───────────────────────────────────────────────────────┘
```

**Data**: `results.tsv` (current round), `graph.json → frontier[]`, baseline from config
**Actions**: `Space` override keep↔discard (writes `claim_updates[]` with `reviewer: "human"`), text box appends to `user_constraints.md`, `Enter` next round, `q` stop research.

### Shared Base Class

```python
class ReviewScreen(Screen):
    BINDINGS = [
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "skip", "Skip"),
    ]

    def __init__(self, state: ResearchState, review_request: dict):
        self.state = state
        self.review_request = review_request

    def action_confirm(self):
        self._apply_decisions()           # Subclass implements
        self.state.clear_awaiting_review()
        self.dismiss(True)

    def action_skip(self):
        self.state.clear_awaiting_review()
        self.state.append_log({"event": "review_skipped", "review_type": self.review_request["type"]})
        self.dismiss(None)
```

---

## 4. Anytime Interactions (g/i keys)

Two features available at any time, independent of checkpoints:

### Goal Edit (g key)

```
┌─────────── Edit Research Goal ───────────────────┐
│                                                   │
│  Current goal (read-only):                        │
│  Maximize ops_per_sec for code-perf bench         │
│                                                   │
│  User constraints (editable):                     │
│  ┌───────────────────────────────────────────┐    │
│  │ Focus on parser layer only.                │    │
│  │ Do NOT touch I/O code.                     │    │
│  └───────────────────────────────────────────┘    │
│                                                   │
│  [Enter] Save    [Esc] Cancel                     │
└───────────────────────────────────────────────────┘
```

- `GoalEditScreen` reads `config.yaml` goal + `.research/user_constraints.md`
- `Enter` overwrites `user_constraints.md`, logs `goal_updated` event
- Manager template reads this file: "If `.research/user_constraints.md` exists, all hypotheses MUST respect these constraints"

### Inject Idea (i key)

```
┌─────────── Inject Experiment ────────────────────┐
│                                                   │
│  Description:                                     │
│  ┌───────────────────────────────────────────┐    │
│  │ Try __slots__ for hot path objects         │    │
│  └───────────────────────────────────────────┘    │
│                                                   │
│  Priority: [3]     ← [+/-] to adjust             │
│                                                   │
│  [Enter] Add to frontier    [Esc] Cancel          │
└───────────────────────────────────────────────────┘
```

- `InjectIdeaScreen` writes to `graph.json`:
  ```python
  graph = state.load_graph()
  counter = graph.get("counters", {}).get("frontier", 0) + 1
  graph["frontier"].append({
      "id": f"frontier-{counter:03d}",
      "description": user_input,
      "priority": user_priority,
      "status": "approved",
      "selection_reason_code": "human_injected",
      "hypothesis_id": "",
      "experiment_spec_id": "",
  })
  graph.setdefault("counters", {})["frontier"] = counter  # MUST increment counter
  state.save_graph(graph)
  ```
- Logs `human_injected` event

### New Keybindings

```python
BINDINGS = [
    Binding("p", "pause", "Pause"),
    Binding("r", "resume", "Resume"),
    Binding("s", "skip", "Skip"),
    Binding("q", "quit", "Quit"),
    Binding("g", "edit_goal", "Goal"),      # NEW
    Binding("i", "inject_idea", "Inject"),  # NEW
]
```

### Edge Cases

| Case | Handling |
|------|----------|
| g/i pressed while Modal is open | Ignored (Modal captures focus) |
| Inject while SkillRunner is mid-skill | Written to graph.json; experiment phase picks it up |
| Injected item has no hypothesis/spec | Experiment agent uses description as task spec |
| user_constraints.md exists before scout | Scout reads it too, influences initial analysis |
| User quits TUI while awaiting review | `action_quit` clears `awaiting_review` so SkillRunner unblocks |
| `push_screen` throws exception | `_review_shown` reset in except block; next poll retries |
| Parallel mode (WorkerPool) | Checkpoints only apply during bootstrap (`run_bootstrap`); WorkerPool experiment phase runs without checkpoints since workers claim independently. `after_round` checkpoint is NOT triggered in parallel mode — use `after_manager` and `after_critic_preflight` instead |
| review_timeout_minutes > 0 | Modal should display countdown timer based on `requested_at + timeout` |

### Skill Template Changes

**manager.md** — add at top:

```markdown
## User Constraints
If `.research/user_constraints.md` exists, read it FIRST. All hypotheses
and frontier items MUST respect these constraints. If a constraint conflicts
with your analysis, prioritize the constraint and note the conflict in the
hypothesis rationale.
```

**experiment.md** — add to "Claiming Your Experiment":

```markdown
**Human-injected items:**
If the claimed frontier item has `selection_reason_code: "human_injected"`
and no linked `experiment_spec_id`, treat the `description` field as your
complete task specification. Design the change_plan and evaluation_plan
yourself based on the description and `.research/evaluation.md`.
```

---

## 5. Configuration

### config.yaml `interaction` Section

```yaml
interaction:
  mode: "autopilot"               # autopilot | checkpoint
  checkpoints:
    after_scout: true             # Confirm direction
    after_manager: true           # Review hypotheses
    after_critic_preflight: true  # Review frontier
    after_round: true             # Review results
  review_timeout_minutes: 0       # 0 = wait forever, >0 = auto-continue
```

Default is `autopilot` — existing behavior unchanged.

### CLI run Command Extensions

```bash
open-researcher run <repo> \
  --mode checkpoint \             # Override interaction.mode
  --no-review-after manager       # Disable specific checkpoint
```

### CLI Review Commands (Headless Support)

```bash
# Show pending review
open-researcher review <repo>

# Approve all and continue
open-researcher review <repo> --approve-all

# Reject specific items
open-researcher review <repo> --reject F-003

# Adjust priority
open-researcher review <repo> --priority F-001=5

# Skip review
open-researcher review <repo> --skip

# Inject idea
open-researcher inject <repo> --desc "Try __slots__" --priority 3

# Add constraint
open-researcher constrain <repo> --add "Do not touch I/O code"
```

### Backward Compatibility

| Scenario | Behavior |
|----------|----------|
| No `interaction` section in config | Default `mode: autopilot`, no change |
| `mode: checkpoint` + headless | Checkpoints trigger; user operates via CLI `review` command |
| Old activity.json without `awaiting_review` | `get_awaiting_review()` returns `None`, no effect |

---

## 6. Log Events & TUI Display

### New Log Events

| event | When | LogPanel Display |
|-------|------|------------------|
| `review_requested` | Checkpoint triggers | `WAIT  Waiting for human review: {type}` |
| `review_completed` | User finishes review | `REVW  Review completed: {type}` |
| `review_timeout` | Timeout auto-continue | `TOUT  Review timed out: {type}` |
| `review_skipped` | User presses Esc | `SKIP  Review skipped: {type}` |
| `human_injected` | User injects frontier item | `INJ   Human injected: {frontier_id}` |
| `human_override` | User overrides AI decision | `OVRD  Human override: {frontier_id}` |
| `goal_updated` | User edits constraints | `GOAL  User constraints updated` |

### StatsBar Indicator

When `awaiting_review` is not null:

```
experiment  |R 1|  3hyps  |0/3 exps  |best —  ⏳ REVIEW HYPOTHESES
```

---

## 7. File Changes

### Modified Files

```
src/open_researcher_v2/state.py          # +3 methods, summary() update, _DEFAULT_ACTIVITY update
src/paperfarm/state.py                   # +3 methods, summary() update, _DEFAULT_ACTIVITY update (BOTH state files)
src/open_researcher_v2/skill_runner.py   # +checkpoint logic, _critic_call_count_this_round
src/open_researcher_v2/cli.py            # +review/inject/constrain commands, run --mode param
src/paperfarm/tui/app.py                 # +g/i keybindings, review detection, action_quit cleanup
src/paperfarm/tui/widgets.py             # StatsBar review indicator, LogPanel new event prefixes
src/paperfarm/tui/styles.css             # Modal styles
src/paperfarm/skills/manager.md          # +user_constraints.md instruction
src/paperfarm/skills/experiment.md       # +human_injected handling
```

### New Files

```
src/paperfarm/tui/modals/__init__.py
src/paperfarm/tui/modals/base.py         # ReviewScreen base class
src/paperfarm/tui/modals/direction.py    # DirectionConfirmScreen
src/paperfarm/tui/modals/hypothesis.py   # HypothesisReviewScreen
src/paperfarm/tui/modals/frontier.py     # FrontierReviewScreen
src/paperfarm/tui/modals/result.py       # ResultReviewScreen
src/paperfarm/tui/modals/goal_edit.py    # GoalEditScreen
src/paperfarm/tui/modals/inject.py       # InjectIdeaScreen
```

### Test Files

```
tests/v2/test_review_state.py           # awaiting_review read/write
tests/v2/test_checkpoint.py             # SkillRunner checkpoint logic
tests/v2/test_review_modals.py          # Modal TUI tests
tests/v2/test_review_cli.py             # CLI review/inject commands
```

---

## 8. Implementation Order

```
Phase 1: State Layer (no TUI dependency)
  1. ResearchState +3 methods (set/get/clear_awaiting_review)
  2. SkillRunner checkpoint logic (_checkpoint_type, _await_review)
  3. config.yaml interaction schema parsing
  4. Unit tests (test_review_state.py, test_checkpoint.py)

Phase 2: CLI Support (headless usable)
  5. review / inject / constrain CLI commands
  6. run command --mode and --no-review-after params
  7. CLI tests (test_review_cli.py)

Phase 3: TUI Modal System
  8. ReviewScreen base class + CSS styles
  9. DirectionConfirmScreen
  10. HypothesisReviewScreen + FrontierReviewScreen
  11. ResultReviewScreen
  12. GoalEditScreen + InjectIdeaScreen
  13. app.py _poll_state detection + push_screen
  14. StatsBar / LogPanel integration
  15. Modal TUI tests (test_review_modals.py)

Phase 4: Skill Templates
  16. manager.md — add user_constraints.md reading instruction
  17. experiment.md — add human_injected item handling
```
