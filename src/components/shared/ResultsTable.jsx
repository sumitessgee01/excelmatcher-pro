import { useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";

const STATUS_TEXT = {
  Match: "text-green-200",
  "Brand Mismatch": "text-red-100",
  "Value Mismatch": "text-red-100",
  "Qty Mismatch": "text-yellow-100",
  "Not In EssGee": "text-blue-100",
  "Not In Brand": "text-slate-200"
};

const WIDTH_SAMPLE_ROWS = 80;
const MIN_VALUE_COLUMN_WIDTH = 92;
const MAX_VALUE_COLUMN_WIDTH = 170;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function pickMainRow(row) {
  return row?.f1_row || row?.f2_row || {};
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  return String(value);
}

function normalize(value) {
  return String(value || "").trim().casefold?.() || String(value || "").trim().toLowerCase();
}

function cleanMappings(mappings, rows) {
  const configured = (Array.isArray(mappings) ? mappings : [])
    .filter((m) => m?.f1_col || m?.f2_col)
    .map((m, idx) => ({
      id: `${m.f1_col || ""}-${m.f2_col || ""}-${idx}`,
      label: m.label || m.f1_col || m.f2_col || "Column",
      f1_col: m.f1_col || "",
      f2_col: m.f2_col || "",
      order: idx
    }));

  if (configured.length > 0) {
    return configured;
  }

  const first = pickMainRow(rows?.[0]);
  return Object.keys(first).slice(0, 8).map((col, idx) => ({
    id: col,
    label: col,
    f1_col: col,
    f2_col: col,
    order: idx
  }));
}

function findInvoiceMapping(mappings) {
  return mappings.find((mapping) => {
    const text = `${mapping.label} ${mapping.f1_col} ${mapping.f2_col}`.toLowerCase();
    return text.includes("invoice") || text.includes("bill") || text.includes("inv");
  });
}

function invoiceValue(row, invoiceMapping) {
  const f1 = row?.f1_row || {};
  const f2 = row?.f2_row || {};
  if (invoiceMapping) {
    return (
      displayValue(f1[invoiceMapping.f1_col]) ||
      displayValue(f2[invoiceMapping.f2_col]) ||
      displayValue(row.normalized_invoice)
    );
  }
  const main = pickMainRow(row);
  return (
    displayValue(main["Invoice No"]) ||
    displayValue(main["Bill Number"]) ||
    displayValue(main["Bill No"]) ||
    displayValue(row.normalized_invoice)
  );
}

function mismatchLabels(row) {
  return new Set((row?.mismatch_columns || []).map((x) => String(x).trim()).filter(Boolean));
}

function isMatched(row) {
  return String(row?.match_status || "") === "Match";
}

function matchRemarkValue(row) {
  return String(row?.match_remark || row?.match_status || "").trim();
}

function textColumnWidth(values, minWidth, maxWidth) {
  const maxLength = values.reduce((max, value) => {
    const text = displayValue(value);
    return Math.max(max, text.length);
  }, 0);
  return clamp(maxLength * 7 + 28, minWidth, maxWidth);
}

function columnWidth(rows, mapping) {
  const sampledRows = rows.slice(0, WIDTH_SAMPLE_ROWS);
  const values = [mapping.label];
  for (const row of sampledRows) {
    values.push(row?.f1_row?.[mapping.f1_col]);
    values.push(row?.f2_row?.[mapping.f2_col]);
  }
  return textColumnWidth(values, MIN_VALUE_COLUMN_WIDTH, MAX_VALUE_COLUMN_WIDTH);
}

function invoiceColumnWidth(rows, invoiceMapping) {
  const values = ["Invoice No", ...rows.slice(0, WIDTH_SAMPLE_ROWS).map((row) => invoiceValue(row, invoiceMapping))];
  return textColumnWidth(values, 118, 180);
}

function remarkColumnWidth(rows) {
  const values = [
    "Remarks",
    ...rows.slice(0, WIDTH_SAMPLE_ROWS).map((row) =>
      isMatched(row) ? "All Matched" : row?.detailed_remark || row?.match_remark || row?.match_status || ""
    )
  ];
  return textColumnWidth(values, 170, 260);
}

function rowHasIssue(row) {
  return !isMatched(row);
}

function buildIssueColumns(rows, mappings) {
  const labelHits = new Set();
  for (const row of rows) {
    for (const label of mismatchLabels(row)) {
      labelHits.add(normalize(label));
    }
  }

  const columns = mappings.filter((mapping) => {
    const label = normalize(mapping.label);
    const f1 = normalize(mapping.f1_col);
    const f2 = normalize(mapping.f2_col);
    return labelHits.has(label) || labelHits.has(f1) || labelHits.has(f2);
  });

  if (columns.length > 0) {
    return columns;
  }

  return rows.some(rowHasIssue)
    ? [{ id: "record", label: "Record", f1_col: "", f2_col: "", order: 9999 }]
    : [];
}

function fieldValue(row, mapping, side) {
  if (mapping.id === "record") {
    if (side === "brand") {
      return row?.f1_row ? "Present" : "Missing";
    }
    return row?.f2_row ? "Present" : "Missing";
  }
  const source = side === "brand" ? row?.f1_row : row?.f2_row;
  const key = side === "brand" ? mapping.f1_col : mapping.f2_col;
  return displayValue(source?.[key]);
}

function shouldDimCell(row, mapping) {
  if (isMatched(row) || mapping.id === "record") {
    return false;
  }
  const labels = mismatchLabels(row);
  return !(
    labels.has(mapping.label) ||
    labels.has(mapping.f1_col) ||
    labels.has(mapping.f2_col)
  );
}

export default function ResultsTable({
  rows,
  mappings,
  filter,
  matchRemarkFilter,
  search,
  searchColumn,
  selectedRow,
  onSelectRow,
  onMarkMatched
}) {
  const parentRef = useRef(null);
  const allMappings = useMemo(() => cleanMappings(mappings, rows), [mappings, rows]);
  const invoiceMapping = useMemo(() => findInvoiceMapping(allMappings), [allMappings]);

  const statusFiltered = useMemo(() => {
    return rows.filter((row) => {
      const statusMatches = !filter || filter === "All" || row.match_status === filter;
      const remarkMatches =
        !matchRemarkFilter || matchRemarkFilter === "All" || matchRemarkValue(row) === matchRemarkFilter;
      return statusMatches && remarkMatches;
    });
  }, [rows, filter, matchRemarkFilter]);

  const issueColumns = useMemo(
    () => buildIssueColumns(statusFiltered, allMappings),
    [statusFiltered, allMappings]
  );
  const visibleColumns = useMemo(
    () => (issueColumns.length > 0 ? issueColumns : allMappings),
    [issueColumns, allMappings]
  );
  const hasIssueColumns = visibleColumns.length > 0;
  const valueColumnWidths = useMemo(
    () => visibleColumns.map((column) => columnWidth(statusFiltered, column)),
    [visibleColumns, statusFiltered]
  );
  const invoiceWidth = useMemo(
    () => invoiceColumnWidth(statusFiltered, invoiceMapping),
    [statusFiltered, invoiceMapping]
  );
  const remarkWidth = useMemo(() => remarkColumnWidth(statusFiltered), [statusFiltered]);
  const valueColumnTemplate = valueColumnWidths.map((width) => `${width}px`).join(" ");
  const tableWidth = useMemo(() => {
    const valueColumnsWidth = valueColumnWidths.reduce((total, width) => total + width, 0);
    return Math.max(760, invoiceWidth + valueColumnsWidth * 2 + remarkWidth);
  }, [invoiceWidth, valueColumnWidths, remarkWidth]);

  const filtered = useMemo(() => {
    const lower = String(search || "").toLowerCase().trim();
    if (!lower) {
      return statusFiltered;
    }

    return statusFiltered.filter((row) => {
      if (searchColumn && searchColumn !== "all") {
        if (searchColumn === "Invoice No") {
          return invoiceValue(row, invoiceMapping).toLowerCase().includes(lower);
        }
        const mapping = allMappings.find((m) => m.label === searchColumn);
        if (mapping) {
          return `${displayValue(row.f1_row?.[mapping.f1_col])} ${displayValue(row.f2_row?.[mapping.f2_col])}`
            .toLowerCase()
            .includes(lower);
        }
        return String(pickMainRow(row)?.[searchColumn] ?? "").toLowerCase().includes(lower);
      }

      const values = allMappings
        .map((mapping) => `${mapping.label} ${displayValue(row.f1_row?.[mapping.f1_col])} ${displayValue(row.f2_row?.[mapping.f2_col])}`)
        .join(" ");
      return `${invoiceValue(row, invoiceMapping)} ${values} ${row.match_status || ""} ${row.detailed_remark || ""}`
        .toLowerCase()
        .includes(lower);
    });
  }, [statusFiltered, search, searchColumn, allMappings, invoiceMapping]);

  const gridTemplateColumns = hasIssueColumns
    ? `${invoiceWidth}px ${valueColumnTemplate} ${valueColumnTemplate} ${remarkWidth}px`
    : `${invoiceWidth}px 140px 140px ${remarkWidth}px`;
  const tableStyle = { width: `${tableWidth}px`, minWidth: "100%" };

  const rowVirtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 42,
    overscan: 14
  });

  return (
    <div className="card overflow-hidden">
      <div className="overflow-x-auto scroll-thin">
        <div style={tableStyle}>
          <div
            className="grid border-b border-borderc bg-slate-900/95 text-xs text-muted"
            style={{ gridTemplateColumns }}
          >
            <div className={`${hasIssueColumns ? "row-span-2" : ""} border-r border-borderc p-2 font-semibold text-slate-100`}>
              Invoice No
            </div>
            {hasIssueColumns ? (
              <>
                <div
                  className="border-r border-borderc p-2 text-center font-semibold text-slate-100"
                  style={{ gridColumn: `span ${visibleColumns.length}` }}
                >
                  Brand
                </div>
                <div
                  className="border-r border-borderc p-2 text-center font-semibold text-slate-100"
                  style={{ gridColumn: `span ${visibleColumns.length}` }}
                >
                  EssGee
                </div>
              </>
            ) : (
              <>
                <div className="border-r border-borderc p-2 text-center font-semibold text-slate-100">Brand</div>
                <div className="border-r border-borderc p-2 text-center font-semibold text-slate-100">EssGee</div>
              </>
            )}
            <div className={`${hasIssueColumns ? "row-span-2" : ""} p-2 font-semibold text-slate-100`}>Remarks</div>

            {hasIssueColumns
              ? visibleColumns.map((column) => (
                  <div key={`brand-head-${column.id}`} className="truncate border-r border-t border-borderc p-2 font-semibold text-slate-100" title={column.label}>
                    {column.label}
                  </div>
                ))
              : null}
            {hasIssueColumns
              ? visibleColumns.map((column) => (
                  <div key={`essgee-head-${column.id}`} className="truncate border-r border-t border-borderc p-2 font-semibold text-slate-100" title={column.label}>
                    {column.label}
                  </div>
                ))
              : null}
          </div>

          <div ref={parentRef} className="h-[470px] overflow-y-auto overflow-x-hidden scroll-thin">
            <div
              style={{
                height: `${rowVirtualizer.getTotalSize()}px`,
                position: "relative"
              }}
            >
              {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                const row = filtered[virtualRow.index];
                const selected = selectedRow === row || (selectedRow?.result_id && selectedRow.result_id === row.result_id);
                const statusClass = STATUS_TEXT[row.match_status] || "text-slate-100";
                const remark = isMatched(row) ? "All Matched" : row.detailed_remark || row.match_remark || row.match_status || "";

                return (
                  <div
                    key={virtualRow.key}
                    className={`absolute left-0 top-0 grid w-full cursor-pointer border-b border-borderc/50 text-xs ${
                      selected ? "bg-blue-500/10 ring-1 ring-blue-300/70" : "bg-slate-950/20 hover:bg-slate-800/35"
                    }`}
                    style={{
                      gridTemplateColumns,
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`
                    }}
                    onClick={() => onSelectRow(row)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      onMarkMatched(row);
                    }}
                  >
                    <div className="mono truncate border-r border-borderc/50 p-2 text-slate-100">
                      {invoiceValue(row, invoiceMapping) || "-"}
                    </div>

                    {hasIssueColumns ? (
                      <>
                        {visibleColumns.map((column) => {
                          const value = fieldValue(row, column, "brand") || "-";
                          return (
                            <div
                              key={`brand-${column.id}`}
                              className={`mono truncate border-r border-borderc/50 p-2 text-slate-100 ${
                                shouldDimCell(row, column) ? "text-slate-500" : ""
                              }`}
                              title={value}
                            >
                              {value}
                            </div>
                          );
                        })}
                        {visibleColumns.map((column) => {
                          const value = fieldValue(row, column, "essgee") || "-";
                          return (
                            <div
                              key={`essgee-${column.id}`}
                              className={`mono truncate border-r border-borderc/50 p-2 text-slate-100 ${
                                shouldDimCell(row, column) ? "text-slate-500" : ""
                              }`}
                              title={value}
                            >
                              {value}
                            </div>
                          );
                        })}
                      </>
                    ) : (
                      <>
                        <div className="truncate border-r border-borderc/50 p-2 text-green-200">All Matched</div>
                        <div className="truncate border-r border-borderc/50 p-2 text-green-200">All Matched</div>
                      </>
                    )}

                    <div className={`truncate p-2 ${isMatched(row) ? "text-green-200" : statusClass}`}>
                      {remark}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
