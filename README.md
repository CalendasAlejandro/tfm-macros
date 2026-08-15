# Clasificacion de macros sospechosas en documentos Office

Proyecto de Trabajo Fin de Master orientado a clasificar macros VBA de documentos
ofimaticos mediante analisis estatico y modelos clasicos de inteligencia
artificial. La solucion permite analizar codigo VBA suelto o documentos Office,
extraer sus macros, calcular senales de riesgo y devolver una clasificacion
multiclase util para un analista SOC.

## Objetivo

El objetivo es apoyar la decision de seguridad ante documentos Office con macros,
sin ejecutar el codigo. El sistema clasifica cada muestra en cuatro niveles:

```text
0 = SEGURA
1 = BAJA SOSPECHA
2 = REVISION RECOMENDADA
3 = ALTO RIESGO
```

Ademas de la clase predicha, la salida incluye probabilidades del modelo,
senales principales, riesgo estatico aproximado y recomendacion operativa.

## Componentes principales

```text
Documento Office o codigo VBA
  -> extraccion de macros
  -> extraccion de caracteristicas estaticas
  -> modelo IA multiclase
  -> API JSON
  -> flujo n8n
  -> interfaz web para analista SOC
```

## Requisitos

Recomendado:

- Python 3.11 o 3.12.
- Sistema operativo Windows o Ubuntu.
- PowerShell en Windows para los comandos locales.
- n8n opcional si se quiere probar el flujo automatizado completo.

Dependencias Python principales:

- pandas
- scikit-learn
- joblib
- matplotlib
- oletools

Las dependencias estan definidas en:

```text
outputs/requirements_modelo.txt
```

## Instalacion en local

Desde la raiz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\outputs\requirements_modelo.txt
```

Si `python` no funciona en Windows, usar:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\outputs\requirements_modelo.txt
```

En Ubuntu:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r outputs/requirements_modelo.txt
```

## Entrenamiento del modelo

El dataset final multiclase se encuentra en:

```text
outputs/macro_dataset_final_multiclass.csv
```

Para reentrenar el modelo:

```powershell
python .\outputs\train_multiclass_macro_classifier.py --dataset .\outputs\macro_dataset_final_multiclass.csv
```

En Ubuntu:

```bash
python outputs/train_multiclass_macro_classifier.py --dataset outputs/macro_dataset_final_multiclass.csv
```

El entrenamiento genera los resultados en:

```text
outputs/resultados_modelo_multiclase/
```

Archivos principales generados:

```text
best_multiclass_model.joblib
metrics_summary_multiclass.csv
test_classification_report_multiclass.txt
test_confusion_matrix_multiclass.csv
test_confusion_matrix_multiclass.png
```

## Analisis de una macro VBA

Ejemplo con una macro de prueba:

```powershell
python .\outputs\predict_multiclass_macro.py --input .\outputs\examples\test_macros\benign\benign_01_format_report.vba
```

Ejemplo con una macro sospechosa:

```powershell
python .\outputs\predict_multiclass_macro.py --input .\outputs\examples\malicioso.vba
```

La salida muestra:

- nivel de riesgo predicho;
- probabilidades por clase;
- riesgo estatico aproximado;
- senales principales detectadas;
- recomendacion operativa.

## API de analisis Office

La API permite analizar documentos Office o codigo VBA mediante peticiones HTTP.

Arranque local:

```powershell
python .\outputs\office_macro_analysis_api.py --host 127.0.0.1 --port 8092
```

Arranque en Ubuntu Server:

```bash
python outputs/office_macro_analysis_api.py --host 0.0.0.0 --port 8092
```

Comprobacion:

```bash
curl http://127.0.0.1:8092/health
```

Endpoint principal:

```text
POST /analyze-office
```

Ejemplo de cuerpo JSON:

```json
{
  "file_name": "documento.docm",
  "file_base64": "BASE64_DEL_DOCUMENTO"
}
```

## Interfaz web

La interfaz web permite subir un documento Office o pegar codigo VBA. La web no
clasifica directamente: envia la muestra a n8n y n8n llama a la API del modelo.

Arranque:

```powershell
python .\web_n8n_office_demo\app.py --webhook-url http://IP_N8N:5678/webhook/analizar-office
```

Abrir en el navegador:

```text
http://127.0.0.1:8093
```

Si se quiere probar sin n8n, se puede arrancar la API y llamar directamente al
endpoint `/analyze-office`.

## Configuracion basica de n8n

Flujo recomendado:

```text
Webhook
  -> HTTP Request
  -> Respond to Webhook
```

Nodo `Webhook`:

```text
HTTP Method: POST
Path: analizar-office
Respond: Using Respond to Webhook Node
```

Nodo `HTTP Request`:

```text
Method: POST
URL: http://IP_API:8092/analyze-office
Body Content Type: JSON
```

Cuerpo JSON:

```json
{
  "file_name": "{{ $json.body.file_name }}",
  "file_base64": "{{ $json.body.file_base64 }}"
}
```

Nodo `Respond to Webhook`:

```text
Respond With: Text
Response Body: ={{ JSON.stringify($json) }}
Header recomendado: Content-Type: application/json
```

## Estructura del repositorio

```text
.
├── outputs/
│   ├── extract_macro_features.py
│   ├── train_multiclass_macro_classifier.py
│   ├── predict_multiclass_macro.py
│   ├── office_macro_analysis_api.py
│   ├── macro_dataset_final_multiclass.csv
│   ├── requirements_modelo.txt
│   ├── examples/
│   └── resultados_modelo_multiclase/
├── web_n8n_office_demo/
│   ├── app.py
├── real_macros/
├── README.md
```

## Resultados principales

El modelo final seleccionado fue `gradient_boosting`. Sobre el conjunto de test
se obtuvieron los siguientes valores:

```text
accuracy:        0.9826
precision_macro: 0.9749
recall_macro:    0.9842
f1_macro:        0.9791
f1_weighted:     0.9827
```

Estos resultados pueden reproducirse ejecutando de nuevo el script de
entrenamiento sobre el dataset final.

## Limitaciones

- El sistema realiza analisis estatico, no ejecuta macros.
- La clasificacion representa una estimacion de riesgo, no una confirmacion
  definitiva de malware.
- El dataset combina macros reales, ejemplos controlados y variantes sinteticas,
  por lo que puede contener sesgos.
- Para uso real deberia complementarse con EDR, sandbox, reputacion de origen y
  validacion por analistas.

## Uso esperado

Este repositorio esta preparado para reproducir:

1. la extraccion de caracteristicas estaticas;
2. el entrenamiento del modelo multiclase;
3. la evaluacion con metricas;
4. la prediccion sobre macros VBA;
5. la API de analisis;
6. la integracion con n8n;
7. la interfaz web orientada a analistas SOC.
