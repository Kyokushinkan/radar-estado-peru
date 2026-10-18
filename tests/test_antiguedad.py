import unittest
from datetime import date, timedelta
from app.antiguedad import aniversario, componentes, convertir_fecha, calcular_antiguedad, antiguedad_meses

class AntiguedadTests(unittest.TestCase):
    def test_limites(self):
        for inicio, fin, texto, meses in [
            ('31 ene 2026', date(2026,3,1), '1 mes, 1 día', 1),
            ('31 ene 2026', date(2026,2,28), '1 mes', 1),
            ('31 ene 2024', date(2024,2,29), '1 mes', 1),
            ('29 feb 2024', date(2025,2,28), '1 año', 12),
            ('31 dic 2025', date(2026,1,30), '30 días', 0),
            ('1 mar 2026', date(2026,3,1), '0 días', 0),
        ]:
            with self.subTest(inicio=inicio, fin=fin):
                self.assertEqual(calcular_antiguedad(inicio, fin), texto)
                self.assertEqual(antiguedad_meses(inicio, fin), meses)

    def test_fechas(self):
        for valor in (None, '', '31 feb 2026', '29 feb 2025', 'abc', '1 xxx 2026'):
            self.assertIsNone(convertir_fecha(valor))
            self.assertIsNone(antiguedad_meses(valor))
        self.assertEqual(convertir_fecha(' 1 SET 2026 '), date(2026,9,1))
        self.assertEqual(convertir_fecha('2026-09-01'), date(2026,9,1))
        self.assertEqual(calcular_antiguedad('2 mar 2026', date(2026,3,1)), 'Fecha futura')

    def test_coherencia_calendario(self):
        for inicio in (date(2023,1,31), date(2024,2,29), date(2025,12,31)):
            for delta in range(800):
                fin = inicio + timedelta(days=delta)
                a,m,d = componentes(inicio, fin)
                total = antiguedad_meses(inicio, fin)
                self.assertEqual(total, a*12+m)
                self.assertGreaterEqual(d, 0)
                self.assertEqual(aniversario(inicio,total)+timedelta(days=d), fin)
                self.assertGreater(aniversario(inicio,total+1), fin)
