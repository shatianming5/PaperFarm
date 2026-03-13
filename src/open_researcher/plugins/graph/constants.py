"""Domain constants for the research-v1 hypothesis/evidence graph.

Migrated from ``open_researcher.research_graph``.
"""

FRONTIER_STATUSES = frozenset({
    "draft",
    "approved",
    "running",
    "needs_post_review",
    "needs_repro",
    "rejected",
    "archived",
})
CLAIM_STATES = frozenset({
    "candidate",
    "under_review",
    "promoted",
    "downgraded",
    "rejected",
    "needs_repro",
})
EVIDENCE_RELIABILITY = frozenset({"pending_critic", "strong", "weak", "invalid", "needs_repro"})
CLAIM_TRANSITIONS = frozenset({"promote", "downgrade", "reject", "needs_repro"})
BRANCH_RELATIONS = frozenset({"refines", "combines", "contradicts", "reproduces"})
SELECTION_REASON_CODES = frozenset({
    "unspecified",
    "initial_frontier",
    "manager_refresh",
    "breadth_exploration",
    "exploit_positive_signal",
    "surprising_result_followup",
    "reproduction_requested",
    "cost_control",
})
REVIEW_REASON_CODES = frozenset({
    "unspecified",
    "approved_for_execution",
    "no_eval_plan",
    "multi_axis_change",
    "too_broad",
    "rollback_risk",
    "weak_attribution",
    "needs_reproduction",
    "strong_evidence",
    "weak_evidence",
    "invalid_result",
    "confounded_signal",
    "contradictory_signal",
    "surprising_improvement",
})
EVIDENCE_REASON_CODES = frozenset({
    "unspecified",
    "result_observed",
    "benchmark_delta",
    "test_improvement",
    "test_regression",
    "performance_signal",
    "reproduction_run",
    "confounded_measurement",
})
CLAIM_REASON_CODES = frozenset({
    "unspecified",
    "supported_by_strong_evidence",
    "supported_but_needs_repro",
    "confounded_signal",
    "contradicted_by_result",
    "regression_detected",
    "reproduction_requested",
    "noisy_measurement",
})
POLICY_STATES = frozenset({
    "neutral",
    "prefer_repro",
    "repeat_failure_risk",
    "duplicate_same_cycle",
})
