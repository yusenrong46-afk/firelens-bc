from __future__ import annotations

from pathlib import Path

from firelens.evaluation.v1_6_baseline import (
    module_inventory,
    public_agent_exception_inventory,
)
from firelens.evaluation.v1_6_standard import (
    REQUIRED_GATES,
    REQUIRED_SCORE,
    load_v1_6_standard,
    standard_identity,
)

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_standard_encodes_fl_v16_s1() -> None:
    standard = load_v1_6_standard(ROOT)

    assert standard.standard_id == "FL-V16-S1"
    assert tuple(standard.hard_gates) == REQUIRED_GATES
    assert standard.weighted_score.model_dump() == REQUIRED_SCORE
    assert standard.route_budgets["pure_static_accepted"].outer_chat_turns == 0
    assert standard.retrieval_bounds.max_cycles == 2
    assert standard.claimbench.minimum_total_cases >= 200
    assert standard.module_size_targets.agent_loop_max_lines == 350


def test_standard_identity_is_content_bound() -> None:
    standard = load_v1_6_standard(ROOT)
    identity = standard_identity(ROOT, standard)

    assert len(identity["spec_sha256"]) == 64
    assert identity["identity_input_sha256"]
    assert identity["harness_input_sha256"]


def test_current_inventory_meets_v1_6_module_targets() -> None:
    inventory = module_inventory(ROOT)
    standard = load_v1_6_standard(ROOT)
    exceptions = public_agent_exception_inventory(ROOT)
    loop_cap = standard.module_size_targets.agent_loop_max_lines
    split_cap = standard.module_size_targets.split_upgrade_benchmark_test_max_lines

    assert inventory["agent_loop_lines"] is not None
    assert inventory["agent_loop_lines"] <= loop_cap
    upgrade_tests = {
        path: count
        for path, count in inventory["test_modules"].items()
        if Path(path).name.startswith("test_upgrade_benchmark")
    }
    assert "tests/test_upgrade_benchmark.py" in upgrade_tests
    assert all(count <= split_cap for count in upgrade_tests.values()), upgrade_tests
    assert exceptions == []
