# Radar Estado Perú · V2.3

Directorio histórico de perfiles públicos de Gob.pe. La antigüedad estimada no
confirma continuidad del nombramiento ni vigencia laboral. Entrada principal:
`app/Panel_de_funcionarios.py`. `app/app.py` es un lanzador compatible.

## Ejecutar localmente (PowerShell)

```powershell
Set-Location C:\radar_estado_peru
$env:RADAR_SOURCE = 'sqlite'
.\.venv\Scripts\python.exe -m streamlit run app\Panel_de_funcionarios.py --server.address 127.0.0.1
```

La fuente predeterminada es `data/enriched/funcionarios.sqlite3`. Se puede indicar
otra ruta con `RADAR_DB`. Las rutas relativas se resuelven desde la raíz del
proyecto. La aplicación abre SQLite con `mode=ro`, espera como máximo un segundo
por bloqueos y limita la consulta mediante un progress handler de diez segundos.
No ejecuta PRAGMA, checkpoint, migraciones ni escrituras. Lee una sola consulta,
cierra la conexión y después normaliza los datos. No usar `immutable=1` ni copiar
sólo el archivo principal mientras haya WAL activo.

La caché incluye fecha local de Lima y firma del archivo principal y WAL, con TTL
de 60 segundos. Se actualiza en la siguiente interacción; no hay sondeo automático.

Instalación nueva: crear un entorno virtual e instalar `requirements.txt`.
Las dependencias de extracción están separadas en `requirements-extractor.txt`.
El entorno verificado en esta implementación usa Python 3.14, Streamlit 1.55.0 y
pandas 2.3.3. Validar la versión de Python elegida para Cloud antes de publicar.

## Antigüedad y consulta

Se cuentan aniversarios mensuales anclados al día inicial. Si el mes destino no
tiene ese día, se usa su último día. El máximo aniversario que no excede la
referencia determina los meses completos; `divmod(meses, 12)` determina años y
meses, y los días son la diferencia desde ese aniversario.

- 31 ene 2026 → 28 feb 2026: 1 mes.
- 31 ene 2026 → 1 mar 2026: 1 mes, 1 día.
- 29 feb 2024 → 28 feb 2025: 1 año.

Se aceptan abreviaturas españolas (incluido sep/set) y fechas ISO. Se conservan
las fechas originales. Ausencias, fechas inválidas, futuras y fines inconsistentes
no reciben meses numéricos. Una fecha de fin válida limita el cálculo; no se
infiere que un cargo sin fecha de fin continúe vigente.

Ambas páginas comparten carga, cálculo, filtros y exportación. La búsqueda ignora
tildes y mayúsculas y exige todos los términos. Hay filtros por entidad,
especialidad, estado OK y rangos de meses completos [0,12), [12,36), [36,60),
[60,+infinito), además de registros sin cálculo. Orden ascendente/descendente
numérico, con ausencias al final. Los indicadores generales corresponden a la
fuente completa; tabla, ficha y CSV responden a los filtros.

Las descargas usan punto y coma y UTF-8 con BOM. Se omite el índice de búsqueda y
se prefijan textos que podrían ejecutarse como fórmulas en hojas de cálculo.
La instantánea ETL conserva los valores originales para uso de la aplicación.

## Exportar una instantánea pública

```powershell
.\.venv\Scripts\python.exe -B scripts\exportar_instantanea.py
```

Genera un nombre único UTC dentro de `data/public/`. Para elegirlo explícitamente:

```powershell
.\.venv\Scripts\python.exe -B scripts\exportar_instantanea.py --output data\public\funcionarios_revision_01.csv.gz
```

El exportador usa el mismo lector de sólo lectura; no llama al extractor. Valida
esquema, identificadores OK, payloads y lectura de vuelta antes de escribir.
Siempre rechaza un destino o manifiesto existente: usar otro nombre. El archivo
se crea exclusivamente y el manifiesto se escribe al final. Una interrupción
puede dejar una salida incompleta, que no debe publicarse; se rechaza al cargarla.
No se borran automáticamente archivos incompletos.

El manifiesto adyacente `.csv.gz.manifest.json` contiene versión del esquema,
fecha UTC de inicio de exportación, conteos, cobertura, calidad de fechas,
columnas, tamaño y SHA-256 del gzip. La aplicación comprueba hash, esquema y
conteo al cargarlo. SHA-256 detecta corrupción; no acredita autenticidad del origen.

Se incluyen explícitamente ID, nombre, cargo, entidad, ID de entidad, fechas de
actualización/consulta/inicio/fin, resumen, formación, experiencia, enlaces a
perfil/norma/declaración, estado y calidad de payload. Se excluyen payload bruto,
tablas de control, evidencia del extractor, HTML, errores internos y otros campos
no seleccionados. Los campos narrativos son texto publicado y requieren revisión
antes de autorizar su difusión. La cobertura de enlaces no comprueba que los
documentos remotos sigan accesibles. Nuevas declaraciones requieren otra exportación.

## Probar la misma fuente que usará Cloud

```powershell
$env:RADAR_SOURCE = 'snapshot'
$env:RADAR_SNAPSHOT = 'data/public/funcionarios_20261018T213022990895Z.csv.gz'
.\.venv\Scripts\python.exe -m streamlit run app\Panel_de_funcionarios.py --server.address 127.0.0.1
```

Este modo no necesita SQLite. No elige automáticamente la última instantánea:
la ruta explícita permite revisar exactamente qué versión se publicará.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Las pruebas V2.3 usan fixtures sintéticos, SQLite temporal y AppTest: calendario,
normalización, búsquedas, filtros, interfaz, exportación, hash, no sobrescritura,
fuente sin SQLite y lectura de WAL mientras existe una transacción de escritura.
Las pruebas existentes del extractor usan solicitudes simuladas y datos temporales;
no ejecutan el extractor de producción. Para ejecutarlas se necesitan también sus
dependencias. Los conteos reales son controles de una instantánea, no constantes
rígidas para todas las versiones futuras.

## Antes de publicar (pendiente; no desplegado)

1. Revisar los textos públicos y autorizar la instantánea exacta y su manifiesto.
2. Agregar excepciones específicas de esos dos archivos a `.gitignore`; actualmente
   `data/public/` sigue excluido. No habilitar toda la carpeta de datos.
3. Revisar explícitamente archivos seleccionados; excluir SQLite, WAL, SHM,
   respaldos y datos operativos. No usar `git add .`.
4. Autorizar por separado commit, push y despliegue.
5. Seleccionar rama aprobada, entrada `app/Panel_de_funcionarios.py`, dependencias
   de la raíz y versión de Python validada. Configurar `RADAR_SOURCE=snapshot` y
   `RADAR_SNAPSHOT` en el entorno de ejecución, o mediante los secretos de Streamlit
   con esas claves en el nivel raíz (Streamlit las expone como variables de entorno).
6. Comprobar navegación, carga, memoria, descargas y legibilidad en Cloud.

Referencia: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization

## Resolución de imports en Streamlit

`app/__init__.py` declara un paquete explícito. Los tres puntos de entrada colocan
la raíz del repositorio al principio de `sys.path`, incluso si ya estaba presente
más adelante. Esto evita que el directorio insertado por Streamlit haga resolver
`app` como el archivo `app/app.py`. No eliminar el inicializador del paquete.
El lanzador compatible conserva únicamente el arranque; la lógica permanece compartida.

`tests/test_importaciones.py` comprueba los tres puntos de entrada en seis procesos
Python nuevos, desde la raíz y desde `app/`, con la carpeta del script primero y
sin ningún módulo `app` precargado. Usa una instantánea sintética y verifica carga
y filtrado; no necesita SQLite operativo. Tras actualizar desde una versión con
el conflicto, reiniciar sólo el servidor Streamlit para descartar módulos antiguos.
