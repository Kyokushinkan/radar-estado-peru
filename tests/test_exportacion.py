import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import os
from streamlit.testing.v1 import AppTest
from app.datos import leer_instantanea, leer_sqlite
from scripts.exportar_instantanea import exportar

class ExportacionTests(unittest.TestCase):
    def test_exportacion_lectura_y_cloud(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/'origen.sqlite3'
            conn = sqlite3.connect(db)
            conn.execute('CREATE TABLE profiles(result TEXT,payload TEXT)')
            conn.execute('INSERT INTO profiles VALUES (?,?)',('ok',json.dumps({'id_funcionario':'001','nombre':'Ana','informacion_adicional':{'Fecha de inicio':'31 ene 2026','secreto':'NO_EXPORTAR'}})))
            conn.commit()
            conn.close()
            antes = hashlib.sha256(db.read_bytes()).hexdigest()
            salida = Path(tmp)/'publico.csv.gz'
            m = exportar(db,salida)
            self.assertEqual(antes,hashlib.sha256(db.read_bytes()).hexdigest())
            self.assertEqual(m['registros'],1)
            self.assertEqual(leer_instantanea(salida).iloc[0].id_funcionario,'001')
            self.assertNotIn('NO_EXPORTAR',leer_instantanea(salida).to_csv())
            with self.assertRaises(FileExistsError):
                exportar(db,salida)
            with patch.dict(os.environ, {'RADAR_SOURCE':'snapshot','RADAR_SNAPSHOT':str(salida),'RADAR_DB':'NO_EXISTE'}):
                for pagina in ['app/Panel_de_funcionarios.py','app/pages/1_Fichas_profesionales.py']:
                    at = AppTest.from_file(pagina,default_timeout=30).run()
                    self.assertEqual(list(at.exception),[])
                    self.assertEqual(len(at.dataframe[0].value),1)
            with salida.open('ab') as f:
                f.write(b'alterado')
            with self.assertRaises(ValueError):
                leer_instantanea(salida)

    def test_wal_escritura_activa(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/'wal.sqlite3'
            conn = sqlite3.connect(db)
            try:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('CREATE TABLE profiles(result TEXT,payload TEXT)')
                conn.execute('INSERT INTO profiles VALUES (?,?)',('ok','{"id_funcionario":"001"}'))
                conn.commit()
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('INSERT INTO profiles VALUES (?,?)',('ok','{"id_funcionario":"002"}'))
                self.assertEqual(len(leer_sqlite(db)),1)
                conn.commit()
                self.assertEqual(len(leer_sqlite(db)),2)
            finally:
                conn.close()
