from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier


TARGET = "label"
SPLIT = "split"
TEXT_LABEL = "label_text"
LABELS = [0, 1, 2, 3]
LABEL_NAMES = ["segura", "baja_sospecha", "revision_recomendada", "alto_riesgo"]
ID_COLUMNS = ["sample_id"]
METADATA_COLUMNS = ["source_type", "source_file", "sha256", "variant_intensity"]
DERIVED_COLUMNS = ["static_risk_score", "sandbox_risk_score", "final_risk_score", "evidence_score"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Entrena modelos multiclase para macros.")
    parser.add_argument("--dataset", default="macro_dataset_final_multiclass.csv")
    parser.add_argument("--output-dir", default="resultados_modelo_multiclase")
    parser.add_argument(
        "--include-derived-scores",
        action="store_true",
        help="Incluye puntuaciones derivadas. Util para baseline, no para evaluacion estricta.",
    )
    parser.add_argument("--random-state", type=int, default=42)
    return parser.parse_args()


def load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No se encontro el dataset: {path}")
    frame = pd.read_csv(path)
    missing = {TARGET, SPLIT}.difference(frame.columns)
    if missing:
        raise ValueError(f"Faltan columnas obligatorias: {sorted(missing)}")
    return frame


def build_feature_lists(frame: pd.DataFrame, include_derived_scores: bool) -> tuple[list[str], list[str], list[str]]:
    excluded = set(ID_COLUMNS + METADATA_COLUMNS + [TARGET, TEXT_LABEL, SPLIT])
    if not include_derived_scores:
        excluded.update(DERIVED_COLUMNS)

    feature_columns = [column for column in frame.columns if column not in excluded]
    numeric_columns = []
    categorical_columns = []
    for column in feature_columns:
        converted = pd.to_numeric(frame[column], errors="coerce")
        if converted.notna().all():
            frame[column] = converted
            numeric_columns.append(column)
        else:
            frame[column] = frame[column].astype("string")
            categorical_columns.append(column)
    return feature_columns, numeric_columns, categorical_columns


def make_preprocessor(numeric_columns: list[str], categorical_columns: list[str]) -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, numeric_columns),
            ("cat", categorical_pipeline, categorical_columns),
        ]
    )


def make_models(random_state: int) -> dict[str, object]:
    return {
        "logistic_regression": LogisticRegression(
            max_iter=3000,
            class_weight="balanced",
            random_state=random_state,
        ),
        "decision_tree": DecisionTreeClassifier(
            max_depth=10,
            min_samples_leaf=10,
            class_weight="balanced",
            random_state=random_state,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=350,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=1,
        ),
        "gradient_boosting": GradientBoostingClassifier(random_state=random_state),
    }


def split_xy(frame: pd.DataFrame, feature_columns: list[str]) -> dict[str, tuple[pd.DataFrame, pd.Series]]:
    result = {}
    for split_name in ["train", "validation", "test"]:
        part = frame[frame[SPLIT] == split_name].copy()
        result[split_name] = (part[feature_columns], part[TARGET].astype(int))
    return result


def evaluate(model: Pipeline, x: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    pred = model.predict(x)
    return {
        "accuracy": accuracy_score(y, pred),
        "precision_macro": precision_score(y, pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y, pred, average="macro", zero_division=0),
        "f1_macro": f1_score(y, pred, average="macro", zero_division=0),
        "f1_weighted": f1_score(y, pred, average="weighted", zero_division=0),
    }


def export_confusion_plot(cm: np.ndarray, output_dir: Path) -> None:
    mpl_config_dir = output_dir / ".matplotlib"
    mpl_config_dir.mkdir(exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig, ax = plt.subplots(figsize=(7.0, 5.8))
    image = ax.imshow(cm, cmap="Blues")
    fig.colorbar(image, ax=ax)
    ax.set_title("Matriz de confusion - multiclase")
    ax.set_xlabel("Prediccion")
    ax.set_ylabel("Valor real")
    ax.set_xticks(range(len(LABEL_NAMES)), labels=LABEL_NAMES, rotation=25, ha="right")
    ax.set_yticks(range(len(LABEL_NAMES)), labels=LABEL_NAMES)
    for row in range(cm.shape[0]):
        for col in range(cm.shape[1]):
            ax.text(col, row, cm[row, col], ha="center", va="center", color="black")
    fig.tight_layout()
    fig.savefig(output_dir / "test_confusion_matrix_multiclass.png", dpi=160)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = load_dataset(dataset_path)
    feature_columns, numeric_columns, categorical_columns = build_feature_lists(
        frame, args.include_derived_scores
    )
    xy = split_xy(frame, feature_columns)
    preprocessor = make_preprocessor(numeric_columns, categorical_columns)
    rows = []
    trained = {}

    for model_name, estimator in make_models(args.random_state).items():
        pipeline = Pipeline(
            steps=[
                ("preprocess", preprocessor),
                ("model", estimator),
            ]
        )
        x_train, y_train = xy["train"]
        x_val, y_val = xy["validation"]
        pipeline.fit(x_train, y_train)
        trained[model_name] = pipeline
        row = {"model": model_name}
        row.update({f"train_{key}": value for key, value in evaluate(pipeline, x_train, y_train).items()})
        row.update({f"validation_{key}": value for key, value in evaluate(pipeline, x_val, y_val).items()})
        rows.append(row)

    summary = pd.DataFrame(rows).sort_values("validation_f1_macro", ascending=False)
    summary.to_csv(output_dir / "metrics_summary_multiclass.csv", index=False)

    best_name = str(summary.iloc[0]["model"])
    best_model = trained[best_name]
    x_test, y_test = xy["test"]
    test_pred = best_model.predict(x_test)
    test_metrics = evaluate(best_model, x_test, y_test)
    cm = confusion_matrix(y_test, test_pred, labels=LABELS)

    pd.DataFrame(cm, index=[f"real_{name}" for name in LABEL_NAMES], columns=[f"pred_{name}" for name in LABEL_NAMES]).to_csv(
        output_dir / "test_confusion_matrix_multiclass.csv"
    )
    report = classification_report(y_test, test_pred, labels=LABELS, target_names=LABEL_NAMES, zero_division=0)
    (output_dir / "test_classification_report_multiclass.txt").write_text(report, encoding="utf-8")
    export_confusion_plot(cm, output_dir)
    joblib.dump(best_model, output_dir / "best_multiclass_model.joblib")

    run_info = {
        "dataset": str(dataset_path),
        "rows": int(len(frame)),
        "features_used": feature_columns,
        "numeric_features": numeric_columns,
        "categorical_features": categorical_columns,
        "include_derived_scores": bool(args.include_derived_scores),
        "best_model": best_name,
        "test_metrics": test_metrics,
        "labels": LABEL_NAMES,
        "confusion_matrix": cm.tolist(),
    }
    (output_dir / "run_info_multiclass.json").write_text(
        json.dumps(run_info, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Entrenamiento multiclase completado")
    print(f"Mejor modelo segun F1 macro de validacion: {best_name}")
    print("Metricas en test:")
    for key, value in test_metrics.items():
        print(f"  {key}: {value:.4f}")
    print(f"Resultados guardados en: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
