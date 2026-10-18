import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

st.set_page_config(
    page_title="Radar Estado Per?",
    page_icon="???",
    layout="wide"
)

paginas = [
    st.Page(
        "Panel_de_funcionarios.py",
        title="Panel de funcionarios",
        icon=":material/dashboard:",
        default=True
    ),
    st.Page(
        "pages/1_Fichas_profesionales.py",
        title="Fichas profesionales",
        icon=":material/badge:"
    )
]

navegacion = st.navigation(paginas)
navegacion.run()
