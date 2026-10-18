"""Pruebas de interfaz V2.3 con SQLite temporal sintético."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

class RadarTests(unittest.TestCase):
    def test_paginas_y_lanzador(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/'fixture.sqlite3'
            with sqlite3.connect(db) as conn:
                conn.execute('CREATE TABLE profiles(result TEXT,payload TEXT)')
                for fid, inicio in [('001','31 ene 2026'),('002','')]:
                    conn.execute('INSERT INTO profiles VALUES (?,?)',('ok',json.dumps({'id_funcionario':fid,'nombre':'Ana María '+fid,'cargo_publicado':'Directora','entidad_publica':'Entidad prueba','informacion_adicional':{'Fecha de inicio':inicio}})))
            conn.close()
            with patch.dict(os.environ, {'RADAR_SOURCE':'sqlite','RADAR_DB':str(db)}):
                for pagina in ['app/Panel_de_funcionarios.py','app/pages/1_Fichas_profesionales.py','app/app.py']:
                    with self.subTest(pagina=pagina):
                        at = AppTest.from_file(pagina,default_timeout=30).run()
                        self.assertEqual(list(at.exception), [])
                        self.assertEqual(len(at.dataframe[0].value),2)
                        at.selectbox(key='rango').set_value('Sin antigüedad calculable').run()
                        self.assertEqual(len(at.dataframe[0].value),1)
                        at.text_input(key='consulta').set_value('sincoincidencia').run()
                        self.assertEqual(len(at.dataframe[0].value),0)
                        self.assertEqual(list(at.exception), [])
