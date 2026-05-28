import { useRef, useState } from "react";
import { UploadCloud, FileSpreadsheet } from "lucide-react";

const ACCEPTED_FILE_TYPES = ".xlsx,.xlsm,.xltx,.xltm,.xls,.xlsb,.ods,.odf,.odt,.csv,.tsv";
const ACCEPTED_FILE_LABEL = ".xlsx .xlsm .xlsb .xls .ods .csv .tsv";

export default function FileDropZone({ title, side, fileState, onFilePicked }) {
  const inputRef = useRef(null);
  const [isOver, setIsOver] = useState(false);

  const handleDrop = (event) => {
    event.preventDefault();
    setIsOver(false);
    const file = event.dataTransfer.files?.[0];
    if (!file) {
      return;
    }
    onFilePicked(side, file);
  };

  return (
    <div
      className={`card p-2 transition ${
        isOver ? "border-accent bg-blue-500/10" : "hover:border-blue-400/60"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setIsOver(true);
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={handleDrop}
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-textc">{title}</h3>
        <span
          className={`rounded-full px-1.5 py-0.5 text-xs ${
            fileState.loaded ? "bg-green-500/20 text-green-300" : "bg-slate-500/20 text-muted"
          }`}
        >
          {fileState.loaded ? "✓" : "○"}
        </span>
      </div>

      <button
        type="button"
        className="flex h-24 w-full items-center justify-center rounded-lg border border-dashed border-borderc bg-slate-800/45 p-2 text-left"
        onClick={() => inputRef.current?.click()}
      >
        <div className="flex items-center gap-2">
          <UploadCloud className="h-5 w-5 text-accent" />
          <div>
            <div className="text-xs font-medium text-textc">Drop/Click</div>
            <div className="text-[10px] text-muted">{ACCEPTED_FILE_LABEL}</div>
          </div>
        </div>
      </button>

      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept={ACCEPTED_FILE_TYPES}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            onFilePicked(side, file);
          }
          e.target.value = "";
        }}
      />

      {fileState.loaded ? (
        <div className="mt-2 rounded-lg border border-borderc bg-slate-900/45 p-2">
          <div className="flex items-center gap-1 text-xs text-textc">
            <FileSpreadsheet className="h-3 w-3 text-blue-300" />
            <span className="mono truncate">{fileState.filename}</span>
          </div>
          <div className="mt-0.5 text-[10px] text-muted">{(fileState.rowCount || 0).toLocaleString()} rows</div>
        </div>
      ) : null}
    </div>
  );
}
