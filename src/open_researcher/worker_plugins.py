"""Optional worker runtime plugins for advanced parallel execution."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from open_researcher.failure_memory import (
    MEMORY_POLICY,
    FailureMemoryLedger,
    classify_failure,
)
from open_researcher.gpu_manager import GPUManager
from open_researcher.resource_scheduler import (
    DEFAULT_SINGLE_GPU_HEADROOM_MB,
    DEFAULT_SINGLE_GPU_HEADROOM_RATIO,
    DEFAULT_SINGLE_GPU_QUALIFICATION_TIMEOUT_MINUTES,
    candidate_single_gpu_saturation_profiles,
    is_single_gpu_saturation_objective,
    normalize_execution_shape,
    normalize_resource_profiles,
    normalize_resource_request,
    resolve_gpu_count,
    resolve_gpu_mem_mb,
    single_gpu_saturation_budget_mb,
    sort_pending_ideas,
)
from open_researcher.worktree import create_worktree, remove_worktree

logger = logging.getLogger(__name__)


class WorkspaceIsolationError(RuntimeError):
    """Raised when worker workspace isolation cannot be established."""


@dataclass(slots=True)
class GPUAllocation:
    """Concrete GPU allocation for one worker."""

    host: str | None = None
    device: int | None = None
    devices: list[dict] = field(default_factory=list)
    reservations: list[dict] = field(default_factory=list)
    resource_request: dict = field(default_factory=dict)
    selected_profile: dict = field(default_factory=dict)
    execution_shape: dict = field(default_factory=dict)
    saturation_context: dict = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    log_lines: list[str] = field(default_factory=list)


class GPUAllocatorPlugin:
    """Optional GPU scheduling capability for worker execution."""

    def __init__(
        self,
        manager: GPUManager,
        *,
        default_memory_per_worker_mb: int = 4096,
        backfill_threshold_minutes: int = 30,
        scheduler_objective: str = "",
        resource_profiles: dict[str, Any] | None = None,
        single_task_headroom_ratio: float = DEFAULT_SINGLE_GPU_HEADROOM_RATIO,
        single_task_headroom_mb: int = DEFAULT_SINGLE_GPU_HEADROOM_MB,
        single_gpu_qualification_timeout_minutes: int = DEFAULT_SINGLE_GPU_QUALIFICATION_TIMEOUT_MINUTES,
    ):
        self.manager = manager
        self.default_memory_per_worker_mb = max(int(default_memory_per_worker_mb or 0), 0)
        self.backfill_threshold_minutes = max(int(backfill_threshold_minutes or 0), 1)
        self.scheduler_objective = str(scheduler_objective or "").strip()
        self.single_gpu_saturation = is_single_gpu_saturation_objective(self.scheduler_objective)
        self.resource_profiles = normalize_resource_profiles(
            resource_profiles or {},
            default_gpu_mem_mb=self.default_memory_per_worker_mb,
        )
        self.single_task_headroom_ratio = max(float(single_task_headroom_ratio or 0.0), 0.0)
        self.single_task_headroom_mb = max(int(single_task_headroom_mb or 0), 0)
        self.single_gpu_qualification_timeout_minutes = max(
            int(single_gpu_qualification_timeout_minutes or DEFAULT_SINGLE_GPU_QUALIFICATION_TIMEOUT_MINUTES),
            1,
        )

    def worker_slots(self, max_workers: int) -> list[dict | None]:
        if max_workers <= 0:
            return []
        if self.single_gpu_saturation:
            try:
                status = self.manager.refresh()
            except Exception:
                logger.debug("GPU refresh failed in saturation mode", exc_info=True)
                status = []
            slots = []
            for gpu in status if isinstance(status, list) else []:
                reservations = gpu.get("reservations", [])
                if reservations:
                    continue
                if self.manager.effective_free_mb(gpu) <= 0:
                    continue
                slots.append(
                    {
                        "host": gpu.get("host", "local"),
                        "device": gpu.get("device", 0),
                    }
                )
            if slots:
                return slots[:max_workers]
        try:
            slots = self.manager.plan_slots(
                max_workers=max_workers,
                memory_mb=max(self.default_memory_per_worker_mb, 1),
            )
        except Exception:
            logger.debug("GPU plan_slots failed", exc_info=True)
            slots = []
        if isinstance(slots, list) and slots:
            return slots
        fallback = max(max_workers, 1)
        return [None] * max(fallback, 1)

    def _status_rows(self) -> list[dict]:
        try:
            status = self.manager.refresh()
        except Exception:
            logger.debug("GPU status refresh failed", exc_info=True)
            status = []
        return status if isinstance(status, list) else []

    @staticmethod
    def _preferred_gpu(status: list[dict], preferred: dict | None) -> dict | None:
        if not isinstance(preferred, dict):
            return None
        try:
            preferred_device = int(preferred.get("device"))
        except (TypeError, ValueError):
            return None
        preferred_host = str(preferred.get("host", "") or "").strip() or "local"
        for gpu in status:
            if str(gpu.get("host", "local") or "local").strip() != preferred_host:
                continue
            if int(gpu.get("device", -1) or -1) != preferred_device:
                continue
            return gpu
        return None

    def _single_gpu_saturation_plan(
        self,
        idea: dict,
        *,
        preferred: dict | None = None,
        status: list[dict] | None = None,
    ) -> dict[str, Any] | None:
        rows = status if isinstance(status, list) else self._status_rows()
        preferred_gpu = self._preferred_gpu(rows, preferred)
        ordered_rows: list[dict] = []
        if preferred_gpu is not None:
            ordered_rows.append(preferred_gpu)
        for gpu in rows:
            if preferred_gpu is not None and gpu is preferred_gpu:
                continue
            ordered_rows.append(gpu)
        for gpu in ordered_rows:
            reservations = gpu.get("reservations", [])
            if reservations:
                continue
            gpu_budget_mb, headroom_mb = single_gpu_saturation_budget_mb(
                total_memory_mb=int(gpu.get("memory_total", 0) or 0),
                free_memory_mb=int(gpu.get("memory_free", 0) or 0),
                headroom_ratio=self.single_task_headroom_ratio,
                minimum_headroom_mb=self.single_task_headroom_mb,
            )
            if gpu_budget_mb <= 0:
                continue
            candidate_profiles = candidate_single_gpu_saturation_profiles(
                idea,
                resource_profiles=self.resource_profiles,
                default_gpu_mem_mb=self.default_memory_per_worker_mb,
            )
            default_profile = next(
                (item for item in candidate_profiles if str(item.get("source", "")).strip() == "idea"),
                candidate_profiles[0] if candidate_profiles else {},
            )
            explicit_profile_name = str(idea.get("resource_profile", "") or "").strip()
            if explicit_profile_name:
                default_profile = next(
                    (item for item in candidate_profiles if str(item.get("name", "")).strip() == explicit_profile_name),
                    default_profile,
                )
            execution_shape = normalize_execution_shape(
                (default_profile or {}).get("execution_shape", idea.get("execution_shape"))
            )
            request = {
                "gpu_count": 1,
                "gpu_mem_mb": max(self.default_memory_per_worker_mb, 1),
                "shareable": False,
                "exclusive": True,
            }
            saturation_context = {
                "objective": self.scheduler_objective,
                "agent_autonomy": True,
                "selected_profile": "",
                "default_profile": str((default_profile or {}).get("name", "")).strip(),
                "gpu_budget_mb": gpu_budget_mb,
                "headroom_mb": headroom_mb,
                "qualification_timeout_minutes": self.single_gpu_qualification_timeout_minutes,
                "profiles": candidate_profiles,
                "qualification_profiles": candidate_profiles,
                "execution_shape": execution_shape,
                "workload_label": str(idea.get("workload_label", "")).strip(),
                "resource_profile": explicit_profile_name,
                "device": {"host": str(gpu.get("host", "local") or "local"), "device": int(gpu.get("device", 0) or 0)},
                "total_memory_mb": int(gpu.get("memory_total", 0) or 0),
                "free_memory_mb": int(gpu.get("memory_free", 0) or 0),
                "expected_memory_mb": int((default_profile or {}).get("expected_memory_mb", 0) or 0),
            }
            return {
                "gpu": gpu,
                "request": request,
                "selected_profile": default_profile or {},
                "execution_shape": execution_shape,
                "saturation_context": saturation_context,
            }
        return None

    def describe_request(self, idea: dict) -> dict:
        if self.single_gpu_saturation:
            plan = self._single_gpu_saturation_plan(idea)
            if plan is not None:
                return dict(plan["request"])
            request = normalize_resource_request(
                idea.get("resource_request"),
                default_gpu_mem_mb=self.default_memory_per_worker_mb,
                fallback_gpu_hint=1,
            )
            request["gpu_count"] = 1
            request["exclusive"] = True
            request["shareable"] = False
            request["gpu_mem_mb"] = resolve_gpu_mem_mb(
                request,
                default_gpu_mem_mb=self.default_memory_per_worker_mb,
                gpu_count=1,
            )
            return request
        request = normalize_resource_request(
            idea.get("resource_request"),
            default_gpu_mem_mb=self.default_memory_per_worker_mb,
            fallback_gpu_hint=idea.get("gpu_hint"),
        )
        status = self._status_rows()
        gpu_count = resolve_gpu_count(request, gpu_available=bool(status))
        request = dict(request)
        request["gpu_count"] = gpu_count
        request["gpu_mem_mb"] = resolve_gpu_mem_mb(
            request,
            default_gpu_mem_mb=self.default_memory_per_worker_mb,
            gpu_count=int(gpu_count or 0),
        )
        return request

    def _request_fits(self, request: dict, status: list[dict]) -> bool:
        return self._request_fits_on_devices(request, status, required_devices=None)

    @staticmethod
    def _required_devices_from_execution_shape(execution_shape: dict) -> list[dict]:
        raw = execution_shape.get("gpus") if isinstance(execution_shape, dict) else None
        if raw in {None, ""}:
            return []
        required: list[dict] = []

        def _append(host: str, device: int) -> None:
            key = {"host": str(host or "local").strip() or "local", "device": int(device)}
            if key not in required:
                required.append(key)

        def _parse_token(token: str) -> None:
            part = str(token or "").strip()
            if not part:
                return
            if part.startswith("local:"):
                tail = part.split(":", 1)[1].strip()
                if tail.isdigit():
                    _append("local", int(tail))
                return
            if part.isdigit():
                _append("local", int(part))

        if isinstance(raw, str):
            for token in raw.split(","):
                _parse_token(token)
            return required
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    host = str(item.get("host", "local") or "local").strip() or "local"
                    try:
                        device = int(item.get("device", 0) or 0)
                    except (TypeError, ValueError):
                        continue
                    _append(host, device)
                    continue
                _parse_token(str(item))
        return required

    def _request_fits_on_devices(
        self,
        request: dict,
        status: list[dict],
        *,
        required_devices: list[dict] | None,
    ) -> bool:
        requested_gpu_count = resolve_gpu_count(request, gpu_available=bool(status))
        if requested_gpu_count <= 0:
            return True
        required_keys = {
            (
                str(item.get("host", "local") or "local").strip() or "local",
                int(item.get("device", 0) or 0),
            )
            for item in (required_devices or [])
            if isinstance(item, dict)
        }
        if required_keys and len(required_keys) < requested_gpu_count:
            return False
        requested_mem = max(
            resolve_gpu_mem_mb(
                request,
                default_gpu_mem_mb=self.default_memory_per_worker_mb,
                gpu_count=requested_gpu_count,
            ),
            1,
        )
        matched = 0
        for gpu in status:
            key = (
                str(gpu.get("host", "local") or "local").strip() or "local",
                int(gpu.get("device", 0) or 0),
            )
            if required_keys and key not in required_keys:
                continue
            if self.manager.effective_free_mb(gpu) < requested_mem:
                continue
            reservations = gpu.get("reservations", [])
            has_existing = bool(reservations)
            if has_existing and not self.manager.allow_same_gpu_packing:
                continue
            if has_existing and bool(request.get("exclusive", False)):
                continue
            if has_existing and not bool(request.get("shareable", True)):
                continue
            matched += 1
            if matched >= requested_gpu_count:
                return True
        return False

    def select_claimable_idea(self, pending_ideas: list[dict]) -> str | None:
        if not pending_ideas:
            return None
        ordered = sort_pending_ideas(
            pending_ideas,
            default_gpu_mem_mb=self.default_memory_per_worker_mb,
            backfill_threshold_minutes=self.backfill_threshold_minutes,
        )
        status = self._status_rows()
        for idea in ordered:
            if self.single_gpu_saturation:
                if self._single_gpu_saturation_plan(idea, status=status) is not None:
                    idea_id = str(idea.get("id", "")).strip()
                    if idea_id:
                        return idea_id
                continue
            execution_shape = normalize_execution_shape(idea.get("execution_shape"))
            required_devices = self._required_devices_from_execution_shape(execution_shape)
            if self._request_fits_on_devices(self.describe_request(idea), status, required_devices=required_devices):
                idea_id = str(idea.get("id", "")).strip()
                if idea_id:
                    return idea_id
        return None

    def allocate_for_idea(self, worker_id: str, idea: dict, preferred: dict | None = None) -> GPUAllocation | None:
        plan = self._single_gpu_saturation_plan(idea, preferred=preferred) if self.single_gpu_saturation else None
        request = dict(plan["request"]) if plan is not None else self.describe_request(idea)
        gpu_count = int(request.get("gpu_count", 0) or 0)
        if gpu_count <= 0:
            return GPUAllocation(resource_request=request)
        selected_profile = dict(plan["selected_profile"]) if plan is not None else {}
        execution_shape = dict(plan["execution_shape"]) if plan is not None else normalize_execution_shape(
            idea.get("execution_shape")
        )
        required_devices = self._required_devices_from_execution_shape(execution_shape)
        saturation_context = dict(plan["saturation_context"]) if plan is not None else {}
        metadata = {
            "kind": "experiment",
            "task_kind": str(idea.get("workload_label", "")).strip(),
            "idea_id": str(idea.get("id", "")).strip(),
            "worker_id": str(worker_id or "").strip(),
            "frontier_id": str(idea.get("frontier_id", "")).strip(),
            "execution_id": str(idea.get("execution_id", "")).strip(),
            "resource_profile": str(
                selected_profile.get("name", "") or idea.get("resource_profile", "")
            ).strip(),
            "workload_label": str(idea.get("workload_label", "")).strip(),
        }
        try:
            reserve_preferred = preferred
            if plan is not None:
                reserve_preferred = {
                    "host": plan["gpu"].get("host", "local"),
                    "device": plan["gpu"].get("device", 0),
                }
            if reserve_preferred is None and len(required_devices) == 1:
                reserve_preferred = dict(required_devices[0])
            reserve_kwargs = {
                "metadata": metadata,
                "preferred": reserve_preferred,
            }
            if required_devices:
                reserve_kwargs["required_devices"] = required_devices
            try:
                reservations = self.manager.reserve(worker_id, request, **reserve_kwargs)
            except TypeError:
                reserve_kwargs.pop("required_devices", None)
                reservations = self.manager.reserve(worker_id, request, **reserve_kwargs)
        except Exception:
            logger.debug("GPU reservation failed", exc_info=True)
            return None
        if not isinstance(reservations, list):
            return None
        if reservations is None:
            return None
        hosts = {str(item.get("host", "")).strip() for item in reservations if str(item.get("host", "")).strip()}
        if len(hosts) > 1:
            self.manager.release_reservations(reservations)
            logger.debug("Rejected cross-host GPU reservation for worker %s: %s", worker_id, sorted(hosts))
            return None
        visible_devices = ",".join(str(item.get("device")) for item in reservations)
        host = str(reservations[0].get("host", "local")).strip() if reservations else None
        device = int(reservations[0].get("device", 0)) if reservations else None
        reserved_mb = sum(int(item.get("memory_mb", 0) or 0) for item in reservations)

        return GPUAllocation(
            host=host,
            device=device,
            devices=[
                {"host": str(item.get("host", "local")).strip(), "device": int(item.get("device", 0))}
                for item in reservations
            ],
            reservations=reservations,
            resource_request=request,
            selected_profile=selected_profile,
            execution_shape=execution_shape,
            saturation_context=saturation_context,
            env={
                "CUDA_VISIBLE_DEVICES": visible_devices,
                "OPEN_RESEARCHER_GPU_MEMORY_BUDGET_MB": str(
                    int(saturation_context.get("gpu_budget_mb", request.get("gpu_mem_mb", 0)) or 0)
                ),
                "OPEN_RESEARCHER_GPU_REQUESTED_MEMORY_MB": str(int(request.get("gpu_mem_mb", 0) or 0)),
                "OPEN_RESEARCHER_GPU_COUNT": str(int(request.get("gpu_count", 0) or 0)),
                "OPEN_RESEARCHER_RESOURCE_PROFILE": str(
                    selected_profile.get("name", "") or idea.get("resource_profile", "")
                ).strip(),
                "OPEN_RESEARCHER_SELECTED_EXECUTION_SHAPE_JSON": json.dumps(execution_shape, separators=(",", ":")),
                "OPEN_RESEARCHER_SINGLE_GPU_SATURATION": "1" if self.single_gpu_saturation else "",
                "OPEN_RESEARCHER_AGENT_OWNS_SATURATION_SHAPE": "1" if self.single_gpu_saturation else "",
                "OPEN_RESEARCHER_GPU_HEADROOM_MB": str(int(saturation_context.get("headroom_mb", 0) or 0)),
                "OPEN_RESEARCHER_SINGLE_GPU_QUALIFICATION_TIMEOUT_MINUTES": str(
                    int(saturation_context.get("qualification_timeout_minutes", 0) or 0)
                ),
            },
            log_lines=[
                f"[{worker_id}] Reserved {len(reservations)} GPU(s) on {visible_devices or 'cpu'} "
                f"(budget {reserved_mb} MiB)"
            ]
            + (
                [
                    f"[{worker_id}] Single-GPU saturation handed control to the agent "
                    f"(default profile hint {str(selected_profile.get('name', '') or '__idea_default__').strip()}, "
                    f"gpu budget {int(saturation_context.get('gpu_budget_mb', 0) or 0)} MiB, "
                    f"headroom {int(saturation_context.get('headroom_mb', 0) or 0)} MiB)"
                ]
                if self.single_gpu_saturation
                else []
            ),
        )

    def release(self, allocation: GPUAllocation) -> None:
        if not allocation.reservations:
            return
        try:
            self.manager.release_reservations(allocation.reservations)
        except Exception:
            logger.warning("GPU release failed — reservation may be stale until TTL reap", exc_info=True)


@dataclass(slots=True)
class FailureMemoryContext:
    """Failure-memory hints derived for one idea."""

    failure_class: str
    ranked_fix_actions: list[str]
    first_fix_action: str
    log_lines: list[str]


class FailureMemoryPlugin:
    """Optional historical failure-memory capability for worker execution."""

    def __init__(self, ledger: FailureMemoryLedger):
        self.ledger = ledger

    def prepare(self, idea_description: str, worker_id: str) -> FailureMemoryContext:
        failure_class = classify_failure(idea_description)
        ranked_fixes = self.ledger.rank_fixes(failure_class)
        ranked_fix_actions = [
            str(item.get("fix_action", "")).strip() for item in ranked_fixes if str(item.get("fix_action", "")).strip()
        ]
        first_fix_action = ranked_fix_actions[0] if ranked_fix_actions else "generate_new_plan"
        log_lines = [f"[{worker_id}] Memory policy {MEMORY_POLICY}: first remediation action {first_fix_action}"]
        return FailureMemoryContext(
            failure_class=failure_class,
            ranked_fix_actions=ranked_fix_actions[:3],
            first_fix_action=first_fix_action,
            log_lines=log_lines,
        )

    def record(self, context: FailureMemoryContext, run_code: int) -> None:
        self.ledger.record(
            failure_class=context.failure_class,
            fix_action=context.first_fix_action,
            verification_result="pass" if run_code == 0 else "fail",
            recovery_iterations=1 if run_code == 0 else 2,
        )


@dataclass(slots=True)
class WorkspaceLease:
    """Workspace allocation for one worker run."""

    workdir: Path
    cleanup: Callable[[], None]
    log_lines: list[str] = field(default_factory=list)


class WorktreeIsolationPlugin:
    """Optional isolated-worktree capability for worker execution."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path

    def acquire(self, worker_id: str, idea_id: str) -> WorkspaceLease:
        try:
            wt_path = create_worktree(self.repo_path, f"{worker_id}-{idea_id}")
        except Exception as exc:
            raise WorkspaceIsolationError(f"[{worker_id}] Worktree creation failed: {exc}") from exc

        def _cleanup() -> None:
            try:
                remove_worktree(self.repo_path, wt_path)
            except Exception as exc:
                raise WorkspaceIsolationError(f"[{worker_id}] Worktree cleanup failed: {exc}") from exc

        return WorkspaceLease(
            workdir=wt_path,
            cleanup=_cleanup,
            log_lines=[f"[{worker_id}] Worktree created: {wt_path.name}"],
        )


@dataclass(slots=True)
class WorkerRuntimePlugins:
    """Bundle of optional advanced runtime plugins used by WorkerManager."""

    gpu_allocator: GPUAllocatorPlugin | None = None
    failure_memory: FailureMemoryPlugin | None = None
    workspace_isolation: WorktreeIsolationPlugin | None = None


def build_default_worker_plugins(
    repo_path: Path,
    research_dir: Path,
    gpu_manager: GPUManager | None,
    *,
    default_gpu_memory_mb: int = 4096,
) -> WorkerRuntimePlugins:
    """Build the default research-v1 worker runtime plugins."""
    return WorkerRuntimePlugins(
        gpu_allocator=GPUAllocatorPlugin(gpu_manager, default_memory_per_worker_mb=default_gpu_memory_mb)
        if gpu_manager is not None
        else None,
        failure_memory=FailureMemoryPlugin(FailureMemoryLedger(research_dir / "failure_memory_ledger.json")),
        workspace_isolation=WorktreeIsolationPlugin(repo_path),
    )


def build_legacy_worker_plugins(
    repo_path: Path,
    research_dir: Path,
    gpu_manager: GPUManager | None,
    *,
    default_gpu_memory_mb: int = 4096,
) -> WorkerRuntimePlugins:
    """Backward-compatible alias for the default worker runtime plugins."""
    return build_default_worker_plugins(
        repo_path=repo_path,
        research_dir=research_dir,
        gpu_manager=gpu_manager,
        default_gpu_memory_mb=default_gpu_memory_mb,
    )
