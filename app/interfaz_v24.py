"""Interfaz institucional exclusiva de V2.4."""
import json
import os
from datetime import datetime
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from app.antiguedad import hoy_lima
from app.datos import DB_PATH, ROOT, cobertura, filtrar, exportar_csv, normalizar
from app.datos_v24 import cargar_datos, oficial
from app.declaraciones_v24 import mostrar as mostrar_declaraciones
from app.visual_v24 import estructura

RANGOS = ['Todos', 'Menos de 1 año', 'De 1 a menos de 3 años', 'De 3 a menos de 5 años', '5 años o más', 'Sin antigüedad calculable']


def fuente_configurada():
    modo = os.environ.get('RADAR_SOURCE', '').lower() or ('sqlite' if DB_PATH.exists() else 'snapshot')
    if modo not in ('sqlite', 'snapshot'):
        raise ValueError('RADAR_SOURCE debe ser sqlite o snapshot')
    valor = os.environ.get('RADAR_SNAPSHOT') if modo == 'snapshot' else os.environ.get('RADAR_DB')
    if modo == 'snapshot' and not valor:
        valor = 'data/public/funcionarios_dji_v24_20261020T213641Z.csv.gz'
    ruta = Path(valor) if valor else DB_PATH
    return modo, ruta if ruta.is_absolute() else ROOT / ruta


def firma_fuente(modo, ruta):
    archivos = [ruta, Path(str(ruta) + '-wal')] if modo == 'sqlite' else [ruta, Path(str(ruta) + '.manifest.json')]
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in archivos if p.exists())


@st.cache_data(show_spinner=False, ttl=60)
def cargar(modo, ruta, firma, referencia):
    return cargar_datos(modo, ruta, referencia)


def fecha_fuente(modo, ruta, firma):
    if modo == 'snapshot':
        m = json.loads(Path(str(ruta) + '.manifest.json').read_text(encoding='utf-8'))
        return f"Exportación de datos: {m.get('fecha_exportacion_utc') or 'No informada'}"
    if not firma:
        return 'Actualización del archivo local: no informada'
    fecha = datetime.fromtimestamp(max(f[1] for f in firma) / 1e9, ZoneInfo('America/Lima'))
    return f'Actualización del archivo local: {fecha:%d/%m/%Y %H:%M} (Lima)'


def indicadores(df):
    c = cobertura(df)
    cols = st.columns(4)
    cols[0].metric('Perfiles en la fuente', f'{len(df):,}')
    cols[1].metric('Perfiles OK', f"{c['perfiles_ok']:,}")
    cols[2].metric('Con fecha de inicio', f"{c['con_fecha_inicio']:,}")
    cols[3].metric('Enlaces DJI admitidos', f"{df.declaracion_jurada.ne('').sum():,}")
    st.caption('OK describe la extracción del perfil. Un enlace admitido no acredita el contenido de una declaración.')


def mostrar_ficha(persona):
    st.subheader(persona['nombre'] or 'Nombre no informado')
    st.caption(f"ID de perfil: {persona['id_funcionario']} · Estado de extracción: {persona['estado'] or 'Sin dato'}")
    a, b = st.columns(2)
    campos = [('cargo', 'Cargo publicado'), ('entidad', 'Entidad'), ('fecha_inicio', 'Fecha de inicio'),
              ('fecha_fin', 'Fecha de fin'), ('antiguedad_estimada', 'Antigüedad estimada'),
              ('fecha_actualizacion', 'Actualización publicada en Gob.pe')]
    for i, (campo, titulo) in enumerate(campos):
        with (a if i % 2 == 0 else b):
            st.markdown(f'**{titulo}**')
            st.write(persona[campo] or '— No disponible')
    for campo, titulo in [('resumen', 'Resumen profesional'), ('formacion_academica', 'Formación académica'), ('experiencia_profesional', 'Experiencia profesional')]:
        with st.expander(titulo, expanded=campo == 'resumen'):
            st.write(persona[campo] or '— No disponible')
    a, b = st.columns(2)
    for col, campo, titulo in [(a, 'perfil', 'Abrir ficha oficial'), (b, 'norma', 'Norma de nombramiento')]:
        with col:
            if oficial(persona[campo]):
                st.link_button(titulo, persona[campo], width='stretch')
            else:
                st.caption(f'{titulo}: no disponible')


def filtros(df):
    with st.container(border=True):
        consulta = st.text_input('Buscar funcionarios', placeholder='Nombre, cargo o entidad', key='consulta')
        a, b = st.columns(2)
        entidad = a.selectbox('Entidad', ['Todas'] + sorted(x for x in df.entidad.unique() if x), key='entidad')
        grupos = sorted({g for valor in df.especialidad for g in valor.split(' | ')})
        grupo = b.selectbox('Especialidad', ['Todas'] + grupos, key='grupo')
        a, b = st.columns(2)
        rango = a.selectbox('Antigüedad estimada', RANGOS, key='rango')
        orden = b.selectbox('Ordenar por', ['Nombre', 'Mayor antigüedad', 'Menor antigüedad'], key='orden')
        solo_ok = st.checkbox('Solo perfiles OK', value=True, key='solo_ok')
    return filtrar(df, consulta, entidad, grupo, rango, orden, solo_ok)


def fichas_profesionales(df, modo, ruta):
    st.header('Fichas profesionales')
    st.caption('Explore perfiles publicados, antecedentes profesionales y enlaces oficiales.')
    resultado = filtros(df)
    st.subheader(f'{len(resultado):,} perfiles encontrados')
    st.caption('La antigüedad es estimada; no acredita continuidad en el cargo. «—» indica un dato no disponible.')
    campos = ['nombre', 'cargo', 'entidad', 'estado', 'antiguedad_estimada', 'antiguedad_meses', 'fecha_inicio', 'fecha_fin', 'estado_fecha', 'perfil', 'norma', 'declaracion_jurada', 'declaraciones']
    tabla = resultado[campos].copy()
    tabla['estado'] = tabla.estado.map({'ok': '● OK', 'parcial': '◌ Parcial', 'error_http': '◌ Error HTTP'}).fillna('— Sin dato')
    for campo in ('nombre', 'cargo', 'entidad', 'fecha_inicio', 'fecha_fin'):
        tabla[campo] = tabla[campo].replace('', '—')
    st.dataframe(tabla, hide_index=True, width='stretch', height=420, column_config={
        'nombre': st.column_config.TextColumn('Funcionario', width='medium'),
        'cargo': st.column_config.TextColumn('Cargo publicado', width='medium'),
        'entidad': st.column_config.TextColumn('Entidad', width='medium'),
        'estado': 'Extracción', 'antiguedad_estimada': 'Antigüedad estimada',
        'antiguedad_meses': 'Meses completos', 'estado_fecha': 'Calidad de fecha',
        'fecha_inicio': 'Inicio publicado', 'fecha_fin': 'Fin publicado',
        'perfil': st.column_config.LinkColumn('Ficha oficial', display_text='Abrir ficha'),
        'norma': st.column_config.LinkColumn('Nombramiento', display_text='Ver norma'),
        'declaracion_jurada': st.column_config.LinkColumn('DJI · enlace registrado', display_text='Consultar DJI'),
        'declaraciones': 'Estado de declaración',
    })
    st.download_button('Descargar resultados CSV', exportar_csv(resultado), file_name='radar_estado_v2_4.csv', mime='text/csv', disabled=resultado.empty)
    if resultado.empty:
        st.info('No hay perfiles con estos filtros. Pruebe otros términos o amplíe los filtros.')
        return
    st.divider()
    paginas = max(1, (len(resultado) + 49) // 50)
    pagina = st.number_input('Página de fichas (50 por página)', min_value=1, max_value=paginas, value=1)
    lote = resultado.iloc[(pagina - 1) * 50:pagina * 50]
    def etiqueta(i):
        p = lote.loc[i]
        return f"{p['nombre']} · {p['entidad']} · ID {p['id_funcionario']}"
    elegido = st.selectbox('Seleccionar funcionario', list(lote.index), format_func=etiqueta)
    with st.container(border=True):
        ficha, declaraciones = st.tabs(['Ficha profesional', 'Declaraciones'])
        with ficha:
            mostrar_ficha(resultado.loc[elegido])
        with declaraciones:
            mostrar_declaraciones(resultado.loc[elegido], modo, ruta)



def entidades(df):
    """Directorio institucional basado en los registros locales."""
    datos = df.copy()
    datos["entidad_id"] = datos["entidad_id"].fillna("").astype(str)
    datos["entidad"] = datos["entidad"].fillna("").astype(str)

    tabla = (
        datos.groupby(["entidad_id", "entidad"], dropna=False)
        .size()
        .reset_index(name="Perfiles")
        .sort_values(
            ["Perfiles", "entidad"],
            ascending=[False, True]
        )
        .reset_index(drop=True)
    )
    return tabla


def paginar(total, clave, opciones=(25, 50, 100)):
    """Controles independientes de paginación."""
    cantidad = st.selectbox(
        "Resultados por página",
        opciones,
        key=f"{clave}_cantidad"
    )

    paginas = max(1, (total + cantidad - 1) // cantidad)

    estado = f"{clave}_pagina"
    if estado not in st.session_state:
        st.session_state[estado] = 1

    if st.session_state[estado] > paginas:
        st.session_state[estado] = paginas

    actual = st.session_state[estado]

    anterior, centro, siguiente = st.columns([1, 2, 1])

    with anterior:
        if st.button(
            "← Anterior",
            disabled=actual <= 1,
            key=f"{clave}_anterior"
        ):
            st.session_state[estado] -= 1
            st.rerun()

    with centro:
        st.caption(f"Página {actual} de {paginas}")

    with siguiente:
        if st.button(
            "Siguiente →",
            disabled=actual >= paginas,
            key=f"{clave}_siguiente"
        ):
            st.session_state[estado] += 1
            st.rerun()

    inicio = (actual - 1) * cantidad
    return inicio, inicio + cantidad


def mostrar_entidades(df, modo, ruta):
    st.header("Directorio de entidades")
    st.caption(
        "Instituciones identificadas en la fuente local. "
        "Los perfiles son históricos y no acreditan cargos vigentes."
    )

    tabla = entidades(df)

    identificadores = (
        df["entidad_id"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    ids_validos = identificadores[
        identificadores.ne("")
    ].nunique()

    a, b, c = st.columns(3)
    a.metric("Identificadores institucionales", f"{ids_validos:,}")
    b.metric("Grupos identificador / nombre", f"{len(tabla):,}")
    c.metric("Perfiles registrados", f"{len(df):,}")

    st.caption(
        "Un identificador puede aparecer con distintas denominaciones. "
        "El conteo no equivale necesariamente al número oficial "
        "de entidades públicas existentes."
    )

    busqueda = st.text_input(
        "Buscar entidad",
        placeholder="Ministerio, municipalidad, organismo...",
        key="v24_busqueda_entidades"
    )

    if busqueda:
        termino = normalizar(busqueda)
        tabla = tabla[
            tabla["entidad"].map(normalizar).str.contains(
                termino, regex=False
            ) |
            tabla["entidad_id"].map(normalizar).str.contains(
                termino, regex=False
            )
        ].reset_index(drop=True)

    st.subheader(f"{len(tabla):,} grupos encontrados")

    if tabla.empty:
        st.info("No se encontraron entidades con ese criterio.")
        return

    inicio, fin = paginar(len(tabla), "v24_entidades")
    pagina = tabla.iloc[inicio:fin].copy()

    st.dataframe(
        pagina.rename(columns={
            "entidad_id": "Identificador",
            "entidad": "Entidad"
        }),
        hide_index=True,
        width="stretch",
        height=400
    )

    opciones = list(pagina.index)

    def etiqueta_entidad(i):
        fila = tabla.loc[i]
        nombre = fila["entidad"] or "Entidad sin nombre"
        return f"{nombre} · {fila['Perfiles']} perfiles"

    seleccionado = st.selectbox(
        "Seleccionar entidad para consultar funcionarios",
        opciones,
        format_func=etiqueta_entidad,
        key="v24_entidad_seleccionada"
    )

    fila = tabla.loc[seleccionado]
    entidad_id = fila["entidad_id"]
    nombre_entidad = fila["entidad"]

    funcionarios = df[
        df["entidad_id"].fillna("").astype(str).eq(entidad_id) &
        df["entidad"].fillna("").astype(str).eq(nombre_entidad)
    ].copy()

    funcionarios = funcionarios.sort_values(
        ["nombre", "id_funcionario"],
        na_position="last"
    ).reset_index(drop=True)

    st.divider()
    st.subheader(nombre_entidad or "Entidad sin nombre")
    st.caption(
        f"Identificador: {entidad_id or 'No informado'} "
        f"· {len(funcionarios):,} perfiles asociados"
    )

    consulta = st.text_input(
        "Buscar funcionario o cargo dentro de esta entidad",
        key="v24_busqueda_funcionarios_entidad"
    )

    if consulta:
        termino = normalizar(consulta)
        coincidencias = (
            funcionarios["nombre"].fillna("").map(normalizar)
            .str.contains(termino, regex=False) |
            funcionarios["cargo"].fillna("").map(normalizar)
            .str.contains(termino, regex=False)
        )
        funcionarios = funcionarios[coincidencias].reset_index(drop=True)

    st.write(f"**{len(funcionarios):,} funcionarios encontrados**")

    if funcionarios.empty:
        st.info("No hay funcionarios que coincidan con la búsqueda.")
        return

    inicio_f, fin_f = paginar(
        len(funcionarios), "v24_funcionarios_entidad"
    )
    lote = funcionarios.iloc[inicio_f:fin_f]

    columnas = [
        "nombre", "cargo", "estado",
        "fecha_inicio", "fecha_fin", "perfil"
    ]

    st.dataframe(
        lote[columnas].rename(columns={
            "nombre": "Funcionario",
            "cargo": "Cargo publicado",
            "estado": "Extracción",
            "fecha_inicio": "Inicio publicado",
            "fecha_fin": "Fin publicado",
            "perfil": "Ficha oficial"
        }),
        hide_index=True,
        width="stretch",
        height=420,
        column_config={
            "Ficha oficial": st.column_config.LinkColumn(
                "Ficha oficial",
                display_text="Abrir ficha"
            )
        }
    )

    opciones_funcionarios = list(lote.index)

    def etiqueta_funcionario(i):
        persona = funcionarios.loc[i]
        return (
            f"{persona['nombre'] or 'Sin nombre'} "
            f"· ID {persona['id_funcionario']}"
        )

    elegido = st.selectbox(
        "Ver detalle del funcionario",
        opciones_funcionarios,
        format_func=etiqueta_funcionario,
        key="v24_funcionario_entidad_seleccionado"
    )

    persona = funcionarios.loc[elegido]

    with st.container(border=True):
        ficha, declaraciones = st.tabs([
            "Ficha profesional", "Declaraciones"
        ])

        with ficha:
            mostrar_ficha(persona)

        with declaraciones:
            mostrar_declaraciones(persona, modo, ruta)

    st.caption(
        "Relaciones jerárquicas y adscripciones: pendientes "
        "de validación con fuentes oficiales."
    )

def main(fichas=False):
    st.set_page_config(page_title='Radar Estado Perú · V2.4', page_icon='🇵🇪', layout='wide')
    referencia = hoy_lima()
    try:
        modo, ruta = fuente_configurada()
        firma = firma_fuente(modo, ruta)
        with st.spinner('Cargando perfiles y validando enlaces…'):
            df = cargar(modo, str(ruta), firma, referencia)
        actualizacion = fecha_fuente(modo, ruta, firma)
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        st.error(f'No se pudo cargar la fuente: {error}')
        st.stop()
    seccion = estructura(len(df), actualizacion, fichas)
    if seccion == 'Inicio':
        st.header('Información pública, en un solo lugar')
        st.write('Consulte perfiles de funcionarios, explore entidades y acceda a las fuentes oficiales.')
        indicadores(df)
        with st.container(border=True):
            st.subheader('Directorio de funcionarios')
            st.write('Busque por nombre, cargo o entidad. Revise la ficha profesional y los enlaces de declaraciones.')
            st.button('Explorar fichas profesionales', on_click=lambda: st.session_state.update(seccion='Fichas profesionales'), type='primary')
        st.info('Los perfiles son históricos. No certifican vigencia laboral ni integridad de las declaraciones.')
    elif seccion == 'Fichas profesionales':
        fichas_profesionales(df, modo, ruta)
    elif seccion == 'Entidades':
        mostrar_entidades(df, modo, ruta)
    elif seccion == 'Estadísticas':
        st.header('Estadísticas')
        indicadores(df)
        a, b = st.columns(2)
        with a:
            st.subheader('Estado de extracción')
            st.bar_chart(df.estado.value_counts().rename('Perfiles'), color='#275d90')
        with b:
            st.subheader('Declaraciones: evidencia local')
            st.dataframe(df.declaraciones.value_counts().rename_axis('Estado').reset_index(name='Perfiles'), hide_index=True, width='stretch')
        st.subheader('Especialidades de perfiles OK')
        grupos = df[df.estado == 'ok'].especialidad.str.split(' | ', regex=False).explode().value_counts()
        st.bar_chart(grupos.rename('Perfiles'), color='#275d90', horizontal=True)
        st.caption('Clasificación por palabras del cargo. Un perfil puede pertenecer a varias especialidades.')
    elif seccion == 'Fuentes y metodología':
        st.header('Fuentes y metodología')
        st.markdown('**Perfiles:** Gob.pe. **Declaraciones juradas de intereses:** enlaces a la consulta pública de Contraloría registrados en la extracción.')
        st.markdown('**Validación local:** coincidencia entre ID, URL del perfil, enlace del payload y tabla de control. Solo se admiten destinos oficiales con formato válido.')
        st.markdown('**Límite de verificación:** enlace registrado no significa documento leído, titular confirmado o contenido verificado. Los enlaces compartidos por varias fichas requieren revisión.')
        st.markdown('**Estados:** sin enlace encontrado requiere un control explícito. Sin resultado registrado puede significar pendiente o fallo no persistido. Los errores HTTP de perfiles se distinguen de la disponibilidad de documentos.')
        st.markdown('**Antigüedad:** meses completos desde la fecha publicada; una fecha de fin válida limita el cálculo. No se presume continuidad laboral.')
        st.markdown('**Actualización:** la cabecera muestra la modificación del archivo SQLite/WAL o la exportación de la instantánea. No acredita una revisión simultánea de todos los perfiles. Las fechas publicadas por Gob.pe se conservan en cada ficha.')
        fechas = pd.to_datetime(df.fecha_consulta, errors='coerce', utc=True, format='mixed').dropna()
        st.write('Última consulta de perfil registrada:', fechas.max().tz_convert('America/Lima').strftime('%d/%m/%Y %H:%M (Lima)') if not fechas.empty else 'No informada')
        st.caption(f'Fecha de referencia para calcular antigüedad: {referencia:%d/%m/%Y} (Lima).')
    else:
        st.header('Configuración')
        st.caption('Configuración efectiva de esta sesión local.')
        st.write('Fuente:', 'SQLite · solo lectura' if modo == 'sqlite' else 'Instantánea validada')
        st.code(str(ruta), language=None)
        st.write('Caché: 60 segundos; actualización en la siguiente interacción.')
        if st.button('Actualizar lectura local'):
            cargar.clear()
            st.rerun()
        st.caption('La actualización vuelve a leer la fuente; no ejecuta extracción ni modifica la base.')
    st.divider()
    st.caption('Radar Estado Perú · V2.4 en desarrollo · Fuente: Gob.pe / Contraloría · Consulta histórica')
