from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from .normalizer import (
    normalize_barcode,
    normalize_bill_number,
    normalize_date,
    normalize_identifier,
    normalize_text,
)


ProgressCallback = Callable[[int, str], None]


@dataclass(slots=True)
class ColumnMapping:
    f1_col: str
    f2_col: str
    label: str
    col_type: str = "key"
    match_type: str = "text"
    tolerance: float = 0.0

    @classmethod
    def from_config(cls, data: dict[str, Any], default_col_type: str) -> "ColumnMapping":
        return cls(
            f1_col=str(data.get("f1_col", "")).strip(),
            f2_col=str(data.get("f2_col", "")).strip(),
            label=str(data.get("label", data.get("f1_col", data.get("f2_col", "")))).strip()
            or "Unnamed",
            col_type=str(data.get("col_type", default_col_type)).strip().lower() or default_col_type,
            match_type=str(data.get("match_type", "text")).strip().lower() or "text",
            tolerance=float(data.get("tolerance", 0.0) or 0.0),
        )


@dataclass(slots=True)
class MatchConfig:
    key_columns: list[ColumnMapping]
    value_columns: list[ColumnMapping]
    fuzzy_enabled: bool = True
    fuzzy_threshold: float = 85.0
    fuzzy_batch_size: int = 250
    qty_expansion_enabled: bool = False
    qty_f1_col: str | None = None
    qty_f2_col: str | None = None
    case_insensitive: bool = True
    trim: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MatchConfig":
        key_cols = [ColumnMapping.from_config(x, "key") for x in data.get("key_columns", [])]
        value_cols = [ColumnMapping.from_config(x, "value") for x in data.get("value_columns", [])]
        return cls(
            key_columns=key_cols,
            value_columns=value_cols,
            fuzzy_enabled=bool(data.get("fuzzy_enabled", True)),
            fuzzy_threshold=float(data.get("fuzzy_threshold", 85.0)),
            fuzzy_batch_size=int(data.get("fuzzy_batch_size", 250)),
            qty_expansion_enabled=bool(data.get("qty_expansion_enabled", False)),
            qty_f1_col=(str(data.get("qty_f1_col", "")).strip() or None),
            qty_f2_col=(str(data.get("qty_f2_col", "")).strip() or None),
            case_insensitive=bool(data.get("case_insensitive", True)),
            trim=bool(data.get("trim", True)),
        )


class MatchingEngine:
    """Runs the end-to-end matching pipeline across Brand (F1) and EssGee (F2)."""
    AUTO_NUMERIC_DECIMAL_TOLERANCE = 0.5

    def __init__(self, config: MatchConfig, progress_callback: ProgressCallback | None = None) -> None:
        if not config.key_columns:
            raise ValueError("At least one key column mapping is required.")
        self.config = config
        self.progress_callback = progress_callback
        self._semantic_cache: dict[int, str] = {}
        for rule in (self.config.key_columns + self.config.value_columns):
            self._semantic_cache[id(rule)] = self._infer_semantic_type(rule)
        self._has_invoice_key_cached = any(
            self._semantic_cache.get(id(rule), "") == "invoice" for rule in self.config.key_columns
        )
        self._key_mismatch_label_cache = {
            str(rule.label or rule.f1_col or rule.f2_col or "Key").strip().casefold() or "key"
            for rule in self.config.key_columns
        }

    def run(self, f1_df: pd.DataFrame, f2_df: pd.DataFrame) -> dict[str, Any]:
        self._progress(10, "Loading files")

        left = f1_df.copy().reset_index(drop=True)
        right = f2_df.copy().reset_index(drop=True)
        left["_orig_index"] = left.index.astype(int)
        right["_orig_index"] = right.index.astype(int)

        self._progress(20, "Normalizing keys")
        left = self._build_normalized_keys(left, self.config.key_columns, source="f1")
        right = self._build_normalized_keys(right, self.config.key_columns, source="f2")
        left = self._prepare_qty(left, source="f1")
        right = self._prepare_qty(right, source="f2")

        self._progress(30, "Qty expansion")
        if self.config.qty_expansion_enabled:
            left = self._expand_qty_rows(left)
            right = self._expand_qty_rows(right)

        left_invoice_qty = self._invoice_qty_totals(left)
        right_invoice_qty = self._invoice_qty_totals(right)
        left_invoice_only_qty = self._invoice_only_qty_totals(left)
        right_invoice_only_qty = self._invoice_only_qty_totals(right)

        self._progress(40, "Exact matching")
        exact_pairs, unmatched_left, unmatched_right = self._exact_match(left, right)

        all_pairs = list(exact_pairs)
        self._progress(60, "Fuzzy matching")
        if self.config.fuzzy_enabled and unmatched_left and unmatched_right:
            strict_pairs, unmatched_left, unmatched_right = self._fuzzy_match(
                left=left,
                right=right,
                unmatched_left=unmatched_left,
                unmatched_right=unmatched_right,
                pass_type="strict",
            )
            all_pairs.extend(strict_pairs)

        if self.config.fuzzy_enabled and unmatched_left and unmatched_right:
            relaxed_pairs, unmatched_left, unmatched_right = self._fuzzy_match(
                left=left,
                right=right,
                unmatched_left=unmatched_left,
                unmatched_right=unmatched_right,
                pass_type="relaxed",
            )
            all_pairs.extend(relaxed_pairs)

        self._progress(75, "Comparing values")
        matched_rows = self._build_matched_rows(left, right, all_pairs)

        self._progress(80, "Applying invoice-level quantity checks")
        self._apply_invoice_qty_mismatch(
            matched_rows,
            left_invoice_qty,
            right_invoice_qty,
            left_invoice_only_qty,
            right_invoice_only_qty,
        )
        self._reconcile_group_sum_matches(matched_rows)

        self._progress(85, "Assembling unmatched rows")
        unmatched_rows = self._build_unmatched_rows(left, right, unmatched_left, unmatched_right)

        rows = matched_rows + unmatched_rows
        self._reconcile_brand_single_split_matches(rows)
        self._reconcile_split_quantity_groups(rows)
        if unmatched_rows or any(str(r.get("match_status", "")) != "Matched" for r in matched_rows):
            self._reconcile_invoice_aggregate_matches(rows)
        stats = self._build_stats(rows)

        self._progress(100, "Done")
        return {
            "rows": rows,
            "stats": stats,
        }

    def _progress(self, progress: int, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(progress, message)

    def _prepare_qty(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        qty_col = self.config.qty_f1_col if source == "f1" else self.config.qty_f2_col
        qty_col = self._resolve_qty_column(df, source, qty_col)
        qty_series = pd.Series([1.0] * len(df), index=df.index, dtype="float64")
        if qty_col and qty_col in df.columns:
            # When qty column is configured, missing qty is treated as 0.
            # This keeps invoice qty-total comparison accurate.
            qty_series = df[qty_col].map(self._to_number).fillna(0.0).astype(float)
            # Keep zero quantities (used for Not In logic). Only clamp negatives to zero.
            qty_series = qty_series.mask(qty_series < 0, 0.0)
        df["_qty_original"] = qty_series
        df["_qty_compare"] = qty_series
        return df

    def _resolve_qty_column(self, df: pd.DataFrame, source: str, configured: str | None) -> str | None:
        if configured and configured in df.columns:
            return configured

        def looks_like_qty(text: Any) -> bool:
            raw = str(text or "").strip().casefold()
            return bool(raw) and (raw == "qty" or "qty" in raw or "quantity" in raw)

        for rule in self.config.value_columns + self.config.key_columns:
            col = rule.f1_col if source == "f1" else rule.f2_col
            if col and (looks_like_qty(rule.label) or looks_like_qty(col)) and col in df.columns:
                return col

        for col in df.columns:
            if str(col).strip().casefold() == "qty":
                return str(col)
        for col in df.columns:
            if looks_like_qty(col):
                return str(col)
        return None

    def _expand_qty_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        repeat_counts = df["_qty_original"].round().astype(int).clip(lower=1)
        expanded = df.loc[df.index.repeat(repeat_counts)].copy()
        expanded["_qty_compare"] = 1.0
        expanded.reset_index(drop=True, inplace=True)
        return expanded

    def _build_normalized_keys(
        self,
        df: pd.DataFrame,
        mappings: Iterable[ColumnMapping],
        source: str,
    ) -> pd.DataFrame:
        key_cols: list[str] = []
        norm_party_col = None
        norm_invoice_col = None

        for idx, rule in enumerate(mappings):
            source_col = rule.f1_col if source == "f1" else rule.f2_col
            key_col = f"_key_{idx}"
            if source_col and source_col in df.columns:
                df[key_col] = df[source_col].map(lambda val, r=rule: self._normalize_for_rule(val, r))
            else:
                df[key_col] = ""
            key_cols.append(key_col)

            semantic = self._semantic_type(rule)
            if semantic == "party" and norm_party_col is None:
                norm_party_col = key_col
            elif semantic == "invoice" and norm_invoice_col is None:
                norm_invoice_col = key_col

        df["_key_tuple"] = list(zip(*(df[col] for col in key_cols)))
        df["_norm_party"] = df[norm_party_col] if norm_party_col else ""
        df["_norm_invoice"] = df[norm_invoice_col] if norm_invoice_col else ""
        return df

    def _infer_semantic_type(self, rule: ColumnMapping) -> str:
        text = f"{rule.label} {rule.match_type} {rule.f1_col} {rule.f2_col}".casefold()
        # Date must win over invoice tokens for labels like "Invoice Date".
        if "date" in text:
            return "date"
        if any(token in text for token in ("invoice", "bill", "inv")):
            return "invoice"
        if any(token in text for token in ("party", "customer", "vendor", "account")):
            return "party"
        if "barcode" in text or "ean" in text or "upc" in text:
            return "barcode"
        return "text"

    def _semantic_type(self, rule: ColumnMapping) -> str:
        cached = self._semantic_cache.get(id(rule))
        if cached:
            return cached
        inferred = self._infer_semantic_type(rule)
        self._semantic_cache[id(rule)] = inferred
        return inferred

    def _barcode_conflicts(self, left_value: Any, right_value: Any) -> bool:
        left_code = normalize_barcode(left_value)
        right_code = normalize_barcode(right_value)
        return bool(left_code and right_code and left_code != right_code)

    def _barcode_token_sets_conflict(self, left_values: list[Any], right_values: list[Any]) -> bool:
        left_tokens = self._group_text_tokens(left_values, normalize_barcode)
        right_tokens = self._group_text_tokens(right_values, normalize_barcode)
        return bool(left_tokens and right_tokens and left_tokens != right_tokens)

    def _normalize_for_rule(self, value: Any, rule: ColumnMapping) -> str:
        semantic = self._semantic_type(rule)
        match_type = rule.match_type
        if match_type == "date":
            return normalize_date(value)
        if semantic == "invoice" or match_type in {"bill_number", "invoice", "bill"}:
            return normalize_bill_number(value)
        if semantic == "date":
            return normalize_date(value)
        if semantic == "barcode" or match_type == "barcode":
            return normalize_barcode(value)
        if semantic == "party" or match_type in {"identifier", "party", "customer"}:
            return normalize_identifier(value)
        return normalize_text(value, self.config.case_insensitive, self.config.trim)

    def _exact_match(
        self, left: pd.DataFrame, right: pd.DataFrame
    ) -> tuple[list[tuple[Any, ...]], set[int], set[int]]:
        left_groups: dict[tuple[Any, ...], list[int]] = defaultdict(list)
        right_groups: dict[tuple[Any, ...], list[int]] = defaultdict(list)
        left_keys = left["_key_tuple"].tolist()
        right_keys = right["_key_tuple"].tolist()
        left_qty_values = left["_qty_compare"].tolist()
        right_qty_values = right["_qty_compare"].tolist()
        for idx, key in enumerate(left_keys):
            left_groups[key].append(int(idx))
        for idx, key in enumerate(right_keys):
            right_groups[key].append(int(idx))

        pairs: list[tuple[Any, ...]] = []
        matched_left: set[int] = set()
        matched_right: set[int] = set()

        all_keys = set(left_groups.keys()) | set(right_groups.keys())
        for key in all_keys:
            l_idxs = left_groups.get(key, [])
            r_idxs = right_groups.get(key, [])
            if not l_idxs or not r_idxs:
                continue

            l_qty = [float(left_qty_values[i] or 0.0) for i in l_idxs]
            r_qty = [float(right_qty_values[i] or 0.0) for i in r_idxs]
            l_total = float(sum(l_qty))
            r_total = float(sum(r_qty))
            qty_balanced = np.isclose(l_total, r_total) and l_total > 0 and r_total > 0
            needs_split = (len(l_idxs) != len(r_idxs)) or any(not np.isclose(q, 1.0) for q in (l_qty + r_qty))

            if qty_balanced and needs_split:
                split_pairs = self._balanced_exact_pairs(l_idxs, r_idxs, l_qty, r_qty)
                for li, ri, lf, rf in split_pairs:
                    pairs.append((li, ri, "exact", 100.0, lf, rf))
                    matched_left.add(li)
                    matched_right.add(ri)
                continue

            pair_order = self._best_exact_pair_order(left, right, l_idxs, r_idxs)
            max_pairs = min(len(l_idxs), len(r_idxs), len(pair_order))
            for k in range(max_pairs):
                li, ri = pair_order[k]
                pairs.append((li, ri, "exact", 100.0, 1.0, 1.0))
                matched_left.add(li)
                matched_right.add(ri)

        unmatched_left = set(map(int, left.index)) - matched_left
        unmatched_right = set(map(int, right.index)) - matched_right
        return pairs, unmatched_left, unmatched_right

    def _balanced_exact_pairs(
        self,
        left_indices: list[int],
        right_indices: list[int],
        left_qty: list[float],
        right_qty: list[float],
    ) -> list[tuple[int, int, float, float]]:
        out: list[tuple[int, int, float, float]] = []
        left_rem = [float(q) for q in left_qty]
        right_rem = [float(q) for q in right_qty]

        i = 0
        j = 0
        eps = 1e-9
        while i < len(left_indices) and j < len(right_indices):
            lq = left_rem[i]
            rq = right_rem[j]
            if lq <= eps:
                i += 1
                continue
            if rq <= eps:
                j += 1
                continue

            take = min(lq, rq)
            if take <= eps:
                break

            l_total = float(left_qty[i]) if float(left_qty[i]) > eps else 1.0
            r_total = float(right_qty[j]) if float(right_qty[j]) > eps else 1.0
            left_factor = take / l_total
            right_factor = take / r_total
            out.append((int(left_indices[i]), int(right_indices[j]), float(left_factor), float(right_factor)))

            left_rem[i] -= take
            right_rem[j] -= take

            if left_rem[i] <= eps:
                i += 1
            if right_rem[j] <= eps:
                j += 1

        return out

    def _best_exact_pair_order(
        self,
        left: pd.DataFrame,
        right: pd.DataFrame,
        left_indices: list[int],
        right_indices: list[int],
    ) -> list[tuple[int, int]]:
        if not left_indices or not right_indices:
            return []

        pair_count = len(left_indices) * len(right_indices)
        # Safety cap for very large duplicate groups: keep old fast rank behavior.
        if pair_count > 4000:
            max_pairs = min(len(left_indices), len(right_indices))
            return [(int(left_indices[i]), int(right_indices[i])) for i in range(max_pairs)]

        score_rows: list[tuple[tuple[float, float, float, int, int], int, int]] = []
        for li in left_indices:
            lrow = left.loc[li]
            lqty = float(lrow.get("_qty_compare", 0.0) or 0.0)
            for ri in right_indices:
                rrow = right.loc[ri]
                rqty = float(rrow.get("_qty_compare", 0.0) or 0.0)

                mismatch_count = 0.0
                numeric_abs_sum = 0.0
                for rule in self.config.value_columns:
                    if self._is_margin_like(rule):
                        continue
                    semantic = self._semantic_type(rule)
                    tag = f"{rule.label} {rule.f1_col} {rule.f2_col}".casefold()
                    if ("qty" in tag) or ("quantity" in tag):
                        continue

                    left_val = lrow.get(rule.f1_col) if rule.f1_col in lrow.index else None
                    right_val = rrow.get(rule.f2_col) if rule.f2_col in rrow.index else None

                    if semantic == "barcode" or rule.match_type == "barcode":
                        if self._barcode_conflicts(left_val, right_val):
                            mismatch_count += 1.0
                        continue

                    left_num = self._to_number(left_val)
                    right_num = self._to_number(right_val)
                    if left_num is not None and right_num is not None:
                        diff = abs(float(left_num) - float(right_num))
                        tol = self._effective_numeric_tolerance(rule, float(left_num), float(right_num))
                        if diff > tol:
                            mismatch_count += 1.0
                        numeric_abs_sum += float(diff)
                    else:
                        left_txt = normalize_text(left_val, self.config.case_insensitive, self.config.trim)
                        right_txt = normalize_text(right_val, self.config.case_insensitive, self.config.trim)
                        if left_txt != right_txt:
                            mismatch_count += 1.0

                qty_diff = abs(lqty - rqty)
                score = (
                    mismatch_count,
                    qty_diff,
                    numeric_abs_sum,
                    abs(int(li) - int(ri)),
                    int(ri),
                )
                score_rows.append((score, int(li), int(ri)))

        score_rows.sort(key=lambda x: x[0])
        used_left: set[int] = set()
        used_right: set[int] = set()
        out: list[tuple[int, int]] = []
        max_pairs = min(len(left_indices), len(right_indices))

        for _, li, ri in score_rows:
            if li in used_left or ri in used_right:
                continue
            used_left.add(li)
            used_right.add(ri)
            out.append((li, ri))
            if len(out) >= max_pairs:
                break

        if len(out) < max_pairs:
            rem_left = [int(i) for i in left_indices if int(i) not in used_left]
            rem_right = [int(i) for i in right_indices if int(i) not in used_right]
            for li, ri in zip(rem_left, rem_right):
                out.append((li, ri))
                if len(out) >= max_pairs:
                    break

        return out

    def _fuzzy_match(
        self,
        left: pd.DataFrame,
        right: pd.DataFrame,
        unmatched_left: set[int],
        unmatched_right: set[int],
        pass_type: str,
    ) -> tuple[list[tuple[int, int, str, float]], set[int], set[int]]:
        left_idx = sorted(unmatched_left)
        right_idx = sorted(unmatched_right)
        if not left_idx or not right_idx:
            return [], unmatched_left, unmatched_right

        left_invoices = left["_norm_invoice"].tolist()
        left_parties = left["_norm_party"].tolist()
        left_tuples = left["_key_tuple"].tolist()
        right_invoices = right["_norm_invoice"].tolist()
        right_parties = right["_norm_party"].tolist()
        right_tuples = right["_key_tuple"].tolist()

        right_blocks: dict[str, list[int]] = defaultdict(list)
        for ridx in right_idx:
            bkey = self._fuzzy_block_key_parts(
                right_invoices[ridx],
                right_parties[ridx],
                right_tuples[ridx],
                pass_type,
            )
            right_blocks[bkey].append(ridx)

        left_blocks: dict[str, list[int]] = defaultdict(list)
        for lidx in left_idx:
            bkey = self._fuzzy_block_key_parts(
                left_invoices[lidx],
                left_parties[lidx],
                left_tuples[lidx],
                pass_type,
            )
            left_blocks[bkey].append(lidx)

        left_key_map = {
            idx: self._fuzzy_key_parts(left_invoices[idx], left_parties[idx], left_tuples[idx], pass_type)
            for idx in left_idx
        }
        right_key_map = {
            idx: self._fuzzy_key_parts(right_invoices[idx], right_parties[idx], right_tuples[idx], pass_type)
            for idx in right_idx
        }

        pairs: list[tuple[int, int, float]] = []
        matched_left_local: set[int] = set()
        matched_right_local: set[int] = set()
        enforce_same_invoice = self._has_invoice_key_cached

        for block_key, lblock in left_blocks.items():
            rblock = right_blocks.get(block_key)
            if not rblock:
                continue

            lkeys = [left_key_map[idx] for idx in lblock]
            rkeys = [right_key_map[idx] for idx in rblock]
            if not lkeys or not rkeys:
                continue

            if len(lblock) <= 3 and len(rblock) <= 3:
                block_pairs = self._small_fuzzy_pairs(
                    left_indices=lblock,
                    right_indices=rblock,
                    left_keys=lkeys,
                    right_keys=rkeys,
                    threshold=self.config.fuzzy_threshold,
                )
            else:
                block_pairs = self._vectorized_fuzzy_pairs(
                    left_indices=lblock,
                    right_indices=rblock,
                    left_keys=lkeys,
                    right_keys=rkeys,
                    threshold=self.config.fuzzy_threshold,
                )
            for l, r, score in block_pairs:
                if enforce_same_invoice and str(left_invoices[l] or "") != str(right_invoices[r] or ""):
                    continue
                if l in matched_left_local or r in matched_right_local:
                    continue
                matched_left_local.add(l)
                matched_right_local.add(r)
                pairs.append((l, r, score))

        remaining_left = [idx for idx in left_idx if idx not in matched_left_local]
        remaining_right = [idx for idx in right_idx if idx not in matched_right_local]

        # Global fallback only when candidate matrix size is manageable.
        max_pairs_for_global = 2_000_000
        if (
            remaining_left
            and remaining_right
            and (not enforce_same_invoice)
            and (len(remaining_left) * len(remaining_right) <= max_pairs_for_global)
        ):
            lkeys = [left_key_map[idx] for idx in remaining_left]
            rkeys = [right_key_map[idx] for idx in remaining_right]
            global_pairs = self._vectorized_fuzzy_pairs(
                left_indices=remaining_left,
                right_indices=remaining_right,
                left_keys=lkeys,
                right_keys=rkeys,
                threshold=self.config.fuzzy_threshold,
            )
            for l, r, score in global_pairs:
                if enforce_same_invoice and str(left_invoices[l] or "") != str(right_invoices[r] or ""):
                    continue
                if l in matched_left_local or r in matched_right_local:
                    continue
                matched_left_local.add(l)
                matched_right_local.add(r)
                pairs.append((l, r, score))

        match_type = "fuzzy_strict" if pass_type == "strict" else "fuzzy_relaxed"
        normalized_pairs = [(l, r, match_type, score) for l, r, score in pairs]

        for l, r, _ in pairs:
            unmatched_left.discard(l)
            unmatched_right.discard(r)
        return normalized_pairs, unmatched_left, unmatched_right

    def _has_invoice_key(self) -> bool:
        return bool(self._has_invoice_key_cached)

    def _allow_relaxed_pair(self, left: pd.DataFrame, right: pd.DataFrame, left_idx: int, right_idx: int) -> bool:
        # When invoice is part of key mapping, relaxed fuzzy must not cross-match different invoices.
        if not self._has_invoice_key():
            return True
        left_inv = str(left.at[left_idx, "_norm_invoice"] or "")
        right_inv = str(right.at[right_idx, "_norm_invoice"] or "")
        if not left_inv or not right_inv:
            return False
        return left_inv == right_inv

    def _fuzzy_block_key_parts(
        self,
        invoice_value: Any,
        party_value: Any,
        key_tuple: Any,
        pass_type: str,
    ) -> str:
        invoice = str(invoice_value or "")
        party = str(party_value or "")
        if pass_type == "strict":
            if invoice:
                return f"inv:{invoice}"
            if party:
                return f"pty:{party[:8]}"
            tpl = key_tuple or ()
            if tpl:
                return f"k:{str(tpl[0])[:8]}"
            return "other"

        if invoice:
            return f"inv:{invoice}"
        if party:
            return f"pty:{party[:8]}"
        return "other"

    def _fuzzy_key_parts(
        self,
        invoice_value: Any,
        party_value: Any,
        key_tuple: Any,
        pass_type: str,
    ) -> str:
        tpl = tuple(key_tuple or ())
        if pass_type == "strict":
            return " | ".join([str(x) for x in tpl if str(x)])

        invoice_text = str(invoice_value or "")
        party_text = str(party_value or "")
        if invoice_text or party_text:
            return f"{invoice_text} | {party_text}".strip(" |")
        return " | ".join([str(x) for x in tpl[:2] if str(x)])

    def _vectorized_fuzzy_pairs(
        self,
        left_indices: list[int],
        right_indices: list[int],
        left_keys: list[str],
        right_keys: list[str],
        threshold: float,
    ) -> list[tuple[int, int, float]]:
        top_k = 2
        batch_size = max(25, int(self.config.fuzzy_batch_size))
        right_count = len(right_keys)
        candidates: list[tuple[float, int, int]] = []

        for start in range(0, len(left_keys), batch_size):
            batch = left_keys[start : start + batch_size]
            workers = -1 if (len(batch) * max(right_count, 1)) >= 50_000 else 1
            matrix = process.cdist(
                batch,
                right_keys,
                scorer=fuzz.WRatio,
                score_cutoff=threshold,
                score_hint=threshold,
                dtype=np.uint8,
                workers=workers,
            )
            scores = np.asarray(matrix)
            if scores.size == 0:
                continue

            for local_q_idx in range(scores.shape[0]):
                row_scores = scores[local_q_idx]
                if right_count <= top_k:
                    selected = np.argsort(row_scores)[::-1]
                else:
                    selected = np.argpartition(row_scores, -top_k)[-top_k:]
                    selected = selected[np.argsort(row_scores[selected])[::-1]]

                q_idx = start + local_q_idx
                for c_idx in selected:
                    score = float(row_scores[c_idx])
                    if score >= threshold:
                        candidates.append((score, q_idx, int(c_idx)))

        candidates.sort(key=lambda x: x[0], reverse=True)
        used_q: set[int] = set()
        used_c: set[int] = set()
        pairs: list[tuple[int, int, float]] = []

        for score, q_local, c_local in candidates:
            if q_local in used_q or c_local in used_c:
                continue
            used_q.add(q_local)
            used_c.add(c_local)
            pairs.append((left_indices[q_local], right_indices[c_local], score))

        return pairs

    def _small_fuzzy_pairs(
        self,
        left_indices: list[int],
        right_indices: list[int],
        left_keys: list[str],
        right_keys: list[str],
        threshold: float,
    ) -> list[tuple[int, int, float]]:
        candidates: list[tuple[float, int, int]] = []
        for li, lkey in enumerate(left_keys):
            for ri, rkey in enumerate(right_keys):
                score = float(fuzz.WRatio(lkey, rkey))
                if score >= threshold:
                    candidates.append((score, li, ri))

        candidates.sort(key=lambda x: x[0], reverse=True)
        used_left: set[int] = set()
        used_right: set[int] = set()
        out: list[tuple[int, int, float]] = []
        for score, li, ri in candidates:
            if li in used_left or ri in used_right:
                continue
            used_left.add(li)
            used_right.add(ri)
            out.append((left_indices[li], right_indices[ri], score))
        return out

    def _build_matched_rows(
        self, left: pd.DataFrame, right: pd.DataFrame, pairs: list[tuple[Any, ...]]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        safe_left_rows: dict[int, dict[str, Any]] = {}
        safe_right_rows: dict[int, dict[str, Any]] = {}
        for pair in pairs:
            if len(pair) >= 6:
                left_idx, right_idx, match_type, fuzzy_score, left_factor, right_factor = pair
            else:
                left_idx, right_idx, match_type, fuzzy_score = pair
                left_factor, right_factor = 1.0, 1.0
            left_row = left.loc[left_idx]
            right_row = right.loc[right_idx]
            left_orig_index = int(left_row["_orig_index"])
            right_orig_index = int(right_row["_orig_index"])
            safe_left_row = safe_left_rows.get(left_orig_index)
            if safe_left_row is None:
                safe_left_row = self._json_safe_row(left_row)
                safe_left_rows[left_orig_index] = safe_left_row
            safe_right_row = safe_right_rows.get(right_orig_index)
            if safe_right_row is None:
                safe_right_row = self._json_safe_row(right_row)
                safe_right_rows[right_orig_index] = safe_right_row

            col_diffs, mismatch_columns = self._compare_value_columns(
                left_row,
                right_row,
                left_factor=float(left_factor or 1.0),
                right_factor=float(right_factor or 1.0),
            )
            self._append_key_mismatches(
                left_row=left_row,
                right_row=right_row,
                col_diffs=col_diffs,
                mismatch_columns=mismatch_columns,
            )
            match_status = "Matched" if not mismatch_columns else "Mismatch"
            status_group = "Matched" if match_status == "Matched" else "Mismatch"

            base_qty_f1 = float(left_row.get("_qty_compare", 1.0) or 1.0)
            base_qty_f2 = float(right_row.get("_qty_compare", 1.0) or 1.0)
            rows.append(
                {
                    "match_status": match_status,
                    "status_group": status_group,
                    "match_type": match_type,
                    "fuzzy_score": fuzzy_score,
                    "mismatch_columns": mismatch_columns,
                    "col_diffs": col_diffs,
                    "f1_index": left_orig_index,
                    "f2_index": right_orig_index,
                    "f1_row": safe_left_row,
                    "f2_row": safe_right_row,
                    "normalized_party": str(left_row.get("_norm_party", "") or ""),
                    "normalized_invoice": str(left_row.get("_norm_invoice", "") or ""),
                    "qty_f1": float(base_qty_f1 * float(left_factor or 1.0)),
                    "qty_f2": float(base_qty_f2 * float(right_factor or 1.0)),
                    "invoice_f1_qty": None,
                    "invoice_f2_qty": None,
                }
            )
        return rows

    def _append_key_mismatches(
        self,
        left_row: pd.Series,
        right_row: pd.Series,
        col_diffs: dict[str, dict[str, Any]],
        mismatch_columns: list[str],
    ) -> None:
        for rule in self.config.key_columns:
            left_val = left_row.get(rule.f1_col) if rule.f1_col in left_row.index else None
            right_val = right_row.get(rule.f2_col) if rule.f2_col in right_row.index else None

            left_norm = self._normalize_for_rule(left_val, rule)
            right_norm = self._normalize_for_rule(right_val, rule)
            semantic = self._semantic_type(rule)
            if semantic == "barcode" or rule.match_type == "barcode":
                if not self._barcode_conflicts(left_val, right_val):
                    continue

            if left_norm == right_norm:
                continue

            label = str(rule.label or rule.f1_col or rule.f2_col or "Key").strip() or "Key"
            if label in mismatch_columns:
                continue
            mismatch_columns.append(label)

            if semantic == "barcode" or rule.match_type == "barcode":
                left_out = normalize_barcode(left_val)
                right_out = normalize_barcode(right_val)
            elif semantic == "date" or rule.match_type == "date":
                left_out = left_norm
                right_out = right_norm
            else:
                left_out = self._json_safe_scalar(left_val)
                right_out = self._json_safe_scalar(right_val)

            col_diffs[label] = {
                "f1_value": self._json_safe_scalar(left_out),
                "f2_value": self._json_safe_scalar(right_out),
                "diff": None,
                "tolerance": 0.0,
            }

    def _compare_value_columns(
        self,
        left_row: pd.Series,
        right_row: pd.Series,
        left_factor: float = 1.0,
        right_factor: float = 1.0,
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        col_diffs: dict[str, dict[str, Any]] = {}
        mismatch_columns: list[str] = []

        for rule in self.config.value_columns:
            left_val = left_row.get(rule.f1_col) if rule.f1_col in left_row.index else None
            right_val = right_row.get(rule.f2_col) if rule.f2_col in right_row.index else None
            semantic = self._semantic_type(rule)

            if semantic == "barcode" or rule.match_type == "barcode":
                left_code = normalize_barcode(left_val)
                right_code = normalize_barcode(right_val)
                if left_code and right_code and left_code != right_code:
                    mismatch_columns.append(rule.label)
                    col_diffs[rule.label] = {
                        "f1_value": left_code,
                        "f2_value": right_code,
                        "diff": None,
                        "tolerance": float(rule.tolerance or 0.0),
                    }
                continue

            left_num = self._to_number(left_val)
            right_num = self._to_number(right_val)

            if left_num is not None and right_num is not None:
                left_comp = float(left_num)
                right_comp = float(right_num)
                if self._rule_scales_with_qty(rule):
                    left_comp = left_comp * float(left_factor or 1.0)
                    right_comp = right_comp * float(right_factor or 1.0)

                diff = abs(left_comp - right_comp)
                effective_tolerance = self._effective_numeric_tolerance(rule, left_comp, right_comp)
                is_mismatch = diff > effective_tolerance
                if is_mismatch:
                    mismatch_columns.append(rule.label)
                    col_diffs[rule.label] = {
                        "f1_value": self._json_safe_scalar(round(left_comp, 6)),
                        "f2_value": self._json_safe_scalar(round(right_comp, 6)),
                        "diff": round(diff, 6),
                        "tolerance": effective_tolerance,
                    }
                continue

            left_txt = normalize_text(left_val, self.config.case_insensitive, self.config.trim)
            right_txt = normalize_text(right_val, self.config.case_insensitive, self.config.trim)
            if left_txt != right_txt:
                mismatch_columns.append(rule.label)
                col_diffs[rule.label] = {
                    "f1_value": self._json_safe_scalar(left_val),
                    "f2_value": self._json_safe_scalar(right_val),
                    "diff": None,
                    "tolerance": float(rule.tolerance or 0.0),
                }

        return col_diffs, mismatch_columns

    def _rule_scales_with_qty(self, rule: ColumnMapping) -> bool:
        text = f"{rule.label} {rule.f1_col} {rule.f2_col}".casefold()
        if ("%" in text) or ("rate" in text):
            return False
        if ("qty" in text) or ("quantity" in text):
            return True
        if ("mrp" in text) and ("value" not in text):
            return False
        if ("value" in text) or ("amount" in text) or ("discount" in text) or ("net" in text):
            return True
        return False

    def _is_margin_like(self, rule: ColumnMapping) -> bool:
        text = f"{rule.label} {rule.f1_col} {rule.f2_col} {rule.match_type}".casefold()
        return "margin" in text

    def _effective_numeric_tolerance(
        self,
        rule: ColumnMapping,
        left_num: float,
        right_num: float,
    ) -> float:
        base_tolerance = float(rule.tolerance or 0.0)
        if base_tolerance > 0:
            return base_tolerance

        context = f"{rule.label} {rule.f1_col} {rule.f2_col} {rule.match_type}".casefold()
        is_qty_like = ("qty" in context) or ("quantity" in context)
        if is_qty_like:
            return base_tolerance

        has_fraction = (not float(left_num).is_integer()) or (not float(right_num).is_integer())
        if has_fraction:
            return self.AUTO_NUMERIC_DECIMAL_TOLERANCE
        return base_tolerance

    def _invoice_qty_totals(self, df: pd.DataFrame) -> dict[tuple[str, str], float]:
        totals: dict[tuple[str, str], float] = defaultdict(float)
        parties = df["_norm_party"].tolist()
        invoices = df["_norm_invoice"].tolist()
        qty_values = df["_qty_compare"].tolist()
        for party, invoice, qty in zip(parties, invoices, qty_values):
            key = (str(party or ""), str(invoice or ""))
            if key == ("", ""):
                continue
            totals[key] += float(qty or 0.0)
        return dict(totals)

    def _invoice_only_qty_totals(self, df: pd.DataFrame) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        invoices = df["_norm_invoice"].tolist()
        qty_values = df["_qty_compare"].tolist()
        for invoice, qty in zip(invoices, qty_values):
            invoice = str(invoice or "")
            if not invoice:
                continue
            totals[invoice] += float(qty or 0.0)
        return dict(totals)

    def _apply_invoice_qty_mismatch(
        self,
        matched_rows: list[dict[str, Any]],
        left_invoice_qty: dict[tuple[str, str], float],
        right_invoice_qty: dict[tuple[str, str], float],
        left_invoice_only_qty: dict[str, float],
        right_invoice_only_qty: dict[str, float],
    ) -> None:
        grouped_indices: dict[tuple[str, str], list[int]] = defaultdict(list)
        for idx, row in enumerate(matched_rows):
            key = (str(row.get("normalized_party", "")), str(row.get("normalized_invoice", "")))
            if key == ("", ""):
                continue
            grouped_indices[key].append(idx)

        for key, indices in grouped_indices.items():
            qty_indices = [i for i in indices if not self._has_key_mismatch(matched_rows[i])]
            if not qty_indices:
                continue

            party, invoice = key
            f1_qty = float(left_invoice_qty.get(key, left_invoice_only_qty.get(invoice, 0.0)))
            f2_qty = float(right_invoice_qty.get(key, right_invoice_only_qty.get(invoice, 0.0)))
            if not np.isclose(f1_qty, f2_qty):
                for i in qty_indices:
                    matched_rows[i]["match_status"] = "Qty Mismatch"
                    matched_rows[i]["status_group"] = "Qty Mismatch"
                    matched_rows[i]["invoice_f1_qty"] = float(round(f1_qty, 6))
                    matched_rows[i]["invoice_f2_qty"] = float(round(f2_qty, 6))

    def _build_unmatched_rows(
        self,
        left: pd.DataFrame,
        right: pd.DataFrame,
        unmatched_left: set[int],
        unmatched_right: set[int],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        safe_left_rows: dict[int, dict[str, Any]] = {}
        safe_right_rows: dict[int, dict[str, Any]] = {}
        for left_idx in sorted(unmatched_left):
            row = left.loc[left_idx]
            orig_index = int(row["_orig_index"])
            safe_row = safe_left_rows.get(orig_index)
            if safe_row is None:
                safe_row = self._json_safe_row(row)
                safe_left_rows[orig_index] = safe_row
            rows.append(
                {
                    "match_status": "Only In F1",
                    "status_group": "Not In Data",
                    "match_type": "none",
                    "fuzzy_score": 0.0,
                    "mismatch_columns": [],
                    "col_diffs": {},
                    "f1_index": orig_index,
                    "f2_index": None,
                    "f1_row": safe_row,
                    "f2_row": None,
                    "normalized_party": str(row.get("_norm_party", "") or ""),
                    "normalized_invoice": str(row.get("_norm_invoice", "") or ""),
                    "qty_f1": float(row.get("_qty_compare", 1.0) or 1.0),
                    "qty_f2": 0.0,
                    "invoice_f1_qty": None,
                    "invoice_f2_qty": None,
                }
            )

        for right_idx in sorted(unmatched_right):
            row = right.loc[right_idx]
            orig_index = int(row["_orig_index"])
            safe_row = safe_right_rows.get(orig_index)
            if safe_row is None:
                safe_row = self._json_safe_row(row)
                safe_right_rows[orig_index] = safe_row
            rows.append(
                {
                    "match_status": "Only In F2",
                    "status_group": "Not In Data",
                    "match_type": "none",
                    "fuzzy_score": 0.0,
                    "mismatch_columns": [],
                    "col_diffs": {},
                    "f1_index": None,
                    "f2_index": orig_index,
                    "f1_row": None,
                    "f2_row": safe_row,
                    "normalized_party": str(row.get("_norm_party", "") or ""),
                    "normalized_invoice": str(row.get("_norm_invoice", "") or ""),
                    "qty_f1": 0.0,
                    "qty_f2": float(row.get("_qty_compare", 1.0) or 1.0),
                    "invoice_f1_qty": None,
                    "invoice_f2_qty": None,
                }
            )
        return rows

    def _reconcile_group_sum_matches(self, matched_rows: list[dict[str, Any]]) -> None:
        """
        If per-row pairing creates false mismatches but invoice-level totals are equal,
        reconcile by (party, invoice) using summed value columns.
        """
        grouped_indices: dict[tuple[str, str], list[int]] = defaultdict(list)
        for idx, row in enumerate(matched_rows):
            if row.get("f1_index") is None or row.get("f2_index") is None:
                continue
            key = (str(row.get("normalized_party", "")), str(row.get("normalized_invoice", "")))
            if key == ("", ""):
                continue
            grouped_indices[key].append(idx)

        for indices in grouped_indices.values():
            # We only need reconciliation for groups that currently contain mismatches.
            if not any(str(matched_rows[i].get("match_status")) == "Mismatch" for i in indices):
                continue
            # Never override invoice-level quantity mismatch.
            if any(str(matched_rows[i].get("match_status")) == "Qty Mismatch" for i in indices):
                continue
            # Key mismatches must stay visible; do not hide them through sum reconciliation.
            if any(self._has_key_mismatch(matched_rows[i]) for i in indices):
                continue

            qty_f1 = sum(float(matched_rows[i].get("qty_f1") or 0.0) for i in indices)
            qty_f2 = sum(float(matched_rows[i].get("qty_f2") or 0.0) for i in indices)
            if not np.isclose(qty_f1, qty_f2):
                continue

            # Keep brand mismatch strict (don't auto-convert to match).
            if any(
                any("brand" in str(label).casefold() for label in (matched_rows[i].get("mismatch_columns") or []))
                for i in indices
            ):
                continue

            totals_ok = True
            for rule in self.config.value_columns:
                if self._is_margin_like(rule):
                    continue
                semantic = self._semantic_type(rule)
                sum_f1 = 0.0
                sum_f2 = 0.0
                numeric_rows = 0
                text_mismatch_found = False

                for i in indices:
                    row = matched_rows[i]
                    f1_row = row.get("f1_row") or {}
                    f2_row = row.get("f2_row") or {}
                    left_val = f1_row.get(rule.f1_col)
                    right_val = f2_row.get(rule.f2_col)

                    if semantic == "barcode" or rule.match_type == "barcode":
                        if self._barcode_conflicts(left_val, right_val):
                            text_mismatch_found = True
                            break
                        continue

                    left_num = self._to_number(left_val)
                    right_num = self._to_number(right_val)
                    if left_num is not None and right_num is not None:
                        sum_f1 += float(left_num)
                        sum_f2 += float(right_num)
                        numeric_rows += 1
                    else:
                        left_txt = normalize_text(left_val, self.config.case_insensitive, self.config.trim)
                        right_txt = normalize_text(right_val, self.config.case_insensitive, self.config.trim)
                        if left_txt != right_txt:
                            text_mismatch_found = True
                            break

                if text_mismatch_found:
                    totals_ok = False
                    break

                if numeric_rows > 0:
                    tol = self._effective_numeric_tolerance(rule, sum_f1, sum_f2)
                    if abs(sum_f1 - sum_f2) > tol:
                        totals_ok = False
                        break

            if not totals_ok:
                continue

            for i in indices:
                matched_rows[i]["match_status"] = "Matched"
                matched_rows[i]["status_group"] = "Matched"
                matched_rows[i]["mismatch_columns"] = []
                matched_rows[i]["col_diffs"] = {}

    def _reconcile_brand_single_split_matches(self, rows: list[dict[str, Any]]) -> None:
        """
        Directional rescue for Brand -> EssGee split rows.

        This keeps the current matching logic intact, but if the Brand file has a
        single source row and EssGee has the same invoice/party split across multiple
        rows, we accept the group when the Brand row matches the EssGee aggregate.
        """
        grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
        for idx, row in enumerate(rows):
            key = (str(row.get("normalized_party", "")), str(row.get("normalized_invoice", "")))
            if key == ("", ""):
                continue
            grouped[key].append(idx)

        for indices in grouped.values():
            left_sources = self._unique_sources_for_side(rows, indices, side="f1")
            right_sources = self._unique_sources_for_side(rows, indices, side="f2")
            if len(left_sources) != 1 or len(right_sources) <= 1:
                continue

            if any(
                any("brand" in str(label).casefold() for label in (rows[i].get("mismatch_columns") or []))
                for i in indices
            ):
                continue

            left_qty_total = self._aggregate_source_qty(left_sources, side="f1")
            right_qty_total = self._aggregate_source_qty(right_sources, side="f2")
            if left_qty_total <= 1.0 or not np.isclose(left_qty_total, right_qty_total):
                continue

            left_row = next(iter(left_sources.values()))
            if not self._brand_single_split_values_match(left_row, list(right_sources.values())):
                continue

            for i in indices:
                rows[i]["match_status"] = "Matched"
                rows[i]["status_group"] = "Matched"
                rows[i]["mismatch_columns"] = []
                rows[i]["col_diffs"] = {}
                rows[i]["force_match"] = True
                rows[i]["match_remark"] = "Match"
                rows[i]["detailed_remark"] = "All values matched"
                rows[i]["invoice_f1_qty"] = float(round(left_qty_total, 6))
                rows[i]["invoice_f2_qty"] = float(round(right_qty_total, 6))

    def _reconcile_split_quantity_groups(self, rows: list[dict[str, Any]]) -> None:
        """
        Symmetric rescue for split groups whose row structure differs but whose
        invoice/party totals and aggregated values still line up.
        """
        grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
        for idx, row in enumerate(rows):
            key = (str(row.get("normalized_party", "")), str(row.get("normalized_invoice", "")))
            if key == ("", ""):
                continue
            grouped[key].append(idx)

        for indices in grouped.values():
            left_sources = self._unique_sources_for_side(rows, indices, side="f1")
            right_sources = self._unique_sources_for_side(rows, indices, side="f2")
            if not left_sources or not right_sources:
                continue

            # Only intervene when the row structure is different or one side is split.
            if len(left_sources) == 1 and len(right_sources) == 1:
                continue

            if any(
                any("brand" in str(label).casefold() for label in (rows[i].get("mismatch_columns") or []))
                for i in indices
            ):
                continue

            left_qty_total = self._aggregate_source_qty(left_sources, side="f1")
            right_qty_total = self._aggregate_source_qty(right_sources, side="f2")
            if left_qty_total <= 0 or right_qty_total <= 0:
                continue
            if not np.isclose(left_qty_total, right_qty_total):
                continue

            if not self._split_group_values_match(left_sources, right_sources):
                continue

            for i in indices:
                rows[i]["match_status"] = "Matched"
                rows[i]["status_group"] = "Matched"
                rows[i]["mismatch_columns"] = []
                rows[i]["col_diffs"] = {}
                rows[i]["force_match"] = True
                rows[i]["match_remark"] = "Match"
                rows[i]["detailed_remark"] = "All values matched"
                rows[i]["invoice_f1_qty"] = float(round(left_qty_total, 6))
                rows[i]["invoice_f2_qty"] = float(round(right_qty_total, 6))

    def _build_stats(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        counts = defaultdict(int)
        for row in rows:
            status = str(row.get("match_status", ""))
            counts[status] += 1

        only_f1 = counts["Only In F1"]
        only_f2 = counts["Only In F2"]
        stats = {
            "total": len(rows),
            "matched": counts["Matched"],
            "mismatch": counts["Mismatch"],
            "qty_mismatch": counts["Qty Mismatch"],
            "only_in_f1": only_f1,
            "only_in_f2": only_f2,
            "not_in_data": only_f1 + only_f2,
        }
        return stats

    def _unique_sources_for_side(
        self,
        rows: list[dict[str, Any]],
        indices: list[int],
        *,
        side: str,
    ) -> dict[int, dict[str, Any]]:
        index_field = "f1_index" if side == "f1" else "f2_index"
        payload_field = "f1_row" if side == "f1" else "f2_row"
        sources: dict[int, dict[str, Any]] = {}
        for idx in indices:
            row = rows[idx]
            src_idx = row.get(index_field)
            payload = row.get(payload_field) or {}
            if src_idx is None or not payload:
                continue
            sources[int(src_idx)] = dict(payload)
        return sources

    def _aggregate_source_qty(self, sources: dict[int, dict[str, Any]], *, side: str) -> float:
        total = 0.0
        for payload in sources.values():
            total += float(self._extract_row_qty(payload, side=side))
        return float(total)

    def _barcode_key_sources_conflict(
        self,
        left_sources: dict[int, dict[str, Any]],
        right_sources: dict[int, dict[str, Any]],
    ) -> bool:
        left_payloads = list(left_sources.values())
        right_payloads = list(right_sources.values())
        if not left_payloads or not right_payloads:
            return False

        for rule in self.config.key_columns:
            semantic = self._semantic_type(rule)
            if semantic != "barcode" and rule.match_type != "barcode":
                continue
            left_vals = [payload.get(rule.f1_col) for payload in left_payloads if rule.f1_col in payload]
            right_vals = [payload.get(rule.f2_col) for payload in right_payloads if rule.f2_col in payload]
            if self._barcode_token_sets_conflict(left_vals, right_vals):
                return True
        return False

    def _extract_row_qty(self, row: dict[str, Any], *, side: str) -> float:
        configured = self.config.qty_f1_col if side == "f1" else self.config.qty_f2_col
        if configured and configured in row:
            configured_qty = self._to_number(row.get(configured))
            if configured_qty is not None:
                return float(max(configured_qty, 0.0))

        for key, value in row.items():
            text = str(key or "").casefold()
            if "qty" in text or "quantity" in text:
                qty = self._to_number(value)
                if qty is not None:
                    return float(max(qty, 0.0))

        return 1.0

    def _brand_single_split_values_match(self, left_row: dict[str, Any], right_rows: list[dict[str, Any]]) -> bool:
        if not right_rows:
            return False

        # Compare keys as repeated identities, not as numeric totals. Barcode
        # only blocks matching when both sides have nonblank conflicting codes.
        for rule in self.config.key_columns:
            left_val = left_row.get(rule.f1_col) if rule.f1_col in left_row else None
            right_vals = [row.get(rule.f2_col) if rule.f2_col in row else None for row in right_rows]
            semantic = self._semantic_type(rule)
            if semantic == "barcode" or rule.match_type == "barcode":
                if self._barcode_token_sets_conflict([left_val], right_vals):
                    return False
                continue
            if not self._single_key_matches_split(left_val, right_vals, rule):
                return False

        # Compare the Brand row against the EssGee aggregate while keeping the
        # Brand -> EssGee direction explicit.
        for rule in self.config.value_columns:
            left_val = left_row.get(rule.f1_col) if rule.f1_col in left_row else None
            right_vals = [row.get(rule.f2_col) if rule.f2_col in row else None for row in right_rows]
            semantic = self._semantic_type(rule)

            if semantic == "barcode" or rule.match_type == "barcode":
                if self._barcode_token_sets_conflict([left_val], right_vals):
                    return False
                continue

            if semantic == "date" or rule.match_type == "date":
                left_date = normalize_date(left_val)
                right_dates = [normalize_date(val) for val in right_vals]
                if any(date != left_date for date in right_dates):
                    return False
                continue

            left_num = self._to_number(left_val)
            right_nums = [self._to_number(val) for val in right_vals]
            if left_num is not None and all(val is not None for val in right_nums):
                right_total = float(sum(float(val or 0.0) for val in right_nums))
                tolerance = self._effective_numeric_tolerance(rule, float(left_num), right_total)
                if abs(float(left_num) - right_total) > tolerance:
                    return False
                continue

            left_txt = normalize_text(left_val, self.config.case_insensitive, self.config.trim)
            right_txts = [normalize_text(val, self.config.case_insensitive, self.config.trim) for val in right_vals]
            if any(text != left_txt for text in right_txts):
                return False

        return True

    def _split_group_values_match(
        self,
        left_sources: dict[int, dict[str, Any]],
        right_sources: dict[int, dict[str, Any]],
    ) -> bool:
        left_payloads = list(left_sources.values())
        right_payloads = list(right_sources.values())
        if not left_payloads or not right_payloads:
            return False

        for rule in self.config.key_columns:
            left_vals = [payload.get(rule.f1_col) for payload in left_payloads if rule.f1_col in payload]
            right_vals = [payload.get(rule.f2_col) for payload in right_payloads if rule.f2_col in payload]
            semantic = self._semantic_type(rule)
            if semantic == "barcode" or rule.match_type == "barcode":
                if self._barcode_token_sets_conflict(left_vals, right_vals):
                    return False
                continue
            left_tokens = self._group_key_tokens(left_vals, rule)
            right_tokens = self._group_key_tokens(right_vals, rule)
            if left_tokens != right_tokens:
                return False

        for rule in self.config.value_columns:
            left_vals = [payload.get(rule.f1_col) for payload in left_payloads if rule.f1_col in payload]
            right_vals = [payload.get(rule.f2_col) for payload in right_payloads if rule.f2_col in payload]

            semantic = self._semantic_type(rule)
            if semantic == "barcode" or rule.match_type == "barcode":
                if self._barcode_token_sets_conflict(left_vals, right_vals):
                    return False
                continue

            if semantic == "date" or rule.match_type == "date":
                left_tokens = self._group_text_tokens(left_vals, normalize_date)
                right_tokens = self._group_text_tokens(right_vals, normalize_date)
                if left_tokens != right_tokens:
                    return False
                continue

            left_nums = [self._to_number(v) for v in left_vals]
            right_nums = [self._to_number(v) for v in right_vals]
            left_has_num = any(v is not None for v in left_nums)
            right_has_num = any(v is not None for v in right_nums)
            if left_has_num and right_has_num and all(v is not None for v in left_nums) and all(v is not None for v in right_nums):
                left_direct = float(sum(float(v or 0.0) for v in left_nums))
                right_direct = float(sum(float(v or 0.0) for v in right_nums))
                direct_tol = self._effective_numeric_tolerance(rule, left_direct, right_direct)
                if abs(left_direct - right_direct) <= direct_tol:
                    continue

                left_weighted = self._group_weighted_numeric_total(left_vals, left_payloads, rule, side="f1")
                right_weighted = self._group_weighted_numeric_total(right_vals, right_payloads, rule, side="f2")
                weighted_tol = self._effective_numeric_tolerance(rule, left_weighted, right_weighted)
                if abs(left_weighted - right_weighted) <= weighted_tol:
                    continue
                return False

            left_tokens = self._group_text_tokens(left_vals, lambda x: normalize_text(x, self.config.case_insensitive, self.config.trim))
            right_tokens = self._group_text_tokens(right_vals, lambda x: normalize_text(x, self.config.case_insensitive, self.config.trim))
            if left_tokens != right_tokens:
                return False

        return True

    def _single_key_matches_split(self, left_value: Any, right_values: list[Any], rule: ColumnMapping) -> bool:
        try:
            left_token = str(self._normalize_for_rule(left_value, rule) or "").strip()
        except Exception:
            left_token = ""

        right_tokens: list[str] = []
        for value in right_values:
            try:
                token = str(self._normalize_for_rule(value, rule) or "").strip()
            except Exception:
                token = ""
            right_tokens.append(token)

        if not left_token:
            return not any(right_tokens)
        return all(token == left_token for token in right_tokens)

    def _group_key_tokens(self, values: list[Any], rule: ColumnMapping) -> set[str]:
        return self._group_text_tokens(values, lambda value, key_rule=rule: self._normalize_for_rule(value, key_rule))

    def _group_text_tokens(self, values: list[Any], normalizer) -> set[str]:
        tokens = set()
        for value in values:
            try:
                token = str(normalizer(value) or "").strip()
            except Exception:
                token = ""
            if token:
                tokens.add(token)
        return tokens

    def _group_weighted_numeric_total(
        self,
        values: list[Any],
        payloads: list[dict[str, Any]],
        rule: ColumnMapping,
        *,
        side: str,
    ) -> float:
        total = 0.0
        for value, payload in zip(values, payloads):
            numeric = self._to_number(value)
            if numeric is None:
                continue
            qty = self._extract_row_qty(payload, side=side)
            if self._rule_scales_with_qty(rule):
                total += float(numeric)
            else:
                total += float(numeric) * float(qty or 0.0)
        return float(total)

    def _reconcile_invoice_aggregate_matches(self, rows: list[dict[str, Any]]) -> None:
        grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
        for idx, row in enumerate(rows):
            key = (str(row.get("normalized_party", "")), str(row.get("normalized_invoice", "")))
            if key == ("", ""):
                continue
            grouped[key].append(idx)

        for indices in grouped.values():
            statuses = {str(rows[i].get("match_status", "")) for i in indices}
            if statuses.issubset({"Matched"}):
                continue
            if not ({"Mismatch", "Only In F1", "Only In F2"} & statuses):
                continue

            has_f1 = any(rows[i].get("f1_row") is not None for i in indices)
            has_f2 = any(rows[i].get("f2_row") is not None for i in indices)
            if not (has_f1 and has_f2):
                continue

            if any(str(rows[i].get("match_status")) == "Qty Mismatch" for i in indices):
                continue
            if any(self._has_key_mismatch(rows[i]) for i in indices):
                continue

            # Keep brand mismatch strict (do not auto-convert to Matched).
            if any(
                any("brand" in str(label).casefold() for label in (rows[i].get("mismatch_columns") or []))
                for i in indices
            ):
                continue

            qty_f1 = sum(float(rows[i].get("qty_f1") or 0.0) for i in indices)
            qty_f2 = sum(float(rows[i].get("qty_f2") or 0.0) for i in indices)
            if not np.isclose(qty_f1, qty_f2):
                continue

            left_sources = self._unique_sources_for_side(rows, indices, side="f1")
            right_sources = self._unique_sources_for_side(rows, indices, side="f2")
            if self._barcode_key_sources_conflict(left_sources, right_sources):
                continue

            values_ok = True
            for rule in self.config.value_columns:
                if self._is_margin_like(rule):
                    continue
                semantic = self._semantic_type(rule)

                left_vals: dict[int, Any] = {}
                right_vals: dict[int, Any] = {}
                left_weights: dict[int, float] = defaultdict(float)
                right_weights: dict[int, float] = defaultdict(float)
                for i in indices:
                    row = rows[i]
                    f1_row = row.get("f1_row") or {}
                    f2_row = row.get("f2_row") or {}
                    left_idx = row.get("f1_index")
                    right_idx = row.get("f2_index")
                    if f1_row and left_idx is not None:
                        left_i = int(left_idx)
                        if left_i not in left_vals:
                            left_vals[left_i] = f1_row.get(rule.f1_col)
                        left_weights[left_i] += float(row.get("qty_f1") or 0.0)
                    if f2_row and right_idx is not None:
                        right_i = int(right_idx)
                        if right_i not in right_vals:
                            right_vals[right_i] = f2_row.get(rule.f2_col)
                        right_weights[right_i] += float(row.get("qty_f2") or 0.0)

                if not left_vals and not right_vals:
                    continue
                if (not left_vals) or (not right_vals):
                    values_ok = False
                    break

                if semantic == "barcode" or rule.match_type == "barcode":
                    if self._barcode_token_sets_conflict(list(left_vals.values()), list(right_vals.values())):
                        values_ok = False
                        break
                    continue

                left_nums = {idx: self._to_number(value) for idx, value in left_vals.items()}
                right_nums = {idx: self._to_number(value) for idx, value in right_vals.items()}
                if all(v is not None for v in left_nums.values()) and all(v is not None for v in right_nums.values()):
                    rule_text = f"{rule.label} {rule.f1_col} {rule.f2_col} {rule.match_type}".casefold()
                    is_qty_rule = ("qty" in rule_text) or ("quantity" in rule_text)
                    scales_with_qty = self._rule_scales_with_qty(rule)

                    if is_qty_rule or scales_with_qty:
                        left_sum = float(sum(float(v) for v in left_nums.values() if v is not None))
                        right_sum = float(sum(float(v) for v in right_nums.values() if v is not None))
                    else:
                        # Unit-rate fields (for example MRP) are compared as qty-weighted totals.
                        left_sum = float(
                            sum(
                                float(v) * float(left_weights.get(idx, 0.0))
                                for idx, v in left_nums.items()
                                if v is not None
                            )
                        )
                        right_sum = float(
                            sum(
                                float(v) * float(right_weights.get(idx, 0.0))
                                for idx, v in right_nums.items()
                                if v is not None
                            )
                        )
                    tol = self._effective_numeric_tolerance(rule, left_sum, right_sum)
                    if abs(left_sum - right_sum) > tol:
                        values_ok = False
                        break
                    continue

                left_weighted: dict[str, float] = defaultdict(float)
                right_weighted: dict[str, float] = defaultdict(float)
                for idx, value in left_vals.items():
                    token = normalize_text(value, self.config.case_insensitive, self.config.trim)
                    left_weighted[token] += float(left_weights.get(idx, 0.0))
                for idx, value in right_vals.items():
                    token = normalize_text(value, self.config.case_insensitive, self.config.trim)
                    right_weighted[token] += float(right_weights.get(idx, 0.0))

                left_keys = set(left_weighted.keys())
                right_keys = set(right_weighted.keys())
                if left_keys != right_keys:
                    values_ok = False
                    break
                token_ok = True
                for token in left_keys:
                    if not np.isclose(float(left_weighted[token]), float(right_weighted[token])):
                        token_ok = False
                        break
                if not token_ok:
                    values_ok = False
                    break

            if not values_ok:
                continue

            for i in indices:
                rows[i]["match_status"] = "Matched"
                rows[i]["status_group"] = "Matched"
                rows[i]["mismatch_columns"] = []
                rows[i]["col_diffs"] = {}
                rows[i]["force_match"] = True

    def _key_mismatch_labels(self) -> set[str]:
        return self._key_mismatch_label_cache

    def _has_key_mismatch(self, row: dict[str, Any]) -> bool:
        key_labels = self._key_mismatch_labels()
        return any(str(label).casefold() in key_labels for label in (row.get("mismatch_columns") or []))

    def _to_number(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        if isinstance(value, (int, float, np.integer, np.floating)):
            try:
                return float(value)
            except Exception:
                return None

        text = str(value).strip()
        if not text:
            return None
        text = text.replace(",", "")
        if text.endswith("%"):
            text = text[:-1].strip()
        try:
            return float(text)
        except Exception:
            return None

    def _json_safe_row(self, row: pd.Series) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for col, value in row.items():
            col_str = str(col)
            if col_str.startswith("_"):
                continue
            lower = col_str.casefold()
            if ("barcode" in lower) or ("ean" in lower) or ("upc" in lower):
                norm = normalize_barcode(value)
                out[col_str] = norm if norm else self._json_safe_scalar(value)
                continue
            out[col_str] = self._json_safe_scalar(value)
        return out

    def _json_safe_scalar(self, value: Any) -> Any:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        if isinstance(value, (pd.Timestamp, np.datetime64)):
            dt = pd.to_datetime(value, errors="coerce")
            return dt.isoformat() if pd.notna(dt) else None
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating, float)):
            if np.isfinite(value):
                return float(value)
            return None
        return value
