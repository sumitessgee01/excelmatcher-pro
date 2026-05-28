import { useEffect, useMemo } from "react";
import StatsCards from "../shared/StatsCards";
import ResultsTable from "../shared/ResultsTable";
import { useAppStore } from "../../store/appStore";

const FILTERS = [
  "All",
  "Match",
  "Qty Mismatch",
  "Brand Mismatch",
  "Value Mismatch",
  "Not In Brand",
  "Not In EssGee"
];

function rowMain(row) {
  return row?.f1_row || row?.f2_row || {};
}

function resultMappings(match) {
  const mappings = Array.isArray(match.mappings) ? match.mappings : [];
  return mappings
    .filter((m) => m?.f1_col || m?.f2_col)
    .map((m, idx) => ({
      id: `${m.f1_col || ""}-${m.f2_col || ""}-${idx}`,
      label: m.label || m.f1_col || m.f2_col || "Column",
      f1_col: m.f1_col || "",
      f2_col: m.f2_col || "",
      col_type: m.col_type === "key" ? "Key" : "Value"
    }));
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function matchRemarkValue(row) {
  return String(row?.match_remark || row?.match_status || "").trim();
}

function comparisonStatus(row, mapping) {
  if (!row?.f1_row || !row?.f2_row) {
    return "Missing";
  }
  const mismatches = new Set((row.mismatch_columns || []).map((x) => String(x).trim()));
  if (mismatches.has(mapping.label) || mismatches.has(mapping.f1_col) || mismatches.has(mapping.f2_col)) {
    return "Mismatch";
  }
  return "Match";
}

function statusClass(status) {
  if (status === "Match") {
    return "bg-green-500/15 text-green-200";
  }
  if (status === "Mismatch") {
    return "bg-red-500/15 text-red-100";
  }
  return "bg-blue-500/15 text-blue-100";
}

export default function TabResults() {
  const match = useAppStore((s) => s.match);
  const ui = useAppStore((s) => s.resultsUI);
  const setFilter = useAppStore((s) => s.setResultsFilter);
  const setMatchRemarkFilter = useAppStore((s) => s.setResultsMatchRemarkFilter);
  const setSearch = useAppStore((s) => s.setResultsSearch);
  const setSearchColumn = useAppStore((s) => s.setResultsSearchColumn);
  const setSelectedRow = useAppStore((s) => s.setSelectedResultRow);
  const markAsActuallyMatched = useAppStore((s) => s.markAsActuallyMatched);
  const exportReport = useAppStore((s) => s.exportReport);

  const firstRow = match.rows?.[0];
  const mappings = useMemo(() => resultMappings(match), [match.mappings]);
  const rawColumns = useMemo(() => Object.keys(rowMain(firstRow)), [firstRow]);
  const columns = useMemo(() => {
    const mappedLabels = mappings.map((m) => m.label);
    return [...new Set([...mappedLabels, ...rawColumns])];
  }, [mappings, rawColumns]);
  const statusFilteredRows = useMemo(() => {
    const rows = match.rows || [];
    if (!ui.filter || ui.filter === "All") {
      return rows;
    }
    return rows.filter((row) => row.match_status === ui.filter);
  }, [match.rows, ui.filter]);
  const matchRemarkFilters = useMemo(() => {
    const remarks = statusFilteredRows
      .map(matchRemarkValue)
      .filter(Boolean);
    return ["All", ...new Set(remarks)];
  }, [statusFilteredRows]);

  useEffect(() => {
    if (!ui.matchRemarkFilter || ui.matchRemarkFilter === "All") {
      return;
    }
    if (!matchRemarkFilters.includes(ui.matchRemarkFilter)) {
      setMatchRemarkFilter("All");
    }
  }, [matchRemarkFilters, setMatchRemarkFilter, ui.matchRemarkFilter]);
  const selectedComparisons = useMemo(() => {
    const row = ui.selectedRow;
    if (!row) {
      return [];
    }
    const activeMappings = mappings.length > 0
      ? mappings
      : rawColumns.map((col) => ({ id: col, label: col, f1_col: col, f2_col: col, col_type: "Value" }));
    return activeMappings.map((mapping) => ({
      ...mapping,
      brandValue: row.f1_row?.[mapping.f1_col],
      essgeeValue: row.f2_row?.[mapping.f2_col],
      status: comparisonStatus(row, mapping)
    }));
  }, [ui.selectedRow, mappings, rawColumns]);

  return (
    <div className="space-y-4">
      <StatsCards stats={match.stats || {}} />

      <div className="card p-3">
        <div className="grid grid-cols-1 gap-2 md:grid-cols-[180px,180px,1fr,180px,auto]">
          <select
            className="rounded bg-slate-900 p-2 text-xs text-textc"
            value={ui.filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            {FILTERS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <select
            className="rounded bg-slate-900 p-2 text-xs text-textc"
            value={ui.matchRemarkFilter || "All"}
            onChange={(e) => setMatchRemarkFilter(e.target.value)}
          >
            {matchRemarkFilters.map((f) => (
              <option key={f} value={f}>
                {f === "All" ? "All Match Remarks" : f}
              </option>
            ))}
          </select>
          <input
            className="rounded bg-slate-900 p-2 text-xs text-textc"
            value={ui.search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search..."
          />
          <select
            className="rounded bg-slate-900 p-2 text-xs text-textc"
            value={ui.searchColumn}
            onChange={(e) => setSearchColumn(e.target.value)}
          >
            <option value="all">All Columns</option>
            {columns.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="rounded bg-blue-600 px-3 py-2 text-xs font-semibold text-white"
            onClick={() => exportReport("summary", { filtered: true })}
          >
            Export Filtered View
          </button>
        </div>
      </div>

      <ResultsTable
        rows={match.rows || []}
        mappings={mappings}
        filter={ui.filter}
        matchRemarkFilter={ui.matchRemarkFilter}
        search={ui.search}
        searchColumn={ui.searchColumn}
        selectedRow={ui.selectedRow}
        onSelectRow={setSelectedRow}
        onMarkMatched={markAsActuallyMatched}
      />

      {ui.selectedRow ? (
        <div className="card p-3">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-textc">{ui.selectedRow.match_status}</div>
              <div className="text-xs text-muted">{ui.selectedRow.match_remark || "Match"}</div>
            </div>
            <button
              type="button"
              className="rounded bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white"
              onClick={() => setSelectedRow(null)}
            >
              Close
            </button>
          </div>

          <div className="overflow-auto rounded border border-borderc bg-slate-950/50 scroll-thin">
            <table className="w-full min-w-[620px] text-[11px]">
              <thead>
                <tr className="bg-slate-800/90 text-muted">
                  <th className="w-[150px] p-1 text-left">Field</th>
                  <th className="p-1 text-left">Brand</th>
                  <th className="p-1 text-left">EssGee</th>
                  <th className="w-[90px] p-1 text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {selectedComparisons.map((row) => (
                  <tr key={row.id} className="border-t border-borderc/50">
                    <td className="p-1 font-semibold text-slate-100">{row.label}</td>
                    <td className="mono p-1 text-slate-100">{displayValue(row.brandValue)}</td>
                    <td className="mono p-1 text-slate-100">{displayValue(row.essgeeValue)}</td>
                    <td className="p-1">
                      <span className={`rounded px-2 py-0.5 ${statusClass(row.status)}`}>{row.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 rounded border border-borderc bg-slate-900/70 p-3 text-xs text-slate-100">
            <div className="mb-1 font-semibold">Remarks</div>
            <div className="whitespace-pre-wrap">{ui.selectedRow.detailed_remark || "All values matched"}</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
