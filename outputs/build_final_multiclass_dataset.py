from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from build_multiclass_edr_dataset import LABEL_TEXT, evidence_score
from extract_macro_features import extract_features


LABEL_FROM_TEXT = {value: key for key, value in LABEL_TEXT.items()}
BASE_COLUMNS = [
    "sample_id",
    "office_app",
    "declared_purpose",
    "macro_length_lines",
    "module_count",
    "comment_ratio",
    "has_digital_signature",
    "external_link_count",
    "autoexec_event_count",
    "shell_call_count",
    "createobject_count",
    "wscript_keyword_count",
    "powershell_keyword_count",
    "url_count",
    "file_write_keyword_count",
    "registry_keyword_count",
    "process_keyword_count",
    "vba_stomping_indicator",
    "chr_function_count",
    "string_concat_count",
    "base64_like_string_count",
    "hex_string_count",
    "long_string_count",
    "suspicious_keyword_count",
    "entropy_score",
    "obfuscation_score",
    "sandbox_process_created",
    "sandbox_network_attempt",
    "sandbox_file_modified",
    "sandbox_registry_modified",
    "on_error_resume_next_count",
    "eqv_operator_count",
    "dead_code_loop_count",
    "line_continuation_count",
    "document_property_access_count",
    "showwindow_keyword_count",
    "dynamic_createobject_indicator",
    "random_identifier_obfuscation_score",
    "static_risk_score",
    "sandbox_risk_score",
    "final_risk_score",
    "evidence_score",
    "label",
    "label_text",
    "split",
    "source_type",
    "source_file",
    "sha256",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera el dataset final multiclase.")
    parser.add_argument("--hardened", default="macro_dataset_tfm_hardened.csv")
    parser.add_argument("--edr", default="macro_dataset_edr_multiclass.csv")
    parser.add_argument("--output", default="macro_dataset_final_multiclass.csv")
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def normalise_label_text(value: str) -> str:
    value = str(value).strip().lower().replace(" ", "_")
    if value in {"revision_recomendada", "revisión_recomendada"}:
        return "revision_recomendada"
    if value in {"alto_riesgo", "riesgo_alto"}:
        return "alto_riesgo"
    if value in {"baja_sospecha", "riesgo_bajo"}:
        return "baja_sospecha"
    if value in {"segura", "benign", "benigna"}:
        return "segura"
    if value in {"sospechosa", "malicious", "maliciosa"}:
        return "alto_riesgo"
    return value


def evidence_label(row: pd.Series, original_label: int | None) -> int:
    score = float(row.get("evidence_score", 0) or 0)
    source_type = str(row.get("source_type", "")).lower()

    if original_label == 0:
        if score < 35:
            return 0
        if score < 62:
            return 1
        return 2 if "real_benign" not in source_type else 1

    if original_label == 1:
        if score < 45:
            return 1
        if score < 70:
            return 2
        return 3

    if original_label in {2, 3}:
        return original_label

    if score < 35:
        return 0
    if score < 55:
        return 1
    if score < 75:
        return 2
    return 3


def prepare_frame(frame: pd.DataFrame, default_source: str) -> pd.DataFrame:
    frame = frame.copy()
    if "source_type" not in frame:
        frame["source_type"] = default_source
    if "source_file" not in frame:
        frame["source_file"] = default_source
    if "sha256" not in frame:
        frame["sha256"] = frame["sample_id"].astype(str).map(sha256_text)
    if "evidence_score" not in frame:
        frame["evidence_score"] = frame.apply(lambda row: evidence_score(row.to_dict()), axis=1)

    labels = []
    for _, row in frame.iterrows():
        raw_label_text = normalise_label_text(row.get("label_text", ""))
        original = LABEL_FROM_TEXT.get(raw_label_text)
        if original is None and "label" in frame:
            try:
                original = int(row.get("label"))
            except (TypeError, ValueError):
                original = None
        label = evidence_label(row, original)
        labels.append(label)

    frame["label"] = labels
    frame["label_text"] = [LABEL_TEXT[int(label)] for label in labels]
    return frame


def extract_example_macros(root: Path) -> pd.DataFrame:
    rows = []
    candidates = []
    candidates.extend((root / "examples" / "test_macros" / "benign").glob("*.vba"))
    candidates.extend((root / "examples" / "test_macros" / "suspicious").glob("*.vba"))
    for name in ["benign_macro.vba", "prueba.vba", "suspicious_macro.vba", "malicioso.vba", "malicius2.vba"]:
        path = root / "examples" / name
        if path.exists():
            candidates.append(path)

    for path in sorted(set(candidates)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        features = extract_features(text, sample_id=f"project_example_{path.stem}")
        source_hint = str(path).lower()
        if any(token in source_hint for token in ["suspicious", "malicioso", "malicius"]):
            original_label = 1
            source_type = "project_suspicious_example"
        else:
            original_label = 0
            source_type = "project_benign_example"
        features["source_type"] = source_type
        features["source_file"] = str(path)
        features["sha256"] = sha256_text(text)
        features["evidence_score"] = evidence_score(features)
        features["label"] = evidence_label(pd.Series(features), original_label)
        features["label_text"] = LABEL_TEXT[int(features["label"])]
        rows.append(features)

    return pd.DataFrame(rows)


def add_targeted_variants(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    variants = []
    suspicious = frame[frame["label"].isin([2, 3])].copy()
    suspicious = suspicious.sort_values("evidence_score", ascending=False).head(180)
    for index, (_, base) in enumerate(suspicious.iterrows(), start=1):
        row = base.copy()
        row["sample_id"] = f"final_variant_highrisk_{index:04d}"
        row["source_type"] = "final_targeted_highrisk_variant"
        row["chr_function_count"] = int(row.get("chr_function_count", 0) or 0) + int(rng.integers(3, 10))
        row["file_write_keyword_count"] = int(row.get("file_write_keyword_count", 0) or 0) + int(rng.integers(2, 9))
        row["line_continuation_count"] = int(row.get("line_continuation_count", 0) or 0) + int(rng.integers(3, 10))
        row["obfuscation_score"] = min(100.0, float(row.get("obfuscation_score", 0) or 0) + float(rng.uniform(12, 35)))
        row["static_risk_score"] = min(100.0, float(row.get("static_risk_score", 0) or 0) + float(rng.uniform(10, 25)))
        row["sandbox_file_modified"] = 1
        row["evidence_score"] = evidence_score(row.to_dict())
        row["label"] = evidence_label(row, 1)
        row["label_text"] = LABEL_TEXT[int(row["label"])]
        row["sha256"] = sha256_text(str(row.to_dict()))
        variants.append(row)

    borderline = frame[frame["label"].isin([0, 1])].copy()
    borderline = borderline.sort_values("evidence_score", ascending=False).head(160)
    for index, (_, base) in enumerate(borderline.iterrows(), start=1):
        row = base.copy()
        row["sample_id"] = f"final_variant_gray_{index:04d}"
        row["source_type"] = "final_targeted_gray_variant"
        row["createobject_count"] = int(row.get("createobject_count", 0) or 0) + int(rng.choice([0, 1]))
        row["long_string_count"] = int(row.get("long_string_count", 0) or 0) + int(rng.integers(0, 3))
        row["string_concat_count"] = int(row.get("string_concat_count", 0) or 0) + int(rng.integers(1, 7))
        row["obfuscation_score"] = min(75.0, float(row.get("obfuscation_score", 0) or 0) + float(rng.uniform(4, 16)))
        row["static_risk_score"] = min(70.0, float(row.get("static_risk_score", 0) or 0) + float(rng.uniform(3, 13)))
        row["evidence_score"] = evidence_score(row.to_dict())
        row["label"] = evidence_label(row, 0)
        row["label_text"] = LABEL_TEXT[int(row["label"])]
        row["sha256"] = sha256_text(str(row.to_dict()))
        variants.append(row)

    review_sources = frame.copy()
    review_sources = review_sources.sort_values("evidence_score", ascending=False).head(650)
    for index, (_, base) in enumerate(review_sources.iterrows(), start=1):
        row = base.copy()
        row["sample_id"] = f"final_variant_review_{index:04d}"
        row["source_type"] = "final_targeted_review_variant"
        row["autoexec_event_count"] = int(rng.choice([0, 1], p=[0.45, 0.55]))
        row["shell_call_count"] = int(rng.choice([0, 1], p=[0.75, 0.25]))
        row["powershell_keyword_count"] = int(rng.choice([0, 1], p=[0.82, 0.18]))
        row["wscript_keyword_count"] = int(rng.choice([0, 1], p=[0.80, 0.20]))
        row["url_count"] = int(rng.choice([0, 1], p=[0.78, 0.22]))
        row["createobject_count"] = int(max(0, row.get("createobject_count", 0) or 0)) + int(rng.integers(0, 3))
        row["chr_function_count"] = int(rng.integers(2, 8))
        row["file_write_keyword_count"] = int(rng.integers(1, 6))
        row["line_continuation_count"] = int(rng.integers(2, 9))
        row["on_error_resume_next_count"] = int(rng.integers(0, 4))
        row["dynamic_createobject_indicator"] = int(rng.choice([0, 1], p=[0.55, 0.45]))
        row["random_identifier_obfuscation_score"] = round(float(rng.uniform(12, 55)), 2)
        row["obfuscation_score"] = round(float(rng.uniform(38, 72)), 2)
        row["static_risk_score"] = round(float(rng.uniform(58, 86)), 2)
        row["sandbox_process_created"] = int(
            bool(row["shell_call_count"] or row["powershell_keyword_count"] or row["wscript_keyword_count"])
        )
        row["sandbox_network_attempt"] = int(bool(row["url_count"]))
        row["sandbox_file_modified"] = 1
        row["sandbox_registry_modified"] = 0
        row["sandbox_risk_score"] = round(float(rng.uniform(12, 42)), 2)
        row["final_risk_score"] = round(
            min(100.0, float(row["static_risk_score"]) * 0.72 + float(row["sandbox_risk_score"]) * 0.28),
            2,
        )
        row["evidence_score"] = evidence_score(row.to_dict())
        row["label"] = 2
        row["label_text"] = LABEL_TEXT[2]
        row["sha256"] = sha256_text(str(row.to_dict()))
        variants.append(row)

    if not variants:
        return frame
    return pd.concat([frame, pd.DataFrame(variants)], ignore_index=True, sort=False)


def balanced_split(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    parts = []
    for _, group in frame.groupby("label", sort=True):
        group = group.sample(frac=1.0, random_state=int(rng.integers(0, 1_000_000))).reset_index(drop=True)
        total = len(group)
        splits = []
        for index in range(total):
            pos = index / max(1, total)
            if pos < 0.70:
                splits.append("train")
            elif pos < 0.85:
                splits.append("validation")
            else:
                splits.append("test")
        group["split"] = splits
        parts.append(group)
    return pd.concat(parts, ignore_index=True, sort=False)


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent
    rng = np.random.default_rng(args.random_state)

    frames = []
    hardened_path = root / args.hardened
    if hardened_path.exists():
        frames.append(prepare_frame(pd.read_csv(hardened_path), "tfm_hardened"))

    edr_path = root / args.edr
    if edr_path.exists():
        frames.append(prepare_frame(pd.read_csv(edr_path), "edr_multiclass"))

    examples = extract_example_macros(root)
    if not examples.empty:
        frames.append(prepare_frame(examples, "project_examples"))

    if not frames:
        raise FileNotFoundError("No se han encontrado datasets de entrada.")

    final = pd.concat(frames, ignore_index=True, sort=False)
    final = add_targeted_variants(final, rng)
    final = final.drop_duplicates(subset=["sample_id"], keep="last")
    final = balanced_split(final, rng)

    for column in BASE_COLUMNS:
        if column not in final.columns:
            final[column] = ""
    final = final[BASE_COLUMNS + [column for column in final.columns if column not in BASE_COLUMNS]]

    output_path = root / args.output
    final.to_csv(output_path, index=False)

    summary = {
        "rows": int(len(final)),
        "labels": final["label_text"].value_counts().to_dict(),
        "splits": final["split"].value_counts().to_dict(),
        "sources": final["source_type"].value_counts().head(20).to_dict(),
    }
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(pd.Series(summary).to_json(indent=2, force_ascii=False), encoding="utf-8")

    print(f"Dataset final guardado en: {output_path.resolve()}")
    print(f"Filas totales: {len(final)}")
    print("Distribucion por etiqueta:")
    print(final["label_text"].value_counts().sort_index().to_string())
    print("Distribucion por split:")
    print(final["split"].value_counts().to_string())


if __name__ == "__main__":
    main()
