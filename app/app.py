"""Lanzador compatible; la implementación vive en la entrada principal."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Streamlit prepends the script directory; the repository must take priority.
while str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))
from app.Panel_de_funcionarios import main

if __name__ == '__main__':
    main()
