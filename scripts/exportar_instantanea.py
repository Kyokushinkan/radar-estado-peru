"""Exporta una instantánea pública nueva; nunca sobrescribe ni escribe en SQLite."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from app.datos import DB_PATH, leer_sqlite, validar_publicos, cobertura, CAMPOS, enriquecer
from app.antiguedad import hoy_lima


def exportar(db, destino):
    destino = Path(destino)
    manifiesto_path = Path(str(destino)+'.manifest.json')
    if destino.exists() or manifiesto_path.exists():
        raise FileExistsError('La salida ya existe. Usa un nombre nuevo; no se sobrescribe.')
    inicio = time.monotonic()
    fecha = datetime.now(timezone.utc).isoformat()
    df = leer_sqlite(db)
    segundos_lectura = time.monotonic()-inicio
    validar_publicos(df)
    # Sólo la lista pública CAMPOS. No payload, controles del extractor ni evidencias.
    raw = df[CAMPOS].to_csv(index=False,sep=';').encode('utf-8-sig')
    comprimido = gzip.compress(raw, mtime=0)
    import pandas as pd
    recuperado = pd.read_csv(io.BytesIO(comprimido),compression='gzip',sep=';',dtype=str,keep_default_na=False)
    pd.testing.assert_frame_equal(df.reset_index(drop=True),recuperado)
    referencia = hoy_lima()
    enriquecidos = enriquecer(df,referencia)
    manifiesto = {
        'version_esquema':1, 'version_aplicacion':'2.3', 'fecha_exportacion_utc':fecha,
        'fecha_referencia_calidad':referencia.isoformat(), 'archivo':destino.name,
        'registros':len(df), 'columnas':CAMPOS, 'cobertura':cobertura(df),
        'calidad_fechas_ok':{str(k):int(v) for k,v in enriquecidos[enriquecidos.estado == 'ok'].estado_fecha.value_counts().items()},
        'sha256':hashlib.sha256(comprimido).hexdigest(), 'bytes_comprimidos':len(comprimido),
        'segundos_lectura_y_normalizacion':round(segundos_lectura,3),
        'nota':'Instantánea consistente de perfiles públicos; no confirma vigencia laboral. Cobertura sobre perfiles OK.',
    }
    destino.parent.mkdir(parents=True,exist_ok=True)
    # Creación exclusiva evita carreras y sobrescrituras. El manifiesto se publica al final.
    # Una interrupción deja un archivo sin manifiesto que la aplicación rechazará.
    with destino.open('xb') as archivo:
        archivo.write(comprimido)
    with manifiesto_path.open('x',encoding='utf-8') as archivo:
        json.dump(manifiesto,archivo,ensure_ascii=False,indent=2)
        archivo.write('\n')
    return manifiesto


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=DB_PATH)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    destino = args.output or ROOT/'data/public'/('funcionarios_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.csv.gz')
    print(json.dumps(exportar(args.db,destino),ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
