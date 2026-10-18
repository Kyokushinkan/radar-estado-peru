"""Meses completos por aniversarios anclados al día original.

Si el mes destino no tiene ese día, se usa su último día. Se toma el
máximo número de aniversarios no posterior a la referencia; años y meses
son divmod(total, 12), y días es la diferencia desde ese aniversario.
Ejemplo: 31 ene -> 28 feb = 1 mes; 31 ene -> 1 mar = 1 mes, 1 día.
"""
import calendar
from datetime import date, datetime, timedelta, timezone
import re

MESES = dict(zip(('ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'), range(1,13)))
MESES['set'] = 9


def hoy_lima():
    return datetime.now(timezone(timedelta(hours=-5))).date()


def convertir_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    cadena = str(valor or '').strip()
    try:
        return date.fromisoformat(cadena)
    except ValueError:
        pass
    match = re.fullmatch(r'(\d{1,2})\s+([a-zA-Z]{3})\s+(\d{4})', cadena)
    if not match:
        return None
    dia, mes, anio = match.groups()
    try:
        return date(int(anio), MESES.get(mes.lower(), 0), int(dia))
    except ValueError:
        return None


def aniversario(inicio, meses):
    anio, mes = divmod(inicio.year * 12 + inicio.month - 1 + meses, 12)
    return date(anio, mes + 1, min(inicio.day, calendar.monthrange(anio, mes + 1)[1]))


def componentes(valor, referencia=None):
    inicio = convertir_fecha(valor)
    fin = referencia or hoy_lima()
    if inicio is None or inicio > fin:
        return None
    meses = (fin.year - inicio.year) * 12 + fin.month - inicio.month
    if aniversario(inicio, meses) > fin:
        meses -= 1
    anios, resto = divmod(meses, 12)
    return anios, resto, (fin - aniversario(inicio, meses)).days


def antiguedad_meses(valor, referencia=None):
    partes = componentes(valor, referencia)
    return None if partes is None else partes[0] * 12 + partes[1]


def calcular_antiguedad(valor, referencia=None):
    inicio = convertir_fecha(valor)
    if inicio is None:
        return 'Sin dato'
    partes = componentes(inicio, referencia)
    if partes is None:
        return 'Fecha futura'
    unidades = [('año', 'años'), ('mes', 'meses'), ('día', 'días')]
    return ', '.join(f'{n} {unidad[n != 1]}' for n, unidad in zip(partes, unidades) if n) or '0 días'
