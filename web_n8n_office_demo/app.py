from __future__ import annotations

import argparse
import base64
import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request


DEFAULT_WEBHOOK_URL = "http://192.168.1.80:5678/webhook/analizar-office"
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


WEBHOOK_URL = DEFAULT_WEBHOOK_URL


def parse_upload(body: bytes, content_type: str) -> tuple[str, bytes]:
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("La peticion no contiene un archivo valido.")

    boundary = content_type.split(marker, 1)[1].strip().strip('"')
    delimiter = ("--" + boundary).encode()

    macro_text = ""
    for part in body.split(delimiter):
        if b"\r\n\r\n" not in part:
            continue
        raw_headers, raw_content = part.split(b"\r\n\r\n", 1)
        headers = raw_headers.decode("utf-8", errors="ignore")
        content = raw_content.rstrip(b"\r\n-")

        if 'name="macro_text"' in headers:
            macro_text = content.decode("utf-8", errors="ignore").strip()
            continue

        if 'name="office_file"' not in headers:
            continue
        if not content:
            continue

        filename = "documento_office"
        if "filename=" in headers:
            filename = headers.split("filename=", 1)[1].split("\r\n", 1)[0].strip().strip('"')
            filename = Path(filename).name or "documento_office"

        suffix = Path(filename).suffix.lower()
        if suffix and suffix not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Extension no soportada para esta demo: {suffix}")
        if not content:
            raise ValueError("El archivo esta vacio.")
        return filename, content

    if macro_text:
        return "macro_pegada.vba", macro_text.encode("utf-8")

    raise ValueError("Sube un archivo Office/VBA o pega codigo VBA para analizar.")


def call_n8n_webhook(filename: str, content: bytes) -> dict[str, object]:
    payload = {
        "file_name": filename,
        "file_base64": base64.b64encode(content).decode("ascii"),
        "source": "web_n8n_office_demo",
    }
    api_request = request.Request(
        WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(api_request, timeout=90) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"n8n ha devuelto error HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"No se ha podido contactar con n8n en {WEBHOOK_URL}: {exc}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"n8n no ha respondido dentro del tiempo esperado en {WEBHOOK_URL}.") from exc

    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"n8n no ha devuelto JSON valido: {raw[:300]}") from exc

    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        raise RuntimeError("n8n ha devuelto una respuesta no esperada.")
    return parsed


def pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def render_probabilities(probabilities: dict[str, object] | None) -> str:
    if not probabilities:
        return "<p class=\"muted\">No hay probabilidades disponibles.</p>"
    rows = []
    for index, label in enumerate(["SEGURA", "BAJA SOSPECHA", "REVISION RECOMENDADA", "ALTO RIESGO"]):
        value = probabilities.get(label, 0)
        try:
            width = max(0.0, min(100.0, float(value) * 100))
        except (TypeError, ValueError):
            width = 0.0
        rows.append(
            f"""
            <div class="prob prob-{index}">
              <div><span>{html.escape(label)}</span><strong>{pct(value)}</strong></div>
              <i><b style="width:{width:.2f}%"></b></i>
            </div>
            """
        )
    return "\n".join(rows)


def render_signals(signals: list[dict[str, object]] | None) -> str:
    if not signals:
        return "<p class=\"muted\">No se han recibido senales principales.</p>"
    return "\n".join(
        f"""
        <li>
          <span>{html.escape(str(item.get("description", item.get("signal", "senal"))))}</span>
          <strong>{html.escape(str(item.get("value", "")))}</strong>
        </li>
        """
        for item in signals
    )


def render_macros(macros: list[dict[str, object]] | None) -> str:
    if not macros:
        return "<p class=\"muted\">No hay detalle de modulos VBA.</p>"
    return "\n".join(
        f"""
        <li>
          <span>{html.escape(str(item.get("vba_filename", "macro")))}</span>
          <small>{html.escape(str(item.get("stream_path", "")))} · {html.escape(str(item.get("code_length", "")))} caracteres</small>
        </li>
        """
        for item in macros
    )


def safe_json(value: object) -> str:
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2))


def analyst_decision(label: object, has_macros: bool) -> tuple[str, str]:
    if not has_macros:
        return "Cerrar como documento sin macros", "No se han encontrado macros VBA que analizar."
    if label == 0:
        return "Permitir si el origen es confiable", "El modelo no observa suficientes indicios para priorizar una investigacion."
    if label == 1:
        return "Validar procedencia antes de permitir", "Existen senales leves; conviene comprobar remitente, ruta de entrada y contexto."
    if label == 2:
        return "Abrir ticket y revisar manualmente", "El modelo detecta combinaciones sospechosas que justifican revision SOC."
    if label == 3:
        return "Aislar muestra y escalar", "La probabilidad de alto riesgo y las evidencias aconsejan no habilitar macros."
    return "Revisar resultado", "El flujo no ha devuelto una etiqueta operativa estandar."


def render_executive_summary(result: dict[str, object], label: object, has_macros: bool) -> str:
    action, reason = analyst_decision(label, has_macros)
    return f"""
    <section class="soc-summary">
      <h3>Resumen para analista SOC</h3>
      <div class="soc-grid">
        <div><span>Decision operativa</span><strong>{html.escape(action)}</strong></div>
        <div><span>Nivel asignado</span><strong>{html.escape(str(label))} - {html.escape(str(result.get("level", "SIN RESULTADO")))}</strong></div>
        <div><span>Macros / riesgo / ofuscacion</span><strong>{html.escape(str(result.get("macro_count", 0)))} / {html.escape(str(result.get("static_risk_score", "-")))} / {html.escape(str(result.get("obfuscation_score", "-")))}</strong></div>
      </div>
      <p>{html.escape(reason)}</p>
    </section>
    """


def render_result(result: dict[str, object] | None, error_message: str | None) -> str:
    if error_message:
        return f"""
        <section class="notice error">
          <strong>No se ha podido completar el analisis</strong>
          <p>{html.escape(error_message)}</p>
        </section>
        """
    if not result:
        return """
        <section class="notice">
          <strong>Esperando documento.</strong>
          <p>Sube un archivo Office o VBA para iniciar el flujo automatico por n8n.</p>
        </section>
        """

    has_macros = bool(result.get("has_macros"))
    level = str(result.get("level", "SIN RESULTADO"))
    label = result.get("label", "-")
    css_level = label if isinstance(label, int) else "none"
    probabilities = result.get("probabilities") if isinstance(result.get("probabilities"), dict) else None
    top_signals = result.get("top_signals") if isinstance(result.get("top_signals"), list) else None
    extracted = result.get("extracted_macros") if isinstance(result.get("extracted_macros"), list) else None

    return f"""
    <section class="result level-{css_level}">
      <div class="result-head">
        <div>
          <span>Archivo analizado</span>
          <h2>{html.escape(str(result.get("file_name", "documento")))}</h2>
        </div>
        <a href="/" class="clear">Nuevo analisis</a>
      </div>

      <div class="verdict">
        <div>
          <span>Nivel IA</span>
          <strong>{html.escape(str(label))} - {html.escape(level)}</strong>
        </div>
        <p>{html.escape(str(result.get("recommendation", "Sin recomendacion disponible.")))}</p>
      </div>

      {render_executive_summary(result, label, has_macros)}

      <div class="metrics">
        <div><span>Macros detectadas</span><strong>{html.escape(str(result.get("macro_count", 0)))}</strong></div>
        <div><span>Contiene macros</span><strong>{"SI" if has_macros else "NO"}</strong></div>
        <div><span>Riesgo estatico</span><strong>{html.escape(str(result.get("static_risk_score", "-")))}</strong></div>
        <div><span>Ofuscacion</span><strong>{html.escape(str(result.get("obfuscation_score", "-")))}</strong></div>
      </div>

      <div class="grid">
        <section>
          <h3>Probabilidades del modelo</h3>
          {render_probabilities(probabilities)}
        </section>
        <section>
          <h3>Senales principales</h3>
          <ul class="signals">{render_signals(top_signals)}</ul>
        </section>
      </div>

      <section class="modules">
        <h3>Macros extraidas</h3>
        <ul>{render_macros(extracted)}</ul>
      </section>

      <div class="result-actions">
        <button class="secondary-button" type="button" id="download-json">Descargar evidencia JSON</button>
        <button class="secondary-button" type="button" id="copy-summary">Copiar resumen SOC</button>
      </div>

      <details>
        <summary>Ver JSON tecnico</summary>
        <pre id="technical-json">{safe_json(result)}</pre>
      </details>
    </section>
    """


def render_page(result: dict[str, object] | None = None, error_message: str | None = None) -> bytes:
    page = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Analizador Office IA con n8n</title>
  <style>
    :root {{
      --ink: #172033;
      --muted: #607086;
      --line: #d9e2ee;
      --panel: #ffffff;
      --soft: #f4f7fb;
      --accent: #087568;
      --safe: #16803c;
      --low: #a16207;
      --review: #6d36c7;
      --danger: #b42318;
      --shadow: 0 20px 60px rgba(31, 44, 68, .09);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #eef3f8;
      font-family: Arial, Helvetica, sans-serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px; }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-end;
      padding-bottom: 22px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: 33px; letter-spacing: 0; }}
    header p {{ max-width: 690px; margin: 8px 0 0; color: var(--muted); line-height: 1.5; }}
    .status {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 10px 12px;
      font-size: 13px;
      white-space: nowrap;
    }}
    .levels {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin: 18px 0 22px;
    }}
    .levels div {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-left: 5px solid var(--safe);
      border-radius: 7px;
      padding: 11px 12px;
      box-shadow: var(--shadow);
      font-size: 13px;
    }}
    .levels div:nth-child(2) {{ border-left-color: var(--low); }}
    .levels div:nth-child(3) {{ border-left-color: var(--review); }}
    .levels div:nth-child(4) {{ border-left-color: var(--danger); }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(320px, 410px) 1fr;
      gap: 22px;
      align-items: start;
    }}
    form, .notice, .result {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 20px;
    }}
    h2, h3 {{ margin: 0; }}
    .upload-box {{
      margin-top: 16px;
      border: 1px dashed #98a9bd;
      border-radius: 8px;
      background: var(--soft);
      padding: 18px;
    }}
    label {{ display: block; font-weight: 700; margin-bottom: 8px; }}
    input[type=file] {{
      width: 100%;
      border: 1px solid var(--line);
      background: white;
      border-radius: 6px;
      padding: 11px;
      font: inherit;
    }}
    textarea {{
      width: 100%;
      min-height: 210px;
      resize: vertical;
      border: 1px solid var(--line);
      background: white;
      border-radius: 6px;
      padding: 11px;
      font: 13px Consolas, "Courier New", monospace;
      line-height: 1.45;
    }}
    button {{
      width: 100%;
      border: 0;
      background: var(--accent);
      color: white;
      border-radius: 6px;
      padding: 13px 16px;
      margin-top: 16px;
      font-weight: 700;
      cursor: pointer;
    }}
    button:disabled {{ opacity: .7; cursor: wait; }}
    .hint {{ margin: 12px 0 0; color: var(--muted); line-height: 1.45; font-size: 13px; }}
    .target-url {{
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 12px;
      word-break: break-all;
      background: var(--soft);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
    }}
    .flow {{
      margin-top: 16px;
      list-style: none;
      padding: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .flow li {{ padding: 8px 0; border-bottom: 1px solid var(--line); }}
    .notice {{ color: var(--muted); line-height: 1.5; }}
    .notice strong {{ color: var(--ink); }}
    .error {{ color: var(--danger); border-color: #f0b0aa; }}
    .result {{ border-top: 6px solid var(--safe); }}
    .level-1 {{ border-top-color: var(--low); }}
    .level-2 {{ border-top-color: var(--review); }}
    .level-3 {{ border-top-color: var(--danger); }}
    .level-none {{ border-top-color: #718096; }}
    .result-head {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: start;
      margin-bottom: 16px;
    }}
    .result-head span, .verdict span, .metrics span {{ color: var(--muted); font-size: 13px; }}
    .result-head h2 {{ margin-top: 5px; font-size: 20px; word-break: break-word; }}
    .clear {{
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      text-decoration: none;
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 13px;
    }}
    .verdict {{
      background: var(--soft);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 14px;
    }}
    .verdict strong {{ display: block; margin-top: 4px; font-size: 25px; }}
    .verdict p {{ margin: 10px 0 0; color: var(--muted); line-height: 1.45; }}
    .soc-summary {{
      border: 1px solid var(--line);
      border-left: 5px solid var(--accent);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 16px;
      background: #fbfdff;
    }}
    .soc-summary h3 {{ margin-bottom: 12px; }}
    .soc-summary p {{ margin: 12px 0 0; color: var(--muted); line-height: 1.45; }}
    .soc-grid {{
      display: grid;
      grid-template-columns: 1.1fr 1fr 1fr;
      gap: 10px;
    }}
    .soc-grid div {{
      background: var(--soft);
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 10px;
    }}
    .soc-grid span {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 5px; }}
    .soc-grid strong {{ display: block; line-height: 1.3; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin-bottom: 18px;
    }}
    .metrics div {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    .metrics strong {{ display: block; margin-top: 5px; font-size: 19px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    h3 {{ font-size: 16px; margin-bottom: 12px; }}
    .prob {{ margin-bottom: 12px; }}
    .prob div {{ display: flex; justify-content: space-between; gap: 12px; }}
    .prob span, .muted {{ color: var(--muted); }}
    .prob i {{ display: block; height: 8px; background: var(--soft); border-radius: 999px; overflow: hidden; margin-top: 5px; }}
    .prob b {{ display: block; height: 100%; background: var(--safe); }}
    .prob-1 b {{ background: var(--low); }}
    .prob-2 b {{ background: var(--review); }}
    .prob-3 b {{ background: var(--danger); }}
    .signals, .modules ul {{ margin: 0; padding: 0; list-style: none; }}
    .signals li, .modules li {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding: 10px 0;
    }}
    .signals span, .modules small {{ color: var(--muted); }}
    .modules {{
      margin-top: 18px;
      border-top: 1px solid var(--line);
      padding-top: 18px;
    }}
    .result-actions {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 18px;
    }}
    .secondary-button {{
      background: #edf3f8;
      color: var(--ink);
      border: 1px solid var(--line);
      margin-top: 0;
    }}
    details {{ margin-top: 16px; border: 1px solid var(--line); border-radius: 8px; padding: 12px; }}
    summary {{ cursor: pointer; font-weight: 700; }}
    pre {{
      background: #101828;
      color: #f8fbff;
      padding: 14px;
      border-radius: 6px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 360px;
    }}
    @media (max-width: 900px) {{
      main {{ padding: 18px; }}
      header, .layout, .levels, .grid, .metrics, .soc-grid, .result-actions {{ display: grid; grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Analizador Office con IA y n8n</h1>
        <p>Adjunta un documento Office. La web envia el archivo a n8n, n8n llama a la API del modelo y el resultado vuelve aqui con nivel de riesgo y evidencias.</p>
      </div>
      <div class="status">Webhook n8n configurado</div>
    </header>

    <section class="levels">
      <div><strong>0</strong> Segura</div>
      <div><strong>1</strong> Baja sospecha</div>
      <div><strong>2</strong> Revision recomendada</div>
      <div><strong>3</strong> Alto riesgo</div>
    </section>

    <div class="layout">
      <form method="post" enctype="multipart/form-data" id="upload-form">
        <h2>Analizar documento o macro</h2>
        <div class="upload-box">
          <label for="office_file">Archivo Office o VBA</label>
          <input id="office_file" name="office_file" type="file" accept=".doc,.dot,.xls,.xlt,.ppt,.pot,.docm,.dotm,.xlsm,.xltm,.pptm,.potm,.vba,.bas,.cls,.frm,.txt">
          <p class="hint" id="file-hint">Formatos admitidos: docm, xlsm, pptm, doc, xls, vba, txt.</p>
        </div>
        <div class="upload-box">
          <label for="macro_text">O pegar codigo VBA</label>
          <textarea id="macro_text" name="macro_text" placeholder="Pega aqui la macro si quieres analizar solo el codigo VBA..."></textarea>
          <p class="hint">Si subes un archivo y tambien pegas texto, se analizara el archivo.</p>
        </div>
        <button type="submit" id="submit-button">Analizar con flujo n8n</button>
        <ul class="flow">
          <li>1. La web convierte el archivo a base64.</li>
          <li>2. n8n recibe el archivo por webhook.</li>
          <li>3. n8n llama a la API de analisis Office.</li>
          <li>4. El modelo IA devuelve la clasificacion.</li>
        </ul>
      </form>

      <div>
        {render_result(result, error_message)}
      </div>
    </div>
  </main>

  <script>
    const form = document.getElementById('upload-form');
    const button = document.getElementById('submit-button');
    const input = document.getElementById('office_file');
    const hint = document.getElementById('file-hint');
    const macroText = document.getElementById('macro_text');
    input.addEventListener('change', () => {{
      hint.textContent = input.files.length
        ? input.files[0].name + ' - ' + (input.files[0].size / 1024).toFixed(1) + ' KB'
        : 'Formatos admitidos: docm, xlsm, pptm, doc, xls, vba, txt.';
    }});
    form.addEventListener('submit', (event) => {{
      if (!input.files.length && !macroText.value.trim()) {{
        event.preventDefault();
        alert('Sube un archivo o pega codigo VBA para analizar.');
        return;
      }}
      button.disabled = true;
      button.textContent = 'Ejecutando flujo n8n...';
    }});
    const technicalJson = document.getElementById('technical-json');
    const downloadJson = document.getElementById('download-json');
    const copySummary = document.getElementById('copy-summary');
    if (technicalJson && downloadJson) {{
      downloadJson.addEventListener('click', () => {{
        const blob = new Blob([technicalJson.textContent], {{ type: 'application/json' }});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'evidencia_analisis_office.json';
        link.click();
        URL.revokeObjectURL(url);
      }});
    }}
    if (copySummary) {{
      copySummary.addEventListener('click', async () => {{
        const verdict = document.querySelector('.verdict strong')?.textContent || '';
        const recommendation = document.querySelector('.verdict p')?.textContent || '';
        const file = document.querySelector('.result-head h2')?.textContent || '';
        const text = 'Archivo: ' + file + '\\nNivel IA: ' + verdict + '\\nRecomendacion: ' + recommendation;
        await navigator.clipboard.writeText(text);
        copySummary.textContent = 'Resumen copiado';
        setTimeout(() => copySummary.textContent = 'Copiar resumen SOC', 1800);
      }});
    }}
  </script>
</body>
</html>"""
    return page.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/":
            self.send_error(404)
            return
        self.respond(render_page())

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_UPLOAD_BYTES * 2:
                raise ValueError("El archivo es demasiado grande para la demo.")
            content_type = self.headers.get("Content-Type", "")
            filename, content = parse_upload(self.rfile.read(length), content_type)
            result = call_n8n_webhook(filename, content)
            self.respond(render_page(result=result))
        except Exception as exc:
            self.respond(render_page(error_message=str(exc)))

    def respond(self, payload: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    global WEBHOOK_URL
    parser = argparse.ArgumentParser(description="Web local que ejecuta un flujo n8n para analizar Office.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8093)
    parser.add_argument("--webhook-url", default=os.environ.get("N8N_WEBHOOK_URL", DEFAULT_WEBHOOK_URL))
    args = parser.parse_args()
    WEBHOOK_URL = args.webhook_url
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Web disponible en http://{args.host}:{args.port}")
    print(f"Webhook n8n: {WEBHOOK_URL}")
    server.serve_forever()


if __name__ == "__main__":
    main()
