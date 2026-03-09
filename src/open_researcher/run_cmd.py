"""Run command — launch AI agents with interactive Textual TUI."""

import json
import threading
from pathlib import Path

from rich.console import Console

from open_researcher.agents import detect_agent, get_agent
from open_researcher.config import load_config
from open_researcher.crash_counter import CrashCounter
from open_researcher.phase_gate import PhaseGate
from open_researcher.watchdog import TimeoutWatchdog

console = Console()


def _launch_agent_thread(
    agent,
    workdir: Path,
    on_output,
    done_event: threading.Event,
    exit_codes: dict,
    key: str,
    program_file: str = "program.md",
):
    """Run an agent in a background thread."""

    def _run():
        try:
            code = agent.run(workdir, on_output=on_output, program_file=program_file)
        except Exception as exc:
            on_output(f"[{key}] Agent error: {exc}")
            code = 1
        exit_codes[key] = code
        done_event.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def _read_latest_status(research_dir: Path) -> str:
    """Read the latest status from results.tsv (last non-header line)."""
    results_path = research_dir / "results.tsv"
    if not results_path.exists():
        return ""
    try:
        lines = results_path.read_text().strip().splitlines()
        if len(lines) < 2:
            return ""
        # TSV columns: timestamp, commit, primary_metric, metric_value, secondary_metrics, status, description
        parts = lines[-1].split("\t")
        if len(parts) >= 6:
            return parts[5].strip()
        return ""
    except OSError:
        return ""


def _set_paused(research_dir: Path, reason: str) -> None:
    """Set control.json paused=True with a reason."""
    from filelock import FileLock

    from open_researcher.storage import atomic_write_json

    ctrl_path = research_dir / "control.json"
    lock = FileLock(str(ctrl_path) + ".lock")
    with lock:
        try:
            ctrl = json.loads(ctrl_path.read_text())
        except (json.JSONDecodeError, OSError, FileNotFoundError):
            ctrl = {}
        ctrl["paused"] = True
        ctrl["pause_reason"] = reason
        atomic_write_json(ctrl_path, ctrl)


def _has_pending_ideas(research_dir: Path) -> bool:
    """Check if idea_pool.json has any pending ideas (thread-safe)."""
    from open_researcher.idea_pool import IdeaPool
    pool = IdeaPool(research_dir / "idea_pool.json")
    return pool.summary().get("pending", 0) > 0



def _classify_line(line: str, phase: str) -> str:
    """Add Rich markup to a log line based on its content."""
    stripped = line.strip()

    # Escape literal brackets so Rich doesn't interpret them as markup
    escaped = line.replace("[", "\\[")

    # System messages
    if stripped.startswith("[exp]") or stripped.startswith("[idea]"):
        return f"[bold cyan]{escaped}[/bold cyan]"

    # Diff coloring
    if stripped.startswith("diff --git"):
        return f"[bold white]{escaped}[/bold white]"
    if stripped.startswith("file update:"):
        return f"[bold magenta]{escaped}[/bold magenta]"
    if stripped.startswith("@@"):
        return f"[yellow]{escaped}[/yellow]"
    if stripped.startswith("+") and not stripped.startswith("+++"):
        return f"[green]{escaped}[/green]"
    if stripped.startswith("-") and not stripped.startswith("---"):
        return f"[red]{escaped}[/red]"

    # Training output
    if "step " in stripped and ("loss" in stripped or "iter" in stripped):
        return f"[cyan]{escaped}[/cyan]"

    # Errors
    if "error" in stripped.lower() or "traceback" in stripped.lower():
        return f"[bold red]{escaped}[/bold red]"

    # Thinking phase → dim italic
    if phase == "thinking":
        return f"[dim italic]{escaped}[/dim italic]"

    # Default
    return f"[dim]{escaped}[/dim]"


def _make_safe_output(app_log_fn, log_path: Path):
    """Create output callback with log coloring and phase separators."""
    state = {"filtering": False, "prompt_done": False, "phase": "acting"}
    lock = threading.Lock()
    # Keep log file open for efficient per-line writes
    try:
        log_file = open(log_path, "a")  # noqa: SIM115
    except OSError:
        log_file = None

    def on_output(line: str):
        with lock:
            # 1. Always write raw line to log file
            if log_file:
                try:
                    log_file.write(line + "\n")
                    log_file.flush()
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
            if stripped == "user":
                # New agent session starting — re-enter prompt filtering
                state["filtering"] = True
                state["prompt_done"] = False
                return
            if stripped == "":
                return

            # 4. Classify and color the line
            colored = _classify_line(line, state["phase"])
            try:
                app_log_fn(colored)
            except Exception:
                pass

    def _close():
        if log_file:
            try:
                log_file.close()
            except OSError:
                pass
    on_output.close = _close

    return on_output


def _resolve_agent(agent_name: str | None, agent_configs: dict | None = None):
    """Resolve agent by name or auto-detect, with per-agent config."""
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


def do_run(repo_path: Path, agent_name: str | None, dry_run: bool) -> None:
    """Single-agent mode — backward compatible."""
    research = repo_path / ".research"
    if not research.is_dir():
        console.print("[red]Error:[/red] .research/ not found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    program_md = research / "program.md"
    if not program_md.exists():
        console.print("[red]Error:[/red] .research/program.md not found.")
        raise SystemExit(1)

    # Load config before agent resolution so agent_config is available
    cfg = load_config(research)
    agent = _resolve_agent(agent_name, cfg.agent_config)

    if dry_run:
        console.print(f"[bold]Agent:[/bold] {agent.name}")
        console.print(f"[bold]Command:[/bold] {' '.join(agent.build_command(program_md, repo_path))}")
        console.print(f"[bold]Working directory:[/bold] {repo_path}")
        console.print("\n[dim]Dry run -- no agent launched.[/dim]")
        return
    watchdog = TimeoutWatchdog(cfg.timeout, on_timeout=lambda: agent.terminate())

    # Launch with Textual TUI
    from open_researcher.tui.app import ResearchApp

    done = threading.Event()
    exit_codes: dict[str, int] = {}
    on_output_ref: list = []

    def start_threads():
        on_output = _make_safe_output(app.append_exp_log, research / "run.log")
        on_output_ref.append(on_output)
        watchdog.start()
        _launch_agent_thread(agent, repo_path, on_output, done, exit_codes, "agent")

    app = ResearchApp(repo_path, multi=False, on_ready=start_threads)
    try:
        app.run()
    finally:
        if on_output_ref and hasattr(on_output_ref[0], 'close'):
            on_output_ref[0].close()

    # Cleanup: stop watchdog and terminate agent subprocess when TUI exits
    watchdog.stop()
    agent.terminate()

    code = exit_codes.get("agent", -1)
    if code == 0:
        console.print(f"\n[green]Agent {agent.name} completed successfully.[/green]")
    else:
        console.print(f"\n[red]Agent {agent.name} exited with code {code}.[/red]")

    from open_researcher.status_cmd import print_status

    print_status(repo_path)


def _run_parallel_workers(
    repo_path: Path,
    research: Path,
    cfg,
    exp_agent,
    idea_agent,
    on_output,
    stop: threading.Event,
    exit_codes: dict,
    watchdog,
) -> None:
    """Launch parallel experiment workers via WorkerManager."""
    from open_researcher.gpu_manager import GPUManager
    from open_researcher.idea_pool import IdeaPool
    from open_researcher.worker import WorkerManager

    gpu_manager = GPUManager(research / "gpu_status.json", cfg.remote_hosts)
    idea_pool = IdeaPool(research / "idea_pool.json")

    def agent_factory():
        name = cfg.worker_agent or exp_agent.name
        return get_agent(name, config=cfg.agent_config.get(name))

    wm = WorkerManager(
        repo_path=repo_path,
        research_dir=research,
        gpu_manager=gpu_manager,
        idea_pool=idea_pool,
        agent_factory=agent_factory,
        max_workers=cfg.max_workers,
        on_output=on_output,
    )

    def _parallel_loop():
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
                on_output("[system] No pending ideas after idea agent. Stopping.")
                break

            on_output(f"[system] Launching {cfg.max_workers} parallel workers...")
            watchdog.reset()
            wm.start()
            wm.join()
            watchdog.stop()

            if not _has_pending_ideas(research):
                on_output("[system] All ideas processed.")
                break

        on_output("[system] Parallel execution finished.")

    t = threading.Thread(target=_parallel_loop, daemon=True)
    t.start()


def do_run_multi(
    repo_path: Path,
    idea_agent_name: str | None,
    exp_agent_name: str | None,
    dry_run: bool,
) -> None:
    """Dual-agent mode — Idea Agent + Experiment Agent in parallel."""
    research = repo_path / ".research"
    if not research.is_dir():
        console.print("[red]Error:[/red] .research/ not found. Run 'open-researcher init' first.")
        raise SystemExit(1)

    idea_program = research / "idea_program.md"
    exp_program = research / "experiment_program.md"

    for p in [idea_program, exp_program]:
        if not p.exists():
            console.print(f"[red]Error:[/red] {p.name} not found. Re-run 'open-researcher init'.")
            raise SystemExit(1)

    # Load config before agent resolution so agent_config is available
    cfg = load_config(research)
    idea_agent = _resolve_agent(idea_agent_name, cfg.agent_config)
    exp_agent = _resolve_agent(exp_agent_name, cfg.agent_config)

    if dry_run:
        console.print(f"[bold]Idea Agent:[/bold] {idea_agent.name}")
        console.print(f"[bold]Experiment Agent:[/bold] {exp_agent.name}")
        console.print(f"[bold]Working directory:[/bold] {repo_path}")
        console.print("\n[dim]Dry run -- no agents launched.[/dim]")
        return

    # Ensure worktrees directory exists for parallel experiments
    worktrees_dir = research / "worktrees"
    worktrees_dir.mkdir(exist_ok=True)
    crash_counter = CrashCounter(cfg.max_crashes)
    phase_gate = PhaseGate(research, cfg.mode)

    # Launch with Textual TUI
    from open_researcher.tui.app import ResearchApp

    stop = threading.Event()
    exit_codes: dict[str, int] = {}

    on_output_ref: list = []

    def start_threads():
        on_output = _make_safe_output(app.append_log, research / "run.log")
        on_output_ref.append(on_output)

        # Watchdog resets each cycle — terminates experiment agent on timeout
        watchdog = TimeoutWatchdog(cfg.timeout, on_timeout=lambda: exp_agent.terminate())

        # Check if parallel workers should be used
        if cfg.max_workers > 1:
            _run_parallel_workers(
                repo_path, research, cfg, exp_agent, idea_agent,
                on_output, stop, exit_codes, watchdog,
            )
            return

        def _alternating():
            """Alternate: idea agent generates 1 idea -> experiment agent runs it -> repeat."""
            cycle = 0
            while not stop.is_set():
                cycle += 1

                # --- Idea Agent: generate 1 idea ---
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
                    on_output("[system] Idea Agent finished but no pending ideas. Stopping.")
                    break

                on_output(f"[system] Idea Agent done (code={code}). Starting Experiment Agent...")

                # --- Experiment Agent: run pending ideas ---
                exp_run = 0
                while not stop.is_set():
                    exp_run += 1
                    on_output(f"[exp] Starting experiment agent (run #{exp_run})...")
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

                    # --- Runtime controls: crash counter & phase gate ---
                    status = _read_latest_status(research)
                    if status and crash_counter.record(status):
                        on_output(f"[system] Crash limit reached ({cfg.max_crashes} consecutive crashes). Pausing.")
                        _set_paused(research, f"Crash limit reached: {cfg.max_crashes} consecutive crashes")
                        stop.set()
                        break

                    phase = phase_gate.check()
                    if phase:
                        on_output(f"[system] Phase transition to '{phase}' — pausing for review.")
                        _set_paused(research, f"Phase transition to '{phase}'")
                        break

                    if not _has_pending_ideas(research):
                        on_output("[exp] No more pending ideas.")
                        break
                    on_output("[exp] Pending ideas remain, restarting...")

                if stop.is_set():
                    break
                on_output(f"[system] Cycle {cycle} complete. Starting next idea generation...")

            watchdog.stop()
            on_output("[system] All cycles finished.")

        t = threading.Thread(target=_alternating, daemon=True)
        t.start()

    app = ResearchApp(repo_path, multi=True, on_ready=start_threads)
    try:
        app.run()
    finally:
        if on_output_ref and hasattr(on_output_ref[0], 'close'):
            on_output_ref[0].close()

    # Cleanup: terminate agent subprocesses when TUI exits
    stop.set()  # Signal alternating thread to stop when TUI exits
    idea_agent.terminate()
    exp_agent.terminate()

    for key, name in [("idea", "Idea Agent"), ("exp", "Experiment Agent")]:
        code = exit_codes.get(key, -1)
        if code == 0:
            console.print(f"[green]{name} completed successfully.[/green]")
        else:
            console.print(f"[red]{name} exited with code {code}.[/red]")

    from open_researcher.status_cmd import print_status

    print_status(repo_path)
