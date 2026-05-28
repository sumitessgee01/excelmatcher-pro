import { create } from "zustand";
import * as api from "../utils/api";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const CONFIG_STORAGE_KEY = "excelmatcher-pro-config-v1";
const MAPPING_PRESETS_STORAGE_KEY = "excelmatcher-pro-column-map-presets-v1";
const EXPORT_DIR_STORAGE_KEY = "excelmatcher-pro-export-dir-v1";
const PREVIEW_DEBOUNCE_MS = 120;
const BACKEND_MAPPING_SAVE_DEBOUNCE_MS = 700;
const RESULT_ID_REFRESH_DELAY_MS = 1500;
const RESULT_ID_REFRESH_ATTEMPTS = 6;
const previewTimers = { f1: null, f2: null };
let backendMappingSaveTimer = null;
let backendMappingSaveInFlight = false;
let lastBackendMappingSignature = "";
let suggestionsInFlight = false;
let matchRunInFlight = false;
let exportRunInFlight = false;
const DEFAULT_OPTIONS = {
  fuzzy_enabled: true,
  fuzzy_threshold: 85,
  qty_expansion_enabled: false,
  qty_f1_col: "",
  qty_f2_col: "",
  case_insensitive: true,
  trim: true
};

function blankFileState() {
  return {
    fileId: "",
    filename: "",
    fileName: "",
    loaded: false,
    sheets: [],
    sheet: "",
    headerRow: 0,
    columns: [],
    previewRows: [],
    rowCount: 0,
    fileSize: 0
  };
}

function newLog(level, message) {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    ts: new Date().toLocaleTimeString(),
    level,
    message
  };
}

function mappingFromSuggestion(item, fallbackType = "value") {
  return {
    id: `${item.f1_col}-${item.f2_col}-${Math.random().toString(36).slice(2, 6)}`,
    use: item.confidence >= 70,
    col_type: item.type || fallbackType,
    label: item.label || item.f1_col || item.f2_col || "Column",
    f1_col: item.f1_col || "",
    f2_col: item.f2_col || "",
    match_type: item.match_type || "text",
    tolerance: Number(item.tolerance || 0)
  };
}

function tryAutoType(label) {
  const text = String(label || "").toLowerCase();
  if (
    text.includes("invoice") ||
    text.includes("bill") ||
    text.includes("party") ||
    text.includes("customer") ||
    text.includes("barcode") ||
    text.includes("date")
  ) {
    return "key";
  }
  return "value";
}

function looksLikeQtyColumn(name) {
  const text = String(name || "").toLowerCase();
  return text === "qty" || text.includes("qty") || text.includes("quantity");
}

function tsPart(n) {
  return String(n).padStart(2, "0");
}

function buildExportFilename(type) {
  const d = new Date();
  const stamp = `${d.getFullYear()}${tsPart(d.getMonth() + 1)}${tsPart(d.getDate())}_${tsPart(
    d.getHours()
  )}${tsPart(d.getMinutes())}${tsPart(d.getSeconds())}`;
  if (type === "full") return `FileMatcher_Full_Report_${stamp}.xlsx`;
  if (type === "summary") return `FileMatcher_Summary_Report_${stamp}.xlsx`;
  return `FileMatcher_Brand_Mismatch_${stamp}.xlsx`;
}

function directoryFromPath(filePath) {
  const text = String(filePath || "");
  const slash = Math.max(text.lastIndexOf("/"), text.lastIndexOf("\\"));
  if (slash <= 0) return "";
  return text.slice(0, slash);
}

function joinDefaultPath(directory, filename) {
  const dir = String(directory || "").trim();
  if (!dir) return filename;
  const clean = dir.replace(/[\\/]+$/, "");
  return `${clean}\\${filename}`;
}

function normalizeColumnName(value) {
  return String(value || "").trim();
}

function mappingColumnsSignature(columns = []) {
  return columns.map((c) => normalizeColumnName(c).toLowerCase()).join("|");
}

function buildMappingPresetKey(f1Columns = [], f2Columns = []) {
  return `f1:${mappingColumnsSignature(f1Columns)}::f2:${mappingColumnsSignature(f2Columns)}`;
}

function readMappingPresets() {
  try {
    const raw = localStorage.getItem(MAPPING_PRESETS_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeMappingPresets(presets) {
  localStorage.setItem(MAPPING_PRESETS_STORAGE_KEY, JSON.stringify(presets || {}));
}

function sanitizeMappingsForColumns(mappings, f1Columns, f2Columns) {
  const f1Set = new Set((f1Columns || []).map((c) => normalizeColumnName(c)));
  const f2Set = new Set((f2Columns || []).map((c) => normalizeColumnName(c)));
  const source = Array.isArray(mappings) ? mappings : [];
  const out = [];
  for (const row of source) {
    const f1 = normalizeColumnName(row?.f1_col);
    const f2 = normalizeColumnName(row?.f2_col);
    if (!f1 || !f2) {
      continue;
    }
    if (!f1Set.has(f1) || !f2Set.has(f2)) {
      continue;
    }
    out.push({
      id: `${f1}-${f2}-${Math.random().toString(36).slice(2, 6)}`,
      use: row?.use !== false,
      col_type: row?.col_type === "key" ? "key" : "value",
      label: row?.label || f1 || f2 || "Column",
      f1_col: f1,
      f2_col: f2,
      match_type: row?.match_type || "text",
      tolerance: Number(row?.tolerance || 0)
    });
  }
  return out;
}

function mappingsCompatibleWithColumns(mappings, f1Columns, f2Columns) {
  if (!Array.isArray(mappings) || mappings.length === 0) {
    return false;
  }
  const f1Set = new Set((f1Columns || []).map((c) => normalizeColumnName(c)));
  const f2Set = new Set((f2Columns || []).map((c) => normalizeColumnName(c)));
  return mappings.every((row) => f1Set.has(normalizeColumnName(row?.f1_col)) && f2Set.has(normalizeColumnName(row?.f2_col)));
}

function buildBackendMappingPayload(state) {
  const f1 = state.files.f1;
  const f2 = state.files.f2;
  if (!f1.fileId || !f2.fileId) {
    return null;
  }
  const cleaned = sanitizeMappingsForColumns(
    state.mappings,
    f1.columns || [],
    f2.columns || []
  )
    .filter((row) => row.use !== false)
    .map((row) => ({
      use: row.use !== false,
      col_type: row.col_type === "key" ? "key" : "value",
      label: row.label || row.f1_col || row.f2_col || "Column",
      f1_col: row.f1_col,
      f2_col: row.f2_col,
      match_type: row.match_type || "text",
      tolerance: Number(row.tolerance || 0)
    }));
  if (cleaned.length === 0) {
    return null;
  }
  return {
    f1_file_id: f1.fileId,
    f2_file_id: f2.fileId,
    brand_name: state.brandName || "",
    f1_columns: f1.columns || [],
    f2_columns: f2.columns || [],
    mappings: cleaned
  };
}

function mergeResultIds(rows = [], refreshedRows = []) {
  return rows.map((row, index) => {
    if (row?.result_id) {
      return row;
    }
    const resultId = refreshedRows[index]?.result_id;
    return resultId ? { ...row, result_id: resultId } : row;
  });
}

export const useAppStore = create((set, get) => ({
  activeTab: "files",
  version: "v1.0.0",
  brandName: "",
  files: {
    f1: blankFileState(),
    f2: blankFileState()
  },
  options: { ...DEFAULT_OPTIONS },
  mappings: [],
  currentMappingPresetKey: "",
  ai: {
    suggestions: [],
    tolerances: {},
    toleranceTable: [],
    toleranceSessions: 0,
    stats: {
      sessions: 0,
      brands: 0,
      accuracy: null,
      last_trained: null
    }
  },
  match: {
    jobId: "",
    status: "idle",
    progress: 0,
    message: "",
    rows: [],
    stats: {},
    sessionId: null,
    mappings: []
  },
  resultsUI: {
    filter: "All",
    matchRemarkFilter: "All",
    search: "",
    searchColumn: "all",
    selectedRow: null
  },
  logs: [newLog("INFO", "FileMatcher initialized")],

  setActiveTab: (activeTab) => set({ activeTab }),
  setBrandName: (brandName) => {
    set({ brandName });
    const state = get();
    if (state.files.f1.loaded && state.files.f2.loaded) {
      void get().fetchAISuggestions();
    }
  },
  setOption: (key, value) =>
    set((state) => ({
      options: {
        ...state.options,
        [key]: value
      }
    })),
  setResultsFilter: (filter) =>
    set((state) => ({ resultsUI: { ...state.resultsUI, filter } })),
  setResultsMatchRemarkFilter: (matchRemarkFilter) =>
    set((state) => ({ resultsUI: { ...state.resultsUI, matchRemarkFilter } })),
  setResultsSearch: (search) =>
    set((state) => ({ resultsUI: { ...state.resultsUI, search } })),
  setResultsSearchColumn: (searchColumn) =>
    set((state) => ({ resultsUI: { ...state.resultsUI, searchColumn } })),
  setSelectedResultRow: (selectedRow) =>
    set((state) => ({ resultsUI: { ...state.resultsUI, selectedRow } })),

  addLog: (level, message) =>
    set((state) => ({
      logs: [newLog(level, message), ...state.logs].slice(0, 400)
    })),

  setMappings: (mappings) => {
    set({ mappings });
    get().scheduleBackendMappingSave();
  },
  resetMappings: () => {
    set({ mappings: [] });
    lastBackendMappingSignature = "";
  },
  applySavedMappingPreset: () => {
    const state = get();
    const f1Columns = state.files.f1.columns || [];
    const f2Columns = state.files.f2.columns || [];
    if (f1Columns.length === 0 || f2Columns.length === 0) {
      return false;
    }
    const presetKey = buildMappingPresetKey(f1Columns, f2Columns);
    const presets = readMappingPresets();
    const saved = presets[presetKey];
    if (!saved || !Array.isArray(saved.mappings)) {
      return false;
    }
    const cleaned = sanitizeMappingsForColumns(saved.mappings, f1Columns, f2Columns);
    if (cleaned.length === 0) {
      return false;
    }
    set({ mappings: cleaned, currentMappingPresetKey: presetKey });
    get().addLog("SUCCESS", `Loaded saved column mapping (${cleaned.length} rows)`);
    return true;
  },
  saveMappingPresetForCurrentFiles: () => {
    const state = get();
    const f1Columns = state.files.f1.columns || [];
    const f2Columns = state.files.f2.columns || [];
    if (f1Columns.length === 0 || f2Columns.length === 0 || state.mappings.length === 0) {
      return false;
    }
    const presetKey = buildMappingPresetKey(f1Columns, f2Columns);
    const cleaned = sanitizeMappingsForColumns(state.mappings, f1Columns, f2Columns);
    if (cleaned.length === 0) {
      return false;
    }
    const presets = readMappingPresets();
    presets[presetKey] = {
      updated_at: new Date().toISOString(),
      mappings: cleaned
    };
    writeMappingPresets(presets);
    set({ currentMappingPresetKey: presetKey });
    return true;
  },

  scheduleBackendMappingSave: () => {
    if (backendMappingSaveTimer) {
      clearTimeout(backendMappingSaveTimer);
    }
    backendMappingSaveTimer = setTimeout(() => {
      backendMappingSaveTimer = null;
      void get().saveMappingsToBackend();
    }, BACKEND_MAPPING_SAVE_DEBOUNCE_MS);
  },

  saveMappingsToBackend: async (options = {}) => {
    const payload = buildBackendMappingPayload(get());
    if (!payload) {
      return false;
    }

    const signature = JSON.stringify(payload);
    if (signature === lastBackendMappingSignature) {
      return true;
    }
    if (backendMappingSaveInFlight) {
      get().scheduleBackendMappingSave();
      return false;
    }

    backendMappingSaveInFlight = true;
    try {
      const result = await api.saveMappings(payload);
      lastBackendMappingSignature = signature;
      if (options?.logSuccess) {
        get().addLog("SUCCESS", `Backend master mapping saved (${result.saved || 0} rows)`);
      }
      return true;
    } catch (error) {
      get().addLog("WARNING", `Backend master mapping save failed: ${error.message}`);
      return false;
    } finally {
      backendMappingSaveInFlight = false;
    }
  },

  addMappingRow: () =>
    set((state) => ({
      mappings: [
        ...state.mappings,
        {
          id: `manual-${Date.now()}`,
          use: true,
          col_type: "value",
          label: "New Column",
          f1_col: "",
          f2_col: "",
          match_type: "text",
          tolerance: 0
        }
      ]
    })),
  addMappingRowWithType: (colType = "value") =>
    set((state) => ({
      mappings: [
        ...state.mappings,
        {
          id: `manual-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          use: true,
          col_type: colType,
          label: colType === "key" ? "New Key" : "New Value",
          f1_col: "",
          f2_col: "",
          match_type: colType === "key" ? "text" : "number",
          tolerance: 0
        }
      ]
    })),
  addKeyMappingRow: () => get().addMappingRowWithType("key"),
  addValueMappingRow: () => get().addMappingRowWithType("value"),
  removeMappingRow: (id) => {
    set((state) => ({
      mappings: state.mappings.filter((x) => x.id !== id)
    }));
    get().scheduleBackendMappingSave();
  },
  removeMappingsByIds: (ids) => {
    set((state) => ({
      mappings: state.mappings.filter((x) => !ids.includes(x.id))
    }));
    get().scheduleBackendMappingSave();
  },
  patchMappingRow: (id, patch) => {
    set((state) => ({
      mappings: state.mappings.map((x) => (x.id === id ? { ...x, ...patch } : x))
    }));
    get().scheduleBackendMappingSave();
  },

  loadFileForSide: async (side, file) => {
    const { addLog, refreshPreviewForSide, fetchAISuggestions, applySavedMappingPreset } = get();
    const prevFileId = get().files[side].fileId;
    try {
      addLog("INFO", `Uploading ${side === "f1" ? "Brand" : "EssGee"} file: ${file.name}`);
      const data = await api.loadFile(file);
      set((state) => ({
        files: {
          ...state.files,
          [side]: {
            ...state.files[side],
            fileId: data.file_id,
            filename: data.filename,
            fileName: data.filename,
            loaded: true,
            sheets: data.sheets || [],
            sheet: (data.sheets || [])[0] || "",
            headerRow: 0,
            rowCount: data.row_count || 0,
            fileSize: data.file_size || 0,
            columns: data.columns || [],
            previewRows: data.rows || []
          }
        }
      }));
      if (prevFileId && prevFileId !== data.file_id) {
        set({ mappings: [], currentMappingPresetKey: "" });
        void api.deleteFile(prevFileId).catch((error) => {
          addLog("WARNING", `Old temp upload cleanup failed: ${error.message}`);
        });
      }
      const guessedQty = (data.columns || []).find((c) => looksLikeQtyColumn(c));
      if (guessedQty) {
        set((state) => ({
          options: {
            ...state.options,
            ...(side === "f1" ? { qty_f1_col: state.options.qty_f1_col || guessedQty } : {}),
            ...(side === "f2" ? { qty_f2_col: state.options.qty_f2_col || guessedQty } : {})
          }
        }));
      }
      addLog("SUCCESS", `${side === "f1" ? "Brand" : "EssGee"} file uploaded (${data.row_count} rows)`);
      if (!data.columns || data.columns.length === 0) {
        await refreshPreviewForSide(side);
      }

      const state = get();
      if (state.files.f1.loaded && state.files.f2.loaded) {
        const usedPreset = applySavedMappingPreset();
        if (!usedPreset && state.mappings.length > 0) {
          set({ mappings: [] });
        }
        void fetchAISuggestions();
      }
    } catch (error) {
      addLog("ERROR", `Upload failed: ${error.message}`);
      throw error;
    }
  },

  updateFileConfig: async (side, patch, options = {}) => {
    const immediate = Boolean(options?.immediate);
    set((state) => ({
      files: {
        ...state.files,
        [side]: {
          ...state.files[side],
          ...patch
        }
      }
    }));
    if (previewTimers[side]) {
      clearTimeout(previewTimers[side]);
    }
    if (immediate) {
      void get().refreshPreviewForSide(side);
      return;
    }
    previewTimers[side] = setTimeout(() => {
      void get().refreshPreviewForSide(side);
    }, PREVIEW_DEBOUNCE_MS);
  },

  refreshPreviewForSide: async (side) => {
    const state = get();
    const sideState = state.files[side];
    if (!sideState.fileId) {
      return;
    }
    try {
      const data = await api.getPreview({
        file_id: sideState.fileId,
        sheet: sideState.sheet || undefined,
        header_row: Number(sideState.headerRow || 0)
      });
      set((s) => ({
        files: {
          ...s.files,
          [side]: {
            ...s.files[side],
            columns: data.columns || [],
            previewRows: data.rows || [],
            rowCount: data.row_count || 0
          }
        }
      }));

      const qtyGuess = (data.columns || []).find((c) =>
        looksLikeQtyColumn(c)
      );
      if (qtyGuess) {
        set((s) => ({
          options: {
            ...s.options,
            ...(side === "f1" ? { qty_f1_col: s.options.qty_f1_col || qtyGuess } : {}),
            ...(side === "f2" ? { qty_f2_col: s.options.qty_f2_col || qtyGuess } : {})
          }
        }));
      }
    } catch (error) {
      get().addLog("ERROR", `Preview failed: ${error.message}`);
    }
  },

  fetchAISuggestions: async () => {
    if (suggestionsInFlight) {
      return;
    }
    const state = get();
    if (!state.files.f1.fileId || !state.files.f2.fileId) {
      return;
    }
    suggestionsInFlight = true;
    try {
      const response = await api.suggestMappings({
        f1: state.files.f1.fileId,
        f2: state.files.f2.fileId,
        brand: state.brandName || undefined
      });
      const suggestions = response.suggestions || [];
      set((s) => ({
        ai: {
          ...s.ai,
          suggestions
        }
      }));
      get().addLog("SUCCESS", `AI auto-read complete (${suggestions.length} mapping suggestions)`);

      const live = get();
      const hasCompatibleMappings = mappingsCompatibleWithColumns(
        live.mappings,
        live.files.f1.columns || [],
        live.files.f2.columns || []
      );

      if (suggestions.length > 0 && !hasCompatibleMappings) {
        const mapped = suggestions.map((x) => {
          const row = mappingFromSuggestion(x);
          row.col_type = x.type || tryAutoType(x.label);
          return row;
        });
        set({ mappings: mapped });
        get().addLog("INFO", "Auto-filled column configuration from AI history");
        get().saveMappingPresetForCurrentFiles();
      }

      if (state.brandName) {
        await get().fetchTolerances();
        get().applyLearnedTolerances();
      }
    } catch (error) {
      get().addLog("ERROR", `Mapping suggestion failed: ${error.message}`);
    } finally {
      suggestionsInFlight = false;
    }
  },

  applySuggestions: (minConfidence = 0) => {
    const suggestions = get().ai.suggestions;
    const mappings = suggestions
      .filter((x) => Number(x.confidence || 0) >= minConfidence)
      .map((x) => {
        const row = mappingFromSuggestion(x);
        row.col_type = x.type || tryAutoType(x.label);
        return row;
      });
      set({ mappings });
      get().saveMappingPresetForCurrentFiles();
      void get().saveMappingsToBackend({ logSuccess: true });
      get().addLog("SUCCESS", `Applied ${mappings.length} suggested mappings`);
  },

  fetchTolerances: async () => {
    const brand = get().brandName;
    if (!brand) {
      get().addLog("WARNING", "Enter brand name before fetching learned tolerances");
      return;
    }
    try {
      const data = await api.getTolerances(brand);
      set((state) => ({
        ai: {
          ...state.ai,
          tolerances: data.tolerances || {},
          toleranceSessions: Number(data.sessions || 0),
          toleranceTable: data.table || []
        }
      }));
      get().addLog("SUCCESS", `Loaded learned tolerances for ${brand}`);
    } catch (error) {
      get().addLog("ERROR", `Tolerance learning failed: ${error.message}`);
    }
  },

  applyLearnedTolerances: () => {
    const tolerances = get().ai.tolerances;
    set((state) => ({
      mappings: state.mappings.map((m) => {
        if (Object.prototype.hasOwnProperty.call(tolerances, m.label)) {
          return { ...m, tolerance: Number(tolerances[m.label]) };
        }
        return m;
      })
    }));
    get().scheduleBackendMappingSave();
    get().addLog("SUCCESS", "Applied learned tolerances");
  },

  saveConfigToLocal: () => {
    try {
      const state = get();
      const payload = {
        brandName: state.brandName || "",
        mappings: state.mappings || [],
        options: state.options || {}
      };
      localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(payload));
      get().saveMappingPresetForCurrentFiles();
      void get().saveMappingsToBackend({ logSuccess: true });
      get().addLog("SUCCESS", "Configuration saved");
    } catch (error) {
      get().addLog("ERROR", `Save config failed: ${error.message}`);
    }
  },

  loadConfigFromLocal: () => {
    try {
      const raw = localStorage.getItem(CONFIG_STORAGE_KEY);
      if (!raw) {
        get().addLog("WARNING", "No saved config found");
        return;
      }
      const parsed = JSON.parse(raw);
      const state = get();
      const presetApplied = get().applySavedMappingPreset();
      const cleanedLoadedMappings = sanitizeMappingsForColumns(
        Array.isArray(parsed.mappings) ? parsed.mappings : state.mappings,
        state.files.f1.columns || [],
        state.files.f2.columns || []
      );
      set({
        brandName: parsed.brandName || state.brandName,
        mappings: presetApplied
          ? get().mappings
          : (cleanedLoadedMappings.length > 0 ? cleanedLoadedMappings : state.mappings),
        options: {
          ...state.options,
          ...(parsed.options || {})
        }
      });
      get().scheduleBackendMappingSave();
      get().addLog("SUCCESS", "Configuration loaded");
    } catch (error) {
      get().addLog("ERROR", `Load config failed: ${error.message}`);
    }
  },

  resetConfigDefaults: () => {
    set({
      options: { ...DEFAULT_OPTIONS },
      mappings: []
    });
    get().addLog("INFO", "Configuration reset to defaults");
  },

  runMatch: async () => {
    if (matchRunInFlight) {
      get().addLog("WARNING", "Match is already running. Please wait.");
      return;
    }

    const state = get();
    if (!state.files.f1.fileId || !state.files.f2.fileId) {
      get().addLog("ERROR", "Please load both files first");
      return;
    }

    const usableMappings = state.mappings.filter((m) => m.use);
    if (usableMappings.length === 0) {
      get().addLog("ERROR", "Please configure at least one mapping");
      return;
    }

    const key_columns = usableMappings
      .filter((m) => m.col_type === "key")
      .map((m) => ({
        f1_col: m.f1_col,
        f2_col: m.f2_col,
        label: m.label,
        col_type: m.col_type,
        match_type: m.match_type,
        tolerance: Number(m.tolerance || 0)
      }));
    const value_columns = usableMappings
      .filter((m) => m.col_type !== "key")
      .map((m) => ({
        f1_col: m.f1_col,
        f2_col: m.f2_col,
        label: m.label,
        col_type: "value",
        match_type: m.match_type,
        tolerance: Number(m.tolerance || 0)
      }));

    if (key_columns.length === 0) {
      get().addLog("ERROR", "At least one Key mapping is required");
      return;
    }

    try {
      matchRunInFlight = true;
      get().saveMappingPresetForCurrentFiles();
      await get().saveMappingsToBackend();
      get().addLog("INFO", "Starting match job");
      set((s) => ({
        match: {
          ...s.match,
          status: "running",
          progress: 0,
          message: "Starting...",
          rows: [],
          stats: {},
          sessionId: null,
          mappings: [...key_columns, ...value_columns]
        }
      }));

      const job = await api.runMatch({
        f1_file_id: state.files.f1.fileId,
        f2_file_id: state.files.f2.fileId,
        brand_name: state.brandName || "Unknown",
        f1_sheet: state.files.f1.sheet,
        f2_sheet: state.files.f2.sheet,
        f1_header_row: Number(state.files.f1.headerRow || 0),
        f2_header_row: Number(state.files.f2.headerRow || 0),
        key_columns,
        value_columns,
        fuzzy_enabled: state.options.fuzzy_enabled,
        fuzzy_threshold: Number(state.options.fuzzy_threshold || 85),
        qty_expansion_enabled: state.options.qty_expansion_enabled,
        qty_f1_col: state.options.qty_f1_col || undefined,
        qty_f2_col: state.options.qty_f2_col || undefined,
        case_insensitive: state.options.case_insensitive,
        trim: state.options.trim
      });

      set((s) => ({
        match: {
          ...s.match,
          jobId: job.job_id
        }
      }));

      let done = false;
      while (!done) {
        const status = await api.getMatchStatus(job.job_id);
        set((s) => ({
          match: {
            ...s.match,
            status: status.status || "running",
            progress: Number(status.progress || 0),
            message: status.message || ""
          }
        }));

        if (status.status === "done") {
          done = true;
          break;
        }
        if (status.status === "error") {
          throw new Error(status.message || "Match failed");
        }
        await sleep(1000);
      }

      const result = await api.getMatchResult(job.job_id);
      const resultRows = result.rows || [];
      set((s) => ({
        match: {
          ...s.match,
          status: "done",
          progress: 100,
          message: "Done",
          rows: resultRows,
          stats: result.stats || {},
          sessionId: result.session_id,
          mappings: [
            ...(result.key_mappings || key_columns),
            ...(result.value_mappings || value_columns)
          ]
        },
        activeTab: "results"
      }));
      get().addLog("SUCCESS", "Match completed");
      if (resultRows.some((row) => !row?.result_id)) {
        setTimeout(async () => {
          for (let attempt = 0; attempt < RESULT_ID_REFRESH_ATTEMPTS; attempt += 1) {
            if (attempt > 0) {
              await sleep(RESULT_ID_REFRESH_DELAY_MS);
            }
            if (get().match.jobId !== job.job_id) {
              return;
            }
            try {
              const history = await api.getMatchStatus(job.job_id);
              if (history.history_status !== "saved") {
                if (history.history_status === "error") {
                  return;
                }
                continue;
              }
              const refreshed = await api.getMatchResult(job.job_id);
              const refreshedRows = refreshed.rows || [];
              if (!refreshedRows.some((row) => row?.result_id)) {
                continue;
              }
              set((s) => {
                if (s.match.jobId !== job.job_id) {
                  return {};
                }
                return {
                  match: {
                    ...s.match,
                    rows: mergeResultIds(s.match.rows, refreshedRows)
                  }
                };
              });
              return;
            } catch {
              return;
            }
          }
        }, RESULT_ID_REFRESH_DELAY_MS);
      }
      void get().loadAIStats();
    } catch (error) {
      set((s) => ({
        match: {
          ...s.match,
          status: "error",
          message: error.message
        }
      }));
      get().addLog("ERROR", `Run match failed: ${error.message}`);
    } finally {
      matchRunInFlight = false;
    }
  },

  markAsActuallyMatched: async (row) => {
    const resultId = row?.result_id;
    if (!resultId) {
      get().addLog("WARNING", "This row has no result_id to save correction");
      return;
    }
    try {
      await api.userCorrection({
        result_id: Number(resultId),
        correct_status: "Matched"
      });
      get().addLog("SUCCESS", "Saved user correction");
      set((state) => ({
        match: {
          ...state.match,
          rows: state.match.rows.map((r) =>
            r.result_id === resultId ? { ...r, match_status: "Match", match_remark: "Match", user_corrected: 1 } : r
          )
        }
      }));
    } catch (error) {
      get().addLog("ERROR", `Failed to save correction: ${error.message}`);
    }
  },

  exportReport: async (type, options = {}) => {
    if (exportRunInFlight) {
      get().addLog("WARNING", "Export already running. Please wait.");
      return;
    }

    const state = get();
    if (!state.match.sessionId) {
      get().addLog("ERROR", "No session to export");
      return;
    }
    const exportFilters = options?.filtered
      ? {
          filter: state.resultsUI.filter,
          search: state.resultsUI.search,
          searchColumn: state.resultsUI.searchColumn
        }
      : {};

    try {
      const electronApi = window?.electron;
      let selectedPath = "";
      if (electronApi?.saveFileDialog) {
        const savedDir = localStorage.getItem(EXPORT_DIR_STORAGE_KEY) || "";
        const defaultName = buildExportFilename(type);
        const suggestedPath = joinDefaultPath(savedDir, defaultName);
        selectedPath = await electronApi.saveFileDialog(suggestedPath);
        if (!selectedPath) {
          get().addLog("WARNING", "Export canceled by user");
          return;
        }
        const selectedDir = directoryFromPath(selectedPath);
        if (selectedDir) {
          localStorage.setItem(EXPORT_DIR_STORAGE_KEY, selectedDir);
        }
      }

      exportRunInFlight = true;
      get().addLog(
        "INFO",
        `Starting export (${type}${options?.filtered ? " filtered" : ""})${selectedPath ? ` to ${selectedPath}` : "..."}`
      );

      set((s) => ({
        match: {
          ...s.match,
          status: "running",
          progress: 0,
          message: `Exporting ${type}...`,
          rows: s.match.rows,
          stats: s.match.stats
        }
      }));

      let start = null;
      try {
        start =
          type === "full"
            ? await api.exportFull(state.match.sessionId, selectedPath, exportFilters)
            : type === "summary"
              ? await api.exportSummary(state.match.sessionId, selectedPath, exportFilters)
              : await api.exportMismatch(state.match.sessionId, selectedPath, exportFilters);
      } catch (startError) {
        const msg = String(startError?.message || "");
        if (type === "summary" && msg.includes("404")) {
          throw new Error(
            "Summary export API not loaded (old backend running). Close app, stop old backend on port 8787, then restart."
          );
        }
        throw startError;
      }

      const exportJobId = start.export_job_id || start.exportJobId;
      if (!exportJobId) {
        throw new Error("Export job id missing from backend response");
      }

      let done = false;
      let lastStageMessage = "";
      while (!done) {
        const st = await api.getExportStatus(exportJobId);
        set((s) => ({
          match: {
            ...s.match,
            status: st.status || "running",
            progress: Number(st.progress || 0),
            message: st.message || "Exporting..."
          }
        }));
        const stageMsg = String(st.message || "").trim();
        if (stageMsg && stageMsg !== lastStageMessage) {
          lastStageMessage = stageMsg;
          get().addLog("INFO", `Export stage: ${stageMsg} (${Number(st.progress || 0)}%)`);
        }

        if (st.status === "done") {
          done = true;
          break;
        }
        if (st.status === "error") {
          throw new Error(st.message || "Export failed");
        }
        await sleep(500);
      }

      const res = await api.getExportResult(exportJobId);
      // Backend stable response: { file_id, filename, file_path }
      const info = res && res.file_id ? res : res && res.result && res.result.file_id ? res.result : res;

      const exportedFilename = info?.filename || "FileMatcher_Report.xlsx";
      const exportedFilePath = info?.file_path || "";
      const exportedFileId = info?.file_id;
      const finalPath = exportedFilePath || selectedPath;

      if (finalPath) {
        get().addLog("SUCCESS", `Saved: ${finalPath}`);
      } else if (exportedFileId) {
        // Browser fallback: backend file id download
        const blob = await api.downloadBlob(exportedFileId);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = exportedFilename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } else {
        throw new Error(`Export completed but file info missing. Got: ${JSON.stringify(res)}`);
      }

      get().addLog("SUCCESS", `Export complete: ${exportedFilename}`);

      set((s) => ({
        match: {
          ...s.match,
          status: "done",
          progress: 100,
          message: "Export done"
        }
      }));
    } catch (error) {
      get().addLog("ERROR", `Export failed: ${error.message}`);
      set((s) => ({
        match: {
          ...s.match,
          status: "error",
          message: `Export failed: ${error.message}`
        }
      }));
    } finally {
      exportRunInFlight = false;
    }
  },


  loadAIStats: async () => {
    try {
      const stats = await api.getAIStats();
      set((state) => ({
        ai: {
          ...state.ai,
          stats
        }
      }));
    } catch (error) {
      get().addLog("WARNING", `AI stats unavailable: ${error.message}`);
    }
  }
}));
