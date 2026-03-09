# TUI Visual Overhaul Design

Date: 2026-03-09

## Problems

1. TUI is visually ugly — black/white text, no color, no visual hierarchy
2. Log panel auto-scrolls to bottom, can't read previous output
3. Agent thinking/acting phases are invisible — all output looks the same
4. No real-time progress indicator for experiment execution

## Design

### Layout (top to bottom)

```
┌──────────────── Open Researcher ─────────────────┐
│ ● research/mar09 │ 3 kept 1 disc │ best: 0.823  │  StatsBar (colored)
├──────────────────────────────────────────────────────┤
│ ┌ Experiment Agent ───────────────────────────┐  │
│ │ ▶ RUNNING idea-003: Add dropout             │  │  ExperimentStatusPanel
│ │ ████████░░░░░░  3/10 ideas  (4m 32s)        │  │  with ProgressBar
│ └─────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────┤
│ Ideas                                                │
│ ✓ #001 baseline                    1.4523 kept      │  IdeaListPanel
│ ▶ #004 Add dropout                 --     running   │  (colored per status)
│ · #005 LR warmup                   --     pending   │
├──────────────────────────────────────────────────────┤
│ Log ────────────────── [m] minimize  [↑ locked]      │
│ ───── 💭 Thinking ─────                              │  LogPanel (colored,
│   considering dropout placement...                   │   lockable, minimizable)
│ ───── ✦ Acting ─────                                 │
│ + dropout = 0.1                                      │
├──────────────────────────────────────────────────────┤
│ [p]ause [r]esume [s]kip [a]dd [l]og [m]in/max [q]   │  HotkeyBar
└──────────────────────────────────────────────────────┘
```

### Component Details

#### 1. StatsBar — Colored status line
- Green: kept count
- Red: discarded count
- Yellow: crash count
- Cyan+bold: best metric value
- Green dot (●) when agents running, dim dot when idle

#### 2. ExperimentStatusPanel — Replaces AgentStatusWidget
- Textual Panel with border
- Line 1: status icon + phase text + current idea description
- Line 2: ProgressBar (completed/total ideas) + elapsed time
- Phase colors: init=cyan, baseline=yellow, running=green, evaluating=blue, idle=dim

#### 3. IdeaListPanel — Replaces IdeaPoolTable (DataTable)
- Custom Static widget, renders Rich Text per line
- Status icons: ✓ (kept/green), ✗ (discarded/red), ▶ (running/yellow+bold), · (pending/dim), – (skipped/dim)
- Columns: icon, ID, description, metric value, verdict
- Wrapped in ScrollableContainer
- Sort: running → pending(by priority) → done → skipped

#### 4. LogPanel — Lockable, minimizable log
- States: expanded (default), locked (user scrolled up), minimized (3 lines)
- Lock detection: on ScrollUp → enter locked state, show "↑ locked N new lines"
- [m] key toggles minimized/expanded
- [Enter] unlocks scroll and jumps to bottom
- Uses RichLog(markup=True) for colored output

#### 5. Log Line Coloring (in _make_safe_output)
| Pattern | Color |
|---------|-------|
| `[exp]`/`[idea]` prefix | bold cyan |
| `diff --git` | bold white |
| `+` line (not `+++`) | green |
| `-` line (not `---`) | red |
| `@@` line | yellow |
| `file update:` | bold magenta |
| `step N:` training | cyan |
| `Error`/`ERROR` | bold red |
| thinking phase content | dim italic |
| other | dim white |

#### 6. Phase Separators
- `thinking` marker → `───── 💭 Thinking ─────` (dim separator)
- `assistant` marker → `───── ✦ Acting ─────` (bright separator)
- `user` marker → still filtered (prompt echo)
- State machine tracks current phase to style subsequent lines

### Files to Modify

- `src/open_researcher/tui/widgets.py` — Replace IdeaPoolTable+AgentStatusWidget with IdeaListPanel+ExperimentStatusPanel
- `src/open_researcher/tui/app.py` — New compose() layout, log lock/minimize logic
- `src/open_researcher/tui/styles.css` — Full CSS rewrite with colors
- `src/open_researcher/run_cmd.py` — _make_safe_output with line classification and Rich markup
- `tests/test_tui.py` — Update for new widget names
