from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from core.exporter import ExcelExporter
from core.loader import load_excel
from core.matcher import MatchConfig, MatchingEngine
from core.remarks_engine import apply_remarks


def _build_split_config() -> MatchConfig:
  return MatchConfig.from_dict(
    {
      "key_columns": [
        {"f1_col": "Invoice No", "f2_col": "Invoice No", "label": "Invoice No", "match_type": "bill"},
        {"f1_col": "Party Name", "f2_col": "Party Name", "label": "Party Name", "match_type": "identifier"},
      ],
      "value_columns": [
        {"f1_col": "Qty", "f2_col": "Qty", "label": "Qty", "match_type": "number", "tolerance": 0},
        {"f1_col": "MRP", "f2_col": "MRP", "label": "MRP", "match_type": "number", "tolerance": 0},
      ],
      "fuzzy_enabled": True,
      "qty_expansion_enabled": False,
      "case_insensitive": True,
      "trim": True,
    }
  )


def _run_split_smoke_test() -> None:
  forward_f1 = pd.DataFrame(
    [{"Invoice No": "INV1", "Party Name": "ABC", "Qty": 2, "MRP": 100}]
  )
  forward_f2 = pd.DataFrame(
    [
      {"Invoice No": "INV1", "Party Name": "ABC", "Qty": 1, "MRP": 50},
      {"Invoice No": "INV1", "Party Name": "ABC", "Qty": 1, "MRP": 50},
    ]
  )
  reverse_f1 = pd.DataFrame(
    [
      {"Invoice No": "INV2", "Party Name": "ABC", "Qty": 1, "MRP": 50},
      {"Invoice No": "INV2", "Party Name": "ABC", "Qty": 1, "MRP": 50},
    ]
  )
  reverse_f2 = pd.DataFrame(
    [{"Invoice No": "INV2", "Party Name": "ABC", "Qty": 2, "MRP": 100}]
  )
  both_f1 = pd.DataFrame(
    [
      {"Invoice No": "INV3", "Party Name": "ABC", "Qty": 1, "MRP": 50},
      {"Invoice No": "INV3", "Party Name": "ABC", "Qty": 1, "MRP": 50},
    ]
  )
  both_f2 = pd.DataFrame(
    [
      {"Invoice No": "INV3", "Party Name": "ABC", "Qty": 1, "MRP": 50},
      {"Invoice No": "INV3", "Party Name": "ABC", "Qty": 1, "MRP": 50},
    ]
  )

  cfg = _build_split_config()
  for name, f1_df, f2_df in (
    ("forward", forward_f1, forward_f2),
    ("reverse", reverse_f1, reverse_f2),
    ("both", both_f1, both_f2),
  ):
    rows = apply_remarks(MatchingEngine(cfg).run(f1_df, f2_df)["rows"])
    statuses = [row["match_status"] for row in rows]
    if not all(status == "Match" for status in statuses):
      raise RuntimeError(f"Split smoke test failed for {name}: {statuses}")

  engine = MatchingEngine(cfg)
  brand_single_ok = engine._brand_single_split_values_match(
    {"Invoice No": 1001, "Party Name": "ABC", "Qty": 2, "MRP": 100},
    [
      {"Invoice No": 1001, "Party Name": "ABC", "Qty": 1, "MRP": 50},
      {"Invoice No": 1001, "Party Name": "ABC", "Qty": 1, "MRP": 50},
    ],
  )
  if not brand_single_ok:
    raise RuntimeError("Numeric invoice split key comparison failed")

  summarized_key_ok = engine._split_group_values_match(
    {
      0: {"Invoice No": 1002, "Party Name": "ABC", "Qty": 1, "MRP": 50},
      1: {"Invoice No": 1002, "Party Name": "ABC", "Qty": 1, "MRP": 50},
    },
    {0: {"Invoice No": 1002, "Party Name": "ABC", "Qty": 2, "MRP": 100}},
  )
  if not summarized_key_ok:
    raise RuntimeError("F1 split to F2 summarized key comparison failed")


def main() -> None:
  parser = argparse.ArgumentParser(description="ExcelMatcher Pro integration test")
  parser.add_argument("--f1", required=True, help="Path to Brand file")
  parser.add_argument("--f2", required=True, help="Path to EssGee file")
  parser.add_argument("--f1-sheet", default=0)
  parser.add_argument("--f2-sheet", default=0)
  parser.add_argument("--brand", default="TestBrand")
  parser.add_argument("--out", default="integration_report.xlsx")
  parser.add_argument("--smoke-split", action="store_true", help="Run split-qty smoke checks")
  args = parser.parse_args()

  df1 = load_excel(args.f1, sheet=args.f1_sheet, header_row=0)
  df2 = load_excel(args.f2, sheet=args.f2_sheet, header_row=0)

  # Minimal auto mapping for quick validation. Update manually for real data.
  key_columns = []
  value_columns = []
  for col1 in df1.columns:
    for col2 in df2.columns:
      if str(col1).strip().lower() == str(col2).strip().lower():
        label = str(col1)
        if any(x in label.lower() for x in ["invoice", "bill", "party", "customer", "barcode", "date"]):
          key_columns.append({"f1_col": col1, "f2_col": col2, "label": label, "match_type": "text"})
        else:
          value_columns.append({"f1_col": col1, "f2_col": col2, "label": label, "tolerance": 0})

  if not key_columns:
    raise RuntimeError("No key columns auto-detected. Please define mappings in code for this dataset.")

  cfg = MatchConfig.from_dict(
    {
      "key_columns": key_columns,
      "value_columns": value_columns,
      "fuzzy_enabled": True,
      "fuzzy_threshold": 85,
      "qty_expansion_enabled": False,
      "case_insensitive": True,
      "trim": True,
    }
  )

  result = MatchingEngine(cfg).run(df1, df2)
  rows = apply_remarks(result["rows"])

  out_path = Path(args.out).resolve()
  ExcelExporter().export_full(
    out_path,
    brand_df=df1,
    essgee_df=df2,
    rows=rows,
    brand_file_name=Path(args.f1).name,
    essgee_file_name=Path(args.f2).name,
    value_mappings=value_columns,
  )

  print("Integration test complete")
  print("Stats:", result["stats"])
  print("Report:", out_path)

  if args.smoke_split:
    _run_split_smoke_test()
    print("Split smoke test: OK")


if __name__ == "__main__":
  main()
