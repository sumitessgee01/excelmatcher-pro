import { useMemo, useState } from "react";

const MATCH_TYPES = [
  "text",
  "bill",
  "identifier",
  "date",
  "barcode",
  "number"
];

export default function MappingTable({
  mappings,
  f1Columns,
  f2Columns,
  onAddKey,
  onAddValue,
  onRemoveSelected,
  onPatchRow
}) {
  const [selectedIds, setSelectedIds] = useState([]);
  const allSelected = useMemo(
    () => mappings.length > 0 && selectedIds.length === mappings.length,
    [mappings.length, selectedIds.length]
  );

  const toggleSelected = (id, checked) => {
    setSelectedIds((prev) => {
      if (checked) {
        return [...new Set([...prev, id])];
      }
      return prev.filter((x) => x !== id);
    });
  };

  const toggleSelectAll = (checked) => {
    if (checked) {
      setSelectedIds(mappings.map((m) => m.id));
      return;
    }
    setSelectedIds([]);
  };

  const handleRemoveSelected = () => {
    if (selectedIds.length === 0) {
      return;
    }
    onRemoveSelected(selectedIds);
    setSelectedIds([]);
  };

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-borderc px-4 py-3">
        <h3 className="text-sm font-semibold text-textc">Column Mapping</h3>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white"
            onClick={onAddKey}
          >
            Add Key
          </button>
          <button
            type="button"
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white"
            onClick={onAddValue}
          >
            Add Value
          </button>
          <button
            type="button"
            className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
            disabled={selectedIds.length === 0}
            onClick={handleRemoveSelected}
          >
            Remove Selected
          </button>
        </div>
      </div>

      <div className="max-h-[360px] overflow-auto scroll-thin">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-slate-800/70 text-muted">
              <th className="p-2 text-left">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => toggleSelectAll(e.target.checked)}
                />
              </th>
              <th className="p-2 text-left">#</th>
              <th className="p-2 text-left">Use</th>
              <th className="p-2 text-left">Type</th>
              <th className="p-2 text-left">Label</th>
              <th className="p-2 text-left">F1 Col</th>
              <th className="p-2 text-left">F2 Col</th>
              <th className="p-2 text-left">Match Type</th>
              <th className="p-2 text-left">Tolerance</th>
            </tr>
          </thead>
          <tbody>
            {mappings.length === 0 ? (
              <tr>
                <td className="p-4 text-muted" colSpan={9}>
                  No mappings yet. Load both files and AI will auto-fill these rows.
                </td>
              </tr>
            ) : (
              mappings.map((row, idx) => (
                <tr key={row.id} className="border-t border-borderc/60">
                  <td className="p-2">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(row.id)}
                      onChange={(e) => toggleSelected(row.id, e.target.checked)}
                    />
                  </td>
                  <td className="p-2 text-muted">{idx + 1}</td>
                  <td className="p-2">
                    <input
                      type="checkbox"
                      checked={Boolean(row.use)}
                      onChange={(e) => onPatchRow(row.id, { use: e.target.checked })}
                    />
                  </td>
                  <td className="p-2">
                    <select
                      className="w-full rounded bg-slate-900 p-1.5 text-textc"
                      value={row.col_type}
                      onChange={(e) => onPatchRow(row.id, { col_type: e.target.value })}
                    >
                      <option value="key">Key</option>
                      <option value="value">Value</option>
                    </select>
                  </td>
                  <td className="p-2">
                    <input
                      className="w-full rounded bg-slate-900 p-1.5 text-textc"
                      value={row.label}
                      onChange={(e) => onPatchRow(row.id, { label: e.target.value })}
                    />
                  </td>
                  <td className="p-2">
                    <select
                      className="w-full rounded bg-slate-900 p-1.5 text-textc"
                      value={row.f1_col}
                      onChange={(e) => onPatchRow(row.id, { f1_col: e.target.value })}
                    >
                      <option value="">Select</option>
                      {f1Columns.map((c) => (
                        <option key={`f1-${c}`} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="p-2">
                    <select
                      className="w-full rounded bg-slate-900 p-1.5 text-textc"
                      value={row.f2_col}
                      onChange={(e) => onPatchRow(row.id, { f2_col: e.target.value })}
                    >
                      <option value="">Select</option>
                      {f2Columns.map((c) => (
                        <option key={`f2-${c}`} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="p-2">
                    <select
                      className="w-full rounded bg-slate-900 p-1.5 text-textc"
                      value={row.match_type}
                      onChange={(e) => onPatchRow(row.id, { match_type: e.target.value })}
                    >
                      {MATCH_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="p-2">
                    <input
                      className="w-full rounded bg-slate-900 p-1.5 text-textc"
                      type="number"
                      step="0.01"
                      value={row.tolerance}
                      onChange={(e) => onPatchRow(row.id, { tolerance: Number(e.target.value) })}
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
