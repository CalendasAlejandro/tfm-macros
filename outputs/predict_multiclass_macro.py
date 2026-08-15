"""
Predice el nivel multiclase de riesgo de una macro VBA.

Etiquetas:
    0 = segura
    1 = baja_sospecha
    2 = revision_recomendada
    3 = alto_riesgo
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from extract_macro_features import extract_features


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clasifica una macro en 4 niveles de riesgo.")
    parser.add_argument("--input", required=True, help="Archivo VBA/TXT a analizar.")
    parser.add_argument(
        "--model",
        default="outputs/resultados_modelo_multiclase/best_multiclass_model.joblib",
        help="Ruta al modelo multiclase entrenado.",
    )
    parser.add_argument("--json", action="store_true", help="Salida en JSON.")
    return parser.parse_args()


def top_signals(features: dict[str, object], limit: int = 7) -> list[dict[str, object]]:
    candidates = []
    for key, description in SIGNAL_LABELS.items():
        value = features.get(key, 0)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        if numeric > 0:
            candidates.append({"signal": key, "description": description, "value": value})
    candidates.sort(key=lambda item: float(item["value"]), reverse=True)
    return candidates[:limit]


def probabilities(model: object, frame: pd.DataFrame) -> dict[int, float]:
    if not hasattr(model, "predict_proba"):
        predicted = int(model.predict(frame)[0])
        return {label: 1.0 if label == predicted else 0.0 for label in LABELS}
    classes = [int(value) for value in model.classes_]
    values = model.predict_proba(frame)[0]
    result = {label: 0.0 for label in LABELS}
    for label, value in zip(classes, values):
        result[label] = float(value)
    return result


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"No encuentro el modelo multiclase: {model_path}")

    text = input_path.read_text(encoding="utf-8", errors="ignore")
    features = extract_features(text, sample_id=input_path.stem)
    frame = pd.DataFrame([features])
    model = joblib.load(model_path)
    predicted_label = int(model.predict(frame)[0])
    probs = probabilities(model, frame)
    signals = top_signals(features)

    result = {
        "input": str(input_path),
        "label": predicted_label,
        "level": LABELS[predicted_label],
        "recommendation": RECOMMENDATIONS[predicted_label],
        "probabilities": {LABELS[label]: round(probability, 4) for label, probability in probs.items()},
        "static_risk_score": features["static_risk_score"],
        "obfuscation_score": features["obfuscation_score"],
        "top_signals": signals,
        "features": features,
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"Archivo: {input_path}")
    print(f"Nivel IA: {predicted_label} - {LABELS[predicted_label]}")
    print("Probabilidades del modelo:")
    for label, probability in probs.items():
        print(f"  {label} - {LABELS[label]}: {probability:.2%}")
    print(f"Riesgo estatico aproximado: {features['static_risk_score']}%")
    print(f"Ofuscacion aproximada: {features['obfuscation_score']}%")
    print(f"Recomendacion: {RECOMMENDATIONS[predicted_label]}")
    print("\nSenales principales:")
    if not signals:
        print("  - No se han detectado senales relevantes.")
    for item in signals:
        print(f"  - {item['description']}: {item['value']}")


if __name__ == "__main__":
    main()
