"""Contrato público compartido; SQLite se abre exclusivamente en modo lectura."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import time
import unicodedata
from urllib.parse import urlparse
import pandas as pd
from app.antiguedad import convertir_fecha, calcular_antiguedad, antiguedad_meses, hoy_lima

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'data/enriched/funcionarios.sqlite3'
CAMPOS = ['id_funcionario','nombre','cargo','entidad','entidad_id','fecha_actualizacion',
          'fecha_consulta','perfil','fecha_inicio','fecha_fin','resumen','formacion_academica',
          'experiencia_profesional','norma','declaracion_jurada','estado','calidad_payload']


def texto(valor):
    if valor is None:
        return ''
    if isinstance(valor, (list, dict)):
        return json.dumps(valor, ensure_ascii=False)
    return str(valor).strip()


def normalizar(valor):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto(valor).casefold()) if not unicodedata.combining(c))


def enlace_valido(valor):
    try:
        url = urlparse(texto(valor))
        return url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password
    except ValueError:
        return False


def especialidad(cargo):
    cargo = normalizar(cargo)
    grupos = {
        'Logística y abastecimiento': ['logistica','abastecimiento','contrataciones','adquisiciones','almacen','compras'],
        'Administración y finanzas': ['administracion','administrativo','economia','finanzas','tesoreria','contabilidad','presupuesto'],
        'Patrimonio': ['patrimonio','patrimonial','saneamiento'],
        'Recursos humanos': ['recursos humanos','personal','talento humano'],
        'Asesoría jurídica': ['juridica','legal','procuraduria'],
        'Planeamiento y proyectos': ['planeamiento','planificacion','proyectos','inversiones'],
        'Tecnologías de información': ['informatica','tecnologia','sistemas'],
    }
    return ' | '.join(g for g, palabras in grupos.items() if any(p in cargo for p in palabras)) or 'Otras funciones'


def normalizar_registros(registros):
    filas = []
    for estado, raw in registros:
        calidad = 'ok'
        try:
            p = json.loads(raw or '{}')
            if not isinstance(p, dict):
                raise ValueError('Perfil no es objeto')
        except (ValueError, TypeError):
            p, calidad = {}, 'JSON inválido'
        adicional = p.get('informacion_adicional') or {}
        if not isinstance(adicional, dict):
            adicional, calidad = {}, 'Información adicional inválida'
        ad = {normalizar(k): v for k,v in adicional.items()}
        def campo(*claves):
            return next((texto(ad.get(normalizar(k))) for k in claves if texto(ad.get(normalizar(k)))), '')
        filas.append(dict(zip(CAMPOS, [
            texto(p.get('id_funcionario')), texto(p.get('nombre_completo') or p.get('nombre')),
            texto(p.get('cargo_publicado')), texto(p.get('entidad_publica') or p.get('denominacion_completa') or p.get('entidad_url')),
            texto(p.get('entidad_url')), texto(p.get('fecha_actualizacion')), texto(p.get('fecha_consulta')),
            texto(p.get('url_oficial') or p.get('perfil')), campo('Fecha de inicio'), campo('Fecha de fin','Fecha de cese','Fecha de término'),
            campo('Resumen'), campo('Formación académica','FORMACI?N ACAD?MICA'), campo('Experiencia Profesional'),
            campo('norma_nombramiento_url'), campo('declaracion_jurada_intereses_url','declaracion_jurada_url','declaracion_intereses_url'),
            texto(estado), calidad,
        ])))
    return pd.DataFrame(filas, columns=CAMPOS)


def leer_sqlite(ruta, limite_segundos=10):
    ruta = Path(ruta).resolve()
    if not ruta.is_file():
        raise FileNotFoundError(ruta)
    # No immutable=1: ignoraría cambios pendientes en WAL. No PRAGMA ni checkpoint.
    inicio = time.monotonic()
    conexion = sqlite3.connect(ruta.as_uri() + '?mode=ro', uri=True, timeout=1)
    try:
        conexion.set_progress_handler(lambda: int(time.monotonic()-inicio > limite_segundos), 1000)
        registros = conexion.execute('SELECT result, payload FROM profiles').fetchall()
    finally:
        conexion.close()
    # Transformación fuera de la transacción: el extractor puede seguir escribiendo.
    return normalizar_registros(registros)


def validar_publicos(df):
    if list(df.columns) != CAMPOS:
        raise ValueError('Esquema público incompatible')
    if df.empty:
        raise ValueError('La instantánea está vacía')
    ok = df[df.estado == 'ok']
    if ok.id_funcionario.eq('').any() or ok.id_funcionario.duplicated().any():
        raise ValueError('Identificadores ausentes o duplicados entre perfiles OK')
    if (ok.calidad_payload != 'ok').any():
        raise ValueError('Payload inválido entre perfiles OK')


def leer_instantanea(ruta):
    ruta = Path(ruta)
    manifiesto = json.loads(Path(str(ruta)+'.manifest.json').read_text(encoding='utf-8'))
    contenido = ruta.read_bytes()
    if manifiesto.get('version_esquema') != 1 or hashlib.sha256(contenido).hexdigest() != manifiesto.get('sha256'):
        raise ValueError('Manifiesto o SHA-256 incompatible')
    df = pd.read_csv(io.BytesIO(contenido), compression='gzip', sep=';', dtype=str, keep_default_na=False)
    validar_publicos(df)
    if len(df) != manifiesto['registros']:
        raise ValueError('Conteo de instantánea incompatible')
    return df


def enriquecer(df, referencia=None):
    referencia = referencia or hoy_lima()
    df = df.copy()
    estados, meses, etiquetas, normalizadas = [], [], [], []
    for inicio_raw, fin_raw in zip(df.fecha_inicio, df.fecha_fin):
        inicio, fin = convertir_fecha(inicio_raw), convertir_fecha(fin_raw)
        estado = 'Calculable'
        corte = referencia
        if not inicio_raw:
            estado = 'Sin dato'
        elif inicio is None:
            estado = 'Fecha inválida'
        elif inicio > referencia:
            estado = 'Fecha futura'
        elif fin_raw and (fin is None or fin < inicio or fin > referencia):
            estado = 'Fecha de fin inconsistente'
        elif fin:
            corte, estado = fin, 'Con fecha de fin'
        calculable = estado in ('Calculable','Con fecha de fin')
        estados.append(estado)
        normalizadas.append(inicio.isoformat() if inicio else '')
        meses.append(antiguedad_meses(inicio, corte) if calculable else None)
        etiquetas.append(calcular_antiguedad(inicio, corte) if calculable else estado)
    df['fecha_inicio_iso'] = normalizadas
    df['estado_fecha'] = estados
    df['antiguedad_meses'] = pd.array(meses, dtype='Int64')
    df['antiguedad_estimada'] = etiquetas
    df['fecha_referencia'] = referencia.isoformat()
    df['especialidad'] = df.cargo.map(especialidad)
    df['_busqueda'] = (df.nombre+' '+df.cargo+' '+df.entidad).map(normalizar)
    return df


def cobertura(df):
    ok = df[df.estado == 'ok']
    return {'registros': len(df), 'perfiles_ok': len(ok),
            'con_fecha_inicio': int(ok.fecha_inicio.ne('').sum()),
            'fechas_inicio_validas': int(ok.fecha_inicio.map(convertir_fecha).notna().sum()),
            'con_declaracion_jurada': int(ok.declaracion_jurada.map(enlace_valido).sum()),
            'payloads_invalidos': int(df.calidad_payload.ne('ok').sum())}


def filtrar(df, consulta='', entidad='Todas', grupo='Todas', rango='Todos', orden='Nombre', solo_ok=True):
    resultado = df[df.estado == 'ok'].copy() if solo_ok else df.copy()
    for termino in normalizar(consulta).split():
        resultado = resultado[resultado._busqueda.str.contains(termino, regex=False, na=False)]
    if entidad != 'Todas':
        resultado = resultado[resultado.entidad == entidad]
    if grupo != 'Todas':
        resultado = resultado[resultado.especialidad.str.split(' | ', regex=False).map(lambda v: grupo in v)]
    meses = resultado.antiguedad_meses
    mascaras = {'Menos de 1 año': meses.lt(12), 'De 1 a menos de 3 años': meses.ge(12)&meses.lt(36),
                'De 3 a menos de 5 años': meses.ge(36)&meses.lt(60), '5 años o más': meses.ge(60),
                'Sin antigüedad calculable': meses.isna()}
    if rango in mascaras:
        resultado = resultado[mascaras[rango].fillna(False)]
    return resultado.sort_values('nombre' if orden == 'Nombre' else 'antiguedad_meses',
                                 ascending=orden != 'Mayor antigüedad', na_position='last', kind='stable')


def exportar_csv(df):
    publico = df.drop(columns=['_busqueda'], errors='ignore').copy()
    # Evita fórmulas al abrir textos publicados externamente en una hoja de cálculo.
    for columna in publico.select_dtypes(include=['object','string']).columns:
        publico[columna] = publico[columna].map(lambda v: "'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v)
    return publico.to_csv(index=False, sep=';').encode('utf-8-sig')
