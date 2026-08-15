from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_analysis_api import analyze_macro  # noqa: E402


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".doc",
    ".dot",
    ".xls",
    ".xlt",
    ".ppt",
    ".pot",
    ".docm",
    ".dotm",
    ".xlsm",
    ".xltm",
    ".pptm",
    ".potm",
    ".vba",
    ".bas",
    ".cls",
    ".frm",
    ".txt",
}


def clean_base64(value: str) -> str:
    value = value.strip()
    if "," in value and value.lower().startswith("data:"):
        value = value.split(",", 1)[1]
    return re.sub(r"\s+", "", value)


def decode_file(payload: dict[str, object]) -> tuple[str, bytes]:
    file_name = str(payload.get("file_name") or "documento_office")
    file_base64 = str(payload.get("file_base64") or payload.get("data") or "")
    if not file_base64:
        raise ValueError("Falta el campo file_base64.")

    suffix = Path(file_name).suffix.lower()
    if suffix and suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extension no soportada para esta prueba: {suffix}")

    try:
        content = base64.b64decode(clean_base64(file_base64), validate=True)
    except Exception as exc:
        raise ValueError("El campo file_base64 no contiene base64 valido.") from exc

    if not content:
        raise ValueError("El archivo recibido esta vacio.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Archivo demasiado grande para la prueba.")
    return file_name, content


def extract_vba_from_office(file_name: str, content: bytes) -> list[dict[str, str]]:
    suffix = Path(file_name).suffix.lower()
    if suffix in {".vba", ".bas", ".cls", ".frm", ".txt"}:
        return [
            {
                "source": file_name,
                "stream_path": "",
                "vba_filename": file_name,
                "code": content.decode("utf-8", errors="ignore"),
            }
        ]

    try:
        from oletools.olevba import VBA_Parser
    except ImportError as exc:
        raise RuntimeError(
            "Falta oletools. Instalalo en Ubuntu con: pip install oletools"
        ) from exc

    macros: list[dict[str, str]] = []
    safe_name = Path(file_name).name or "documento_office"
    with tempfile.TemporaryDirectory(prefix="tfm_office_macro_") as tmp_dir:
        sample_path = Path(tmp_dir) / safe_name
        sample_path.write_bytes(content)
        parser = VBA_Parser(str(sample_path))
        try:
            if not parser.detect_vba_macros():
                return []
            for source, stream_path, vba_filename, code in parser.extract_macros():
                macros.append(
                    {
                        "source": str(source),
                        "stream_path": str(stream_path),
                        "vba_filename": str(vba_filename),
                        "code": str(code or ""),
                    }
                )
        finally:
            parser.close()
    return macros


def aggregate_analysis(file_name: str, macros: list[dict[str, str]]) -> dict[str, object]:
    if not macros:
        return {
            "file_name": file_name,
            "has_macros": False,
            "macro_count": 0,
            "level": "SIN MACROS",
            "label": None,
            "recommendation": "No se han encontrado macros VBA en el documento.",
        }

    combined_code = "\n\n".join(item["code"] for item in macros if item["code"].strip())
    if not combined_code.strip():
        return {
            "file_name": file_name,
            "has_macros": True,
            "macro_count": len(macros),
            "level": "MACROS VACIAS",
            "label": None,
            "recommendation": "Se han detectado contenedores VBA, pero no codigo legible para analizar.",
        }

    result = analyze_macro(file_name, combined_code)
    result.update(
        {
            "has_macros": True,
            "macro_count": len(macros),
            "extracted_macros": [
                {
                    "source": item["source"],
                    "stream_path": item["stream_path"],
                    "vba_filename": item["vba_filename"],
                    "code_length": len(item["code"]),
                }
                for item in macros
            ],
        }
    )
    return result


def analyze_office_payload(payload: dict[str, object]) -> dict[str, object]:
    file_name, content = decode_file(payload)
    macros = extract_vba_from_office(file_name, content)
    return aggregate_analysis(file_name, macros)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json({"status": "ok", "service": "office_macro_analysis_api"})
            return
        self.send_json({"error": "endpoint no encontrado"}, status=404)

    def do_POST(self) -> None:
        if self.path not in {"/analyze-office", "/analyze"}:
            self.send_json({"error": "endpoint no encontrado"}, status=404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_UPLOAD_BYTES * 2:
                raise ValueError("Peticion demasiado grande.")
            raw_body = self.rfile.read(length).decode("utf-8", errors="ignore")
            payload = json.loads(raw_body or "{}")
            self.send_json(analyze_office_payload(payload))
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
    parser = argparse.ArgumentParser(description="API local para analizar documentos Office.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"API Office disponible en http://{args.host}:{args.port}")
    print("Healthcheck: GET /health")
    print("Analisis Office: POST /analyze-office")
    server.serve_forever()


if __name__ == "__main__":
    main()
