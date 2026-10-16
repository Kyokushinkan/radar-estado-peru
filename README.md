# Radar Estado Peruano · versión 1

Aplicación Streamlit para consultar la relación histórica de perfiles de funcionarios de gob.pe. La presencia de un perfil **no acredita que la persona esté actualmente en funciones**. La base no contiene cargos, remuneraciones, fechas de ejercicio ni nombres completos verificados de entidades.

## Ejecutar en PowerShell

Desde este equipo, con el entorno local preparado:

```powershell
Set-Location C:\radar_estado_peru
.\.venv\Scripts\python.exe -m streamlit run app\app.py --server.address 127.0.0.1
```

Abrir http://localhost:8501. Para detener el servidor, usar Ctrl+C.

Para instalar en otro equipo con Python 3.11 o superior:

```powershell
Set-Location C:\radar_estado_peru
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app\app.py --server.address 127.0.0.1
```

No es necesario activar el entorno ni cambiar la política de ejecución de PowerShell.

## Fuente y alcance

Única entrada: `data/processed/funcionarios_gobpe_consolidado.csv`, UTF-8 y delimitador `;`. La ruta se resuelve respecto al archivo de la aplicación, independientemente del directorio de ejecución. La aplicación solo lee el archivo y mantiene una caché que se invalida al cambiar su fecha de modificación.

Base de referencia: 41,866 registros y perfiles únicos; 2,829 identificadores de entidades; páginas 1 a 2,094. Las páginas son posiciones en la fuente, no fechas. Se valida el esquema, los campos obligatorios, páginas, duplicados y prefijo oficial de enlaces. Una cantidad diferente de registros produce una advertencia visible.

La búsqueda ignora mayúsculas y tildes; todos los términos deben aparecer en el nombre, en cualquier orden. La selección de varias entidades incluye cualquiera de ellas. Los indicadores superiores siempre representan la base completa; las dos tablas y la descarga responden a los filtros. Los identificadores de entidad se conservan literalmente.

La descarga incluye todas las coincidencias y las cinco columnas de origen, sin el índice interno de búsqueda. Usa punto y coma y UTF-8 con BOM para facilitar su apertura en Excel. Las tablas permiten ordenar columnas y desplazarse horizontalmente en pantallas pequeñas; los controles utilizan el ancho disponible.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Se comprueban los conteos reales, cobertura completa, SHA-256 de la base original, búsqueda, filtros múltiples, exportación, agregaciones y ejecución interactiva con Streamlit AppTest. Las pruebas usan la biblioteca estándar y las dependencias de la aplicación.

## Futura publicación (no realizada)

El punto de entrada para Streamlit Cloud será `app/app.py`. `requirements.txt` fija las dependencias directas. `.gitignore` excluye entornos, secretos, datos originales, ZIP y respaldos; permite únicamente el consolidado dentro de `data/`. Revisar los archivos seleccionados antes de publicar y obtener autorización explícita para subir los datos. No se configura PostgreSQL ni Neon.

Referencia de implementación: [columnas de enlaces de Streamlit](https://docs.streamlit.io/develop/api-reference/data/st.column_config/st.column_config.linkcolumn).
