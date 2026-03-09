"""Parallel worker manager -- run experiments across multiple GPUs."""

import threading
from pathlib import Path
from typing import Callable

from open_researcher.activity import ActivityMonitor
from open_researcher.gpu_manager import GPUManager
from open_researcher.idea_pool import IdeaPool


class WorkerManager:
    """Orchestrate parallel experiment workers across GPUs."""

    def __init__(
        self,
        repo_path: Path,
        research_dir: Path,
        gpu_manager: GPUManager,
        idea_pool: IdeaPool,
        agent_factory: Callable,
        max_workers: int,
        on_output: Callable[[str], None],
    ):
        self.repo_path = repo_path
        self.research_dir = research_dir
        self.gpu_manager = gpu_manager
        self.idea_pool = idea_pool
        self.agent_factory = agent_factory
        self.max_workers = max_workers
        self.on_output = on_output
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._activity = ActivityMonitor(research_dir)

    def start(self) -> None:
        """Start worker threads based on available GPUs."""
        self._stop.clear()
        self._workers.clear()
        try:
            gpus = self.gpu_manager.refresh()
        except Exception:
            gpus = []
        available = [g for g in gpus if g.get("allocated_to") is None]
        if available:
            n_workers = min(self.max_workers, len(available)) if self.max_workers > 0 else len(available)
        else:
            # 无可用 GPU 时限制为最多 1 个 worker
            n_workers = min(self.max_workers, 1) if self.max_workers > 0 else 1
        n_workers = max(n_workers, 1)  # at least 1 worker

        for i in range(n_workers):
            gpu = available[i] if i < len(available) else None
            t = threading.Thread(
                target=self._worker_loop, args=(i, gpu), daemon=True
            )
            t.start()
            self._workers.append(t)
        self.on_output(f"[system] Started {n_workers} worker(s)")

    def stop(self) -> None:
        """Signal all workers to stop."""
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        """Wait for all worker threads to finish."""
        for t in self._workers:
            t.join(timeout=timeout)

    def _worker_loop(self, worker_id: int, gpu: dict | None) -> None:
        wid = f"worker-{worker_id}"
        gpu_env: dict[str, str] = {}
        actual_host: str | None = None
        actual_device: int | None = None

        if gpu:
            # 使用 allocate 的返回值作为实际分配结果
            alloc_result = self.gpu_manager.allocate(tag=wid)
            if alloc_result is not None:
                actual_host, actual_device = alloc_result
            else:
                # allocate 未能分配，回退到已选的 gpu 信息
                actual_host, actual_device = gpu["host"], gpu["device"]
            gpu_env = {"CUDA_VISIBLE_DEVICES": str(actual_device)}
            self.on_output(f"[{wid}] Allocated GPU {actual_host}:{actual_device}")

        while not self._stop.is_set():
            idea = self.idea_pool.claim_idea(wid)
            if not idea:
                self.on_output(f"[{wid}] No more pending ideas, stopping")
                break

            self._activity.update_worker(
                "experiment_agent",
                wid,
                status="running",
                idea=idea["description"][:50],
            )
            self.on_output(f"[{wid}] Running: {idea['description'][:60]}")
            if gpu_env:
                self.on_output(f"[{wid}] Using GPU env: {gpu_env}")

            # Create agent and run in this worker's context
            agent = self.agent_factory()
            try:
                code = agent.run(
                    self.repo_path,
                    on_output=self.on_output,
                    program_file="experiment_program.md",
                    env=gpu_env if gpu_env else None,
                )
                if code == 0:
                    self.idea_pool.mark_done(idea["id"], metric_value=None, verdict="completed")
                else:
                    self.idea_pool.update_status(idea["id"], "skipped")
            except Exception as exc:
                self.on_output(f"[{wid}] Error: {exc}")
                self.idea_pool.update_status(idea["id"], "skipped")

        self._activity.update_worker(
            "experiment_agent", wid, status="idle"
        )
        if gpu and actual_host is not None and actual_device is not None:
            try:
                self.gpu_manager.release(actual_host, actual_device)
            except Exception:
                pass
