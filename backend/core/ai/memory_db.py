from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class MemoryDB:
    """SQLite persistence layer for self-learning match history."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.master_mapping_path = self.db_path.parent / "master_mappings.json"
        self._master_mapping_lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("PRAGMA cache_size = -20000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS match_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_date TEXT NOT NULL,
                    brand_file TEXT,
                    essgee_file TEXT,
                    brand_name TEXT,
                    total_rows INTEGER DEFAULT 0,
                    matched INTEGER DEFAULT 0,
                    mismatch INTEGER DEFAULT 0,
                    qty_mismatch INTEGER DEFAULT 0,
                    not_in_data INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS match_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    brand TEXT,
                    party_name TEXT,
                    invoice_no TEXT,
                    barcode TEXT,
                    match_status TEXT,
                    col_diffs TEXT,
                    match_type TEXT,
                    fuzzy_score REAL DEFAULT 0,
                    user_corrected INTEGER DEFAULT 0,
                    correct_status TEXT,
                    FOREIGN KEY(session_id) REFERENCES match_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS column_mapping_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    f1_col TEXT,
                    f2_col TEXT,
                    label TEXT,
                    col_type TEXT,
                    match_type TEXT,
                    tolerance REAL DEFAULT 0,
                    FOREIGN KEY(session_id) REFERENCES match_sessions(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS party_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    confirmed INTEGER DEFAULT 0,
                    UNIQUE(raw_name, normalized_name)
                );

                CREATE INDEX IF NOT EXISTS idx_match_sessions_brand ON match_sessions(brand_name);
                CREATE INDEX IF NOT EXISTS idx_match_results_session ON match_results(session_id);
                CREATE INDEX IF NOT EXISTS idx_match_results_brand ON match_results(brand);
                CREATE INDEX IF NOT EXISTS idx_match_results_corrected ON match_results(user_corrected);
                CREATE INDEX IF NOT EXISTS idx_mapping_history_session ON column_mapping_history(session_id);
                """
            )
            self._ensure_match_result_columns(conn)
            conn.commit()

    def _ensure_match_result_columns(self, conn: sqlite3.Connection) -> None:
        existing = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(match_results)").fetchall()
        }
        columns_to_add = {
            "qty_f1": "REAL DEFAULT 0",
            "qty_f2": "REAL DEFAULT 0",
            "invoice_f1_qty": "REAL",
            "invoice_f2_qty": "REAL",
            "f1_index": "INTEGER",
            "f2_index": "INTEGER",
            "normalized_party": "TEXT",
            "normalized_invoice": "TEXT",
            "force_match": "INTEGER DEFAULT 0",
        }
        for column_name, column_type in columns_to_add.items():
            if column_name in existing:
                continue
            conn.execute(f"ALTER TABLE match_results ADD COLUMN {column_name} {column_type}")

    def save_session(
        self,
        *,
        brand_file: str,
        essgee_file: str,
        brand_name: str,
        total_rows: int,
        matched: int,
        mismatch: int,
        qty_mismatch: int,
        not_in_data: int,
        session_date: str | None = None,
    ) -> int:
        date_value = session_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO match_sessions (
                    session_date, brand_file, essgee_file, brand_name,
                    total_rows, matched, mismatch, qty_mismatch, not_in_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date_value,
                    brand_file,
                    essgee_file,
                    brand_name,
                    int(total_rows),
                    int(matched),
                    int(mismatch),
                    int(qty_mismatch),
                    int(not_in_data),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def save_results(self, session_id: int, brand: str, rows: list[dict[str, Any]]) -> list[int]:
        payload_rows: list[tuple[Any, ...]] = []
        with self._connect() as conn:
            for row in rows:
                f1_row = row.get("f1_row") or {}
                f2_row = row.get("f2_row") or {}
                party = row.get("normalized_party") or f1_row.get("Party Name") or f2_row.get("Party Name")
                invoice = row.get("normalized_invoice") or f1_row.get("Invoice No") or f2_row.get("Invoice No")
                barcode = self._extract_barcode(f1_row) or self._extract_barcode(f2_row)

                payload_rows.append(
                    (
                        int(session_id),
                        brand,
                        str(party or ""),
                        str(invoice or ""),
                        str(barcode or ""),
                        str(row.get("match_status", "")),
                        json.dumps(row.get("col_diffs", {}), ensure_ascii=False),
                        str(row.get("match_type", "")),
                        float(row.get("fuzzy_score", 0.0) or 0.0),
                        int(bool(row.get("user_corrected", 0))),
                        str(row.get("correct_status", row.get("match_status", ""))),
                        float(row.get("qty_f1", 0.0) or 0.0),
                        float(row.get("qty_f2", 0.0) or 0.0),
                        self._optional_float(row.get("invoice_f1_qty")),
                        self._optional_float(row.get("invoice_f2_qty")),
                        self._optional_int(row.get("f1_index")),
                        self._optional_int(row.get("f2_index")),
                        str(row.get("normalized_party", "") or ""),
                        str(row.get("normalized_invoice", "") or ""),
                        int(bool(row.get("force_match", 0))),
                    )
                )

            if payload_rows:
                conn.executemany(
                    """
                    INSERT INTO match_results (
                        session_id, brand, party_name, invoice_no, barcode,
                        match_status, col_diffs, match_type, fuzzy_score,
                        user_corrected, correct_status,
                        qty_f1, qty_f2, invoice_f1_qty, invoice_f2_qty,
                        f1_index, f2_index, normalized_party, normalized_invoice, force_match
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload_rows,
                )
                row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
                last_id = int((row or {"id": 0})["id"] or 0)
                first_id = max(last_id - len(payload_rows) + 1, 1)
                inserted_ids = list(range(first_id, last_id + 1))
            else:
                inserted_ids = []
            conn.commit()
        return inserted_ids

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            if value == "":
                return None
            return float(value)
        except Exception:
            return None

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            if value == "":
                return None
            return int(value)
        except Exception:
            return None

    def save_column_mappings(self, session_id: int, mappings: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO column_mapping_history (
                    session_id, f1_col, f2_col, label, col_type, match_type, tolerance
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        int(session_id),
                        str(item.get("f1_col", "")),
                        str(item.get("f2_col", "")),
                        str(item.get("label", "")),
                        str(item.get("col_type", "")),
                        str(item.get("match_type", "")),
                        float(item.get("tolerance", 0.0) or 0.0),
                    )
                    for item in mappings
                ],
            )
            conn.commit()

    def save_master_mappings(
        self,
        *,
        brand_name: str | None,
        f1_columns: list[Any],
        f2_columns: list[Any],
        mappings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Store the latest usable column configuration in a backend JSON master file.
        This works before a match run, so the next same/similar file pair can be auto-mapped.
        """
        f1_names = [str(col).strip() for col in f1_columns if str(col).strip()]
        f2_names = [str(col).strip() for col in f2_columns if str(col).strip()]
        f1_set = set(f1_names)
        f2_set = set(f2_names)

        cleaned: list[dict[str, Any]] = []
        for item in mappings or []:
            mapped = self._clean_master_mapping_item(item, f1_set=f1_set, f2_set=f2_set)
            if mapped:
                cleaned.append(mapped)

        if not cleaned:
            return {"saved": 0, "path": str(self.master_mapping_path)}

        now = datetime.now().isoformat(timespec="seconds")
        brand_text = str(brand_name or "").strip()
        brand_norm = self._normalize_colname(brand_text)
        f1_signature = self._columns_signature(f1_names)
        f2_signature = self._columns_signature(f2_names)

        with self._master_mapping_lock:
            payload = self._read_master_mapping_file()
            presets = [
                preset
                for preset in payload.get("presets", [])
                if not (
                    str(preset.get("brand_norm", "")) == brand_norm
                    and str(preset.get("f1_signature", "")) == f1_signature
                    and str(preset.get("f2_signature", "")) == f2_signature
                )
            ]
            presets.append(
                {
                    "brand_name": brand_text,
                    "brand_norm": brand_norm,
                    "f1_signature": f1_signature,
                    "f2_signature": f2_signature,
                    "f1_columns": f1_names,
                    "f2_columns": f2_names,
                    "mappings": cleaned,
                    "updated_at": now,
                }
            )

            pair_map = {
                self._master_pair_key(pair): dict(pair)
                for pair in payload.get("pairs", [])
                if self._master_pair_key(pair)
            }
            for item in cleaned:
                f1_norm = self._normalize_colname(item["f1_col"])
                f2_norm = self._normalize_colname(item["f2_col"])
                key = f"{brand_norm}|{f1_norm}|{f2_norm}"
                previous = pair_map.get(key, {})
                pair_map[key] = {
                    "brand_name": brand_text,
                    "brand_norm": brand_norm,
                    "f1_col": item["f1_col"],
                    "f2_col": item["f2_col"],
                    "f1_col_norm": f1_norm,
                    "f2_col_norm": f2_norm,
                    "label": item["label"],
                    "col_type": item["col_type"],
                    "match_type": item["match_type"],
                    "tolerance": item["tolerance"],
                    "pair_count": int(previous.get("pair_count", 0) or 0) + 1,
                    "updated_at": now,
                }

            payload["version"] = 1
            payload["updated_at"] = now
            payload["presets"] = sorted(
                presets,
                key=lambda row: str(row.get("updated_at", "")),
                reverse=True,
            )[:500]
            payload["pairs"] = sorted(
                pair_map.values(),
                key=lambda row: (int(row.get("pair_count", 0) or 0), str(row.get("updated_at", ""))),
                reverse=True,
            )[:5000]
            self._write_master_mapping_file(payload)

        return {"saved": len(cleaned), "path": str(self.master_mapping_path)}

    def get_master_mapping_suggestions(
        self,
        *,
        f1_columns: list[Any],
        f2_columns: list[Any],
        brand_name: str | None = None,
    ) -> list[dict[str, Any]]:
        f1_names = [str(col).strip() for col in f1_columns if str(col).strip()]
        f2_names = [str(col).strip() for col in f2_columns if str(col).strip()]
        if not f1_names or not f2_names:
            return []

        f1_signature = self._columns_signature(f1_names)
        f2_signature = self._columns_signature(f2_names)
        brand_norm = self._normalize_colname(str(brand_name or "").strip())

        with self._master_mapping_lock:
            payload = self._read_master_mapping_file()

        matches = []
        for preset in payload.get("presets", []):
            if str(preset.get("f1_signature", "")) != f1_signature:
                continue
            if str(preset.get("f2_signature", "")) != f2_signature:
                continue
            preset_brand = str(preset.get("brand_norm", ""))
            brand_rank = 0 if brand_norm and preset_brand == brand_norm else 1
            if brand_norm and preset_brand and preset_brand != brand_norm:
                brand_rank = 2
            matches.append((brand_rank, str(preset.get("updated_at", "")), preset))

        if not matches:
            return []

        matches.sort(key=lambda row: row[1], reverse=True)
        matches.sort(key=lambda row: row[0])
        chosen = matches[0][2]
        f1_set = set(f1_names)
        f2_set = set(f2_names)
        out: list[dict[str, Any]] = []
        for item in chosen.get("mappings", []):
            mapped = self._clean_master_mapping_item(item, f1_set=f1_set, f2_set=f2_set, skip_use_check=True)
            if not mapped:
                continue
            out.append({**mapped, "confidence": 99.0, "source": "master"})
        return out

    def get_master_mapping_pair_counts(
        self,
        *,
        brand: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        brand_norm = self._normalize_colname(str(brand or "").strip())
        with self._master_mapping_lock:
            payload = self._read_master_mapping_file()

        rows: list[dict[str, Any]] = []
        for item in payload.get("pairs", []):
            item_brand = str(item.get("brand_norm", ""))
            if brand_norm and item_brand and item_brand != brand_norm:
                continue
            rows.append(dict(item))

        rows.sort(
            key=lambda row: (int(row.get("pair_count", 0) or 0), str(row.get("updated_at", ""))),
            reverse=True,
        )
        return rows[: max(1, int(limit or 5000))]

    def _clean_master_mapping_item(
        self,
        item: dict[str, Any],
        *,
        f1_set: set[str],
        f2_set: set[str],
        skip_use_check: bool = False,
    ) -> dict[str, Any] | None:
        if not skip_use_check and item.get("use") is False:
            return None
        f1_col = str(item.get("f1_col", "") or "").strip()
        f2_col = str(item.get("f2_col", "") or "").strip()
        if not f1_col or not f2_col:
            return None
        if f1_set and f1_col not in f1_set:
            return None
        if f2_set and f2_col not in f2_set:
            return None

        raw_col_type = str(item.get("col_type", item.get("type", "value")) or "value").strip().lower()
        col_type = "key" if raw_col_type == "key" else "value"
        try:
            tolerance = float(item.get("tolerance", 0.0) or 0.0)
        except Exception:
            tolerance = 0.0

        return {
            "f1_col": f1_col,
            "f2_col": f2_col,
            "label": str(item.get("label", "") or f1_col or f2_col or "Column").strip(),
            "col_type": col_type,
            "match_type": str(item.get("match_type", "") or "text").strip() or "text",
            "tolerance": tolerance,
        }

    def _read_master_mapping_file(self) -> dict[str, Any]:
        if not self.master_mapping_path.exists():
            return {"version": 1, "updated_at": "", "presets": [], "pairs": []}
        try:
            payload = json.loads(self.master_mapping_path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1, "updated_at": "", "presets": [], "pairs": []}
        if not isinstance(payload, dict):
            return {"version": 1, "updated_at": "", "presets": [], "pairs": []}
        payload.setdefault("version", 1)
        payload.setdefault("updated_at", "")
        payload.setdefault("presets", [])
        payload.setdefault("pairs", [])
        return payload

    def _write_master_mapping_file(self, payload: dict[str, Any]) -> None:
        self.master_mapping_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.master_mapping_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self.master_mapping_path)

    def _columns_signature(self, columns: list[Any]) -> str:
        return "|".join(self._normalize_colname(str(col)) for col in columns)

    def _normalize_colname(self, value: str) -> str:
        text = str(value or "").strip().casefold().replace("_", " ")
        return " ".join(part for part in text.split() if part)

    def _master_pair_key(self, pair: dict[str, Any]) -> str:
        brand = str(pair.get("brand_norm", "") or "")
        f1 = str(pair.get("f1_col_norm", "") or "")
        f2 = str(pair.get("f2_col_norm", "") or "")
        if not f1 or not f2:
            return ""
        return f"{brand}|{f1}|{f2}"

    def get_all_results_for_brand(self, brand: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    mr.*,
                    ms.session_date,
                    ms.brand_name
                FROM match_results mr
                JOIN match_sessions ms ON ms.id = mr.session_id
                WHERE ms.brand_name = ?
                ORDER BY mr.id DESC
                """,
                (brand,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["col_diffs"] = json.loads(data.get("col_diffs") or "{}")
            out.append(data)
        return out

    def save_user_correction(self, result_id: int, correct_status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE match_results
                SET user_corrected = 1, correct_status = ?
                WHERE id = ?
                """,
                (correct_status, int(result_id)),
            )
            conn.commit()

    def save_party_alias(self, raw_name: str, normalized_name: str, confirmed: bool = False) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO party_aliases (raw_name, normalized_name, confirmed)
                VALUES (?, ?, ?)
                ON CONFLICT(raw_name, normalized_name)
                DO UPDATE SET confirmed = MAX(confirmed, excluded.confirmed)
                """,
                (raw_name, normalized_name, int(bool(confirmed))),
            )
            conn.commit()

    def save_party_aliases_bulk(
        self,
        aliases: list[tuple[str, str]],
        confirmed: bool = False,
    ) -> None:
        if not aliases:
            return
        payload = []
        seen: set[tuple[str, str]] = set()
        for raw_name, normalized_name in aliases:
            raw = str(raw_name or "").strip()
            norm = str(normalized_name or "").strip()
            if not raw or not norm:
                continue
            key = (raw, norm)
            if key in seen:
                continue
            seen.add(key)
            payload.append((raw, norm, int(bool(confirmed))))
        if not payload:
            return

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO party_aliases (raw_name, normalized_name, confirmed)
                VALUES (?, ?, ?)
                ON CONFLICT(raw_name, normalized_name)
                DO UPDATE SET confirmed = MAX(confirmed, excluded.confirmed)
                """,
                payload,
            )
            conn.commit()

    def get_party_aliases(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, raw_name, normalized_name, confirmed FROM party_aliases ORDER BY id DESC"
            ).fetchall()
        return [dict(x) for x in rows]

    def get_column_mapping_history(self, brand: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT
                cmh.*,
                ms.brand_name,
                ms.session_date
            FROM column_mapping_history cmh
            JOIN match_sessions ms ON cmh.session_id = ms.id
        """
        params: tuple[Any, ...] = ()
        if brand:
            query += " WHERE ms.brand_name = ?"
            params = (brand,)
        query += " ORDER BY cmh.id DESC"
        if limit and int(limit) > 0:
            query += " LIMIT ?"
            params = params + (int(limit),)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(x) for x in rows]

    def get_column_mapping_pair_counts(
        self,
        brand: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                LOWER(TRIM(cmh.f1_col)) AS f1_col_norm,
                LOWER(TRIM(cmh.f2_col)) AS f2_col_norm,
                COUNT(*) AS pair_count
            FROM column_mapping_history cmh
            JOIN match_sessions ms ON cmh.session_id = ms.id
        """
        params: tuple[Any, ...] = ()
        if brand:
            query += " WHERE ms.brand_name = ?"
            params = (brand,)
        query += """
            GROUP BY LOWER(TRIM(cmh.f1_col)), LOWER(TRIM(cmh.f2_col))
            ORDER BY pair_count DESC
            LIMIT ?
        """
        params = params + (int(limit),)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(x) for x in rows]

    def get_brand_session_count(self, brand: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM match_sessions WHERE brand_name = ?",
                (brand,),
            ).fetchone()
        return int((row or {"count": 0})["count"])

    def get_ai_stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            sessions = conn.execute("SELECT COUNT(*) AS c FROM match_sessions").fetchone()["c"]
            brands = conn.execute(
                "SELECT COUNT(DISTINCT brand_name) AS c FROM match_sessions WHERE brand_name <> ''"
            ).fetchone()["c"]
            corrected = conn.execute(
                "SELECT COUNT(*) AS c FROM match_results WHERE user_corrected = 1"
            ).fetchone()["c"]
            total_results = conn.execute("SELECT COUNT(*) AS c FROM match_results").fetchone()["c"]

            acc_row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN correct_status = match_status THEN 1 ELSE 0 END) AS ok,
                    SUM(CASE WHEN user_corrected = 1 THEN 1 ELSE 0 END) AS corrected
                FROM match_results
                """
            ).fetchone()

        correction_accuracy = 0.0
        corrected_count = int(acc_row["corrected"] or 0)
        if corrected_count > 0:
            correction_accuracy = float(acc_row["ok"] or 0) / corrected_count

        return {
            "sessions": int(sessions),
            "brands": int(brands),
            "results": int(total_results),
            "user_corrections": int(corrected),
            "correction_accuracy": round(correction_accuracy * 100, 2),
        }

    def _extract_barcode(self, row: dict[str, Any]) -> str:
        if not row:
            return ""
        for key, value in row.items():
            key_text = str(key).casefold()
            if "barcode" in key_text or "ean" in key_text or "upc" in key_text:
                return str(value or "")
        return ""
