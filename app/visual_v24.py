"""Presentación institucional exclusiva de V2.4."""
from html import escape
import streamlit as st

SECCIONES = ["Inicio", "Fichas profesionales", "Entidades", "Estadísticas",
             "Fuentes y metodología", "Configuración"]


def estructura(total, actualizacion, fichas=False):
    st.markdown("""
<style>
.stApp { background: #f5f8fc; }
.block-container { max-width: 1540px; padding-top: 2rem; }
[data-testid="stSidebar"] { background: #edf3fa; border-right: 1px solid #d9e4f0; }
[data-testid="stMetric"] { background: white; border: 1px solid #d9e4f0;
  border-radius: 12px; padding: 18px; }
[data-testid="stBaseButton-primary"] { background: #174a78; border-color: #174a78; color: white; }
[data-testid="stBaseButton-primary"]:hover { background: #10385c; border-color: #10385c; color: white; }
[data-testid="stSidebar"] label:has(input:checked) { color: #174a78; font-weight: 650; }
[data-testid="stSidebar"] label:has(input:checked) > div:first-child { background-color: #174a78; }
[role="tab"][aria-selected="true"] { color: #174a78; }
[data-baseweb="tab-highlight"] { background-color: #174a78; }
a { color: #174a78; }
.radar-header { background: #102d50; color: white; border-radius: 16px;
  padding: 30px 34px; margin-bottom: 26px; }
.radar-header h1 { color: white; font-size: clamp(1.8rem, 4vw, 2.65rem);
  padding: 6px 0 8px; font-weight: 700; letter-spacing: -.035em; }
.radar-header p { color: #dfebfa; margin: 0 0 18px; }
.radar-version { display: inline-block; font-size: .8rem; color: #dcecff;
  border: 1px solid #6383a6; border-radius: 20px; padding: 4px 12px; }
.radar-meta { display: flex; gap: 12px 30px; flex-wrap: wrap;
  border-top: 1px solid #436080; padding-top: 16px; font-size: .88rem; color: #dcecff; }
@media(max-width: 640px) {
 .block-container { padding: 1rem; }
 .radar-header { padding: 22px 20px; border-radius: 12px; }
}
</style>""", unsafe_allow_html=True)
    st.markdown(
        '<header class="radar-header"><span class="radar-version">'
        'Versión 2.4 — En desarrollo</span><h1>Radar Estado Perú</h1>'
        '<p>Funcionarios públicos · Transparencia · Datos abiertos</p>'
        f'<div class="radar-meta"><span>{total:,} perfiles de funcionarios</span>'
        f'<span>{escape(actualizacion)}</span></div></header>',
        unsafe_allow_html=True,
    )
    with st.sidebar:
        st.markdown("### Radar Estado Perú")
        st.caption("CONSULTA INSTITUCIONAL")
        seccion = st.radio("Navegación", SECCIONES, index=1 if fichas else 0, key="seccion")
        st.divider()
        st.caption("V2.4 · Entorno de desarrollo")
        st.caption("Perfiles históricos de Gob.pe. Un perfil no acredita un cargo vigente.")
    return seccion
