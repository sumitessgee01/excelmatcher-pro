from __future__ import annotations

import argparse
import re
import tempfile
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import uvicorn
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from .core.exporter import ExcelExporter
    from .core.loader import (
        SUPPORTED_EXTENSIONS,
        SUPPORTED_EXTENSIONS_TEXT,
        fast_row_count,
        list_sheets,
        load_excel,
        preview_rows,
        _to_json_safe,
    )

    from .core.matcher import MatchConfig, MatchingEngine
    from .core.remarks_engine import apply_remarks
    from .core.ai.column_suggester import ColumnSuggester
    from .core.ai.memory_db import MemoryDB
    from .core.ai.smart_remarks import SmartRemarks
    from .core.ai.tolerance_learner import ToleranceLearner
    from .core.ai.trainer import MatchOutcomeTrainer
except ImportError:  # pragma: no cover - allows running as `python backend/server.py`
    from core.exporter import ExcelExporter
    from core.loader import (
        SUPPORTED_EXTENSIONS,
        SUPPORTED_EXTENSIONS_TEXT,
        fast_row_count,
        list_sheets,
        load_excel,
        preview_rows,
        _to_json_safe,
    )

    from core.matcher import MatchConfig, MatchingEngine
    from core.remarks_engine import apply_remarks
    from core.ai.column_suggester import ColumnSuggester
    from core.ai.memory_db import MemoryDB
    from core.ai.smart_remarks import SmartRemarks
    from core.ai.tolerance_learner import ToleranceLearner
    from core.ai.trainer import MatchOutcomeTrainer


class PreviewRequest(BaseModel):
    file_id: str
    sheet: str | int | None = None
    header_row: int | None = 0


class UserCorrectionRequest(BaseModel):
    result_id: int
    correct_status: str


class ExportRequest(BaseModel):
    session_id: int
    output_path: str | None = None
    filter: str | None = None
    search: str | None = None
    search_column: str | None = None


class MappingSaveRequest(BaseModel):
    f1_file_id: str
    f2_file_id: str
    brand_name: str | None = None
    f1_columns: list[str] = []
    f2_columns: list[str] = []
    mappings: list[dict[str, Any]] = []


class AppContext:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._upload_tmp = tempfile.TemporaryDirectory(prefix="excelmatcher_uploads_")
        self.upload_dir = Path(self._upload_tmp.name)
        self.export_dir = data_dir / "exports"
        self.export_dir.mkdir(parents=True, exist_ok=True)

        self.db = MemoryDB(data_dir / "learning.db")
        self.suggester = ColumnSuggester(self.db)
        self.tolerance_learner = ToleranceLearner(self.db)
        self.smart_remarks = SmartRemarks(self.db)
        self.trainer = MatchOutcomeTrainer(self.db)
        self.exporter = ExcelExporter()

        self.files: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.results: dict[str, dict[str, Any]] = {}
        self.results_by_session: dict[int, dict[str, Any]] = {}
        self.df_cache: dict[tuple[str, str, int], pd.DataFrame] = {}
        self.suggestion_cache: dict[str, list[dict[str, Any]]] = {}
        self.lock = threading.Lock()

    def cleanup(self) -> None:
        self._upload_tmp.cleanup()



def create_app(data_dir: Path) -> FastAPI:
    app = FastAPI(title="FileMatcher Local API", version="1.0.0")
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    ctx = AppContext(data_dir)
    app.state.ctx = ctx

    @app.on_event("shutdown")
    def cleanup_temp_uploads() -> None:
        ctx.cleanup()

    @app.middleware("http")
    async def add_cache_headers(request: Request, call_next):
        response = await call_next(request)
        # Cache preview and metadata endpoints for 5 minutes
        if "/api/get-preview" in request.url.path or "/api/load-file" in request.url.path:
            response.headers["Cache-Control"] = "public, max-age=300"
        # Cache AI predictions for 10 minutes
        elif "/api/ai/" in request.url.path:
            response.headers["Cache-Control"] = "public, max-age=600"
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/load-file")
    async def api_load_file(file: UploadFile = File(...)) -> dict[str, Any]:

        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Supported: {SUPPORTED_EXTENSIONS_TEXT}",
            )

        file_id = uuid.uuid4().hex
        dest = ctx.upload_dir / f"{file_id}{suffix}"
        try:
            with dest.open("wb") as handle:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
        finally:
            await file.close()

        try:
            # Fast load: headers + first 5 rows + row count
            sheets = list_sheets(dest)
            default_sheet = sheets[0] if sheets else None
            df_preview = load_excel(dest, sheet=default_sheet, header_row=0, nrows=5)
            row_count = fast_row_count(dest, sheet=default_sheet, header_row=0)

            cols = [str(c) for c in df_preview.columns.tolist()]
            rows = preview_rows(df_preview, n=5)
        except Exception as exc:
            if dest.exists():
                dest.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}") from exc

        # Get file size
        file_size = dest.stat().st_size if dest.exists() else 0

        with ctx.lock:
            preview_key = _preview_key(sheets[0] if sheets else None, 0)
            ctx.files[file_id] = {
                "path": str(dest),
                "filename": file.filename,
                "sheets": sheets,
                "row_count": row_count,
                "file_size": file_size,
                "uploaded_at": datetime.now().isoformat(),
                "preview_cache": {
                    preview_key: {
                        "columns": cols,
                        "rows": rows,
                        "row_count": row_count,
                    }
                },
            }
            ctx.suggestion_cache.clear()

        return {
            "file_id": file_id,
            "filename": file.filename,
            "sheets": sheets,
            "row_count": row_count,
            "file_size": file_size,
            "columns": cols,
            "rows": rows,
        }

    @app.post("/api/get-preview")
    def api_get_preview(req: PreviewRequest) -> dict[str, Any]:

        file_info = _get_file_or_404(ctx, req.file_id)
        sheet = req.sheet
        if sheet is None:
            sheet = (file_info.get("sheets") or [None])[0]
        header = int(req.header_row or 0)
        key = _preview_key(sheet, header)

        with ctx.lock:
            cached = (file_info.get("preview_cache") or {}).get(key)
        if cached:
            return cached

        try:
            df = load_excel(file_info["path"], sheet=sheet, header_row=header, nrows=5)
            row_count = int(fast_row_count(file_info["path"], sheet=sheet, header_row=header))
            payload = {
                "columns": [str(c) for c in df.columns.tolist()],
                "rows": preview_rows(df, n=5),
                "row_count": row_count,
            }
            with ctx.lock:
                file_info.setdefault("preview_cache", {})
                file_info["preview_cache"][key] = payload
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Preview failed: {exc}") from exc

        return payload

    @app.delete("/api/files/{file_id}")
    def api_delete_file(file_id: str) -> dict[str, Any]:
        deleted = _delete_uploaded_file(ctx, file_id)
        return {"ok": True, "deleted": deleted}


    @app.get("/api/load-full/{file_id}")
    def api_load_full(
        file_id: str,
        sheet: str | int | None = Query(None),
        header_row: int | None = Query(0),
    ) -> dict[str, Any]:
        """Lazy load full file data with caching headers for performance."""
        file_info = _get_file_or_404(ctx, file_id)
        if sheet is None:
            sheet = (file_info.get("sheets") or [None])[0]
        
        try:
            df_full = load_excel(file_info["path"], sheet=sheet, header_row=header_row, nrows=None)

            
            if isinstance(df_full, tuple):
                # Multiple chunks - concatenate for response
                df_full = pd.concat(df_full, ignore_index=True)
            
            all_rows = df_full.to_dict(orient="records")
            all_rows_safe = []
            for row in all_rows:
                safe_row = {k: _to_json_safe(v) for k, v in row.items()}
                all_rows_safe.append(safe_row)
            
            return {
                "file_id": file_id,
                "sheet": sheet,
                "columns": [str(c) for c in df_full.columns.tolist()],
                "rows": all_rows_safe,
                "total_rows": len(df_full),
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to load full file: {exc}") from exc

    @app.get("/api/ai/suggest-mappings")
    def api_ai_suggest_mappings(
        f1: str = Query(...),
        f2: str = Query(...),
        brand: str | None = Query(None),
    ) -> dict[str, Any]:
        f1_file = _get_file_or_404(ctx, f1)
        f2_file = _get_file_or_404(ctx, f2)
        cache_key = f"{f1}|{f2}|{(brand or '').strip().casefold()}"
        with ctx.lock:
            cached = ctx.suggestion_cache.get(cache_key)
        if cached is not None:
            return {"suggestions": cached}

        df1_cols = _quick_columns(ctx, f1, f1_file)
        df2_cols = _quick_columns(ctx, f2, f2_file)
        suggestions = ctx.suggester.suggest_mappings(
            f1_columns=df1_cols,
            f2_columns=df2_cols,
            brand_name=brand,
        )
        with ctx.lock:
            ctx.suggestion_cache[cache_key] = suggestions
        return {"suggestions": suggestions}

    @app.post("/api/ai/save-mappings")
    def api_ai_save_mappings(req: MappingSaveRequest) -> dict[str, Any]:
        f1_file = _get_file_or_404(ctx, req.f1_file_id)
        f2_file = _get_file_or_404(ctx, req.f2_file_id)
        f1_columns = req.f1_columns or _quick_columns(ctx, req.f1_file_id, f1_file)
        f2_columns = req.f2_columns or _quick_columns(ctx, req.f2_file_id, f2_file)

        saved = ctx.db.save_master_mappings(
            brand_name=req.brand_name,
            f1_columns=f1_columns,
            f2_columns=f2_columns,
            mappings=req.mappings,
        )
        with ctx.lock:
            ctx.suggestion_cache.clear()
        return {"ok": True, **saved}

    @app.get("/api/ai/tolerances")
    def api_ai_tolerances(brand: str = Query(...)) -> dict[str, Any]:
        learned = ctx.tolerance_learner.learn_for_brand(brand)
        return {"tolerances": learned["tolerances"], "sessions": learned["sessions"], "table": learned["table"]}

    @app.get("/api/ai/prediction")
    def api_ai_prediction(
        f1: str = Query(...),
        f2: str = Query(...),
        brand: str | None = Query(None),
    ) -> dict[str, Any]:
        f1_file = _get_file_or_404(ctx, f1)
        _ = _get_file_or_404(ctx, f2)  # keep contract: both files must exist

        sample_sheet = (f1_file.get("sheets") or [None])[0]
        try:
            sample_df = load_excel(f1_file["path"], sheet=sample_sheet, header_row=0, nrows=500)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Prediction sample load failed: {exc}") from exc

        sample_rows = preview_rows(sample_df, n=500)
        resolved_brand = _resolve_brand_name(
            brand_name_input=str(brand or ""),
            brand_df=sample_df,
            key_columns=[],
            value_columns=[],
            brand_filename=str(f1_file.get("filename", "")),
        )

        prediction = ctx.trainer.predict_distribution(resolved_brand, sample_rows)
        prediction["brand"] = resolved_brand
        prediction["samples"] = len(sample_rows)
        prediction["sessions"] = ctx.db.get_brand_session_count(resolved_brand) if resolved_brand else 0
        return prediction

    @app.post("/api/run-match")
    def api_run_match(payload: dict[str, Any]) -> dict[str, str]:
        job_id = uuid.uuid4().hex
        with ctx.lock:
            ctx.jobs[job_id] = {"status": "queued", "progress": 0, "message": "Queued"}

        thread = threading.Thread(target=_run_match_job, args=(ctx, job_id, payload), daemon=True)
        thread.start()
        return {"job_id": job_id}

    @app.get("/api/match-status/{job_id}")
    def api_match_status(job_id: str) -> dict[str, Any]:
        with ctx.lock:
            job = ctx.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.get("/api/match-result/{job_id}")
    def api_match_result(job_id: str) -> dict[str, Any]:
        with ctx.lock:
            result = ctx.results.get(job_id)
            job = ctx.jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.get("status") != "done":
            return {"rows": [], "stats": {}, "session_id": None}
        if not result:
            raise HTTPException(status_code=500, detail="Result missing for completed job")
        return {
            "rows": result["rows"],
            "stats": result["stats"],
            "session_id": result["session_id"],
            "key_mappings": result.get("key_mappings", []),
            "value_mappings": result.get("value_mappings", []),
        }

    @app.post("/api/user-correction")
    def api_user_correction(req: UserCorrectionRequest) -> dict[str, bool]:
        try:
            ctx.db.save_user_correction(req.result_id, req.correct_status)
            ctx.trainer.train_if_needed(force=False)
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to save correction: {exc}") from exc

    @app.post("/api/export/full")
    def api_export_full(req: ExportRequest) -> dict[str, Any]:
        export_job_id = uuid.uuid4().hex
        with ctx.lock:
            ctx.jobs[export_job_id] = {
                "status": "queued",
                "progress": 0,
                "message": "Queued",
                "kind": "export_full",
            }

        thread = threading.Thread(
            target=_run_export_job,
            args=(ctx, export_job_id, req.session_id, "full", req.output_path, req.filter, req.search, req.search_column),
            daemon=True,
        )
        thread.start()
        return {"export_job_id": export_job_id}

    @app.post("/api/export/mismatch")
    def api_export_mismatch(req: ExportRequest) -> dict[str, Any]:
        export_job_id = uuid.uuid4().hex
        with ctx.lock:
            ctx.jobs[export_job_id] = {
                "status": "queued",
                "progress": 0,
                "message": "Queued",
                "kind": "export_mismatch",
            }

        thread = threading.Thread(
            target=_run_export_job,
            args=(ctx, export_job_id, req.session_id, "mismatch", req.output_path, req.filter, req.search, req.search_column),
            daemon=True,
        )
        thread.start()
        return {"export_job_id": export_job_id}

    @app.post("/api/export/summary")
    def api_export_summary(req: ExportRequest) -> dict[str, Any]:
        export_job_id = uuid.uuid4().hex
        with ctx.lock:
            ctx.jobs[export_job_id] = {
                "status": "queued",
                "progress": 0,
                "message": "Queued",
                "kind": "export_summary",
            }

        thread = threading.Thread(
            target=_run_export_job,
            args=(ctx, export_job_id, req.session_id, "summary", req.output_path, req.filter, req.search, req.search_column),
            daemon=True,
        )
        thread.start()
        return {"export_job_id": export_job_id}

    @app.get("/api/export-status/{export_job_id}")
    def api_export_status(export_job_id: str) -> dict[str, Any]:
        with ctx.lock:
            job = ctx.jobs.get(export_job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Export job not found")
        return {
            "status": job.get("status"),
            "progress": job.get("progress", 0),
            "message": job.get("message", ""),
        }

    @app.get("/api/export-result/{export_job_id}")
    def api_export_result(export_job_id: str) -> dict[str, Any]:
        with ctx.lock:
            job = ctx.jobs.get(export_job_id)
            result = ctx.results.get(export_job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Export job not found")
        if job.get("status") != "done":
            return {"result": None}
        if not result:
            # fallback for older/newer shapes
            with ctx.lock:
                result = ctx.results.get(f"export_{export_job_id}")
        if not result:
            raise HTTPException(status_code=500, detail="Export result missing")
        if isinstance(result, dict) and "file_id" in result:
            return result
        return {"result": result}



    @app.get("/api/download/{file_id}")
    def api_download(file_id: str):
        file_info = _get_file_or_404(ctx, file_id)
        path = Path(file_info["path"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        return FileResponse(path, filename=file_info.get("filename") or path.name)

    @app.get("/api/ai/stats")
    def api_ai_stats() -> dict[str, Any]:
        stats = ctx.db.get_ai_stats()
        meta = ctx.trainer._load_metadata()
        model_ready = bool(ctx.trainer.model_path.exists())
        return {
            "sessions": stats.get("sessions", 0),
            "brands": stats.get("brands", 0),
            "accuracy": meta.get("accuracy"),
            "last_trained": meta.get("trained_on_sessions"),
            "model_ready": model_ready,
            "results": stats.get("results", 0),
            "user_corrections": stats.get("user_corrections", 0),
        }

    return app


def _run_export_job(
    ctx: AppContext,
    export_job_id: str,
    session_id: int,
    kind: str,
    output_path: str | None = None,
    export_filter: str | None = None,
    search: str | None = None,
    search_column: str | None = None,
) -> None:
    try:
        _set_job(ctx, export_job_id, status="running", progress=5, message="Building export")

        job_result = _find_result_by_session(ctx, session_id)
        if not job_result:
            raise ValueError("Session result not found in memory")
        job_result = _filter_job_result_for_export(
            job_result,
            export_filter=export_filter,
            search=search,
            search_column=search_column,
        )

        if output_path:
            output = Path(output_path).expanduser().resolve()
            filename = output.name
            if output.suffix.lower() != ".xlsx":
                output = output.with_suffix(".xlsx")
                filename = output.name
        else:
            if kind == "full":
                filename = f"FileMatcher_Full_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            elif kind == "summary":
                filename = f"FileMatcher_Summary_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            else:
                filename = f"FileMatcher_Brand_Mismatch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            output = ctx.export_dir / filename
        _set_job(ctx, export_job_id, status="running", progress=35, message="Writing Excel")

        def export_progress(step: int, msg: str) -> None:
            clipped = max(0, min(100, int(step)))
            mapped = 35 + int(clipped * 0.55)
            _set_job(ctx, export_job_id, status="running", progress=mapped, message=msg)

        brand_df, essgee_df = _resolve_export_frames(job_result, need_essgee=(kind != "mismatch"))
        if export_filter or search:
            brand_df, essgee_df, filtered_rows = _reindex_export_frames_for_rows(
                brand_df=brand_df,
                essgee_df=essgee_df,
                rows=job_result["rows"],
            )
            job_result = {**job_result, "rows": filtered_rows}

        if kind == "full":
            ctx.exporter.export_full(
                output,
                brand_df=brand_df,
                essgee_df=essgee_df,
                rows=job_result["rows"],
                brand_file_name=job_result["brand_file_name"],
                essgee_file_name=job_result["essgee_file_name"],
                value_mappings=job_result.get("value_mappings", []),
                qty_f1_col=job_result.get("qty_f1_col"),
                qty_f2_col=job_result.get("qty_f2_col"),
                progress_callback=export_progress,
            )
        elif kind == "summary":
            ctx.exporter.export_summary(
                output,
                brand_df=brand_df,
                essgee_df=essgee_df,
                rows=job_result["rows"],
                key_mappings=job_result.get("key_mappings", []),
                value_mappings=job_result.get("value_mappings", []),
                brand_file_name=job_result["brand_file_name"],
                essgee_file_name=job_result["essgee_file_name"],
                progress_callback=export_progress,
            )
        else:
            ctx.exporter.export_mismatch_only(
                output,
                brand_df=brand_df,
                rows=job_result["rows"],
                brand_file_name=job_result["brand_file_name"],
                essgee_file_name=job_result["essgee_file_name"],
                progress_callback=export_progress,
            )

        _set_job(ctx, export_job_id, status="running", progress=90, message="Finalizing")
        file_id = _register_generated_file(ctx, output)

        with ctx.lock:
            ctx.results[export_job_id] = {
                "file_id": file_id,
                "filename": filename,
                "file_path": str(output),
            }
            ctx.results[f"export_{export_job_id}"] = ctx.results[export_job_id]


        _set_job(ctx, export_job_id, status="done", progress=100, message="Done")
    except Exception as exc:
        _set_job(ctx, export_job_id, status="error", progress=100, message=f"{exc}")
        with ctx.lock:
            ctx.jobs[export_job_id]["traceback"] = traceback.format_exc()


def _run_match_job(ctx: AppContext, job_id: str, payload: dict[str, Any]) -> None:
    try:
        _set_job(ctx, job_id, status="running", progress=5, message="Loading configuration")

        # Canonical side mapping:
        # F1 = Brand file, F2 = EssGee file.
        f1_id, f2_id = _resolve_brand_essgee_file_ids(payload)
        if not f1_id or not f2_id:
            raise ValueError("Missing file IDs for f1/f2")

        f1_file = _get_file_or_404(ctx, f1_id)
        f2_file = _get_file_or_404(ctx, f2_id)

        # Prefer explicit brand/essgee keys when both are present.
        f1_sheet = payload.get("brand_sheet", payload.get("f1_sheet", 0))
        f2_sheet = payload.get("essgee_sheet", payload.get("f2_sheet", 0))
        f1_header = int(payload.get("brand_header_row", payload.get("f1_header_row", 0)) or 0)
        f2_header = int(payload.get("essgee_header_row", payload.get("f2_header_row", 0)) or 0)

        brand_name_input = str(payload.get("brand_name", payload.get("brand", "")) or "")

        df1 = _load_for_match(ctx, f1_id, f1_file["path"], f1_sheet, f1_header)
        df2 = _load_for_match(ctx, f2_id, f2_file["path"], f2_sheet, f2_header)

        key_columns, value_columns = _extract_mappings(payload)
        brand_name = _resolve_brand_name(
            brand_name_input=brand_name_input,
            brand_df=df1,
            key_columns=key_columns,
            value_columns=value_columns,
            brand_filename=str(f1_file.get("filename", "")),
        )
        
        # Apply learned tolerances for the brand
        learned_tolerances = ctx.tolerance_learner.learn_for_brand(brand_name)
        if learned_tolerances.get("tolerances"):
            value_columns = ctx.tolerance_learner.apply_to_mappings(
                value_columns,
                learned_tolerances["tolerances"]
            )
        
        qty_f1_col, qty_f2_col = _resolve_qty_columns(
            payload=payload,
            key_columns=key_columns,
            value_columns=value_columns,
            df1=df1,
            df2=df2,
        )

        config_dict = {
            "key_columns": key_columns,
            "value_columns": value_columns,
            "fuzzy_enabled": bool(payload.get("fuzzy_enabled", True)),
            "fuzzy_threshold": float(payload.get("fuzzy_threshold", 85.0)),
            "fuzzy_batch_size": int(payload.get("fuzzy_batch_size", 250)),
            "qty_expansion_enabled": bool(payload.get("qty_expansion_enabled", False)),
            "qty_f1_col": qty_f1_col,
            "qty_f2_col": qty_f2_col,
            "case_insensitive": bool(payload.get("case_insensitive", True)),
            "trim": bool(payload.get("trim", True)),
        }

        def progress_cb(progress: int, message: str) -> None:
            mapped = 5 + int(max(0, min(100, progress)) * 0.83)
            _set_job(ctx, job_id, status="running", progress=min(mapped, 88), message=message)

        engine = MatchingEngine(MatchConfig.from_dict(config_dict), progress_callback=progress_cb)
        result = engine.run(df1, df2)
        _set_job(ctx, job_id, status="running", progress=89, message="Building result remarks")
        rows = apply_remarks(result["rows"])
        # Keep remarks simple and business-friendly (no historical/AI analytics text).

        stats = result["stats"]
        _set_job(ctx, job_id, status="running", progress=91, message="Saving match session")
        session_id = ctx.db.save_session(
            brand_file=str(f1_file.get("filename", "brand")),
            essgee_file=str(f2_file.get("filename", "essgee")),
            brand_name=brand_name,
            total_rows=int(stats.get("total", 0)),
            matched=int(stats.get("matched", 0)),
            mismatch=int(stats.get("mismatch", 0)),
            qty_mismatch=int(stats.get("qty_mismatch", 0)),
            not_in_data=int(stats.get("not_in_data", 0)),
        )
        _set_job(ctx, job_id, status="running", progress=93, message="Preparing result table")
        f1_columns_for_history = [str(c) for c in df1.columns.tolist()]
        f2_columns_for_history = [str(c) for c in df2.columns.tolist()]
        with ctx.lock:
            result_payload = {
                "rows": rows,
                "stats": stats,
                "session_id": session_id,
                "brand_file_path": str(f1_file.get("path", "")),
                "essgee_file_path": str(f2_file.get("path", "")),
                "f1_sheet": f1_sheet,
                "f2_sheet": f2_sheet,
                "f1_header_row": f1_header,
                "f2_header_row": f2_header,
                "brand_file_name": str(f1_file.get("filename", "brand.xlsx")),
                "essgee_file_name": str(f2_file.get("filename", "essgee.xlsx")),
                "key_mappings": key_columns,
                "value_mappings": value_columns,
                "qty_f1_col": config_dict["qty_f1_col"],
                "qty_f2_col": config_dict["qty_f2_col"],
            }
            ctx.results[job_id] = result_payload
            ctx.results_by_session[int(session_id)] = result_payload
        # Drop cached full DataFrames for this match to keep memory usage low.
        _clear_df_cache_for_file(ctx, str(f1_id))
        _clear_df_cache_for_file(ctx, str(f2_id))
        _set_job(ctx, job_id, status="done", progress=100, message="Done")
        threading.Thread(
            target=_persist_match_history_after_result,
            args=(
                ctx,
                job_id,
                int(session_id),
                brand_name,
                rows,
                key_columns,
                value_columns,
                f1_columns_for_history,
                f2_columns_for_history,
            ),
            daemon=True,
        ).start()

    except Exception as exc:
        _set_job(ctx, job_id, status="error", progress=100, message=f"{exc}")
        with ctx.lock:
            ctx.jobs[job_id]["traceback"] = traceback.format_exc()


def _persist_match_history_after_result(
    ctx: AppContext,
    job_id: str,
    session_id: int,
    brand_name: str,
    rows: list[dict[str, Any]],
    key_columns: list[dict[str, Any]],
    value_columns: list[dict[str, Any]],
    f1_columns: list[str],
    f2_columns: list[str],
) -> None:
    try:
        inserted_ids = ctx.db.save_results(session_id=session_id, brand=brand_name, rows=rows)
        for i, row in enumerate(rows):
            if i < len(inserted_ids):
                row["result_id"] = inserted_ids[i]

        if key_columns or value_columns:
            ctx.db.save_column_mappings(session_id, key_columns + value_columns)
            ctx.db.save_master_mappings(
                brand_name=brand_name,
                f1_columns=f1_columns,
                f2_columns=f2_columns,
                mappings=key_columns + value_columns,
            )
            with ctx.lock:
                ctx.suggestion_cache.clear()

        ctx.trainer.train_if_needed(force=False)
    except Exception:
        # History/AI learning should never delay or break result delivery.
        with ctx.lock:
            job = ctx.jobs.setdefault(job_id, {})
            job["history_status"] = "error"
            job["history_traceback"] = traceback.format_exc()
    else:
        with ctx.lock:
            job = ctx.jobs.setdefault(job_id, {})
            job["history_status"] = "saved"


def _pick(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _resolve_brand_essgee_file_ids(payload: dict[str, Any]) -> tuple[Any, Any]:
    """
    Resolve file IDs with strict role priority:
      F1 (Brand): brand_file_id > f1_file_id > f1
      F2 (EssGee): essgee_file_id > f2_file_id > f2
    """
    f1_id = _pick(payload, "brand_file_id", "f1_file_id", "f1")
    f2_id = _pick(payload, "essgee_file_id", "f2_file_id", "f2")
    return f1_id, f2_id


def _clean_brand_name(name: Any) -> str:
    text = str(name or "").strip()
    if not text:
        return ""
    norm = text.casefold()
    if norm in {"unknown", "na", "n/a", "none", "null", "-"}:
        return ""
    return text


def _infer_brand_name_from_df(
    brand_df: pd.DataFrame,
    key_columns: list[dict[str, Any]],
    value_columns: list[dict[str, Any]],
) -> str:
    if brand_df is None or brand_df.empty:
        return ""

    candidates: list[str] = []
    for item in (key_columns + value_columns):
        f1_col = str(item.get("f1_col", "") or "").strip()
        label = str(item.get("label", "") or "").strip().casefold()
        if not f1_col:
            continue
        col_norm = f1_col.casefold()
        if ("brand" in col_norm) or ("brand" in label):
            candidates.append(f1_col)

    if not candidates:
        for col in brand_df.columns:
            name = str(col or "").strip()
            if "brand" in name.casefold():
                candidates.append(name)

    seen: set[str] = set()
    ordered = []
    for col in candidates:
        if col in seen:
            continue
        seen.add(col)
        ordered.append(col)

    for col in ordered:
        if col not in brand_df.columns:
            continue
        series = brand_df[col]
        text_series = series.astype(str).str.strip()
        text_series = text_series[text_series != ""]
        if text_series.empty:
            continue
        counts = text_series.value_counts(dropna=True)
        if counts.empty:
            continue
        top = str(counts.index[0]).strip()
        clean = _clean_brand_name(top)
        if clean:
            return clean
    return ""


def _brand_from_filename(filename: str) -> str:
    stem = Path(str(filename or "")).stem.strip()
    if not stem:
        return ""
    lowered = stem.casefold()
    for token in ("brand data", "brand", "file", "data", "report", "sheet"):
        lowered = lowered.replace(token, " ")
    lowered = re.sub(r"[_\-]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    candidate = lowered.title() if lowered else stem
    return _clean_brand_name(candidate)


def _resolve_brand_name(
    brand_name_input: str,
    brand_df: pd.DataFrame,
    key_columns: list[dict[str, Any]],
    value_columns: list[dict[str, Any]],
    brand_filename: str,
) -> str:
    explicit = _clean_brand_name(brand_name_input)
    if explicit:
        return explicit

    inferred_df = _infer_brand_name_from_df(
        brand_df=brand_df,
        key_columns=key_columns,
        value_columns=value_columns,
    )
    if inferred_df:
        return inferred_df

    inferred_file = _brand_from_filename(brand_filename)
    if inferred_file:
        return inferred_file

    return "Unknown"


def _preview_key(sheet: str | int | None, header_row: int) -> str:
    return f"{sheet if sheet is not None else '__default__'}|{int(header_row)}"


def _quick_columns(ctx: AppContext, file_id: str, file_info: dict[str, Any]) -> list[str]:
    default_sheet = (file_info.get("sheets") or [None])[0]
    key = _preview_key(default_sheet, 0)
    with ctx.lock:
        cached = (file_info.get("preview_cache") or {}).get(key)
    if cached and cached.get("columns"):
        return [str(c) for c in cached["columns"]]

    df = load_excel(file_info["path"], sheet=default_sheet, header_row=0, nrows=1)
    cols = [str(c) for c in df.columns.tolist()]
    with ctx.lock:
        file_info.setdefault("preview_cache", {})
        file_info["preview_cache"][key] = {
            "columns": cols,
            "rows": preview_rows(df, n=1),
            "row_count": int(file_info.get("row_count", 0)),
        }
    return cols


def _load_for_match(
    ctx: AppContext,
    file_id: str,
    file_path: str,
    sheet: str | int | None,
    header_row: int,
) -> pd.DataFrame:
    cache_key = (file_id, str(sheet if sheet is not None else "__default__"), int(header_row))
    with ctx.lock:
        cached = ctx.df_cache.get(cache_key)
    if cached is not None:
        return cached

    df = load_excel(file_path, sheet=sheet, header_row=header_row)
    with ctx.lock:
        ctx.df_cache[cache_key] = df
    return df


def _clear_df_cache_for_file(ctx: AppContext, file_id: str) -> None:
    with ctx.lock:
        keys_to_drop = [k for k in ctx.df_cache.keys() if str(k[0]) == str(file_id)]
        for key in keys_to_drop:
            ctx.df_cache.pop(key, None)


def _load_for_export(file_path: str, sheet: str | int | None, header_row: int) -> pd.DataFrame:
    if not file_path:
        raise ValueError("Missing source file path for export")
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"Source file not found for export: {path}")
    return load_excel(str(path), sheet=sheet, header_row=int(header_row or 0))


def _resolve_export_frames(
    job_result: dict[str, Any],
    need_essgee: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """
    Resolve Brand/EssGee DataFrames for export.
    Backward-compatible with older in-memory payloads and newer lightweight payloads.
    """
    brand_df = job_result.get("brand_df")
    essgee_df = job_result.get("essgee_df")

    if brand_df is None:
        brand_df = _load_for_export(
            file_path=str(job_result.get("brand_file_path", "")),
            sheet=job_result.get("f1_sheet"),
            header_row=int(job_result.get("f1_header_row", 0) or 0),
        )
    if need_essgee and essgee_df is None:
        essgee_df = _load_for_export(
            file_path=str(job_result.get("essgee_file_path", "")),
            sheet=job_result.get("f2_sheet"),
            header_row=int(job_result.get("f2_header_row", 0) or 0),
        )

    return brand_df, essgee_df


def _filter_job_result_for_export(
    job_result: dict[str, Any],
    *,
    export_filter: str | None,
    search: str | None,
    search_column: str | None,
) -> dict[str, Any]:
    rows = list(job_result.get("rows", []) or [])
    status_filter = str(export_filter or "").strip()
    search_text = str(search or "").strip().casefold()
    search_col = str(search_column or "all").strip()
    mappings = list(job_result.get("key_mappings", []) or []) + list(job_result.get("value_mappings", []) or [])

    out: list[dict[str, Any]] = []
    for row in rows:
        if status_filter and status_filter != "All" and str(row.get("match_status", "")) != status_filter:
            continue
        if search_text and search_text not in _export_search_blob(row, mappings, search_col):
            continue
        out.append(dict(row))

    return {**job_result, "rows": out}


def _export_search_blob(row: dict[str, Any], mappings: list[dict[str, Any]], search_column: str) -> str:
    f1_row = row.get("f1_row") or {}
    f2_row = row.get("f2_row") or {}
    if search_column and search_column != "all":
        for mapping in mappings:
            label = str(mapping.get("label", "") or "")
            if label != search_column:
                continue
            f1_col = str(mapping.get("f1_col", "") or "")
            f2_col = str(mapping.get("f2_col", "") or "")
            return f"{f1_row.get(f1_col, '')} {f2_row.get(f2_col, '')}".casefold()
        return str((f1_row or f2_row).get(search_column, "")).casefold()

    pieces = [
        str(row.get("match_status", "")),
        str(row.get("match_remark", "")),
        str(row.get("detailed_remark", "")),
        str(row.get("normalized_invoice", "")),
        str(row.get("normalized_party", "")),
    ]
    for mapping in mappings:
        f1_col = str(mapping.get("f1_col", "") or "")
        f2_col = str(mapping.get("f2_col", "") or "")
        pieces.append(str(mapping.get("label", "") or ""))
        pieces.append(str(f1_row.get(f1_col, "")))
        pieces.append(str(f2_row.get(f2_col, "")))
    return " ".join(pieces).casefold()


def _reindex_export_frames_for_rows(
    *,
    brand_df: pd.DataFrame,
    essgee_df: pd.DataFrame | None,
    rows: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame | None, list[dict[str, Any]]]:
    f1_indices = _ordered_row_indices(rows, "f1_index")
    f2_indices = _ordered_row_indices(rows, "f2_index")

    brand_subset = brand_df.iloc[f1_indices].reset_index(drop=True) if f1_indices else brand_df.iloc[0:0].copy()
    essgee_subset = None
    if essgee_df is not None:
        essgee_subset = essgee_df.iloc[f2_indices].reset_index(drop=True) if f2_indices else essgee_df.iloc[0:0].copy()

    f1_map = {old: new for new, old in enumerate(f1_indices)}
    f2_map = {old: new for new, old in enumerate(f2_indices)}
    out_rows: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if item.get("f1_index") is not None:
            old_f1 = int(item["f1_index"])
            item["f1_index"] = f1_map.get(old_f1)
        if item.get("f2_index") is not None:
            old_f2 = int(item["f2_index"])
            item["f2_index"] = f2_map.get(old_f2)
        out_rows.append(item)

    return brand_subset, essgee_subset, out_rows


def _ordered_row_indices(rows: list[dict[str, Any]], field: str) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for row in rows:
        value = row.get(field)
        if value is None:
            continue
        idx = int(value)
        if idx in seen:
            continue
        seen.add(idx)
        out.append(idx)
    return out


def _extract_mappings(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if payload.get("key_columns") or payload.get("value_columns"):
        return list(payload.get("key_columns", [])), list(payload.get("value_columns", []))

    mappings = payload.get("mappings", []) or payload.get("column_mappings", []) or []
    key_columns: list[dict[str, Any]] = []
    value_columns: list[dict[str, Any]] = []

    for item in mappings:
        if not item:
            continue
        if item.get("use") is False:
            continue
        col_type = str(item.get("col_type", item.get("type", "value"))).strip().lower()
        f1_col = item.get("f1_col", item.get("brand_col"))
        f2_col = item.get("f2_col", item.get("essgee_col"))
        mapped = {
            "f1_col": f1_col,
            "f2_col": f2_col,
            "label": item.get("label", f1_col or f2_col or "Column"),
            "col_type": col_type,
            "match_type": item.get("match_type", "text"),
            "tolerance": float(item.get("tolerance", 0.0) or 0.0),
        }
        if col_type == "key":
            key_columns.append(mapped)
        else:
            value_columns.append(mapped)

    return key_columns, value_columns


def _looks_like_qty(text: Any) -> bool:
    raw = str(text or "").strip().casefold()
    if not raw:
        return False
    return raw == "qty" or ("qty" in raw) or ("quantity" in raw)


def _guess_qty_from_columns(columns: list[Any]) -> str | None:
    names = [str(c) for c in columns]
    for name in names:
        if str(name).strip().casefold() == "qty":
            return name
    for name in names:
        if _looks_like_qty(name):
            return name
    return None


def _resolve_qty_columns(
    payload: dict[str, Any],
    key_columns: list[dict[str, Any]],
    value_columns: list[dict[str, Any]],
    df1: pd.DataFrame,
    df2: pd.DataFrame,
) -> tuple[str | None, str | None]:
    qty_f1 = _pick(payload, "brand_qty_col", "qty_f1_col")
    qty_f2 = _pick(payload, "essgee_qty_col", "qty_f2_col")

    candidates = value_columns + key_columns
    if (not qty_f1) or (not qty_f2):
        for item in candidates:
            f1_col = str(item.get("f1_col") or "").strip()
            f2_col = str(item.get("f2_col") or "").strip()
            label = str(item.get("label") or "").strip()
            if _looks_like_qty(label) or _looks_like_qty(f1_col) or _looks_like_qty(f2_col):
                if (not qty_f1) and f1_col:
                    qty_f1 = f1_col
                if (not qty_f2) and f2_col:
                    qty_f2 = f2_col
                if qty_f1 and qty_f2:
                    break

    if not qty_f1:
        qty_f1 = _guess_qty_from_columns(df1.columns.tolist())
    if not qty_f2:
        qty_f2 = _guess_qty_from_columns(df2.columns.tolist())

    return (str(qty_f1).strip() or None, str(qty_f2).strip() or None)


def _set_job(ctx: AppContext, job_id: str, *, status: str, progress: int, message: str) -> None:
    with ctx.lock:
        job = ctx.jobs.setdefault(job_id, {})
        job["status"] = status
        job["progress"] = int(progress)
        job["message"] = message
        job["updated_at"] = datetime.now().isoformat()



def _get_file_or_404(ctx: AppContext, file_id: str) -> dict[str, Any]:
    with ctx.lock:
        info = ctx.files.get(file_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"File ID not found: {file_id}")
    return info


def _delete_uploaded_file(ctx: AppContext, file_id: str) -> bool:
    with ctx.lock:
        info = ctx.files.pop(file_id, None)
        keys_to_drop = [key for key in ctx.df_cache if str(key[0]) == str(file_id)]
        for key in keys_to_drop:
            ctx.df_cache.pop(key, None)
        ctx.suggestion_cache.clear()

    if not info:
        return False

    path = Path(str(info.get("path", ""))).expanduser().resolve()
    upload_root = ctx.upload_dir.resolve()
    try:
        if not path.is_relative_to(upload_root):
            return False
    except ValueError:
        return False

    if path.exists() and path.is_file():
        path.unlink(missing_ok=True)
        return True
    return False


def _register_generated_file(ctx: AppContext, path: Path) -> str:
    file_id = uuid.uuid4().hex
    with ctx.lock:
        ctx.files[file_id] = {
            "path": str(path),
            "filename": path.name,
            "sheets": [],
            "uploaded_at": datetime.now().isoformat(),
        }
    return file_id


def _find_result_by_session(ctx: AppContext, session_id: int) -> dict[str, Any] | None:
    with ctx.lock:
        hit = ctx.results_by_session.get(int(session_id))
        if hit is not None:
            return hit
        for result in ctx.results.values():
            if int(result.get("session_id", 0)) == int(session_id):
                return result
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="FileMatcher backend server")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--data-dir", type=str, default=str(Path.cwd() / "data"))
    args = parser.parse_args()

    data_dir = Path(args.data_dir).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    app = create_app(data_dir)
    uvicorn.run(app, host="127.0.0.1", port=args.port, reload=False)


if __name__ == "__main__":
    main()
