import FileDropZone from "../shared/FileDropZone";
import { useAppStore } from "../../store/appStore";

const PREVIEW_ROW_COUNT = 5;

function CompactFileInfo({ side, data, onUpdate }) {
  const formatFileSize = (bytes) => {
    if (!bytes) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 10) / 10 + " " + sizes[i];
  };

  if (!data.loaded) return null;

  const rowCount = data.rowCount || 0;
  const colCount = data.columns?.length || 0;
  const fileSize = formatFileSize(data.fileSize);
  const sheets = data.sheets || [];
  const sheetCount = sheets.length;
  const headerRow = Math.max(0, Number(data.headerRow || 0));

  const updateHeader = (value) => {
    const safe = Math.max(0, Number(value || 0));
    onUpdate(side, { headerRow: safe }, { immediate: true });
  };

  return (
    <div className="card space-y-2 p-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="font-semibold text-textc">{data.fileName}</span>
        <span className="text-muted">{fileSize}</span>
      </div>

      <div className="flex flex-wrap gap-3 text-xs text-muted">
        <span>{rowCount.toLocaleString()} rows</span>
        <span>{colCount} cols</span>
        <span>{sheetCount} sheet{sheetCount !== 1 ? "s" : ""}</span>
      </div>

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        <div className="flex items-center gap-2">
          <label className="w-24 text-xs text-muted">Workbook:</label>
          <select
            className="min-w-0 flex-1 rounded bg-slate-800 px-2 py-1 text-xs text-textc"
            value={data.sheet}
            onChange={(e) => onUpdate(side, { sheet: e.target.value }, { immediate: true })}
            disabled={sheetCount === 0}
          >
            {sheets.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="w-24 text-xs text-muted">Header Row:</label>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="h-7 w-7 rounded bg-slate-800 text-sm text-textc hover:bg-slate-700"
              onClick={() => updateHeader(headerRow - 1)}
            >
              -
            </button>
            <input
              className="w-14 rounded bg-slate-800 px-2 py-1 text-center text-xs text-textc"
              type="number"
              min={0}
              value={headerRow}
              onChange={(e) => updateHeader(e.target.value)}
            />
            <button
              type="button"
              className="h-7 w-7 rounded bg-slate-800 text-sm text-textc hover:bg-slate-700"
              onClick={() => updateHeader(headerRow + 1)}
            >
              +
            </button>
          </div>
        </div>
      </div>

      <div className="rounded border border-borderc/50 bg-slate-900/60 px-2 py-1 text-[11px] text-muted">
        Live Header: row {headerRow + 1} is used as column names. Preview updates instantly.
      </div>
    </div>
  );
}

function CompactPreviewTable({ columns, rows }) {
  const visibleColumns = (columns || []).slice(0, 8);
  const normalizedRows = Array.from({ length: PREVIEW_ROW_COUNT }, (_, i) => rows?.[i] || null);

  return (
    <div className="card overflow-hidden">
      <div className="max-h-48 overflow-auto scroll-thin">
        <table className="w-full table-fixed text-xs">
          <thead>
            <tr className="sticky top-0 bg-slate-800/90 text-muted">
              <th className="w-10 p-1 text-left">#</th>
              {visibleColumns.map((c) => (
                <th key={c} className="p-1 text-left">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {normalizedRows.map((r, idx) => (
              <tr key={idx} className="border-t border-borderc/30">
                <td className="p-1 text-muted">{idx + 1}</td>
                {visibleColumns.map((c) => (
                  <td key={`${idx}-${c}`} className="p-1">
                    <span className="mono block truncate text-xs">
                      {r ? String(r[c] ?? "") : ""}
                    </span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function TabFiles() {
  const files = useAppStore((s) => s.files);
  const loadFileForSide = useAppStore((s) => s.loadFileForSide);
  const updateFileConfig = useAppStore((s) => s.updateFileConfig);

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        <FileDropZone title="Brand File (F1)" side="f1" fileState={files.f1} onFilePicked={loadFileForSide} />
        <FileDropZone title="EssGee File (F2)" side="f2" fileState={files.f2} onFilePicked={loadFileForSide} />
      </div>

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        <CompactFileInfo side="f1" data={files.f1} onUpdate={updateFileConfig} />
        <CompactFileInfo side="f2" data={files.f2} onUpdate={updateFileConfig} />
      </div>

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {files.f1.loaded && (
          <div>
            <div className="mb-1 text-xs font-semibold text-muted">Brand Preview (Top 5)</div>
            <CompactPreviewTable columns={files.f1.columns || []} rows={files.f1.previewRows || []} />
          </div>
        )}
        {files.f2.loaded && (
          <div>
            <div className="mb-1 text-xs font-semibold text-muted">EssGee Preview (Top 5)</div>
            <CompactPreviewTable columns={files.f2.columns || []} rows={files.f2.previewRows || []} />
          </div>
        )}
      </div>
    </div>
  );
}
