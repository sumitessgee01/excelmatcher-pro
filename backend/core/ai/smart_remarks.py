from __future__ import annotations

from collections import defaultdict
from typing import Any

from .memory_db import MemoryDB
from .pattern_detector import PatternDetector


class SmartRemarks:
    def __init__(self, db: MemoryDB) -> None:
        self.db = db
        self.detector = PatternDetector(db)

    def enrich(self, brand: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pattern_info = self.detector.detect(brand=brand, rows=rows)
        row_notes = pattern_info.get("row_notes", {})

        history = self.db.get_all_results_for_brand(brand)
        diff_stats = self._build_diff_stats(history)
        qty_stats = self._build_qty_party_stats(history)
        barcode_stats = self._build_barcode_last_seen(history)

        for idx, row in enumerate(rows):
            notes: list[str] = []
            status = str(row.get("match_status", ""))
            party = str(row.get("normalized_party", "") or "")

            # Pattern-driven notes.
            notes.extend(row_notes.get(idx, []))

            # Historical mismatch frequency note.
            if status in {"Mismatch", "Qty Mismatch"}:
                col_diffs = row.get("col_diffs", {}) or {}
                for label, payload in col_diffs.items():
                    diff = payload.get("diff")
                    if isinstance(diff, (int, float)):
                        bucket = self._bucket_diff(float(diff))
                        stat = diff_stats.get((str(label), bucket))
                        if stat and stat["rate"] >= 0.5 and stat["count"] >= 3:
                            rupees = abs(float(diff))
                            pct = int(round(stat["rate"] * 100))
                            notes.append(f"{label} diff of Rs{rupees:g} seen in {pct}% of past invoices")
                            break

            # Chronic qty warning.
            if status == "Qty Mismatch" and party in qty_stats:
                n_bad = qty_stats[party]["qty_mismatch"]
                n_total = qty_stats[party]["total"]
                if n_total > 0 and n_bad > 0:
                    notes.append(f"{party} had Qty mismatch in {n_bad} of last {n_total} sessions")

            # Barcode last-seen hint for Not In Data.
            if status in {"Only In F1", "Only In F2"}:
                barcode = self._extract_barcode(row)
                if barcode and barcode in barcode_stats:
                    notes.append(f"Barcode {barcode} last seen in session {barcode_stats[barcode]}")

            if notes:
                unique_notes = []
                for note in notes:
                    if note not in unique_notes:
                        unique_notes.append(note)
                base = str(row.get("detailed_remark", "") or "")
                row["detailed_remark"] = f"{base}\nNote: " + " | ".join(unique_notes) if base else "Note: " + " | ".join(unique_notes)
                row["ai_enhanced"] = True
            else:
                row["ai_enhanced"] = False

        return rows

    def _build_diff_stats(self, history: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
        total_by_col: dict[str, int] = defaultdict(int)
        bucket_hits: dict[tuple[str, str], int] = defaultdict(int)
        for row in history:
            col_diffs = row.get("col_diffs", {}) or {}
            for label, payload in col_diffs.items():
                diff = payload.get("diff")
                if isinstance(diff, (int, float)):
                    total_by_col[str(label)] += 1
                    bucket = self._bucket_diff(float(diff))
                    bucket_hits[(str(label), bucket)] += 1

        out: dict[tuple[str, str], dict[str, float]] = {}
        for key, count in bucket_hits.items():
            col = key[0]
            total = total_by_col.get(col, 0)
            rate = (count / total) if total > 0 else 0.0
            out[key] = {"count": float(count), "rate": rate}
        return out

    def _build_qty_party_stats(self, history: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
        # Last 5 sessions per party.
        seen: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for row in history:
            party = str(row.get("party_name", "") or "")
            if not party:
                continue
            session_id = int(row.get("session_id", 0) or 0)
            status = str(row.get("match_status", "") or "")
            if session_id > 0:
                seen[party].append((session_id, status))

        out: dict[str, dict[str, int]] = {}
        for party, values in seen.items():
            values.sort(key=lambda x: x[0], reverse=True)
            latest = values[:5]
            total = len(latest)
            bad = len([1 for _, st in latest if st == "Qty Mismatch"])
            out[party] = {"total": total, "qty_mismatch": bad}
        return out

    def _build_barcode_last_seen(self, history: list[dict[str, Any]]) -> dict[str, str]:
        out: dict[str, str] = {}
        for row in history:
            barcode = str(row.get("barcode", "") or "")
            session_date = str(row.get("session_date", "") or "")
            if barcode and session_date:
                out[barcode] = session_date[:10]
        return out

    def _bucket_diff(self, value: float) -> str:
        v = abs(value)
        if v <= 0.05:
            return "0.01-0.05"
        if v <= 0.5:
            return "0.06-0.5"
        if v <= 2:
            return "0.51-2"
        if v <= 5:
            return "2.01-5"
        return ">5"

    def _extract_barcode(self, row: dict[str, Any]) -> str:
        for side in ("f1_row", "f2_row"):
            payload = row.get(side) or {}
            for key, value in payload.items():
                key_text = str(key).casefold()
                if "barcode" in key_text or "ean" in key_text or "upc" in key_text:
                    return str(value or "")
        return ""

