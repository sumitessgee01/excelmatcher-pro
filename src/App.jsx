import { DatabaseZap, FileSpreadsheet, Settings2, PlayCircle, Download, Bug } from "lucide-react";
import { useAppStore } from "./store/appStore";
import TabFiles from "./components/tabs/TabFiles";
import TabColumnConfig from "./components/tabs/TabColumnConfig";
import TabResults from "./components/tabs/TabResults";
import TabLog from "./components/tabs/TabLog";

const TABS = [
  { key: "files", label: "Files", icon: FileSpreadsheet },
  { key: "config", label: "Column Config", icon: Settings2 },
  { key: "results", label: "Results", icon: DatabaseZap },
  { key: "log", label: "Log", icon: Bug }
];

function SidebarButton({ active, icon: Icon, label, onClick }) {
  return (
    <button
      type="button"
      className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition ${
        active ? "bg-blue-600 text-white" : "text-slate-200 hover:bg-slate-700/70"
      }`}
      onClick={onClick}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </button>
  );
}

function MainTab() {
  const activeTab = useAppStore((s) => s.activeTab);
  if (activeTab === "files") return <TabFiles />;
  if (activeTab === "config") return <TabColumnConfig />;
  if (activeTab === "results") return <TabResults />;
  return <TabLog />;
}

export default function App() {
  const activeTab = useAppStore((s) => s.activeTab);
  const setActiveTab = useAppStore((s) => s.setActiveTab);
  const runMatch = useAppStore((s) => s.runMatch);
  const exportReport = useAppStore((s) => s.exportReport);
  const match = useAppStore((s) => s.match);
  const progress = Math.max(0, Math.min(100, Number(match.progress || 0)));

  return (
    <div className="flex h-full">
      <aside className="w-[220px] border-r border-borderc bg-slate-950/60 p-3">
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-borderc bg-slate-900/70 p-3">
          <img
            src="/icon.png"
            alt="FileMatcher"
            className="h-10 w-10 shrink-0 rounded-xl"
          />
          <div className="text-lg font-extrabold text-white">FileMatcher</div>
        </div>

        <div className="space-y-1">
          {TABS.map((tab) => (
            <SidebarButton
              key={tab.key}
              active={activeTab === tab.key}
              icon={tab.icon}
              label={tab.label}
              onClick={() => setActiveTab(tab.key)}
            />
          ))}
        </div>

        <div className="mt-4 space-y-2">
          <button
            type="button"
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-green-600 px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
            disabled={match.status === "running"}
            onClick={runMatch}
          >
            <PlayCircle className="h-4 w-4" />
            Run Match
          </button>
          <button
            type="button"
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-semibold text-white"
            onClick={() => exportReport("full")}
          >
            <Download className="h-4 w-4" />
            Export Excel
          </button>
          <button
            type="button"
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white"
            onClick={() => exportReport("summary")}
          >
            <Download className="h-4 w-4" />
            Export Summary
          </button>
          <button
            type="button"
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-slate-700 px-3 py-2 text-sm font-semibold text-white"
            onClick={() => exportReport("mismatch")}
          >
            <Download className="h-4 w-4" />
            Export Mismatch
          </button>
        </div>

        <div className="absolute bottom-3 left-3 text-xs text-muted">v1.0.0</div>
      </aside>

      <main className="flex-1 overflow-hidden p-4">
        <header className="card mb-4 p-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-muted">Desktop Reconciliation Workspace</div>
              <div className="text-sm font-semibold text-textc">
                {match.status === "running" ? match.message || "Running..." : "Ready"}
              </div>
            </div>
            <div className="mono text-xs text-slate-300">
              Status: <span className="font-semibold text-white">{match.status}</span>
            </div>
          </div>
          <div className="mt-2 h-2 w-full rounded bg-slate-800">
            <div
              className="h-2 rounded bg-blue-500 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="mt-1 text-right mono text-[11px] text-slate-300">{progress}%</div>
        </header>

        <section className="h-[calc(100%-112px)] overflow-auto pr-1 scroll-thin">
          <MainTab />
        </section>
      </main>
    </div>
  );
}
