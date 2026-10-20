"""Entrada local independiente; conserva las entradas públicas V2.3."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from app.interfaz_v24 import main
import streamlit as st

if __name__ == "__main__":
    # Evita que Streamlit incorpore automáticamente app/pages (entradas V2.3).
    st.navigation([st.Page(main, title="Radar Estado Perú V2.4")], position="hidden").run()
