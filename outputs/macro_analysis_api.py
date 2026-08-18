"""
API HTTP local para analizar macros VBA con el modelo multiclase.

Pensada para integracion con n8n mediante el nodo HTTP Request.

Uso:
    python outputs/macro_analysis_api.py --host 0.0.0.0 --port 8091

Endpoints:
    GET  /health
    POST /analyze

Body /analyze:
    {
      "file_name": "macro.vba",
      "macro_text": "Sub Auto_Open()..."
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import joblib
import pandas as pd


ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "resultados_modelo_multiclase" / "best_multiclass_model.joblib"
sys.path.insert(0, str(ROOT))

from extract_macro_features import extract_features  # noqa: E402


LABELS = {
    0: "SEGURA",
    1: "BAJA SOSPECHA",
    2: "REVISION RECOMENDADA",
    3: "ALTO RIESGO",
}

RECOMMENDATIONS = {
    0: "No se observan indicios suficientes para priorizar una revision.",
    1: "Conviene revisar el origen si el documento no procede de una fuente confiable.",
    2: "Debe revisarse manualmente antes de abrir o habilitar macros.",
    3: "No debe ejecutarse. Analizar en entorno controlado.",
}

SIGNAL_LABELS = {
    "obfuscation_score": "puntuacion de ofuscacion",
    "static_risk_score": "riesgo estatico",
    "random_identifier_obfuscation_score": "identificadores aleatorios/ofuscados",
    "file_write_keyword_count": "escritura o modificacion de ficheros",
    "chr_function_count": "uso de Chr/ChrW",
    "autoexec_event_count": "eventos de autoejecucion",
    "createobject_count": "creacion dinamica de objetos COM",
    "powershell_keyword_count": "referencias a PowerShell",
    "url_count": "URLs o enlaces externos",
    "line_continuation_count": "continuaciones de linea",
    "on_error_resume_next_count": "uso repetido de On Error Resume Next",
    "dead_code_loop_count": "bucles de relleno o codigo muerto",
    "entropy_score": "entropia de cadenas/codigo",
}


MODEL = joblib.load(MODEL_PATH)


def top_signals(features: dict[str, object], limit: int = 8) -> list[dict[str, object]]:
    candidates = []
    for key, description in SIGNAL_LABELS.items():
        value = features.get(key, 0)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        if numeric > 0:
            candidates.append(
                {
                    "signal": key,
                    "description": description,
                    "value": value,
                }
            )
    candidates.sort(key=lambda item: float(item["value"]), reverse=True)
    return candidates[:limit]


def probabilities(frame: pd.DataFrame) -> dict[int, float]:
    if not hasattr(MODEL, "predict_proba"):
        predicted = int(MODEL.predict(frame)[0])
        return {label: 1.0 if label == predicted else 0.0 for label in LABELS}

    classes = [int(value) for value in MODEL.classes_]
    values = MODEL.predict_proba(frame)[0]
    result = {label: 0.0 for label in LABELS}
    for label, value in zip(classes, values):
        result[label] = float(value)
    return result


def analyze_macro(file_name: str, macro_text: str) -> dict[str, object]:
    features = extract_features(macro_text, sample_id=Path(file_name).stem or "api_input")
    frame = pd.DataFrame([features])
    predicted_label = int(MODEL.predict(frame)[0])
    probs = probabilities(frame)
    return {
        "file_name": file_name,
        "label": predicted_label,
        "level": LABELS[predicted_label],
        "recommendation": RECOMMENDATIONS[predicted_label],
        "probabilities": {
            LABELS[label]: round(probability, 4)
            for label, probability in probs.items()
        },
        "static_risk_score": features["static_risk_score"],
        "obfuscation_score": features["obfuscation_score"],
        "top_signals": top_signals(features),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json({"status": "ok", "model": str(MODEL_PATH)})
            return
        self.send_json({"error": "endpoint no encontrado"}, status=404)

    def do_POST(self) -> None:
        if self.path != "/analyze":
            self.send_json({"error": "endpoint no encontrado"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 5_000_000:
                raise ValueError("Peticion demasiado grande.")
            raw_body = self.rfile.read(length).decode("utf-8", errors="ignore")
            payload = json.loads(raw_body or "{}")
            file_name = str(payload.get("file_name") or "macro_api.vba")
            macro_text = str(payload.get("macro_text") or "")
            if not macro_text.strip():
                raise ValueError("Falta el campo macro_text.")
            self.send_json(analyze_macro(file_name, macro_text))
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def send_json(self, payload: dict[str, object], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="API local para analizar macros VBA.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"API disponible en http://{args.host}:{args.port}")
    print("Healthcheck: GET /health")
    print("Analisis: POST /analyze")
    server.serve_forever()


if __name__ == "__main__":
    main()
