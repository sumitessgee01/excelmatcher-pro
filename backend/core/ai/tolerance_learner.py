from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from .memory_db import MemoryDB


class ToleranceLearner:
    def __init__(self, db: MemoryDB) -> None:
        self.db = db

    def learn_for_brand(self, brand: str) -> dict[str, Any]:
        history = self.db.get_all_results_for_brand(brand)
        if not history:
            return {"brand": brand, "sessions": 0, "tolerances": {}, "table": []}

        values_by_col: dict[str, list[float]] = defaultdict(list)
        seen_sessions: set[int] = set()

        for row in history:
            if int(row.get("user_corrected", 0) or 0) != 1:
                continue
            if str(row.get("correct_status", "")).strip().casefold() not in {"matched", "match"}:
                continue

            seen_sessions.add(int(row.get("session_id", 0) or 0))
            col_diffs = row.get("col_diffs", {}) or {}
            for label, payload in col_diffs.items():
                diff_val = payload.get("diff")
                if isinstance(diff_val, (int, float)):
                    values_by_col[str(label)].append(abs(float(diff_val)))

        tolerances: dict[str, float] = {}
        table: list[dict[str, Any]] = []
        for col, values in sorted(values_by_col.items()):
            if not values:
                continue
            arr = np.asarray(values, dtype="float64")
            p95 = float(np.percentile(arr, 95))
            avg = float(np.mean(arr))
            tolerances[col] = round(p95, 6)
            table.append(
                {
                    "column": col,
                    "avg_diff": round(avg, 6),
                    "suggested_tolerance": round(p95, 6),
                    "samples": int(len(values)),
                }
            )

        return {
            "brand": brand,
            "sessions": len([s for s in seen_sessions if s > 0]),
            "tolerances": tolerances,
            "table": table,
        }

    def apply_to_mappings(
        self, mappings: list[dict[str, Any]], learned_tolerances: dict[str, float]
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in mappings:
            item = dict(row)
            label = str(item.get("label", ""))
            if label in learned_tolerances:
                item["tolerance"] = float(learned_tolerances[label])
                item["tolerance_source"] = "learned"
            out.append(item)
        return out
