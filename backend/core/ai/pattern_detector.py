from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from ..normalizer import normalize_bill_number, normalize_identifier
from .memory_db import MemoryDB


class PatternDetector:
    def __init__(self, db: MemoryDB) -> None:
        self.db = db

    def detect(self, brand: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        history = self.db.get_all_results_for_brand(brand)
        hist_summary = self._build_history_summary(history)

        row_notes: dict[int, list[str]] = defaultdict(list)
        aliases_to_save: set[tuple[str, str]] = set()

        for idx, row in enumerate(rows):
            status = str(row.get("match_status", ""))
            col_diffs = row.get("col_diffs", {}) or {}
            party = str(row.get("normalized_party", "") or "")

            # Pattern 1: Rounding difference.
            for label, payload in col_diffs.items():
                diff = payload.get("diff")
                if isinstance(diff, (int, float)) and 0.01 <= abs(float(diff)) <= 0.05:
                    freq = hist_summary["rounding_frequency"].get(str(label), 0.0)
                    if freq >= 0.5:
                        row_notes[idx].append("Likely rounding difference")

            # Pattern 2: GST inclusion.
            for payload in col_diffs.values():
                f1 = self._to_number(payload.get("f1_value"))
                f2 = self._to_number(payload.get("f2_value"))
                if f1 and f2 and f1 != 0:
                    ratio = f2 / f1
                    if 1.16 <= ratio <= 1.20:
                        row_notes[idx].append("EssGee value may include GST")
                        break

            # Pattern 3: consistent party variant.
            if status in {"Matched", "Mismatch", "Qty Mismatch"}:
                raw_left = self._extract_party_name(row.get("f1_row") or {})
                raw_right = self._extract_party_name(row.get("f2_row") or {})
                if raw_left and raw_right:
                    left_norm = normalize_identifier(raw_left)
                    right_norm = normalize_identifier(raw_right)
                    if left_norm and right_norm and left_norm != right_norm:
                        canonical = left_norm if len(left_norm) >= len(right_norm) else right_norm
                        aliases_to_save.add((raw_left, canonical))
                        aliases_to_save.add((raw_right, canonical))

            # Pattern 4: invoice format variant.
            raw_inv_left = self._extract_invoice_no(row.get("f1_row") or {})
            raw_inv_right = self._extract_invoice_no(row.get("f2_row") or {})
            if raw_inv_left and raw_inv_right:
                norm_l = normalize_bill_number(raw_inv_left)
                norm_r = normalize_bill_number(raw_inv_right)
                if norm_l == norm_r and raw_inv_left != raw_inv_right:
                    row_notes[idx].append("Invoice format variant detected")

            # Pattern 5: chronic qty discrepancy.
            if status == "Qty Mismatch" and party:
                qty_rate = hist_summary["party_qty_mismatch_rate"].get(party, 0.0)
                if qty_rate >= 0.5 and hist_summary["party_qty_mismatch_count"].get(party, 0) >= 3:
                    row_notes[idx].append("Known Qty pattern for this party")

            # Not In Data helper: seen barcode in old sessions.
            if status in {"Only In F1", "Only In F2"}:
                barcode = self._extract_barcode(row)
                if barcode and barcode in hist_summary["barcode_last_seen"]:
                    last_seen = hist_summary["barcode_last_seen"][barcode]
                    row_notes[idx].append(f"Last seen in session {last_seen}")

        self.db.save_party_aliases_bulk(list(aliases_to_save), confirmed=False)

        return {
            "row_notes": {k: v for k, v in row_notes.items()},
            "saved_aliases": len(aliases_to_save),
        }

    def _build_history_summary(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        rounding_hits: Counter[str] = Counter()
        rounding_totals: Counter[str] = Counter()
        party_qty_mismatch: Counter[str] = Counter()
        party_total: Counter[str] = Counter()
        barcode_last_seen: dict[str, str] = {}

        for row in history:
            status = str(row.get("match_status", ""))
            party = str(row.get("party_name", "") or "")
            if party:
                party_total[party] += 1
                if status == "Qty Mismatch":
                    party_qty_mismatch[party] += 1

            col_diffs = row.get("col_diffs", {}) or {}
            for label, payload in col_diffs.items():
                diff = payload.get("diff")
                if isinstance(diff, (int, float)):
                    rounding_totals[str(label)] += 1
                    if 0.01 <= abs(float(diff)) <= 0.05:
                        rounding_hits[str(label)] += 1

            barcode = str(row.get("barcode", "") or "")
            if barcode:
                session_date = str(row.get("session_date", "") or "")
                if session_date:
                    barcode_last_seen[barcode] = self._safe_date(session_date)

        rounding_frequency = {
            col: (rounding_hits[col] / rounding_totals[col]) if rounding_totals[col] > 0 else 0.0
            for col in set(rounding_totals) | set(rounding_hits)
        }
        party_qty_rate = {
            party: (party_qty_mismatch[party] / party_total[party]) if party_total[party] > 0 else 0.0
            for party in set(party_total) | set(party_qty_mismatch)
        }

        return {
            "rounding_frequency": rounding_frequency,
            "party_qty_mismatch_rate": party_qty_rate,
            "party_qty_mismatch_count": dict(party_qty_mismatch),
            "barcode_last_seen": barcode_last_seen,
        }

    def _extract_party_name(self, row: dict[str, Any]) -> str:
        for key, value in row.items():
            text = str(key).casefold()
            if "party" in text or "customer" in text or "dealer" in text:
                return str(value or "")
        return ""

    def _extract_invoice_no(self, row: dict[str, Any]) -> str:
        for key, value in row.items():
            text = str(key).casefold()
            if "invoice" in text or "bill" in text or "inv" in text:
                return str(value or "")
        return ""

    def _extract_barcode(self, row: dict[str, Any]) -> str:
        for side in ("f1_row", "f2_row"):
            payload = row.get(side) or {}
            for key, value in payload.items():
                text = str(key).casefold()
                if "barcode" in text or "ean" in text or "upc" in text:
                    return str(value or "")
        return ""

    def _to_number(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            text = str(value).replace(",", "").replace("%", "").strip()
            if not text:
                return None
            return float(text)
        except Exception:
            return None

    def _safe_date(self, value: str) -> str:
        try:
            dt = datetime.fromisoformat(value.replace("Z", ""))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return value[:10] if len(value) >= 10 else value
