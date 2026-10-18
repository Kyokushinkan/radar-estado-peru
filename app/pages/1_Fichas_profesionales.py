"""Vista de fichas con el mismo contrato y filtros que el panel."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Streamlit prepends the script directory; the repository must take priority.
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))
from app.interfaz import main

main(fichas=True)
