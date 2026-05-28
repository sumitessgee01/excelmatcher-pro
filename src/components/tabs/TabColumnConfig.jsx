import MappingTable from "../shared/MappingTable";
import { useAppStore } from "../../store/appStore";

export default function TabColumnConfig() {
  const files = useAppStore((s) => s.files);
  const mappings = useAppStore((s) => s.mappings);
  const addKeyMappingRow = useAppStore((s) => s.addKeyMappingRow);
  const addValueMappingRow = useAppStore((s) => s.addValueMappingRow);
  const removeMappingsByIds = useAppStore((s) => s.removeMappingsByIds);
  const patchMappingRow = useAppStore((s) => s.patchMappingRow);
  const saveConfigToLocal = useAppStore((s) => s.saveConfigToLocal);
  const loadConfigFromLocal = useAppStore((s) => s.loadConfigFromLocal);
  const resetConfigDefaults = useAppStore((s) => s.resetConfigDefaults);

  return (
    <div className="space-y-4">
      <MappingTable
        mappings={mappings}
        f1Columns={files.f1.columns || []}
        f2Columns={files.f2.columns || []}
        onAddKey={addKeyMappingRow}
        onAddValue={addValueMappingRow}
        onRemoveSelected={removeMappingsByIds}
        onPatchRow={patchMappingRow}
      />

      <div className="card p-3">
        <div className="mb-2 text-sm font-semibold text-textc">Save / Load</div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded bg-blue-600 px-3 py-2 text-xs font-semibold text-white"
            onClick={saveConfigToLocal}
          >
            Save Config
          </button>
          <button
            type="button"
            className="rounded bg-slate-700 px-3 py-2 text-xs font-semibold text-white"
            onClick={loadConfigFromLocal}
          >
            Load Config
          </button>
          <button
            type="button"
            className="rounded bg-slate-600 px-3 py-2 text-xs font-semibold text-white"
            onClick={resetConfigDefaults}
          >
            Reset Defaults
          </button>
        </div>
      </div>
    </div>
  );
}
