"""PaperFarm Hub CLI commands."""

from __future__ import annotations

import os
import shlex
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import typer
from rich.console import Console

from open_researcher.hub import (
    HUB_REGISTRY_URL,
    apply_manifest_to_config_yaml,
    fetch_index,
    fetch_index_full,
    fetch_manifest,
    manifest_summary,
    manifest_to_bootstrap_overrides,
)

hub_app = typer.Typer(help="PaperFarm Hub — verified research environment registry.")
console = Console()


@hub_app.command()
def lookup(
    arxiv_id: str = typer.Argument(help="ArXiv ID (e.g. 2507.19457)"),
    registry: str = typer.Option(HUB_REGISTRY_URL, "--registry", help="Hub registry base URL"),
) -> None:
    """Show the Hub manifest for a paper."""
    try:
        manifest = fetch_manifest(arxiv_id, registry_url=registry)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]PaperFarm Hub — {arxiv_id}[/bold]")
    console.print(manifest_summary(manifest))

    overrides = manifest_to_bootstrap_overrides(manifest)
    if overrides:
        console.print("\n[dim]Bootstrap overrides (applied by `hub apply`):[/dim]")
        for k, v in overrides.items():
            console.print(f"  [cyan]{k}[/cyan] = {v}")


@hub_app.command(name="list")
def list_entries(
    area: str = typer.Option(None, "--area", help="Filter by area (e.g. nlp, cv, ml-systems, agents)"),
    award: str = typer.Option(None, "--award", help="Filter by award (best-paper, oral, spotlight)"),
    registry: str = typer.Option(HUB_REGISTRY_URL, "--registry", help="Hub registry base URL"),
) -> None:
    """List all entries in the Hub registry."""
    from rich.table import Table

    try:
        entries = fetch_index_full(registry_url=registry)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    if area:
        entries = [e for e in entries if e.get("area") == area]
    if award:
        entries = [e for e in entries if e.get("venue", {}).get("award") == award]

    table = Table(title=f"PaperFarm Hub — {len(entries)} entries")
    table.add_column("ArXiv ID", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Area")
    table.add_column("Venue")
    table.add_column("Award")
    table.add_column("GPU")
    table.add_column("✓")

    award_style = {"best-paper": "[gold1]★[/gold1]", "oral": "[green]●[/green]", "spotlight": "[blue]◆[/blue]"}

    for e in entries:
        venue = e.get("venue", {})
        env = e.get("env_summary", {})
        status = e.get("status", {})
        award_val = venue.get("award") or ""
        table.add_row(
            e.get("arxiv_id", ""),
            e.get("short_name", e.get("folder", "")),
            e.get("area", ""),
            f"{venue.get('name', '')} {venue.get('year', '')}",
            award_style.get(award_val, award_val),
            "yes" if env.get("gpu_required") else "no",
            str(status.get("verified_count", 0)),
        )

    console.print(table)


@hub_app.command()
def install(
    arxiv_id: str = typer.Argument(help="ArXiv ID (e.g. 2507.19457)"),
    registry: str = typer.Option(HUB_REGISTRY_URL, "--registry", help="Hub registry base URL"),
    live: bool = typer.Option(False, "--live", help="Pass --live to smoke_test.py (makes real API calls)"),
    provider: str = typer.Option("openai", "--provider", help="LLM provider for --live (openai/anthropic/ollama)"),
    skip_smoke: bool = typer.Option(False, "--skip-smoke", help="Run install_command but skip smoke_test.py"),
) -> None:
    """
    Fetch Hub manifest, run install_command and smoke_test.py.

    Equivalent to reading the paper's README and running the verified install steps.
    """
    try:
        manifest = fetch_manifest(arxiv_id, registry_url=registry)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    env_block = manifest.get("env") if isinstance(manifest.get("env"), dict) else {}
    install_cmd = str(env_block.get("install_command", "") or "").strip()
    test_cmd = str(env_block.get("test_command", "") or "").strip()

    console.print(f"\n[bold]Hub install — {arxiv_id}[/bold]")
    console.print(manifest_summary(manifest))

    # Check hardware requirements
    resources = manifest.get("resources") if isinstance(manifest.get("resources"), dict) else {}
    gpu_req = str(resources.get("gpu", "none") or "none").strip().lower()
    min_vram = resources.get("min_vram_gb")
    if gpu_req == "required":
        try:
            import torch
            if not torch.cuda.is_available():
                console.print("\n[yellow][WARN] This paper requires a GPU but CUDA is not available.[/yellow]")
            elif min_vram:
                vram = torch.cuda.get_device_properties(0).total_memory / 1e9
                if vram < min_vram:
                    console.print(
                        f"\n[yellow][WARN] Min VRAM required: {min_vram}GB, "
                        f"available: {vram:.1f}GB.[/yellow]"
                    )
        except ImportError:
            if gpu_req == "required":
                console.print("\n[yellow][WARN] GPU required but torch not installed — cannot check VRAM.[/yellow]")
        except Exception as exc:
            console.print(f"\n[yellow][WARN] GPU check failed: {exc}[/yellow]")

    # Step 1: install
    if not install_cmd:
        console.print("\n[yellow]No install_command in manifest — skipping install step.[/yellow]")
    else:
        console.print("\n[bold]Step 1/2: Install[/bold]")
        console.print(f"  $ {install_cmd}")
        try:
            argv = shlex.split(install_cmd)
        except ValueError:
            console.print("[red]Invalid install_command in manifest (cannot parse).[/red]")
            raise typer.Exit(code=1)
        result = subprocess.run(argv, timeout=600)
        if result.returncode != 0:
            exit_code = max(result.returncode, 1)
            console.print(f"[red]Install failed (exit {result.returncode}).[/red]")
            raise typer.Exit(code=exit_code)
        console.print("[green]Install OK.[/green]")

    # Step 2: smoke test
    if skip_smoke or not test_cmd:
        if not skip_smoke and not test_cmd:
            console.print("[yellow]No test_command in manifest — skipping smoke test.[/yellow]")
        raise typer.Exit(code=0)

    console.print("\n[bold]Step 2/2: Smoke test[/bold]")

    # Fetch smoke_test.py from Hub into a temp file
    folder = _get_folder(arxiv_id, registry)
    from urllib.parse import quote
    smoke_url = f"{registry}/hub/{quote(folder, safe='')}/smoke_test.py"
    console.print("  Fetching smoke_test.py from Hub...")
    try:
        with urllib.request.urlopen(smoke_url, timeout=10) as resp:
            smoke_src = resp.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, UnicodeDecodeError, OSError) as exc:
        console.print(f"[red]Failed to fetch smoke_test.py: {exc}[/red]")
        raise typer.Exit(code=1)

    with tempfile.NamedTemporaryFile(suffix="_smoke_test.py", mode="w", delete=False) as tmp:
        tmp.write(smoke_src)
        tmp_path = tmp.name

    try:
        smoke_argv = [sys.executable, tmp_path]
        if live:
            smoke_argv += ["--live", "--provider", provider]

        console.print(f"  $ {' '.join(smoke_argv[1:])}")
        result = subprocess.run(smoke_argv, timeout=300)
        if result.returncode != 0:
            exit_code = max(result.returncode, 1)
            console.print(f"[red]Smoke test failed (exit {result.returncode}).[/red]")
            raise typer.Exit(code=exit_code)
    except subprocess.TimeoutExpired:
        console.print("[red]Smoke test timed out after 300s.[/red]")
        raise typer.Exit(code=124)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    console.print(f"\n[green]✅  Hub install complete for {arxiv_id}.[/green]")
    console.print(
        f"[dim]Run `open-researcher hub apply {arxiv_id}` to write these settings into .research/config.yaml[/dim]"
    )


@hub_app.command()
def apply(
    arxiv_id: str = typer.Argument(help="ArXiv ID (e.g. 2507.19457)"),
    registry: str = typer.Option(HUB_REGISTRY_URL, "--registry", help="Hub registry base URL"),
    repo_path: str = typer.Option(".", "--path", help="Path to the research repo"),
) -> None:
    """
    Write Hub manifest bootstrap fields into .research/config.yaml.

    After running this, `open-researcher run` will use the Hub-verified
    install and smoke commands automatically.
    """
    research_dir = Path(repo_path) / ".research"

    try:
        manifest = fetch_manifest(arxiv_id, registry_url=registry)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    try:
        written = apply_manifest_to_config_yaml(manifest, research_dir)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    if not written:
        console.print("[yellow]No bootstrap overrides to write (manifest has no install/test commands).[/yellow]")
        return

    console.print(f"\n[bold]Applied Hub manifest {arxiv_id} → .research/config.yaml[/bold]")
    for k, v in written.items():
        console.print(f"  [cyan]{k}[/cyan] = {v}")
    console.print("\n[dim]Run `open-researcher run` to start the workflow with Hub-verified settings.[/dim]")


def _get_folder(arxiv_id: str, registry: str) -> str:
    index = fetch_index(registry_url=registry)
    folder = index.get(arxiv_id)
    if not folder:
        raise ValueError(f"arxiv_id {arxiv_id!r} not found in Hub index")
    return folder
