from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

from .memory_db import MemoryDB


ALIASES: dict[str, set[str]] = {
    "invoice_no": {"bill no", "invoice no", "inv no", "bill number", "invoice number", "bill_no"},
    "invoice_date": {"bill date", "invoice date", "inv date", "billing date"},
    "mrp_value": {"mrp value", "mrp val", "mrp amount"},
    "mrp": {"mrp", "mrp", "mrp"},
    "discount_value": {"dis value", "discount", "discount value", "disc value"},
    "party_name": {"party_name", "party name", "customer", "dealer name"},
    "barcode": {"barcode", "ean", "upc", "product barcode"},
    "qty": {"qty", "quantity", "pieces"},
}


@dataclass(slots=True)
class Suggestion:
    f1_col: str
    f2_col: str
    confidence: float
    label: str
    type: str
    match_type: str
    source: str
    tolerance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "f1_col": self.f1_col,
            "f2_col": self.f2_col,
            "confidence": round(self.confidence, 2),
            "label": self.label,
            "type": self.type,
            "match_type": self.match_type,
            "source": self.source,
            "tolerance": round(float(self.tolerance or 0.0), 6),
        }


class ColumnSuggester:
    def __init__(self, db: MemoryDB | None = None) -> None:
        self.db = db
        self._alias_groups = {
            key: {self._normalize_colname(v) for v in values}
            for key, values in ALIASES.items()
        }

    def suggest_mappings(
        self,
        f1_columns: list[str],
        f2_columns: list[str],
        brand_name: str | None = None,
    ) -> list[dict[str, Any]]:
        f1_cols = [str(x).strip() for x in f1_columns if str(x).strip()]
        f2_cols = [str(x).strip() for x in f2_columns if str(x).strip()]
        if not f1_cols or not f2_cols:
            return []

        history_scores = self._history_pair_scores(brand_name)
        master_scores = self._master_pair_scores(brand_name)
        master_exact = self._master_exact_suggestions(f1_cols, f2_cols, brand_name)
        master_by_f1 = {item.f1_col: item for item in master_exact}
        candidates: list[Suggestion] = []

        for f1 in f1_cols:
            best: Suggestion | None = master_by_f1.get(f1)
            if best is not None:
                candidates.append(best)
                continue
            for f2 in f2_cols:
                suggestion = self._score_pair(f1, f2, history_scores, master_scores)
                if not best or suggestion.confidence > best.confidence:
                    best = suggestion
            if best:
                candidates.append(best)

        # Make assignments unique by best-confidence greedy selection.
        candidates.sort(key=lambda x: x.confidence, reverse=True)
        used_f2: set[str] = set()
        final: list[Suggestion] = []
        for suggestion in candidates:
            if suggestion.f2_col in used_f2:
                continue
            used_f2.add(suggestion.f2_col)
            final.append(suggestion)

        # Return in F1 column order for stable UI rows.
        order = {name: idx for idx, name in enumerate(f1_cols)}
        final.sort(key=lambda x: order.get(x.f1_col, 10_000))
        return [x.to_dict() for x in final]

    def _master_exact_suggestions(
        self,
        f1_columns: list[str],
        f2_columns: list[str],
        brand_name: str | None,
    ) -> list[Suggestion]:
        if not self.db or not hasattr(self.db, "get_master_mapping_suggestions"):
            return []

        rows = self.db.get_master_mapping_suggestions(
            f1_columns=f1_columns,
            f2_columns=f2_columns,
            brand_name=brand_name,
        )
        out: list[Suggestion] = []
        for row in rows:
            out.append(
                Suggestion(
                    f1_col=str(row.get("f1_col", "") or ""),
                    f2_col=str(row.get("f2_col", "") or ""),
                    confidence=float(row.get("confidence", 99.0) or 99.0),
                    label=str(row.get("label", "") or row.get("f1_col", "") or "Column"),
                    type=str(row.get("col_type", row.get("type", "value")) or "value"),
                    match_type=str(row.get("match_type", "") or "text"),
                    source="master",
                    tolerance=float(row.get("tolerance", 0.0) or 0.0),
                )
            )
        return out

    def _history_pair_scores(self, brand_name: str | None) -> dict[tuple[str, str], float]:
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        if not self.db:
            return {}

        if hasattr(self.db, "get_column_mapping_pair_counts"):
            history_rows = self.db.get_column_mapping_pair_counts(brand=brand_name, limit=5000)
            for row in history_rows:
                f1 = self._normalize_colname(str(row.get("f1_col_norm", "")))
                f2 = self._normalize_colname(str(row.get("f2_col_norm", "")))
                if f1 and f2:
                    pair_counts[(f1, f2)] += int(row.get("pair_count", 0) or 0)
        else:
            history = self.db.get_column_mapping_history(brand=brand_name) if brand_name else self.db.get_column_mapping_history()
            for row in history:
                f1 = self._normalize_colname(str(row.get("f1_col", "")))
                f2 = self._normalize_colname(str(row.get("f2_col", "")))
                if f1 and f2:
                    pair_counts[(f1, f2)] += 1

        if not pair_counts:
            return {}

        max_count = max(pair_counts.values())
        scores: dict[tuple[str, str], float] = {}
        for pair, count in pair_counts.items():
            scores[pair] = 82.0 + (18.0 * (count / max_count))
        return scores

    def _master_pair_scores(self, brand_name: str | None) -> dict[tuple[str, str], dict[str, Any]]:
        if not self.db or not hasattr(self.db, "get_master_mapping_pair_counts"):
            return {}

        rows = self.db.get_master_mapping_pair_counts(brand=brand_name, limit=5000)
        if not rows:
            return {}

        max_count = max(int(row.get("pair_count", 0) or 0) for row in rows) or 1
        scores: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            f1 = self._normalize_colname(str(row.get("f1_col_norm", row.get("f1_col", ""))))
            f2 = self._normalize_colname(str(row.get("f2_col_norm", row.get("f2_col", ""))))
            if not f1 or not f2:
                continue
            count = int(row.get("pair_count", 0) or 0)
            scores[(f1, f2)] = {
                "score": 90.0 + (9.0 * (count / max_count)),
                "label": str(row.get("label", "") or ""),
                "type": str(row.get("col_type", "") or "value"),
                "match_type": str(row.get("match_type", "") or "text"),
                "tolerance": float(row.get("tolerance", 0.0) or 0.0),
            }
        return scores

    def _alias_bucket(self, f1_norm: str, f2_norm: str) -> str | None:
        for key, norm_values in self._alias_groups.items():
            if f1_norm in norm_values and f2_norm in norm_values:
                return key
        return None

    def _normalize_colname(self, value: str) -> str:
        text = str(value).strip().casefold().replace("_", " ")
        parts = [p for p in text.split() if p]
        return " ".join(parts)

    def _to_label(self, raw: str) -> str:
        words = raw.replace("_", " ").split()
        return " ".join(w.capitalize() for w in words) if words else "Column"

    def _infer_col_type(self, text: str) -> str:
        norm = text.casefold()
        key_tokens = ("invoice", "bill", "party", "customer", "barcode", "date")
        return "key" if any(token in norm for token in key_tokens) else "value"

    def _infer_match_type(self, text: str) -> str:
        norm = text.casefold()
        if "invoice" in norm or "bill" in norm:
            return "bill"
        if "date" in norm:
            return "date"
        if "barcode" in norm or "ean" in norm or "upc" in norm:
            return "barcode"
        if "party" in norm or "customer" in norm:
            return "identifier"
        return "text"

    def _score_pair(
        self,
        f1_col: str,
        f2_col: str,
        history_scores: dict[tuple[str, str], float],
        master_scores: dict[tuple[str, str], dict[str, Any]],
    ) -> Suggestion:
        f1_norm = self._normalize_colname(f1_col)
        f2_norm = self._normalize_colname(f2_col)

        history_score = history_scores.get((f1_norm, f2_norm), 0.0)
        master_hit = master_scores.get((f1_norm, f2_norm), {})
        master_score = float(master_hit.get("score", 0.0) or 0.0)
        alias_name = self._alias_bucket(f1_norm, f2_norm)
        alias_score = 95.0 if alias_name else 0.0
        fuzzy_score = float(fuzz.token_sort_ratio(f1_norm, f2_norm))

        if master_score >= history_score and master_score >= alias_score and master_score >= fuzzy_score:
            score = master_score
            source = "master"
        elif history_score >= alias_score and history_score >= fuzzy_score:
            score = history_score
            source = "history"
        elif alias_score >= fuzzy_score:
            score = alias_score
            source = "alias"
        else:
            score = fuzzy_score
            source = "fuzzy"

        if source == "master":
            label = str(master_hit.get("label", "") or self._to_label(f1_norm or f1_col))
            col_type = str(master_hit.get("type", "") or self._infer_col_type(f1_norm or f2_norm))
            match_type = str(master_hit.get("match_type", "") or self._infer_match_type(f1_norm or f2_norm))
            tolerance = float(master_hit.get("tolerance", 0.0) or 0.0)
        else:
            label = self._to_label(alias_name or f1_norm or f1_col)
            col_type = self._infer_col_type(alias_name or f1_norm or f2_norm)
            match_type = self._infer_match_type(alias_name or f1_norm or f2_norm)
            tolerance = 0.0

        return Suggestion(
            f1_col=f1_col,
            f2_col=f2_col,
            confidence=score,
            label=label,
            type=col_type,
            match_type=match_type,
            source=source,
            tolerance=tolerance,
        )
    
