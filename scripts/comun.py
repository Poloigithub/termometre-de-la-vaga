"""Utilidades compartidas: configuración, descargas fiables, estado y hora civil."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yaml

RAIZ = Path(__file__).resolve().parent.parent
RAW = RAIZ / "data" / "raw"
PROCESADO = RAIZ / "data" / "processed"
LOG = RAIZ / "data" / "log"
ESTADO = RAIZ / "data" / "estado.json"
TZ = "Europe/Madrid"
FORMATO_SELLO = "%Y%m%dT%H%MZ"


def cargar_config():
    with open(RAIZ / "config.yaml", encoding="utf8") as f:
        cfg = yaml.safe_load(f)
    cfg["dia_huelga"] = str(cfg["dia_huelga"])
    cfg["dias_referencia"] = [str(d) for d in cfg["dias_referencia"]]
    cfg["validacion"]["festivo"] = str(cfg["validacion"]["festivo"])
    cfg["validacion"]["referencias"] = [str(d) for d in cfg["validacion"]["referencias"]]
    cfg["calibracion"]["periodos"] = [[str(a), str(b)] for a, b in cfg["calibracion"]["periodos"]]
    return cfg


def dias_comparados(cfg):
    return sorted({cfg["dia_huelga"], *cfg["dias_referencia"]})


def dias_validacion(cfg):
    return sorted({cfg["validacion"]["festivo"], *cfg["validacion"]["referencias"]})


def periodos_calibracion(cfg):
    """Miércoles de cada periodo de calibración, en listas separadas."""
    return [
        [d.strftime("%Y-%m-%d") for d in pd.date_range(a, b, freq="W-WED")]
        for a, b in cfg["calibracion"]["periodos"]
    ]


def dias_calibracion(cfg):
    return sorted(d for periodo in periodos_calibracion(cfg) for d in periodo)


def dias_medidos(cfg):
    return sorted({*dias_comparados(cfg), *dias_validacion(cfg), *dias_calibracion(cfg)})


def hoy_local():
    return datetime.now(ZoneInfo(TZ)).strftime("%Y-%m-%d")


def dias_disponibles(dias):
    """Solo los días que ya han empezado."""
    hoy = hoy_local()
    return [d for d in dias if d <= hoy]


def sello():
    return datetime.now(timezone.utc).strftime(FORMATO_SELLO)


def registrar(mensaje):
    LOG.mkdir(parents=True, exist_ok=True)
    linea = f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ} {mensaje}"
    print(linea)
    with open(LOG / "descargas.log", "a", encoding="utf8") as f:
        f.write(linea + "\n")


def pedir(url, intentos=4, valido=None, metodo="GET", **kwargs):
    """Petición con reintentos y espera. Rechaza respuestas cortadas: el portal
    de la Generalitat y el visor de REE devuelven a veces un 200 incompleto."""
    kwargs.setdefault("timeout", 90)
    ultimo = None
    for intento in range(intentos):
        try:
            r = requests.request(metodo, url, **kwargs)
            esperado = r.headers.get("Content-Length")
            cortada = (
                metodo == "GET"
                and esperado is not None
                and "Content-Encoding" not in r.headers
                and len(r.content) != int(esperado)
            )
            if r.ok and not cortada and (valido is None or valido(r)):
                return r
            ultimo = f"http {r.status_code}, {len(r.content)} bytes"
        except requests.RequestException as e:
            ultimo = type(e).__name__
        if intento < intentos - 1:
            time.sleep(2 * (intento + 1))
    raise RuntimeError(f"{url.split('?')[0]}: {ultimo}")


def guardar_raw(subcarpeta, nombre, contenido):
    """Escribe una respuesta original. Los ficheros de raw no se modifican nunca."""
    carpeta = RAW / subcarpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    if not ruta.exists():  # dos ejecuciones en el mismo minuto: gana la primera
        ruta.write_bytes(contenido)
    return ruta


def sello_de(ruta):
    """Fecha de descarga, que va al final del nombre del fichero."""
    return datetime.strptime(ruta.stem.rsplit("_", 1)[1], FORMATO_SELLO).replace(tzinfo=timezone.utc)


def ultimo_raw(subcarpeta, patron):
    candidatos = sorted((RAW / subcarpeta).glob(patron), key=sello_de)
    return candidatos[-1] if candidatos else None


def leer_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf8"))
    return {}


def escribir_estado(estado):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf8")


def anotar(estado, fuente, ok, **campos):
    e = estado.setdefault(fuente, {})
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    e["ultimo_intento"] = ahora
    error = campos.pop("error", "desconocido")
    e["error"] = None if ok else error
    if ok:
        e["ultima_correcta"] = ahora
    e.update(campos)


def etiqueta_a_civil(etiquetas):
    """Convierte la hora publicada por la red de aire a hora civil.

    Ni la Generalitat ni la Agencia Europea siguen el cambio de hora: la
    etiqueta L cubre [L-1, L) UTC todo el año. El resultado es el inicio de la
    hora en Europe/Madrid: L en horario de invierno, L+1 en horario de verano.
    """
    return (etiquetas.dt.tz_localize("UTC") - pd.Timedelta(hours=1)).dt.tz_convert(TZ)


def leer_demanda(ruta, dia):
    """Serie de 5 minutos de un día, en MW y hora local, de un raw del visor o de ESIOS."""
    texto = ruta.read_text(encoding="utf8")
    if ruta.name.startswith("visor"):
        filas = json.loads(texto[texto.index("(") + 1 : texto.rindex(")")])["valoresHorariosGeneracion"]
        d = pd.DataFrame(filas, columns=["ts", "dem"])
        t = pd.to_datetime(d["ts"], errors="coerce")
        v = pd.to_numeric(d["dem"], errors="coerce")
    else:
        d = pd.DataFrame(json.loads(texto)["indicator"]["values"], columns=["datetime", "value"])
        t = pd.to_datetime(d["datetime"], utc=True).dt.tz_convert(TZ).dt.tz_localize(None)
        v = pd.to_numeric(d["value"], errors="coerce")
    s = pd.Series(v.values, index=pd.DatetimeIndex(t))
    s = s[s.index.notna() & (s > 0)]
    return s[s.index.strftime("%Y-%m-%d") == dia].sort_index()
