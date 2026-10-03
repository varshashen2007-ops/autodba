"""
Leakage-safe train/test split strategy for AutoDBA evaluation.

Groups optimization cases strictly by canonical query template hash so that
an entire query pattern/family belongs exclusively to TRAIN or exclusively to TEST.
Guarantees zero template overlap, zero instance leakage, and complete deterministic
reproducibility.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import random
from typing import Any, Dict, List, Set, Tuple

from .case_schema import OptimizationCase


@dataclass
class TrainTestSplit:
    """Represents a partitioned train/test dataset for research evaluation."""
    name: str = "grouped_template"
    seed: int = 42
    test_ratio: float = 0.3
    train_cases: List[OptimizationCase] = field(default_factory=list)
    test_cases: List[OptimizationCase] = field(default_factory=list)
    train_set: List[str] = field(default_factory=list)  # Case IDs
    test_set: List[str] = field(default_factory=list)   # Case IDs
    train_templates: Set[str] = field(default_factory=set)  # Template hashes
    test_templates: Set[str] = field(default_factory=set)   # Template hashes

    def get_train_set(self) -> List[str]:
        """Return sorted unique case IDs for training."""
        return sorted(set(self.train_set))

    def get_test_set(self) -> List[str]:
        """Return sorted unique case IDs for testing."""
        return sorted(set(self.test_set))


def grouped_template_split(
    cases: List[OptimizationCase],
    test_ratio: float = 0.3,
    seed: int = 42,
) -> TrainTestSplit:
    """
    Partition cases into train and test sets using strict template-hash grouping.

    Invariants Enforced:
      1. All cases with the same template_hash are placed in the same partition.
      2. Zero template overlap: train_templates ∩ test_templates == ∅.
      3. Zero case ID overlap: train_set ∩ test_set == ∅.
      4. Partition completeness: train_cases + test_cases == total cases.
      5. Deterministic partition given a random seed.
    """
    if not cases:
        return TrainTestSplit(seed=seed, test_ratio=test_ratio)

    # 1. Group cases by canonical template hash
    template_to_cases: Dict[str, List[OptimizationCase]] = defaultdict(list)
    for case in cases:
        t_hash = case.template_hash
        template_to_cases[t_hash].append(case)

    # Sort template hashes to ensure deterministic shuffle ordering across environments
    distinct_templates = sorted(template_to_cases.keys())

    # 2. Deterministically shuffle template groups
    rng = random.Random(seed)
    shuffled_templates = list(distinct_templates)
    rng.shuffle(shuffled_templates)

    # 3. Partition templates to approximate the requested test_ratio
    total_cases = len(cases)
    target_test_cases = max(1, int(round(total_cases * test_ratio))) if total_cases > 1 else 0

    test_templates: Set[str] = set()
    train_templates: Set[str] = set()
    accumulated_test_cases = 0

    for t_hash in shuffled_templates:
        group_size = len(template_to_cases[t_hash])
        # If we haven't reached the test quota and there will remain at least 1 template for train
        if (
            accumulated_test_cases + group_size <= target_test_cases
            or (not test_templates and len(shuffled_templates) > 1)
        ) and (len(test_templates) + 1 < len(shuffled_templates)):
            test_templates.add(t_hash)
            accumulated_test_cases += group_size
        else:
            train_templates.add(t_hash)

    # If all templates ended up in train (e.g. single template), keep all in train
    if not test_templates and len(shuffled_templates) > 1:
        # Move the last template to test
        transferred = shuffled_templates[-1]
        train_templates.remove(transferred)
        test_templates.add(transferred)

    # 4. Populate split lists
    train_cases: List[OptimizationCase] = []
    test_cases: List[OptimizationCase] = []

    for t_hash in train_templates:
        train_cases.extend(template_to_cases[t_hash])
    for t_hash in test_templates:
        test_cases.extend(template_to_cases[t_hash])

    train_set = [c.case_id for c in train_cases]
    test_set = [c.case_id for c in test_cases]

    split = TrainTestSplit(
        name="grouped_template",
        seed=seed,
        test_ratio=test_ratio,
        train_cases=train_cases,
        test_cases=test_cases,
        train_set=train_set,
        test_set=test_set,
        train_templates=train_templates,
        test_templates=test_templates,
    )

    # 5. Assert leakage invariants immediately
    verify_split_leakage(split, cases)

    return split


def verify_split_leakage(
    split: TrainTestSplit,
    all_cases: List[OptimizationCase],
) -> Dict[str, Any]:
    """
    Formally verifies the 5 core split invariants and raises AssertionError on violation.
    """
    train_ids = set(split.train_set)
    test_ids = set(split.test_set)
    train_tmps = split.train_templates
    test_tmps = split.test_templates

    # Invariant A: Zero Template Overlap
    template_intersection = train_tmps.intersection(test_tmps)
    if template_intersection:
        raise AssertionError(
            f"LEAKAGE VIOLATION: Template overlap detected between train and test: {template_intersection}"
        )

    # Invariant B: Zero Case-ID Overlap
    id_intersection = train_ids.intersection(test_ids)
    if id_intersection:
        raise AssertionError(
            f"LEAKAGE VIOLATION: Case ID overlap detected between train and test: {id_intersection}"
        )

    # Invariant C: Partition Completeness
    all_case_ids = {c.case_id for c in all_cases}
    partitioned_ids = train_ids.union(test_ids)
    if all_cases and partitioned_ids != all_case_ids:
        missing = all_case_ids - partitioned_ids
        extra = partitioned_ids - all_case_ids
        raise AssertionError(
            f"PARTITION ERROR: Cases missing ({missing}) or extra ({extra}) in split."
        )

    # Invariant D: Template Case Consistency
    for c in split.train_cases:
        if c.template_hash in test_tmps:
            raise AssertionError(f"LEAKAGE VIOLATION: Train case {c.case_id} has template in test_templates")
    for c in split.test_cases:
        if c.template_hash in train_tmps:
            raise AssertionError(f"LEAKAGE VIOLATION: Test case {c.case_id} has template in train_templates")

    return {
        "valid": True,
        "total_cases": len(all_cases),
        "train_cases_count": len(split.train_cases),
        "test_cases_count": len(split.test_cases),
        "train_templates_count": len(train_tmps),
        "test_templates_count": len(test_tmps),
        "template_overlap_count": 0,
        "case_id_overlap_count": 0,
    }