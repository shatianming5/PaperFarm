"""Generic resource-shaping helpers for research-v1 scheduling."""

from __future__ import annotations

from typing import Any

DEFAULT_EXPECTED_DURATION_MINUTES = 60
DEFAULT_DURATION_MINUTES = DEFAULT_EXPECTED_DURATION_MINUTES
DEFAULT_GPU_MEMORY_MB = 4096
SINGLE_GPU_SATURATION_OBJECTIVE = "single_gpu_saturation"
DEFAULT_SINGLE_GPU_HEADROOM_RATIO = 0.10
DEFAULT_SINGLE_GPU_HEADROOM_MB = 2048
DEFAULT_SINGLE_GPU_QUALIFICATION_TIMEOUT_MINUTES = 10


def _safe_int(value: Any, default: int = 0, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return max(default, minimum)
    return max(parsed, minimum)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _safe_float(value: Any, default: float = 0.0, *, minimum: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return max(default, minimum)
    return max(parsed, minimum)


def normalize_execution_shape(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        clean_key = key.strip()
        if not clean_key:
            continue
        if isinstance(raw, (str, int, float, bool)):
            normalized[clean_key] = raw
    return normalized


def _normalize_string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, raw in value.items():
        clean_key = str(key or "").strip()
        if not clean_key:
            continue
        clean_value = str(raw or "").strip()
        if not clean_value:
            continue
        normalized[clean_key] = clean_value
    return normalized


def normalize_verification_level(value: Any) -> str:
    level = str(value or "").strip().lower()
    if level in {"qualification", "full"}:
        return level
    return "full"


def _normalized_gpu_count(resource_request: dict[str, Any], gpu_hint: int | str | None) -> int | str:
    raw = resource_request.get("gpu_count")
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized == "auto":
            return "auto"
        return _safe_int(normalized, default=0, minimum=0)
    if raw is not None:
        return _safe_int(raw, default=0, minimum=0)
    if isinstance(gpu_hint, int):
        return max(gpu_hint, 0)
    if str(gpu_hint or "").strip().lower() == "auto":
        return "auto"
    return 0


def normalize_resource_request(
    value: Any,
    *,
    gpu_hint: int | str | None = None,
    fallback_gpu_hint: int | str | None = None,
    default_gpu_mem_mb: int = DEFAULT_GPU_MEMORY_MB,
) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    hint = gpu_hint if gpu_hint is not None else fallback_gpu_hint
    gpu_count = _normalized_gpu_count(payload, hint)
    gpu_mem_mb = _safe_int(
        payload.get("gpu_mem_mb", payload.get("memory_mb", payload.get("gpu_memory_mb"))),
        default=0,
        minimum=0,
    )
    if gpu_mem_mb <= 0 and gpu_count not in {0, "auto"}:
        gpu_mem_mb = max(int(default_gpu_mem_mb or 0), 0)
    return {
        "gpu_count": gpu_count,
        "gpu_mem_mb": gpu_mem_mb,
        "cpu_cores": _safe_int(payload.get("cpu_cores"), default=1, minimum=0),
        "ram_mb": _safe_int(payload.get("ram_mb"), default=0, minimum=0),
        "shareable": _safe_bool(payload.get("shareable"), default=True),
        "exclusive": _safe_bool(payload.get("exclusive"), default=False),
    }


def normalize_resource_profiles(
    value: Any,
    *,
    default_gpu_mem_mb: int = DEFAULT_GPU_MEMORY_MB,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for raw_name, raw_profile in value.items():
        name = str(raw_name or "").strip()
        if not name or not isinstance(raw_profile, dict):
            continue
        rr = raw_profile.get("resource_request")
        request_source = rr if isinstance(rr, dict) else raw_profile
        request = normalize_resource_request(
            request_source,
            gpu_hint=raw_profile.get("gpu_count"),
            default_gpu_mem_mb=default_gpu_mem_mb,
        )
        expected_memory_mb = _safe_int(
            raw_profile.get("expected_memory_mb", request.get("gpu_mem_mb", 0)),
            default=max(int(request.get("gpu_mem_mb", 0) or 0), 0),
            minimum=0,
        )
        normalized[name] = {
            "name": name,
            "resource_request": request,
            "execution_shape": normalize_execution_shape(raw_profile.get("execution_shape")),
            "expected_duration_minutes": normalize_expected_duration_minutes(
                raw_profile.get("expected_duration_minutes", raw_profile.get("duration_minutes"))
            ),
            "expected_memory_mb": expected_memory_mb,
            "verification_level": normalize_verification_level(raw_profile.get("verification_level")),
            "workload_label": normalize_workload_label(raw_profile.get("workload_label")),
            "launcher": str(raw_profile.get("launcher", "") or "").strip(),
            "env": _normalize_string_map(raw_profile.get("env")),
            "source": f"config.resources.profiles.{name}",
        }
    return normalized


def normalize_expected_duration_minutes(value: Any, *, default: int = DEFAULT_EXPECTED_DURATION_MINUTES) -> int:
    return _safe_int(value, default=default, minimum=1)


def normalize_workload_label(value: Any) -> str:
    return str(value or "").strip()


def is_single_gpu_saturation_objective(objective: Any) -> bool:
    return str(objective or "").strip().lower() == SINGLE_GPU_SATURATION_OBJECTIVE


def single_gpu_saturation_headroom_mb(
    total_memory_mb: int,
    *,
    headroom_ratio: float = DEFAULT_SINGLE_GPU_HEADROOM_RATIO,
    minimum_headroom_mb: int = DEFAULT_SINGLE_GPU_HEADROOM_MB,
) -> int:
    total = max(int(total_memory_mb or 0), 0)
    minimum = max(int(minimum_headroom_mb or 0), 0)
    ratio = _safe_float(headroom_ratio, default=DEFAULT_SINGLE_GPU_HEADROOM_RATIO, minimum=0.0)
    if total <= 0:
        return minimum
    return max(minimum, int(total * ratio))


def single_gpu_saturation_budget_mb(
    *,
    total_memory_mb: int,
    free_memory_mb: int,
    headroom_ratio: float = DEFAULT_SINGLE_GPU_HEADROOM_RATIO,
    minimum_headroom_mb: int = DEFAULT_SINGLE_GPU_HEADROOM_MB,
) -> tuple[int, int]:
    headroom = single_gpu_saturation_headroom_mb(
        total_memory_mb,
        headroom_ratio=headroom_ratio,
        minimum_headroom_mb=minimum_headroom_mb,
    )
    free = max(int(free_memory_mb or 0), 0)
    return max(free - headroom, 0), headroom


def enforce_single_gpu_saturation_request(
    resource_request: dict[str, Any],
    *,
    default_gpu_mem_mb: int = DEFAULT_GPU_MEMORY_MB,
) -> dict[str, Any]:
    request = normalize_resource_request(
        resource_request,
        gpu_hint=1,
        default_gpu_mem_mb=default_gpu_mem_mb,
    )
    request["gpu_count"] = 1
    request["exclusive"] = True
    request["shareable"] = False
    if int(request.get("gpu_mem_mb", 0) or 0) <= 0:
        request["gpu_mem_mb"] = max(int(default_gpu_mem_mb or 0), 0)
    return request


def build_implicit_resource_profile(
    idea: dict[str, Any],
    *,
    default_gpu_mem_mb: int = DEFAULT_GPU_MEMORY_MB,
) -> dict[str, Any]:
    request = normalize_resource_request(
        idea.get("resource_request"),
        default_gpu_mem_mb=default_gpu_mem_mb,
        fallback_gpu_hint=idea.get("gpu_hint", 1),
    )
    expected_memory_mb = _safe_int(
        idea.get("expected_memory_mb", request.get("gpu_mem_mb", 0)),
        default=max(int(request.get("gpu_mem_mb", 0) or 0), 0),
        minimum=0,
    )
    return {
        "name": str(idea.get("resource_profile", "") or "__idea_default__").strip() or "__idea_default__",
        "resource_request": request,
        "execution_shape": normalize_execution_shape(idea.get("execution_shape")),
        "expected_duration_minutes": normalize_expected_duration_minutes(
            idea.get("expected_duration_minutes"),
            default=DEFAULT_DURATION_MINUTES,
        ),
        "expected_memory_mb": expected_memory_mb,
        "verification_level": normalize_verification_level(idea.get("verification_level", "full")),
        "workload_label": normalize_workload_label(idea.get("workload_label")),
        "launcher": "",
        "env": {},
        "source": "idea",
    }


def candidate_single_gpu_saturation_profiles(
    idea: dict[str, Any],
    *,
    resource_profiles: dict[str, Any] | None = None,
    default_gpu_mem_mb: int = DEFAULT_GPU_MEMORY_MB,
) -> list[dict[str, Any]]:
    normalized_profiles = normalize_resource_profiles(resource_profiles or {}, default_gpu_mem_mb=default_gpu_mem_mb)
    candidates: list[dict[str, Any]] = [build_implicit_resource_profile(idea, default_gpu_mem_mb=default_gpu_mem_mb)]
    explicit_profile = str(idea.get("resource_profile", "") or "").strip()
    workload_label = normalize_workload_label(idea.get("workload_label"))

    if explicit_profile:
        profile = normalized_profiles.get(explicit_profile)
        if profile is not None:
            candidates.append(profile)
    else:
        for profile in normalized_profiles.values():
            profile_label = normalize_workload_label(profile.get("workload_label"))
            if workload_label and profile_label and profile_label != workload_label:
                continue
            candidates.append(profile)

    deduped: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        name = str(candidate.get("name", "") or "").strip()
        if not name or name in deduped:
            continue
        request = enforce_single_gpu_saturation_request(
            candidate.get("resource_request", {}),
            default_gpu_mem_mb=default_gpu_mem_mb,
        )
        gpu_count = resolve_gpu_count(request, gpu_available=True)
        if gpu_count != 1:
            continue
        normalized = dict(candidate)
        normalized["resource_request"] = request
        normalized["expected_memory_mb"] = _safe_int(
            candidate.get("expected_memory_mb", request.get("gpu_mem_mb", 0)),
            default=max(int(request.get("gpu_mem_mb", 0) or 0), 0),
            minimum=0,
        )
        deduped[name] = normalized

    return sorted(
        deduped.values(),
        key=lambda item: (
            int(item.get("expected_memory_mb", 0) or 0),
            int(item.get("resource_request", {}).get("gpu_mem_mb", 0) or 0),
            str(item.get("name", "")),
        ),
    )


def select_single_gpu_saturation_profile(
    idea: dict[str, Any],
    *,
    resource_profiles: dict[str, Any] | None = None,
    gpu: dict[str, Any],
    default_gpu_mem_mb: int = DEFAULT_GPU_MEMORY_MB,
    headroom_ratio: float = DEFAULT_SINGLE_GPU_HEADROOM_RATIO,
    minimum_headroom_mb: int = DEFAULT_SINGLE_GPU_HEADROOM_MB,
) -> dict[str, Any]:
    total_memory_mb = max(int(gpu.get("memory_total", 0) or 0), 0)
    free_memory_mb = max(int(gpu.get("memory_free", 0) or 0), 0)
    gpu_budget_mb, headroom_mb = single_gpu_saturation_budget_mb(
        total_memory_mb=total_memory_mb,
        free_memory_mb=free_memory_mb,
        headroom_ratio=headroom_ratio,
        minimum_headroom_mb=minimum_headroom_mb,
    )
    candidates = candidate_single_gpu_saturation_profiles(
        idea,
        resource_profiles=resource_profiles,
        default_gpu_mem_mb=default_gpu_mem_mb,
    )
    feasible = [
        item
        for item in candidates
        if int(item.get("resource_request", {}).get("gpu_mem_mb", 0) or 0) <= gpu_budget_mb
    ]
    selected = feasible[-1] if feasible else None
    qualification_profiles = candidates[:]
    full_profiles = [item for item in feasible if str(item.get("verification_level", "")).strip() != "qualification"]
    if full_profiles:
        selected = full_profiles[-1]
    elif selected is None and candidates:
        selected = candidates[0]
    return {
        "gpu_budget_mb": gpu_budget_mb,
        "headroom_mb": headroom_mb,
        "profiles": candidates,
        "qualification_profiles": qualification_profiles,
        "selected_profile": selected,
        "supported": selected is not None and bool(feasible),
    }


def classify_single_gpu_saturation_status(
    *,
    gpu_budget_mb: int,
    observed_peak_gpu_mem_mb: int | None = None,
    expected_peak_gpu_mem_mb: int | None = None,
) -> str:
    budget = max(int(gpu_budget_mb or 0), 0)
    if budget <= 0:
        return "unsupported"
    reference = observed_peak_gpu_mem_mb
    if reference is None:
        reference = expected_peak_gpu_mem_mb
    if reference is None:
        return "underfilled"
    peak = max(int(reference or 0), 0)
    return "saturated" if peak >= int(budget * 0.85) else "underfilled"


def resolve_gpu_count(resource_request: dict[str, Any], *, gpu_available: bool) -> int:
    """Resolve auto GPU requests at runtime."""
    raw = resource_request.get("gpu_count")
    if isinstance(raw, str) and raw.strip().lower() == "auto":
        return 1 if gpu_available else 0
    return _safe_int(raw, default=0, minimum=0)


def resolve_gpu_mem_mb(resource_request: dict[str, Any], *, default_gpu_mem_mb: int, gpu_count: int) -> int:
    if gpu_count <= 0:
        return 0
    explicit = _safe_int(resource_request.get("gpu_mem_mb"), default=0, minimum=0)
    return explicit if explicit > 0 else max(int(default_gpu_mem_mb or 0), 0)


def resource_cost_units(resource_request: dict[str, Any], expected_duration_minutes: int) -> float:
    duration = max(int(expected_duration_minutes or DEFAULT_EXPECTED_DURATION_MINUTES), 1)
    raw_gpu_count = resource_request.get("gpu_count")
    if isinstance(raw_gpu_count, str) and raw_gpu_count.strip().lower() == "auto":
        gpu_count = 1
    else:
        gpu_count = _safe_int(raw_gpu_count, default=0, minimum=0)
    cpu_cores = _safe_int(resource_request.get("cpu_cores"), default=1, minimum=1)
    primary_width = gpu_count if gpu_count > 0 else cpu_cores
    return float(max(primary_width, 1) * duration)


def utility_density(
    scores: dict[str, Any] | None,
    *,
    resource_request: dict[str, Any],
    expected_duration_minutes: int,
) -> float:
    expected_value = _safe_int((scores or {}).get("expected_value"), default=3, minimum=1)
    return expected_value / max(resource_cost_units(resource_request, expected_duration_minutes), 1.0)


def is_backfill_candidate(
    *,
    resource_request: dict[str, Any],
    expected_duration_minutes: int,
    threshold_minutes: int,
) -> bool:
    if _safe_bool(resource_request.get("exclusive"), default=False):
        return False
    if not _safe_bool(resource_request.get("shareable"), default=True):
        return False
    return expected_duration_minutes <= max(int(threshold_minutes or 0), 0)


def sort_pending_ideas(
    ideas: list[dict],
    *,
    default_gpu_mem_mb: int = DEFAULT_GPU_MEMORY_MB,
    default_duration_minutes: int = DEFAULT_DURATION_MINUTES,
    backfill_threshold_minutes: int = 30,
) -> list[dict]:
    def _normalized(item: dict) -> tuple[dict[str, Any], int, float, bool]:
        request = normalize_resource_request(
            item.get("resource_request"),
            default_gpu_mem_mb=default_gpu_mem_mb,
            fallback_gpu_hint=item.get("gpu_hint", "auto"),
        )
        duration = normalize_expected_duration_minutes(
            item.get("expected_duration_minutes"),
            default=default_duration_minutes,
        )
        density = utility_density(
            item.get("scores"),
            resource_request=request,
            expected_duration_minutes=duration,
        )
        backfill = is_backfill_candidate(
            resource_request=request,
            expected_duration_minutes=duration,
            threshold_minutes=backfill_threshold_minutes,
        )
        return request, duration, density, backfill

    decorated: list[tuple[tuple, dict]] = []
    for item in ideas:
        request, duration, density, backfill = _normalized(item)
        decorated.append(
            (
                (
                    0 if not backfill else 1,
                    -density,
                    int(item.get("runtime_priority", item.get("priority", 9999)) or 9999),
                    int(item.get("manager_priority", item.get("priority", 9999)) or 9999),
                    duration,
                    0 if request.get("shareable", True) else 1,
                    str(item.get("id", "")),
                ),
                item,
            )
        )
    decorated.sort(key=lambda pair: pair[0])
    return [item for _, item in decorated]
