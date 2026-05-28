from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from .memory_db import MemoryDB


class MatchOutcomeTrainer:
    """
    Trains a local ML model to estimate:
      Matched / Mismatch / Not In Data
    """

    def __init__(
        self,
        db: MemoryDB,
        model_path: str | Path = "backend/ai_models/classifier.pkl",
        metadata_path: str | Path = "backend/ai_models/classifier_meta.json",
    ) -> None:
        self.db = db
        self.model_path = Path(model_path).expanduser().resolve()
        self.metadata_path = Path(metadata_path).expanduser().resolve()
        self.model_path.parent.mkdir(parents=True, exist_ok=True)

    def train_if_needed(self, force: bool = False) -> dict[str, Any]:
        stats = self.db.get_ai_stats()
        session_count = int(stats.get("sessions", 0))
        previous_meta = self._load_metadata()
        previous_sessions = int(previous_meta.get("trained_on_sessions", 0))

        if not force:
            # Train immediately when new sessions arrive.
            # We still keep a small dataset guard below to avoid training on empty/degenerate history.
            if self.model_path.exists() and session_count <= previous_sessions:
                return {
                    "trained": False,
                    "reason": "retrain_not_due",
                    "sessions": session_count,
                }


        features, labels = self._build_training_dataset()
        if len(features) < 20 or len(set(labels)) < 2:
            return {"trained": False, "reason": "insufficient_rows", "rows": len(features)}

        X_train, X_test, y_train, y_test = self._safe_train_test_split(features, labels)

        vectorizer = DictVectorizer(sparse=False)
        X_train_vec = vectorizer.fit_transform(X_train)
        X_test_vec = vectorizer.transform(X_test) if X_test else np.empty((0, X_train_vec.shape[1]))

        model = RandomForestClassifier(
            n_estimators=300,
            random_state=42,
            class_weight="balanced_subsample",
            n_jobs=-1,
        )
        model.fit(X_train_vec, y_train)

        accuracy = None
        if len(X_test) > 0:
            y_pred = model.predict(X_test_vec)
            accuracy = float(accuracy_score(y_test, y_pred))

        payload = {
            "vectorizer": vectorizer,
            "model": model,
            "classes": list(model.classes_),
        }
        joblib.dump(payload, self.model_path)

        meta = {
            "trained_on_sessions": session_count,
            "rows": len(features),
            "accuracy": round((accuracy or 0.0) * 100, 2) if accuracy is not None else None,
        }
        self.metadata_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return {
            "trained": True,
            "sessions": session_count,
            "rows": len(features),
            "accuracy": meta["accuracy"],
            "model_path": str(self.model_path),
        }

    def predict_distribution(self, brand_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.model_path.exists():
            return {
                "enabled": False,
                "reason": "model_not_trained",
                "pcts": {"Matched": 0.0, "Mismatch": 0.0, "Not In Data": 0.0},
                "confidence": 0.0,
            }

        payload = joblib.load(self.model_path)
        model: RandomForestClassifier = payload["model"]
        vectorizer: DictVectorizer = payload["vectorizer"]
        classes: list[str] = list(payload["classes"])

        if not rows:
            return {
                "enabled": True,
                "pcts": {"Matched": 0.0, "Mismatch": 0.0, "Not In Data": 0.0},
                "confidence": 0.0,
            }

        party_rates, brand_rates = self._historical_rates()
        feature_rows = []
        for row in rows:
            party_name = self._extract_party_name(row)
            invoice_no = self._extract_invoice_no(row)
            barcode = self._extract_barcode(row)
            feature_rows.append(
                {
                    "brand_name": brand_name or "unknown",
                    "party_name_length": len(party_name),
                    "invoice_format_type": self._invoice_format_type(invoice_no),
                    "qty_value": float(self._extract_qty(row) or 1.0),
                    "mrp_range_bucket": self._extract_mrp_bucket(row),
                    "is_new_party": 1 if party_name and party_name not in party_rates else 0,
                    "is_new_barcode": 1 if not barcode else 0,
                    "historical_match_rate_for_party": float(party_rates.get(party_name, 0.5)),
                    "historical_match_rate_for_brand": float(brand_rates.get(brand_name, 0.5)),
                }
            )

        X = vectorizer.transform(feature_rows)
        probs = model.predict_proba(X)
        avg_probs = np.mean(probs, axis=0)

        pcts = {"Matched": 0.0, "Mismatch": 0.0, "Not In Data": 0.0}
        for idx, class_name in enumerate(classes):
            if class_name in pcts:
                pcts[class_name] = round(float(avg_probs[idx]) * 100.0, 2)

        confidence = round(float(np.max(avg_probs)) * 100.0, 2)
        return {
            "enabled": True,
            "pcts": pcts,
            "confidence": confidence,
        }

    def _build_training_dataset(self) -> tuple[list[dict[str, Any]], list[str]]:
        rows = self._fetch_training_rows()
        if not rows:
            return [], []

        party_rates, brand_rates = self._historical_rates(rows)

        features: list[dict[str, Any]] = []
        labels: list[str] = []
        for row in rows:
            status = str(row.get("match_status", "") or "")
            label = self._target_label(status)
            party_name = str(row.get("party_name", "") or "")
            invoice_no = str(row.get("invoice_no", "") or "")
            barcode = str(row.get("barcode", "") or "")
            brand_name = str(row.get("brand_name", "") or "unknown")
            fuzzy_score = float(row.get("fuzzy_score", 0.0) or 0.0)

            col_diffs = row.get("col_diffs", {}) or {}
            feature = {
                "brand_name": brand_name,
                "party_name_length": len(party_name),
                "invoice_format_type": self._invoice_format_type(invoice_no),
                "qty_value": 2.0 if status == "Qty Mismatch" else 1.0,
                "mrp_range_bucket": self._mrp_bucket_from_diffs(col_diffs),
                "is_new_party": 0 if party_name in party_rates else 1,
                "is_new_barcode": 0 if barcode else 1,
                "historical_match_rate_for_party": float(party_rates.get(party_name, 0.5)),
                "historical_match_rate_for_brand": float(brand_rates.get(brand_name, 0.5)),
                "fuzzy_score": fuzzy_score,
            }
            features.append(feature)
            labels.append(label)

        return features, labels

    def _safe_train_test_split(
        self, features: list[dict[str, Any]], labels: list[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
        if len(features) < 30:
            return features, [], labels, []

        class_counts: dict[str, int] = {}
        for label in labels:
            class_counts[label] = class_counts.get(label, 0) + 1
        can_stratify = all(v >= 2 for v in class_counts.values())

        return train_test_split(
            features,
            labels,
            test_size=0.2,
            random_state=42,
            shuffle=True,
            stratify=labels if can_stratify else None,
        )

    def _fetch_training_rows(self) -> list[dict[str, Any]]:
        with self.db._connect() as conn:
            data = conn.execute(
                """
                SELECT
                    mr.id,
                    mr.session_id,
                    mr.party_name,
                    mr.invoice_no,
                    mr.barcode,
                    mr.match_status,
                    mr.col_diffs,
                    mr.fuzzy_score,
                    ms.brand_name
                FROM match_results mr
                JOIN match_sessions ms ON mr.session_id = ms.id
                ORDER BY mr.id ASC
                """
            ).fetchall()

        rows: list[dict[str, Any]] = []
        for row in data:
            item = dict(row)
            try:
                item["col_diffs"] = json.loads(item.get("col_diffs") or "{}")
            except Exception:
                item["col_diffs"] = {}
            rows.append(item)
        return rows

    def _historical_rates(self, rows: list[dict[str, Any]] | None = None) -> tuple[dict[str, float], dict[str, float]]:
        if rows is None:
            rows = self._fetch_training_rows()

        party_ok: dict[str, int] = {}
        party_total: dict[str, int] = {}
        brand_ok: dict[str, int] = {}
        brand_total: dict[str, int] = {}

        for row in rows:
            party = str(row.get("party_name", "") or "")
            brand = str(row.get("brand_name", "") or "")
            label = self._target_label(str(row.get("match_status", "") or ""))
            matched = 1 if label == "Matched" else 0

            if party:
                party_total[party] = party_total.get(party, 0) + 1
                party_ok[party] = party_ok.get(party, 0) + matched

            if brand:
                brand_total[brand] = brand_total.get(brand, 0) + 1
                brand_ok[brand] = brand_ok.get(brand, 0) + matched

        party_rate = {
            party: (party_ok.get(party, 0) / party_total[party]) if party_total[party] else 0.5
            for party in party_total
        }
        brand_rate = {
            brand: (brand_ok.get(brand, 0) / brand_total[brand]) if brand_total[brand] else 0.5
            for brand in brand_total
        }
        return party_rate, brand_rate

    def _target_label(self, status: str) -> str:
        status_norm = status.strip()
        if status_norm in {"Matched", "Match"}:
            return "Matched"
        if status_norm in {"Only In F1", "Only In F2", "Not In Data", "Not In Brand", "Not In EssGee"}:
            return "Not In Data"
        return "Mismatch"

    def _invoice_format_type(self, invoice_no: str) -> str:
        inv = (invoice_no or "").strip()
        if not inv:
            return "unknown"
        if inv.isdigit():
            return "numeric"
        has_alpha = any(ch.isalpha() for ch in inv)
        has_digit = any(ch.isdigit() for ch in inv)
        if has_alpha and has_digit:
            if inv[:3].isalpha():
                return "prefix"
            return "mixed"
        if has_alpha:
            return "alpha"
        return "mixed"

    def _mrp_bucket_from_diffs(self, col_diffs: dict[str, Any]) -> str:
        for key, payload in col_diffs.items():
            if "mrp" in str(key).casefold():
                base = self._to_number(payload.get("f1_value")) or self._to_number(payload.get("f2_value"))
                return self._mrp_bucket(base)
        return "unknown"

    def _mrp_bucket(self, value: float | None) -> str:
        if value is None:
            return "unknown"
        v = abs(float(value))
        if v < 100:
            return "lt_100"
        if v < 500:
            return "100_499"
        if v < 1000:
            return "500_999"
        return "ge_1000"

    def _extract_party_name(self, row: dict[str, Any]) -> str:
        for key, value in row.items():
            k = str(key).casefold()
            if "party" in k or "customer" in k:
                return str(value or "")
        return ""

    def _extract_invoice_no(self, row: dict[str, Any]) -> str:
        for key, value in row.items():
            k = str(key).casefold()
            if "invoice" in k or "bill" in k or "inv" in k:
                return str(value or "")
        return ""

    def _extract_barcode(self, row: dict[str, Any]) -> str:
        for key, value in row.items():
            k = str(key).casefold()
            if "barcode" in k or "ean" in k or "upc" in k:
                return str(value or "")
        return ""

    def _extract_qty(self, row: dict[str, Any]) -> float | None:
        for key, value in row.items():
            k = str(key).casefold()
            if "qty" in k or "quantity" in k:
                return self._to_number(value)
        return None

    def _extract_mrp_bucket(self, row: dict[str, Any]) -> str:
        for key, value in row.items():
            k = str(key).casefold()
            if "mrp" in k:
                return self._mrp_bucket(self._to_number(value))
        return "unknown"

    def _to_number(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            text = str(value).replace(",", "").replace("%", "").strip()
            if not text:
                return None
            return float(text)
        except Exception:
            return None

    def _load_metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            return {}
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
