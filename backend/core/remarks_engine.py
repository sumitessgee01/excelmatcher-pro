from __future__ import annotations

from collections import defaultdict
from typing import Any

from .normalizer import normalize_barcode

EPSILON = 1e-9


def _fmt(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return str(value)


def _is_brand_col(label: str) -> bool:
    return "brand" in label.casefold()


def _is_barcode_col(label: str) -> bool:
    text = label.casefold()
    return ("barcode" in text) or ("ean" in text) or ("upc" in text)


def _is_qty_col(label: str) -> bool:
    text = (label or "").casefold()
    return ("qty" in text) or ("quantity" in text)


def _is_discount_col(label: str) -> bool:
    text = (label or "").casefold()
    return ("discount" in text) or ("disc" in text)


def _is_key_identity_col(label: str) -> bool:
    text = (label or "").casefold()
    return any(token in text for token in ("invoice", "bill", "party", "customer", "vendor", "dealer"))


def _label_title(label: str) -> str:
    text = (label or "").strip()
    return text if text else "Value"


def _build_value_detail(label: str, payload: dict[str, Any]) -> str:
    title = _label_title(label)
    if _is_barcode_col(title):
        f1_val = _fmt(normalize_barcode(payload.get("f1_value")))
        f2_val = _fmt(normalize_barcode(payload.get("f2_value")))
        return (
            "Barcode is different.\n\n"
            f"Brand File Barcode = {f1_val}\n"
            f"EssGee File Barcode = {f2_val}"
        )
    f1_val = _fmt(payload.get("f1_value"))
    f2_val = _fmt(payload.get("f2_value"))
    return (
        f"{title} is different.\n\n"
        f"Brand File {title} = {f1_val}\n"
        f"EssGee File {title} = {f2_val}"
    )


def _build_qty_detail(row: dict[str, Any], mismatch_columns: list[str]) -> str:
    f1_qty, f2_qty = _qty_pair(row)
    if any(_is_barcode_col(label) for label in mismatch_columns):
        header = "Invoice matched, but Barcode and Qty are different."
    else:
        header = "Invoice matched, but Qty is different."
    return (
        f"{header}\n\n"
        f"Brand File Qty = {_fmt(f1_qty)}\n"
        f"EssGee File Qty = {_fmt(f2_qty)}"
    )


def _has_missing_side(row: dict[str, Any]) -> bool:
    return row.get("f1_index") is None or row.get("f2_index") is None


def _qty_pair(row: dict[str, Any]) -> tuple[float, float]:
    f1_qty = row.get("invoice_f1_qty")
    f2_qty = row.get("invoice_f2_qty")
    if f1_qty is None:
        f1_qty = row.get("qty_f1")
    if f2_qty is None:
        f2_qty = row.get("qty_f2")
    try:
        left = float(f1_qty or 0.0)
    except Exception:
        left = 0.0
    try:
        right = float(f2_qty or 0.0)
    except Exception:
        right = 0.0
    return left, right


def _is_zero(value: float) -> bool:
    return abs(float(value or 0.0)) <= EPSILON


def _row_qty_not_equal(row: dict[str, Any]) -> bool:
    left = row.get("qty_f1")
    right = row.get("qty_f2")
    try:
        f1 = float(left or 0.0)
    except Exception:
        f1 = 0.0
    try:
        f2 = float(right or 0.0)
    except Exception:
        f2 = 0.0
    return abs(f1 - f2) > EPSILON


def _qty_not_in_status(row: dict[str, Any]) -> str | None:
    # Priority by file side: F1 is always Brand, F2 is always EssGee.
    if row.get("f1_index") is None and row.get("f2_index") is not None:
        return "Not In Brand"
    if row.get("f2_index") is None and row.get("f1_index") is not None:
        return "Not In EssGee"
    return None


def _not_in_detail(status: str, row: dict[str, Any]) -> str:
    _ = row
    return "Invoice not found in Brand data." if status == "Not In Brand" else "Invoice not found in EssGee data."


def _qty_difference_detail(row: dict[str, Any]) -> str:
    f1_qty, f2_qty = _qty_pair(row)
    return (
        "Qty is different.\n\n"
        f"Brand File Qty = {_fmt(f1_qty)}\n"
        f"EssGee File Qty = {_fmt(f2_qty)}"
    )


def _invoice_not_in_status_from_totals(row: dict[str, Any]) -> str | None:
    # Not In status is only valid for one-sided rows.
    if not _has_missing_side(row):
        return None

    side_status = _qty_not_in_status(row)
    if side_status:
        return side_status

    # Fallback: if invoice-level totals show one side fully missing, mark as Not In.
    f1_qty = row.get("invoice_f1_qty")
    f2_qty = row.get("invoice_f2_qty")
    if f1_qty is None or f2_qty is None:
        return None
    try:
        left = float(f1_qty or 0.0)
    except Exception:
        left = 0.0
    try:
        right = float(f2_qty or 0.0)
    except Exception:
        right = 0.0

    if left > EPSILON and abs(right) <= EPSILON:
        return "Not In EssGee"
    if right > EPSILON and abs(left) <= EPSILON:
        return "Not In Brand"
    return None


def _build_qty_remark(row: dict[str, Any], mismatch_columns: list[str]) -> str:
    qty_not_in = _qty_not_in_status(row)
    if qty_not_in:
        return "Not In"
    if _row_qty_not_equal(row):
        return "Not In"
    if _has_missing_side(row):
        return "Not In"
    if not mismatch_columns:
        return "All Match"

    if any(_is_brand_col(label) for label in mismatch_columns):
        return "Brand Mismatch"
    if any(_is_barcode_col(label) for label in mismatch_columns):
        return "Barcode Mismatch"
    return "Value Mismatch"


def _build_qty_detailed_remark(
    row: dict[str, Any],
    mismatch_columns: list[str],
    col_diffs: dict[str, Any],
) -> str:
    qty_not_in = _qty_not_in_status(row)
    if qty_not_in:
        return _qty_difference_detail(row)
    if _row_qty_not_equal(row):
        return _qty_difference_detail(row)
    if _has_missing_side(row):
        return _qty_difference_detail(row)

    if not mismatch_columns:
        return "All values matched"

    # For invoice-level qty mismatch, a paired row can have matching row qty
    # while value columns differ. Show only those row-level value differences;
    # the missing split row carries the qty-total detail.
    details: list[str] = []
    for label in mismatch_columns:
        payload = col_diffs.get(label, {}) or {}
        details.append(_build_value_detail(label, payload))
    return "\n\n".join(details)


def _first_reference_value_label(mismatch_columns: list[str]) -> str | None:
    for label in mismatch_columns:
        if _is_qty_col(label) or _is_brand_col(label) or _is_key_identity_col(label):
            continue
        return label
    return None


def _mismatch_remark_for_label(label: str) -> str:
    title = _label_title(label)
    text = title.casefold()
    if _is_discount_col(title):
        return "Discount Mismatch"
    if "mrp" in text:
        return "MRP Mismatch"
    if "net" in text:
        return "Net Mismatch"
    if _is_barcode_col(title):
        return "Barcode Mismatch"

    words = title.split()
    if words and words[-1].casefold() in {"value", "val"}:
        title = " ".join(words[:-1]) or title
    return f"{title} Mismatch"


def _apply_first_reference_mismatch(
    row: dict[str, Any],
    label: str,
    col_diffs: dict[str, Any],
    detail_labels: list[str] | None = None,
) -> None:
    if _is_discount_col(label):
        labels = [label]
    else:
        labels = [x for x in (detail_labels or [label]) if x in col_diffs]
        if label not in labels:
            labels.insert(0, label)
    clean_diffs = {x: (col_diffs.get(x, {}) or {}) for x in labels}

    row["mismatch_columns"] = labels
    row["col_diffs"] = clean_diffs
    row["match_status"] = "Value Mismatch"
    row["match_remark"] = _mismatch_remark_for_label(label)
    row["detailed_remark"] = "\n\n".join(_build_value_detail(x, clean_diffs.get(x, {}) or {}) for x in labels)


def apply_remarks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Generates business-friendly 3-column remarks:
      1) Match Status
      2) Match Remark
      3) Detailed Remark
    """
    invoice_presence: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"f1": 0, "f2": 0})
    invoice_qty_totals: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"f1": 0.0, "f2": 0.0})
    invoice_has_missing_side: dict[tuple[str, str], bool] = defaultdict(bool)
    invoice_has_true_pair: dict[tuple[str, str], bool] = defaultdict(bool)

    for row in rows:
        party = str(row.get("normalized_party", "") or "").strip()
        invoice = str(row.get("normalized_invoice", "") or "").strip()
        if not invoice:
            continue
        key = (party, invoice)
        if row.get("f1_index") is not None:
            invoice_presence[key]["f1"] += 1
        if row.get("f2_index") is not None:
            invoice_presence[key]["f2"] += 1
        if row.get("f1_index") is not None and row.get("f2_index") is not None:
            invoice_has_true_pair[key] = True
        if _has_missing_side(row):
            invoice_has_missing_side[key] = True
        try:
            invoice_qty_totals[key]["f1"] += float(row.get("qty_f1") or 0.0)
        except Exception:
            pass
        try:
            invoice_qty_totals[key]["f2"] += float(row.get("qty_f2") or 0.0)
        except Exception:
            pass

    for row in rows:
        raw_status = str(row.get("match_status", "") or "")
        row["internal_match_status"] = raw_status
        row["ai_enhanced"] = False
        force_match = bool(row.get("force_match"))

        col_diffs = row.get("col_diffs", {}) or {}
        mismatch_columns = [str(x) for x in (row.get("mismatch_columns") or []) if str(x).strip()]
        qty_not_in_status = _qty_not_in_status(row)

        if raw_status == "Matched":
            if force_match:
                row["match_status"] = "Match"
                row["match_remark"] = "Match"
                row["detailed_remark"] = "All values matched"
                continue
            if qty_not_in_status:
                row["match_status"] = qty_not_in_status
                row["match_remark"] = qty_not_in_status
                row["detailed_remark"] = _not_in_detail(qty_not_in_status, row)
                continue
            row["match_status"] = "Match"
            row["match_remark"] = "Match"
            row["detailed_remark"] = "All values matched"
            continue

        if raw_status == "Qty Mismatch":
            invoice_not_in = _invoice_not_in_status_from_totals(row)
            if invoice_not_in:
                row["match_status"] = invoice_not_in
                row["match_remark"] = invoice_not_in
                row["detailed_remark"] = _not_in_detail(invoice_not_in, row)
                continue

            party = str(row.get("normalized_party", "") or "").strip()
            invoice = str(row.get("normalized_invoice", "") or "").strip()
            group_key = (party, invoice)
            has_missing_in_group = bool(invoice and invoice_has_missing_side.get(group_key, False))

            non_qty_mismatches = [label for label in mismatch_columns if not _is_qty_col(label)]
            filtered_col_diffs = {k: v for k, v in col_diffs.items() if k in non_qty_mismatches}
            first_value_label = _first_reference_value_label(non_qty_mismatches)
            if (
                first_value_label
                and not qty_not_in_status
                and not _row_qty_not_equal(row)
                and not _has_missing_side(row)
            ):
                _apply_first_reference_mismatch(
                    row,
                    first_value_label,
                    filtered_col_diffs,
                    detail_labels=non_qty_mismatches,
                )
                continue

            # Split-qty scenario:
            # The paired qty portion can still be value-clean; the missing split
            # row carries the Not In qty-shortage detail.
            if (
                has_missing_in_group
                and not qty_not_in_status
                and not _row_qty_not_equal(row)
                and not _has_missing_side(row)
                and not non_qty_mismatches
            ):
                row["match_status"] = "Qty Mismatch"
                row["match_remark"] = "All Match"
                row["detailed_remark"] = "All values matched"
                continue

            if qty_not_in_status or _row_qty_not_equal(row):
                row["match_status"] = "Qty Mismatch"
                row["match_remark"] = "Not In"
                row["detailed_remark"] = _qty_difference_detail(row)
                continue
            row["match_status"] = "Qty Mismatch"
            row["match_remark"] = _build_qty_remark(row, non_qty_mismatches)
            row["detailed_remark"] = _build_qty_detailed_remark(row, non_qty_mismatches, filtered_col_diffs)
            continue

        if raw_status in {"Only In F1", "Only In F2", "Not In Data"}:
            party = str(row.get("normalized_party", "") or "").strip()
            invoice = str(row.get("normalized_invoice", "") or "").strip()
            if invoice:
                key = (party, invoice)
                has_f1 = invoice_presence[key]["f1"] > 0
                has_f2 = invoice_presence[key]["f2"] > 0
                # Qty mismatch conversion is valid only when there is at least one
                # real paired row in this invoice group.
                if has_f1 and has_f2 and bool(invoice_has_true_pair.get(key, False)):
                    f1_total = float(invoice_qty_totals[key]["f1"])
                    f2_total = float(invoice_qty_totals[key]["f2"])
                    if abs(f1_total - f2_total) > EPSILON:
                        row["invoice_f1_qty"] = round(f1_total, 6)
                        row["invoice_f2_qty"] = round(f2_total, 6)
                        side_status = _qty_not_in_status(row)
                        if side_status:
                            row["match_status"] = "Qty Mismatch"
                            row["match_remark"] = "Not In"
                            row["detailed_remark"] = _qty_difference_detail(row)
                            continue
                        row["match_status"] = "Qty Mismatch"
                        row["match_remark"] = _build_qty_remark(row, mismatch_columns)
                        row["detailed_remark"] = _build_qty_detailed_remark(row, mismatch_columns, col_diffs)
                        continue

        invoice_not_in = _invoice_not_in_status_from_totals(row)
        if invoice_not_in:
            row["match_status"] = invoice_not_in
            row["match_remark"] = invoice_not_in
            row["detailed_remark"] = _not_in_detail(invoice_not_in, row)
            continue

        if raw_status == "Only In F1":
            row["match_status"] = "Not In EssGee"
            row["match_remark"] = "Not In EssGee"
            row["detailed_remark"] = _not_in_detail("Not In EssGee", row)
            continue

        if raw_status == "Only In F2":
            row["match_status"] = "Not In Brand"
            row["match_remark"] = "Not In Brand"
            row["detailed_remark"] = _not_in_detail("Not In Brand", row)
            continue

        if raw_status == "Not In Data":
            if row.get("f1_index") is None and row.get("f2_index") is not None:
                row["match_status"] = "Not In Brand"
                row["match_remark"] = "Not In Brand"
                row["detailed_remark"] = _not_in_detail("Not In Brand", row)
            else:
                row["match_status"] = "Not In EssGee"
                row["match_remark"] = "Not In EssGee"
                row["detailed_remark"] = _not_in_detail("Not In EssGee", row)
            continue

        # Mismatch path
        brand_diff_label = next((label for label in mismatch_columns if _is_brand_col(label)), None)
        if brand_diff_label and brand_diff_label in col_diffs:
            payload = col_diffs.get(brand_diff_label, {}) or {}
            f1_val = _fmt(payload.get("f1_value"))
            f2_val = _fmt(payload.get("f2_value"))
            row["mismatch_columns"] = [brand_diff_label]
            row["col_diffs"] = {brand_diff_label: payload}
            row["match_status"] = "Brand Mismatch"
            row["match_remark"] = "Brand Mismatch"
            row["detailed_remark"] = (
                "Brand is different.\n\n"
                f"Brand File Brand = {f1_val}\n"
                f"EssGee File Brand = {f2_val}"
            )
            continue

        first_value_label = _first_reference_value_label(mismatch_columns)
        has_key_identity_mismatch = any(_is_key_identity_col(label) for label in mismatch_columns)
        if first_value_label and not has_key_identity_mismatch:
            _apply_first_reference_mismatch(
                row,
                first_value_label,
                col_diffs,
                detail_labels=mismatch_columns,
            )
            continue

        row["match_status"] = "Value Mismatch"
        row["match_remark"] = "Mismatch"
        details: list[str] = []
        for label in mismatch_columns:
            payload = col_diffs.get(label, {}) or {}
            details.append(_build_value_detail(label, payload))
        row["detailed_remark"] = "\n\n".join(details) if details else "Value is different."

    return rows
