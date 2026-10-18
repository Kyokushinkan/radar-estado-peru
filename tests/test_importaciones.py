"""Regression: fresh interpreters with Streamlit's script-directory precedence."""
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ImportResolutionTests(unittest.TestCase):
    def test_entrypoints_in_fresh_processes(self):
        from app.datos import CAMPOS
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp)/'fixture.csv.gz'
            text = io.StringIO()
            writer = csv.DictWriter(text,fieldnames=CAMPOS,delimiter=';')
            writer.writeheader()
            row = dict.fromkeys(CAMPOS,'')
            row.update(id_funcionario='001',nombre='Ana',estado='ok',calidad_payload='ok',fecha_inicio='31 ene 2026')
            writer.writerow(row)
            content = gzip.compress(text.getvalue().encode('utf-8-sig'))
            snapshot.write_bytes(content)
            Path(str(snapshot)+'.manifest.json').write_text(json.dumps({
                'version_esquema':1,'sha256':hashlib.sha256(content).hexdigest(),
                'registros':1,'fecha_exportacion_utc':'2026-10-18T00:00:00Z'}),encoding='utf-8')
            env = dict(os.environ,RADAR_SOURCE='snapshot',RADAR_SNAPSHOT=str(snapshot),RADAR_DB='DOES_NOT_EXIST')
            script = r'''
import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest
root = Path(sys.argv[1])
entry = root / sys.argv[2]
# The root is already present, but AFTER app/app.py: original failure condition.
sys.path[:] = [str(root/'app'),str(entry.parent),str(root)] + [p for p in sys.path if p not in (str(root),str(root/'app'))]
assert 'app' not in sys.modules
at = AppTest.from_file(str(entry),default_timeout=45).run()
assert not at.exception, [e.message for e in at.exception]
assert not at.error, [e.value for e in at.error]
assert len(at.dataframe[0].value) == 1
import app
assert Path(app.__file__).resolve() == root/'app/__init__.py'
at.text_input(key='consulta').set_value('nothing_matches').run()
assert not at.exception
assert len(at.dataframe[0].value) == 0
'''
            for cwd in (ROOT,ROOT/'app'):
                for entry in ('app/Panel_de_funcionarios.py','app/app.py','app/pages/1_Fichas_profesionales.py'):
                    with self.subTest(cwd=str(cwd),entry=entry):
                        result = subprocess.run([sys.executable,'-B','-c',script,str(ROOT),entry],
                            cwd=cwd,env=env,capture_output=True,text=True,timeout=90)
                        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
