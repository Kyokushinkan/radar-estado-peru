import json
import unittest
from datetime import date
from app.datos import normalizar_registros, enriquecer, CAMPOS, filtrar

class DatosTests(unittest.TestCase):
    def test_normalizacion_y_fechas(self):
        p = {'id_funcionario':'001', 'nombre':'Ana María', 'cargo_publicado':'Directora',
             'informacion_adicional':{'FORMACIÓN ACADÉMICA':'Ingeniera','Fecha de inicio':'31 ene 2026',
                                      'declaracion_jurada_url':'https://example.org/doc'}}
        df = normalizar_registros([('ok',json.dumps(p)),('error','[]'),('error','{')])
        self.assertEqual(list(df.columns), CAMPOS)
        self.assertEqual(df.iloc[0].formacion_academica, 'Ingeniera')
        self.assertEqual(df.iloc[0].id_funcionario, '001')
        datos = enriquecer(df,date(2026,3,1))
        self.assertEqual(datos.iloc[0].antiguedad_estimada, '1 mes, 1 día')
        self.assertEqual(len(filtrar(datos, 'MARIA ana')), 1)
        self.assertTrue(filtrar(datos, '.*').empty)
        self.assertTrue(enriquecer(normalizar_registros([])).empty)

    def test_fin_de_cargo(self):
        p = {'informacion_adicional':{'Fecha de inicio':'31 ene 2026','Fecha de fin':'28 feb 2026'}}
        df = enriquecer(normalizar_registros([('ok',json.dumps(p))]),date(2026,10,18))
        self.assertEqual(df.iloc[0].antiguedad_meses, 1)
        self.assertEqual(df.iloc[0].estado_fecha, 'Con fecha de fin')

    def test_rangos_orden_y_csv(self):
        import io
        import pandas as pd
        from app.datos import exportar_csv
        filas = []
        for fid, inicio in [('0','1 oct 2026'),('1','1 oct 2025'),('2','1 oct 2023'),('3','1 oct 2021'),('4','')]:
            filas.append(('ok',json.dumps({'id_funcionario':fid,'nombre':'=formula' if fid == '0' else fid,'informacion_adicional':{'Fecha de inicio':inicio}})))
        df = enriquecer(normalizar_registros(filas),date(2026,10,18))
        for rango, esperado in [('Menos de 1 año','0'),('De 1 a menos de 3 años','1'),('De 3 a menos de 5 años','2'),('5 años o más','3'),('Sin antigüedad calculable','4')]:
            self.assertEqual(filtrar(df,rango=rango).id_funcionario.tolist(),[esperado])
        self.assertEqual(filtrar(df,orden='Mayor antigüedad').id_funcionario.tolist(),['3','2','1','0','4'])
        salida = exportar_csv(filtrar(df,rango='Menos de 1 año'))
        self.assertTrue(salida.startswith(b'\xef\xbb\xbf'))
        csv = pd.read_csv(io.BytesIO(salida),sep=';',dtype=str,keep_default_na=False)
        self.assertEqual(csv.iloc[0]['nombre'], "'=formula")
        self.assertNotIn('_busqueda',csv.columns)
