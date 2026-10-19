# Extractor de funcionarios · V2

El extractor lee el consolidado original y escribe únicamente en `data/enriched/`
y `reports/`. No modifica el dashboard V1. Las fichas son históricas: publicar un
cargo en Gob.pe no acredita que la persona siga ejerciéndolo.

## Instalación y pruebas (PowerShell)

```powershell
Set-Location C:\radar_estado_peru
.\.venv\Scripts\python.exe -m pip install -r requirements-extractor.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Si el entorno carece de pip: `.\.venv\Scripts\python.exe -m ensurepip`.
Las dependencias de extracción están separadas de `requirements.txt` de V1.
Python 3.11 o superior. No necesita Playwright: las fichas probadas incluyen los
campos en el HTML servido por HTTP.

## Lotes y reanudación

Lote de hasta 10 perfiles pendientes (el valor predeterminado es 10):

```powershell
.\.venv\Scripts\python.exe scripts\extract_funcionarios_detalle.py --limit 10 --resume --delay 3 --save-html
```

Comando preparado para la base completa, **no ejecutarlo como parte del piloto**:

```powershell
.\.venv\Scripts\python.exe scripts\extract_funcionarios_detalle.py --limit 41866 --resume --delay 3 --retries 2 --backoff 10 --timeout 30 --max-wait 300 --pause-every 100 --pause-seconds 60
```

`--limit` limita los perfiles pendientes seleccionados, no las solicitudes HTTP:
hay una comprobación de robots.txt y pueden existir reintentos o redirecciones.
`--limit 0` selecciona todos los pendientes. `--resume` omite resultados `ok`,
pero vuelve a intentar los parciales y errores. Sin `--resume`, una salida que
ya contiene perfiles produce error para evitar repetirla accidentalmente.
Para otro experimento, usar una subcarpeta, por ejemplo
`--output-dir data/enriched/piloto_alternativo`. Ejecutar una sola instancia
por carpeta de salida. No se hace refresco automático de los perfiles `ok`.

## Salidas y garantías

- `data/enriched/funcionarios.sqlite3`: estado principal, con transacción y
  sincronización durable después de cada perfil. Permite reanudar incluso si
  se interrumpe el proceso antes de exportar el CSV.
- `data/enriched/funcionarios_detalle.csv`: vista de los últimos resultados
  guardados, exportada al terminar o al interrumpir normalmente con Ctrl+C.
  UTF-8 con BOM, separador `;`. No contiene los pendientes aún no consultados.
- `reports/extraccion_<UTC>.jsonl`: registro incremental de cada intento HTTP y
  cada extracción, con fecha UTC, estado, tiempo y error; se sincroniza a disco.
- `reports/extraccion_<UTC>.json`: resumen, cobertura de campos y estimación.
- `data/enriched/html/`: HTML de respuestas 200, sólo con `--save-html`, útil
  para revisar una muestra. No hace falta conservar HTML para la ejecución total.

Las cinco columnas originales se mantienen literalmente. `nombre_completo`
conserva `nombre` cuando no se identifica un valor publicado. Los demás campos
conservan un valor previo si venía en la entrada; si no existía, quedan vacíos.
El SHA-256 vincula el checkpoint a una fuente exacta e impide mezclar fuentes.
`campos_extraidos` distingue datos observados de valores conservados;
`evidencia` registra el texto y el mecanismo que identificó cada campo.

## Campos y reconocimiento

| Columna | Criterio |
|---|---|
| `nombre_completo` | H1 coincidente con la fuente o Person de JSON-LD |
| `cargo_publicado` | Etiqueta explícita, microdatos, JSON-LD o tarjeta oficial corroborada en title |
| `entidad_publica` | Nombre publicado en la tarjeta, enlace de la entidad o dato semántico |
| `denominacion_completa` | Denominación publicada en la tarjeta oficial, etiqueta explícita o legalName; no se expanden siglas |
| `fecha_publicacion` | Etiqueta o metadato explícito; no se sustituye por la fecha de inicio |
| `fecha_actualizacion` | Etiqueta, metadato o «Último cambio» de la ficha |
| `informacion_adicional` | Resumen, trayectoria, formación, funciones, fechas de inicio/fin y enlace de nombramiento disponibles |
| `url_oficial` | URL consultada y validada del mismo identificador de funcionario |

Las fechas se conservan en su formato publicado. `denominacion_completa` refleja
el texto institucional publicado, no una verificación registral independiente.
No se descargan documentos enlazados ni se recopilan contactos personales.
El reconocimiento combina mecanismos; no exige que todas las fichas tengan
la misma plantilla. Si no se reconoce el titular, detiene el lote para revisión.
`ok` exige identificar nombre y cargo; los demás campos son opcionales.
`parcial` identifica al titular pero no obtiene un cargo. Ambos conservan
los datos obtenidos. Errores HTTP y restricciones tienen estados diferenciados.

## Restricciones y duración

Se consulta robots.txt antes de acceder a fichas y se respetan Disallow,
Crawl-delay y Request-rate. Un fallo al verificar robots detiene el lote
(404 se interpreta como ausencia de reglas). No se siguen redirecciones fuera
del mismo perfil y host oficial. 401, 403, 418 y 451 detienen sin reintentar.
429 y errores transitorios tienen reintentos limitados con espera exponencial
y Retry-After. Si la espera requerida supera `--max-wait`, se detiene sin
acortarla. No se cambian identidades ni se intenta superar desafíos del servidor.

El código de salida 2 indica detención/error; 0 indica que terminó el lote,
pero no implica que todos sus registros sean `ok`: revisar `resultados` y
`lote_validado`. Una ejecución sin pendientes no realiza solicitudes.

La estimación sólo se calcula si todo el lote consultado fue `ok`. Usa la
duración observada por perfil, excluye las pausas programadas del lote y añade
las pausas previstas para la base completa. Puede aumentar por red, reintentos,
restricciones o cambios de HTML. El piloto de 10 pertenece a una sola entidad
y no demuestra cobertura de todas las plantillas de las 2.829 entidades.

Datos, HTML, checkpoints y reportes están excluidos por `.gitignore` hasta
obtener autorización de publicación. No se ha realizado publicación desde
esta implementación.
