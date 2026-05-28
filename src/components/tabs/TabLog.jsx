import { useAppStore } from "../../store/appStore";

function levelClass(level) {
  if (level === "SUCCESS") {
    return "text-green-300";
  }
  if (level === "WARNING") {
    return "text-yellow-300";
  }
  if (level === "ERROR") {
    return "text-red-300";
  }
  return "text-slate-200";
}

export default function TabLog() {
  const logs = useAppStore((s) => s.logs);

  return (
    <div className="card p-3">
      <div className="mb-2 text-sm font-semibold text-textc">System Log</div>
      <div className="max-h-[520px] space-y-1 overflow-auto rounded border border-borderc bg-slate-950/70 p-2 scroll-thin mono text-xs">
        {logs.map((log) => (
          <div key={log.id} className="flex gap-2">
            <span className="text-muted">[{log.ts}]</span>
            <span className={levelClass(log.level)}>{log.level}</span>
            <span className="text-slate-100">{log.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
