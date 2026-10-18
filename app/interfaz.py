"""Interfaz compartida de Radar Estado Perú V2.3."""
import json
import os
from pathlib import Path
import sqlite3
import pandas as pd
import streamlit as st
from app.antiguedad import hoy_lima
from app.datos import DB_PATH, ROOT, leer_sqlite, leer_instantanea, enriquecer, cobertura, filtrar, exportar_csv, enlace_valido

RANGOS = ['Todos','Menos de 1 año','De 1 a menos de 3 años','De 3 a menos de 5 años','5 años o más','Sin antigüedad calculable']


def fuente_configurada():
    modo = os.environ.get('RADAR_SOURCE', 'sqlite').lower()
    if modo not in ('sqlite','snapshot'):
        raise ValueError('RADAR_SOURCE debe ser sqlite o snapshot')
    valor = os.environ.get('RADAR_SNAPSHOT') if modo == 'snapshot' else os.environ.get('RADAR_DB')
    if modo == 'snapshot' and not valor:
        raise ValueError('Define RADAR_SNAPSHOT con la ruta de una instantánea validada')
    ruta = Path(valor) if valor else DB_PATH
    if not ruta.is_absolute():
        ruta = ROOT / ruta
    return modo, ruta


@st.cache_data(show_spinner=False, ttl=60)
def cargar(modo, ruta, firma, referencia):
    datos = leer_sqlite(ruta) if modo == 'sqlite' else leer_instantanea(ruta)
    return enriquecer(datos, referencia)


def firma_fuente(modo, ruta):
    archivos = [ruta, Path(str(ruta)+'-wal')] if modo == 'sqlite' else [ruta, Path(str(ruta)+'.manifest.json')]
    return tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in archivos if p.exists())


def mostrar_ficha(persona):
    st.subheader(persona['nombre'] or 'Nombre no informado')
    for campo, titulo in [('cargo','Cargo'),('entidad','Entidad'),('fecha_inicio','Fecha de inicio'),
                          ('fecha_fin','Fecha de fin publicada'),('antiguedad_estimada','Antigüedad estimada en el cargo'),
                          ('fecha_actualizacion','Última actualización')]:
        st.write(f'**{titulo}:**', persona[campo] or 'No informado')
    for campo, titulo in [('resumen','Resumen profesional'),('formacion_academica','Formación académica'),('experiencia_profesional','Experiencia profesional')]:
        with st.expander(titulo, expanded=campo == 'resumen'):
            st.write(persona[campo] or 'No informado')
    for campo, titulo in [('perfil','Ficha Gob.pe'),('norma','Norma de nombramiento'),('declaracion_jurada','Declaración jurada de intereses')]:
        if enlace_valido(persona[campo]):
            st.link_button(titulo, persona[campo])


def main(fichas=False):
    st.set_page_config(page_title='Radar Estado Perú · V2.3', page_icon='🇵🇪', layout='wide')
    st.caption('RADAR ESTADO PERÚ · VERSIÓN 2.3')
    st.title('Fichas profesionales' if fichas else 'Panel de funcionarios públicos')
    st.info('La antigüedad es estimada desde la fecha de inicio publicada. No confirma la continuidad del nombramiento ni que la persona siga en funciones. Si existe fecha de fin válida, el cálculo termina en ella.')
    referencia = hoy_lima()
    try:
        modo, ruta = fuente_configurada()
        with st.spinner('Cargando funcionarios…'):
            df = cargar(modo, str(ruta), firma_fuente(modo,ruta), referencia)
        if modo == 'snapshot':
            manifiesto = json.loads(Path(str(ruta)+'.manifest.json').read_text(encoding='utf-8'))
            st.caption(f"Instantánea: {manifiesto['fecha_exportacion_utc']} · Referencia de antigüedad: {referencia:%d/%m/%Y} (Lima)")
        else:
            st.caption(f'Fuente local SQLite · Referencia de antigüedad: {referencia:%d/%m/%Y} (Lima)')
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        st.error(f'No se pudo cargar la fuente: {error}')
        st.stop()
    c = cobertura(df)
    columnas = st.columns(4)
    columnas[0].metric('Perfiles OK', f"{c['perfiles_ok']:,}")
    columnas[1].metric('Registros totales', f"{c['registros']:,}")
    for col, titulo, clave in [(columnas[2],'Con fecha de inicio','con_fecha_inicio'),(columnas[3],'Con declaración enlazada','con_declaracion_jurada')]:
        porcentaje = 100*c[clave]/c['perfiles_ok'] if c['perfiles_ok'] else 0
        col.metric(titulo, f"{c[clave]:,}", f'{porcentaje:.1f}% de perfiles OK', delta_color='off')
    consulta = st.text_input('Nombre, cargo o entidad', key='consulta')
    a,b,c1 = st.columns(3)
    entidad = a.selectbox('Entidad', ['Todas']+sorted(x for x in df.entidad.unique() if x), key='entidad')
    grupos = sorted({g for valor in df.especialidad for g in valor.split(' | ')})
    grupo = b.selectbox('Especialidad', ['Todas']+grupos, key='grupo')
    solo_ok = c1.checkbox('Solo perfiles OK', value=True, key='solo_ok')
    a,b = st.columns(2)
    rango = a.selectbox('Rango de antigüedad (meses completos)', RANGOS, key='rango')
    orden = b.selectbox('Ordenar por', ['Nombre','Mayor antigüedad','Menor antigüedad'], key='orden')
    resultado = filtrar(df,consulta,entidad,grupo,rango,orden,solo_ok)
    st.write(f'**{len(resultado):,} perfiles encontrados**')
    campos = ['nombre','cargo','entidad','fecha_inicio','antiguedad_estimada','antiguedad_meses','estado_fecha','fecha_fin','perfil','norma','declaracion_jurada']
    tabla = resultado[campos].copy()
    for campo in ('perfil','norma','declaracion_jurada'):
        tabla[campo] = tabla[campo].where(tabla[campo].map(enlace_valido), '')
    st.dataframe(tabla, hide_index=True, width='stretch', height=450, column_config={
        'perfil':st.column_config.LinkColumn('Ficha oficial',display_text='Ver ficha'),
        'norma':st.column_config.LinkColumn('Nombramiento',display_text='Ver norma'),
        'declaracion_jurada':st.column_config.LinkColumn('Declaración jurada',display_text='Ver declaración'),
        'antiguedad_estimada':'Antigüedad estimada', 'antiguedad_meses':'Meses completos'})
    st.download_button('Exportar resultados CSV', exportar_csv(resultado), file_name='radar_estado_v2_3.csv', mime='text/csv', disabled=resultado.empty)
    if not resultado.empty:
        opciones = {
            ' '.join(f"{i} · {p['nombre']} | {p['entidad']} | {p['cargo']}".split()): i
            for i, p in resultado.iterrows()
        }
        etiqueta = st.selectbox('Seleccionar funcionario', list(opciones), key='funcionario')
        elegido = opciones[etiqueta]
        mostrar_ficha(resultado.loc[elegido])
    if not fichas:
        with st.expander('Distribución por entidad y especialidad'):
            st.dataframe(df[df.estado == 'ok'].groupby(['entidad_id','entidad']).size().reset_index(name='Perfiles').sort_values('Perfiles',ascending=False),hide_index=True)
            st.dataframe(df[df.estado == 'ok'].especialidad.str.split(' | ',regex=False).explode().value_counts().rename_axis('Especialidad').reset_index(name='Perfiles'),hide_index=True)
            st.caption('Clasificación automática por palabras del cargo. Un perfil puede pertenecer a varias especialidades.')
    st.caption('Fuente: perfiles públicos de Gob.pe. Consulta histórica; no acredita vigencia laboral.')
