const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8787";

async function parseResponse(res) {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const json = await res.json();
      detail = json.detail || JSON.stringify(json);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function loadFile(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/load-file`, {
    method: "POST",
    body: form
  });
  return parseResponse(res);
}

export async function getPreview({ file_id, sheet, header_row }) {
  const res = await fetch(`${API_BASE}/api/get-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_id, sheet, header_row })
  });
  return parseResponse(res);
}

export async function deleteFile(fileId) {
  const res = await fetch(`${API_BASE}/api/files/${fileId}`, {
    method: "DELETE"
  });
  return parseResponse(res);
}

export async function suggestMappings({ f1, f2, brand }) {
  const params = new URLSearchParams({ f1, f2 });
  if (brand) {
    params.set("brand", brand);
  }
  const res = await fetch(`${API_BASE}/api/ai/suggest-mappings?${params.toString()}`);
  return parseResponse(res);
}

export async function saveMappings(payload) {
  const res = await fetch(`${API_BASE}/api/ai/save-mappings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return parseResponse(res);
}

export async function getTolerances(brand) {
  const params = new URLSearchParams({ brand });
  const res = await fetch(`${API_BASE}/api/ai/tolerances?${params.toString()}`);
  return parseResponse(res);
}

export async function getAIPrediction({ f1, f2, brand }) {
  const params = new URLSearchParams({ f1, f2 });
  if (brand) {
    params.set("brand", brand);
  }
  const res = await fetch(`${API_BASE}/api/ai/prediction?${params.toString()}`);
  return parseResponse(res);
}

export async function runMatch(payload) {
  const res = await fetch(`${API_BASE}/api/run-match`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return parseResponse(res);
}

export async function getMatchStatus(jobId) {
  const res = await fetch(`${API_BASE}/api/match-status/${jobId}`);
  return parseResponse(res);
}

export async function getMatchResult(jobId) {
  const res = await fetch(`${API_BASE}/api/match-result/${jobId}`);
  return parseResponse(res);
}

export async function userCorrection(payload) {
  const res = await fetch(`${API_BASE}/api/user-correction`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return parseResponse(res);
}

function exportPayload(sessionId, outputPath, filters = {}) {
  return {
    session_id: sessionId,
    output_path: outputPath || null,
    filter: filters.filter || null,
    search: filters.search || null,
    search_column: filters.searchColumn || filters.search_column || null
  };
}

export async function exportFull(sessionId, outputPath, filters = {}) {
  const res = await fetch(`${API_BASE}/api/export/full`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(exportPayload(sessionId, outputPath, filters))
  });
  return parseResponse(res);
}

export async function exportMismatch(sessionId, outputPath, filters = {}) {
  const res = await fetch(`${API_BASE}/api/export/mismatch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(exportPayload(sessionId, outputPath, filters))
  });
  return parseResponse(res);
}

export async function exportSummary(sessionId, outputPath, filters = {}) {
  const res = await fetch(`${API_BASE}/api/export/summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(exportPayload(sessionId, outputPath, filters))
  });
  return parseResponse(res);
}

export async function getExportStatus(exportJobId) {
  const res = await fetch(`${API_BASE}/api/export-status/${exportJobId}`);
  return parseResponse(res);
}

export async function getExportResult(exportJobId) {
  const res = await fetch(`${API_BASE}/api/export-result/${exportJobId}`);
  return parseResponse(res);
}


export async function getAIStats() {
  const res = await fetch(`${API_BASE}/api/ai/stats`);
  return parseResponse(res);
}

export function downloadUrl(fileId) {
  return `${API_BASE}/api/download/${fileId}`;
}

export async function downloadBlob(fileId) {
  const res = await fetch(downloadUrl(fileId));
  if (!res.ok) {
    throw new Error(`Download failed: ${res.status}`);
  }
  return res.blob();
}
