from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path


AUTOEXEC_PATTERNS = [
    r"\bAutoOpen\b",
    r"\bAuto_Open\b",
    r"\bDocument_Open\b",
    r"\bWorkbook_Open\b",
    r"\bPresentation_Open\b",
]

SHELL_PATTERNS = [
    r"\bShell\b",
    r"\bRun\b",
    r"\bExec\b",
]

FILE_WRITE_PATTERNS = [
    r"\bOpen\b.+\bFor\s+(Output|Append|Binary)\b",
    r"\bWrite\b",
    r"\bPrint\s+#",
    r"\bSaveAs\b",
    r"\bCreateTextFile\b",
    r"\bFileSystemObject\b",
]

REGISTRY_PATTERNS = [
    r"\bRegWrite\b",
    r"\bRegRead\b",
    r"\bRegDelete\b",
    r"\bHKEY_",
    r"\bCurrentVersion\\Run\b",
]

PROCESS_PATTERNS = [
    r"\bCreateProcess\b",
    r"\bWinExec\b",
    r"\bcmd(?:\.exe)?\b",
    r"\bpowershell(?:\.exe)?\b",
    r"\bwscript(?:\.exe)?\b",
    r"\bcscript(?:\.exe)?\b",
]

URL_RE = re.compile(r"https?://[^\s\"']+|www\.[^\s\"']+", re.IGNORECASE)
BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")
HEX_RE = re.compile(r"\b(?:0x)?[A-Fa-f0-9]{16,}\b")
STRING_RE = re.compile(r'"([^"]*)"')
IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
CREATEOBJECT_RE = re.compile(r"\bCreateObject\s*\((.*?)\)", re.IGNORECASE | re.DOTALL)

VBA_KEYWORDS = {
    "attribute", "vb_name", "sub", "function", "end", "for", "each", "in",
    "next", "do", "loop", "until", "on", "error", "resume", "set", "dim",
    "as", "object", "integer", "long", "string", "double", "if", "then",
    "else", "select", "case", "while", "wend", "true", "false", "nothing",
    "thisdocument", "createobject", "showwindow", "int", "cdbl",
}


def count_patterns(text: str, patterns: list[str]) -> int:
    return sum(len(re.findall(pattern, text, flags=re.IGNORECASE)) for pattern in patterns)


def normalize_vba_text(text: str) -> str:
    normalized_lines = []
    for line in text.splitlines():
        line = re.sub(r";{2,}\s*$", "", line.rstrip())
        if len(line) >= 2 and line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        line = line.replace('""""', '"')
        line = line.replace('""', '"')
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    frequencies = {}
    for char in value:
        frequencies[char] = frequencies.get(char, 0) + 1
    entropy = 0.0
    total = len(value)
    for count in frequencies.values():
        probability = count / total
        entropy -= probability * math.log2(probability)
    return entropy


def random_identifier_score(text: str) -> float:
    identifiers = [
        item
        for item in IDENTIFIER_RE.findall(text)
        if item.lower() not in VBA_KEYWORDS and not item.lower().startswith("wd")
    ]
    if not identifiers:
        return 0.0

    suspicious = 0
    for item in identifiers:
        has_upper = any(char.isupper() for char in item)
        has_lower = any(char.islower() for char in item)
        has_digit = any(char.isdigit() for char in item)
        has_underscore = "_" in item
        entropy = shannon_entropy(item)
        vowel_count = sum(1 for char in item.lower() if char in "aeiou")
        vowel_ratio = vowel_count / max(1, len(item))
        looks_generated = (
            has_digit
            or has_underscore
            or entropy >= 3.25
            or (has_upper and has_lower and vowel_ratio < 0.22)
        )
        if len(item) >= 6 and looks_generated:
            suspicious += 1

    return round(min(100.0, suspicious / len(identifiers) * 100), 2)


def dynamic_createobject_count(text: str) -> int:
    count = 0
    for match in CREATEOBJECT_RE.finditer(text):
        argument = match.group(1).strip()
        if not re.fullmatch(r'"[^"]+"', argument):
            count += 1
    return count


def createobject_targets(text: str) -> list[str]:
    targets = []
    for match in CREATEOBJECT_RE.finditer(text):
        argument = match.group(1).strip()
        literal = re.fullmatch(r'"([^"]+)"', argument)
        if literal:
            targets.append(literal.group(1).lower())
    return targets


def detect_office_app(text: str) -> str:
    lowered = text.lower()
    if "workbook" in lowered or "worksheet" in lowered or "range(" in lowered:
        return "Excel"
    if "presentation" in lowered or "slide" in lowered:
        return "PowerPoint"
    return "Word"


def infer_declared_purpose(features: dict[str, float | int | str]) -> str:
    if features["powershell_keyword_count"] or features["shell_call_count"]:
        return "command_execution_like"
    if features["url_count"] or features["sandbox_network_attempt"]:
        return "downloader_like"
    if features["obfuscation_score"] >= 35:
        return "obfuscated_loader_like"
    if features["file_write_keyword_count"]:
        return "data_cleanup"
    return "template_automation"


def extract_features(text: str, sample_id: str = "MACRO_INPUT") -> dict[str, float | int | str]:
    text = normalize_vba_text(text)
    lines = text.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
    comment_lines = [line for line in non_empty_lines if line.strip().startswith("'")]
    strings = STRING_RE.findall(text)
    joined_strings = "".join(strings)

    macro_length_lines = max(1, len(non_empty_lines))
    module_count = max(1, len(re.findall(r"^\s*(Attribute\s+VB_Name|Option\s+Explicit)", text, re.IGNORECASE | re.MULTILINE)))
    comment_ratio = round(len(comment_lines) / macro_length_lines, 3)

    autoexec_event_count = count_patterns(text, AUTOEXEC_PATTERNS)
    shell_call_count = count_patterns(text, SHELL_PATTERNS)
    createobject_count = len(re.findall(r"\bCreateObject\s*\(", text, flags=re.IGNORECASE))
    createobject_literals = createobject_targets(text)
    benign_createobject_count = sum(
        1
        for target in createobject_literals
        if target in {"scripting.dictionary"}
    )
    wscript_keyword_count = len(re.findall(r"\bWScript\b|\bWScript\.Shell\b", text, flags=re.IGNORECASE))
    powershell_keyword_count = len(re.findall(r"\bPowerShell\b|\bpowershell\.exe\b", text, flags=re.IGNORECASE))
    urls = URL_RE.findall(text)
    url_count = len(urls)
    file_write_keyword_count = count_patterns(text, FILE_WRITE_PATTERNS)
    registry_keyword_count = count_patterns(text, REGISTRY_PATTERNS)
    process_keyword_count = count_patterns(text, PROCESS_PATTERNS)
    on_error_resume_next_count = len(re.findall(r"\bOn\s+Error\s+Resume\s+Next\b", text, flags=re.IGNORECASE))
    eqv_operator_count = len(re.findall(r"\bEqv\b", text, flags=re.IGNORECASE))
    dead_code_loop_count = min(
        len(re.findall(r"\bFor\s+Each\b", text, flags=re.IGNORECASE)),
        len(re.findall(r"\bLoop\s+Until\b", text, flags=re.IGNORECASE)),
    )
    line_continuation_count = len(re.findall(r"_\s*$", text, flags=re.MULTILINE))
    document_property_access_count = len(re.findall(r"\bThisDocument\.[A-Za-z_][A-Za-z0-9_]*", text, flags=re.IGNORECASE))
    showwindow_keyword_count = len(re.findall(r"\bShowWindow\b", text, flags=re.IGNORECASE))
    dynamic_createobject_indicator = 1 if dynamic_createobject_count(text) else 0
    random_identifier_obfuscation_score = random_identifier_score(text)

    chr_function_count = len(re.findall(r"\bChrW?\s*\(", text, flags=re.IGNORECASE))
    string_concat_count = text.count("&") + text.count("+")
    base64_like_string_count = len(BASE64_RE.findall(text))
    hex_string_count = len(HEX_RE.findall(text))
    long_string_count = sum(1 for item in strings if len(item) >= 80)
    entropy_score = round(shannon_entropy(joined_strings or text), 3)

    suspicious_keyword_count = (
        shell_call_count
        + max(0, createobject_count - benign_createobject_count)
        + wscript_keyword_count
        + powershell_keyword_count
        + process_keyword_count
        + url_count
        + registry_keyword_count
    )

    obfuscation_score = min(
        100.0,
        chr_function_count * 2
        + string_concat_count * 1.2
        + base64_like_string_count * 8
        + hex_string_count * 2.6
        + long_string_count * 2.1
        + on_error_resume_next_count * 3.0
        + eqv_operator_count * 2.2
        + dead_code_loop_count * 3.5
        + dynamic_createobject_indicator * 12
        + showwindow_keyword_count * 6
        + random_identifier_obfuscation_score * 0.35
        + (10 if entropy_score > 5.4 else 0),
    )

    sandbox_process_created = 1 if shell_call_count or powershell_keyword_count or process_keyword_count else 0
    sandbox_network_attempt = 1 if url_count else 0
    sandbox_file_modified = 1 if file_write_keyword_count else 0
    sandbox_registry_modified = 1 if registry_keyword_count else 0

    static_risk_score = min(
        100.0,
        autoexec_event_count * 12
        + shell_call_count * 18
        + max(0, createobject_count - benign_createobject_count) * 8
        + wscript_keyword_count * 14
        + powershell_keyword_count * 22
        + url_count * 10
        + file_write_keyword_count * 7
        + registry_keyword_count * 15
        + suspicious_keyword_count * 4
        + obfuscation_score * 0.42
        + on_error_resume_next_count * 4
        + dead_code_loop_count * 5
        + eqv_operator_count * 2
        + dynamic_createobject_indicator * 22
        + showwindow_keyword_count * 8
        + document_property_access_count * 5
        + random_identifier_obfuscation_score * 0.2
        - comment_ratio * 16,
    )
    static_risk_score = max(0.0, static_risk_score)
    sandbox_risk_score = min(
        100.0,
        sandbox_process_created * 24
        + sandbox_network_attempt * 22
        + sandbox_file_modified * 12
        + sandbox_registry_modified * 18,
    )
    final_risk_score = round(min(100.0, static_risk_score * 0.72 + sandbox_risk_score * 0.28), 2)

    features: dict[str, float | int | str] = {
        "sample_id": sample_id,
        "office_app": detect_office_app(text),
        "declared_purpose": "template_automation",
        "macro_length_lines": macro_length_lines,
        "module_count": module_count,
        "comment_ratio": comment_ratio,
        "has_digital_signature": 0,
        "external_link_count": url_count,
        "autoexec_event_count": autoexec_event_count,
        "shell_call_count": shell_call_count,
        "createobject_count": createobject_count,
        "wscript_keyword_count": wscript_keyword_count,
        "powershell_keyword_count": powershell_keyword_count,
        "url_count": url_count,
        "file_write_keyword_count": file_write_keyword_count,
        "registry_keyword_count": registry_keyword_count,
        "process_keyword_count": process_keyword_count,
        "vba_stomping_indicator": 0,
        "chr_function_count": chr_function_count,
        "string_concat_count": string_concat_count,
        "base64_like_string_count": base64_like_string_count,
        "hex_string_count": hex_string_count,
        "long_string_count": long_string_count,
        "suspicious_keyword_count": suspicious_keyword_count,
        "entropy_score": entropy_score,
        "obfuscation_score": round(obfuscation_score, 2),
        "sandbox_process_created": sandbox_process_created,
        "sandbox_network_attempt": sandbox_network_attempt,
        "sandbox_file_modified": sandbox_file_modified,
        "sandbox_registry_modified": sandbox_registry_modified,
        "on_error_resume_next_count": on_error_resume_next_count,
        "eqv_operator_count": eqv_operator_count,
        "dead_code_loop_count": dead_code_loop_count,
        "line_continuation_count": line_continuation_count,
        "document_property_access_count": document_property_access_count,
        "showwindow_keyword_count": showwindow_keyword_count,
        "dynamic_createobject_indicator": dynamic_createobject_indicator,
        "random_identifier_obfuscation_score": random_identifier_obfuscation_score,
        "static_risk_score": round(static_risk_score, 2),
        "sandbox_risk_score": round(sandbox_risk_score, 2),
        "final_risk_score": final_risk_score,
        "label": "",
        "label_text": "",
        "split": "input",
    }
    features["declared_purpose"] = infer_declared_purpose(features)
    return features


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extrae caracteristicas estaticas de una macro VBA.")
    parser.add_argument("--input", required=True, help="Archivo de texto con codigo VBA.")
    parser.add_argument("--output", help="CSV de salida con una fila de caracteristicas.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    text = input_path.read_text(encoding="utf-8", errors="ignore")
    features = extract_features(text, sample_id=input_path.stem)

    output_path = Path(args.output) if args.output else input_path.with_suffix(".features.csv")
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(features.keys()))
        writer.writeheader()
        writer.writerow(features)

    print(f"Caracteristicas guardadas en: {output_path}")
    print(f"Riesgo estatico aproximado: {features['static_risk_score']}%")


if __name__ == "__main__":
    main()
