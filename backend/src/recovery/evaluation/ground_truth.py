"""Evaluator-only access to hidden counterfactual ground truth.

WARNING: Decision modules (diagnosis, strategy, coordination, economics, policy,
execution pipeline) must NOT import from this module. Use ingestion.runtime_loader
for case data at runtime.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CaseGroundTruth:
    case_id: str
    p_pay_anyway: float
    generation_seed: int
    feature_snapshot: dict


def load_ground_truth(conn: sqlite3.Connection, case_id: str) -> CaseGroundTruth | None:
    row = conn.execute(
        """
        SELECT case_id, p_pay_anyway, generation_seed, feature_snapshot
        FROM case_ground_truth
        WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()
    if row is None:
        return None
    return CaseGroundTruth(
        case_id=row["case_id"],
        p_pay_anyway=float(row["p_pay_anyway"]),
        generation_seed=int(row["generation_seed"]),
        feature_snapshot=json.loads(row["feature_snapshot"]),
    )


def load_all_ground_truth(conn: sqlite3.Connection) -> list[CaseGroundTruth]:
    rows = conn.execute(
        """
        SELECT case_id, p_pay_anyway, generation_seed, feature_snapshot
        FROM case_ground_truth
        ORDER BY case_id
        """
    ).fetchall()
    return [
        CaseGroundTruth(
            case_id=row["case_id"],
            p_pay_anyway=float(row["p_pay_anyway"]),
            generation_seed=int(row["generation_seed"]),
            feature_snapshot=json.loads(row["feature_snapshot"]),
        )
        for row in rows
    ]
