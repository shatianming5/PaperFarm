"""Tests for evaluation-contract backfill helpers."""

from pathlib import Path

from open_researcher.config import load_config
from open_researcher.evaluation_contract import ensure_evaluation_contract, evaluation_doc_needs_backfill

_PLACEHOLDER_EVAL = """# Evaluation Design

> This file is filled by the AI agent during Phase 2.
> Human: review and edit as needed. This defines how experiments are judged.

## Primary Metric

- **Name:** <!-- e.g. accuracy, val_loss, test_pass_rate -->
- **Direction:** <!-- higher_is_better | lower_is_better -->
- **Why this metric:** <!-- brief justification -->

## How to Measure

### Command

```bash
# Exact command to run evaluation
```

### Extracting the Metric

```bash
# How to extract the primary metric value from output
```
"""


def test_ensure_evaluation_contract_backfills_placeholder_eval_and_metrics(tmp_path: Path) -> None:
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text(
        "bootstrap:\n"
        "  smoke_command: python smoke.py --dataset rsar\n",
        encoding="utf-8",
    )
    (research / "evaluation.md").write_text(_PLACEHOLDER_EVAL, encoding="utf-8")

    cfg = load_config(research)
    result = ensure_evaluation_contract(
        research,
        cfg,
        graph_payload={
            "repo_profile": {
                "primary_metric": "mAP",
                "direction": "higher_is_better",
            }
        },
    )

    updated_cfg = load_config(research)
    updated_eval = (research / "evaluation.md").read_text(encoding="utf-8")

    assert result["updated"] is True
    assert result["updated_config"] is True
    assert result["updated_evaluation"] is True
    assert updated_cfg.primary_metric == "mAP"
    assert updated_cfg.direction == "higher_is_better"
    assert "- **Name:** mAP" in updated_eval
    assert "- **Direction:** higher_is_better" in updated_eval
    assert "python smoke.py --dataset rsar" in updated_eval
    assert ".research/results.tsv" in updated_eval
    assert evaluation_doc_needs_backfill(research / "evaluation.md") is False


def test_ensure_evaluation_contract_preserves_real_eval_doc(tmp_path: Path) -> None:
    research = tmp_path / ".research"
    research.mkdir()
    (research / "config.yaml").write_text("", encoding="utf-8")
    real_eval = (
        "# Evaluation Design\n\n"
        "## Primary Metric\n\n"
        "- **Name:** accuracy\n"
        "- **Direction:** higher_is_better\n"
        "- **Why this metric:** regression target\n\n"
        "## How to Measure\n\n"
        "### Command\n\n"
        "```bash\n"
        "python eval.py\n"
        "```\n\n"
        "### Extracting the Metric\n\n"
        "```bash\n"
        "python parse_eval.py\n"
        "```\n"
    )
    (research / "evaluation.md").write_text(real_eval, encoding="utf-8")

    cfg = load_config(research)
    result = ensure_evaluation_contract(
        research,
        cfg,
        graph_payload={"repo_profile": {"primary_metric": "accuracy", "direction": "higher_is_better"}},
    )

    assert result["updated_config"] is True
    assert result["updated_evaluation"] is False
    assert (research / "evaluation.md").read_text(encoding="utf-8") == real_eval
