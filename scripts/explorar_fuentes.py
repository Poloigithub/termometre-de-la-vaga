#!/usr/bin/env python3
"""Fase 1: exploración de fuentes del Termòmetre de la vaga.

Descarga un miércoles normal de cada fuente, guarda la respuesta original en
data/raw/fase1/ e imprime qué devuelve cada una. No calcula ningún indicador.

Uso: python scripts/explorar_fuentes.py [AAAA-MM-DD]
Con la variable ESIOS_TOKEN definida, comprueba además qué ofrece ESIOS.
"""
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

DIA = sys.argv[1] if len(sys.argv) > 1 else "2026-10-21"
TZ = "Europe/Madrid"
RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "fase1"
SELLO = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")

REE = "https://apidatos.ree.es/es/datos/demanda/evolucion"
VISIONA = "https://demanda.ree.es/WSvisionaMovilesPeninsulaRest/resources/demandaGeneracionPeninsula"
GVA = "https://dadesobertes.gva.es"
GVA_ULTIMOS = "20e3d8ff-ee72-47fe-95c6-c36a134648a5"
EEA = "https://eeadmz1-downloads-api-appservice.azurewebsites.net/ParquetFile/urls"
EEA_NO2 = "http://dd.eionet.europa.eu/vocabulary/aq/pollutant/8"
OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
ESIOS = "https://api.esios.ree.es"

# Códigos de la Red Valenciana (los mismos en la Agencia Europea).
ESTACIONES = {
    "12040010": ("Castelló - Grau", "urbana"),
    "12040015": ("Castelló - Patronat d'Esports", "urbana"),
    "12040020": ("Castelló - CEIP La Marina", "urbana"),
    "12009007": ("Almassora - CP Ochando", "contraste"),
    "12028001": ("Benicàssim", "contraste"),
    "12032001": ("Borriana", "contraste"),
    "12005005": ("L'Alcora", "contraste"),
}


def titulo(texto):
    print(f"\n{'=' * 8} {texto} {'=' * 8}")


def pedir(url, intentos=4, valido=None, **kwargs):
    """GET/POST con reintentos. Comprueba que la respuesta llega entera:
    el portal de la Generalitat corta a veces las descargas con un 200."""
    metodo = kwargs.pop("metodo", "GET")
    kwargs.setdefault("timeout", 90)
    ultimo = None
    for intento in range(intentos):
        try:
            r = requests.request(metodo, url, **kwargs)
            esperado = r.headers.get("Content-Length")
            cortada = (
                esperado is not None
                and "Content-Encoding" not in r.headers
                and len(r.content) != int(esperado)
            )
            if r.ok and not cortada and (valido is None or valido(r)):
                return r
            ultimo = f"http {r.status_code}, {len(r.content)} bytes"
        except requests.RequestException as e:
            ultimo = repr(e)[:160]
        time.sleep(2 * (intento + 1))
    raise RuntimeError(f"{url[:90]}: {ultimo}")


def guardar(nombre, contenido):
    RAW.mkdir(parents=True, exist_ok=True)
    ruta = RAW / f"{SELLO}_{nombre}"
    ruta.write_bytes(contenido)
    return ruta


def etiqueta_a_civil(fecha, hora):
    """Convierte la hora publicada por la Red Valenciana a hora civil.

    Las series no siguen el cambio de hora: la etiqueta L cubre [L-1, L) UTC,
    todo el año. Devuelve el inicio de la hora en Europe/Madrid. Con horario de
    invierno coincide con L; con horario de verano es L+1.
    """
    return (pd.Timestamp(f"{fecha} {hora:02d}:00", tz="UTC") - pd.Timedelta(hours=1)).tz_convert(TZ)


def visor_con_datos(r):
    """El visor responde a veces 200 con la lista vacía."""
    return b'"ts"' in r.content


def ree_url(trunc, limite, ids, ini, fin):
    return (
        f"{REE}?start_date={ini}&end_date={fin}&time_trunc={trunc}"
        f"&geo_trunc=electric_system&geo_limit={limite}&geo_ids={ids}"
    )


def explorar_ree():
    titulo("REE · REData: granularidad por ámbito")
    mes = DIA[:7]
    pruebas = [
        ("C. Valenciana, hora", "hour", "ccaa", 15, f"{DIA}T00:00", f"{DIA}T23:59"),
        ("C. Valenciana, día", "day", "ccaa", 15, f"{mes}-01T00:00", f"{mes}-28T23:59"),
        ("C. Valenciana, mes", "month", "ccaa", 15, "2026-01-01T00:00", f"{DIA}T23:59"),
        ("Península, hora", "hour", "peninsular", 8741, f"{DIA}T00:00", f"{DIA}T23:59"),
        ("Península, día", "day", "peninsular", 8741, f"{mes}-01T00:00", f"{mes}-28T23:59"),
    ]
    horaria = None
    for nombre, trunc, limite, ids, ini, fin in pruebas:
        r = requests.get(ree_url(trunc, limite, ids, ini, fin), timeout=60)
        if r.status_code != 200:
            print(f"  {nombre:22} http {r.status_code}: no disponible")
            continue
        valores = r.json()["included"][0]["attributes"]["values"]
        print(f"  {nombre:22} {len(valores)} valores; primero {valores[0]['datetime'][:16]} = {valores[0]['value']:.1f}")
        if trunc == "hour":
            guardar(f"ree_peninsular_hora_{DIA}.json", r.content)
            horaria = pd.Series(
                [v["value"] for v in valores],
                index=pd.to_datetime([v["datetime"][:16] for v in valores]),
            )

    titulo("REE · Visor de demanda (península, cada 5 min)")
    visor = None
    r = pedir(f"{VISIONA}?curva=DEMANDAAU&fecha={DIA}", valido=visor_con_datos)
    guardar(f"ree_visor_{DIA}.jsonp", r.content)
    texto = r.text
    filas = json.loads(texto[texto.index("(") + 1 : texto.rindex(")")])["valoresHorariosGeneracion"]
    d = pd.DataFrame(filas)
    d["ts"] = pd.to_datetime(d["ts"], errors="coerce")
    d = d[d["ts"].dt.strftime("%Y-%m-%d") == DIA]
    visor = d.set_index("ts")["dem"].resample("1h").mean()
    print(f"  {len(d)} filas el {DIA}; demanda en MW")
    if horaria is not None:
        x = pd.concat([horaria, visor], axis=1, join="inner").dropna()
        x.columns = ["redata", "visor"]
        dif = (x.visor / x.redata - 1) * 100
        print(f"  frente a REData: correlación {x.redata.corr(x.visor):.4f}; diferencia media {dif.mean():+.1f} % (de {dif.min():+.1f} a {dif.max():+.1f})")
    hoy = datetime.now().strftime("%Y-%m-%d")
    t = pedir(f"{VISIONA}?curva=DEMANDAAU&fecha={hoy}", valido=visor_con_datos).text
    ult = [f for f in json.loads(t[t.index("(") + 1 : t.rindex(")")])["valoresHorariosGeneracion"] if f.get("dem")][-1]
    print(f"  último dato del visor ahora: {ult['ts']} (reloj local {datetime.now():%H:%M})")


def explorar_esios():
    titulo("REE · ESIOS")
    token = os.environ.get("ESIOS_TOKEN")
    if not token:
        print("  Sin ESIOS_TOKEN: no se puede comprobar (la API responde 403).")
        return
    cab = {"Accept": "application/json; application/vnd.esios-api-v1+json", "x-api-key": token}
    lista = pedir(f"{ESIOS}/indicators", headers=cab).json()["indicators"]
    demanda = [i for i in lista if "demanda" in i["name"].lower()]
    print(f"  {len(lista)} indicadores, {len(demanda)} con 'demanda' en el nombre")
    for i in demanda:
        meta = pedir(f"{ESIOS}/indicators/{i['id']}", headers=cab).json()["indicator"]
        geos = [g["geo_name"] for g in meta.get("geos", [])]
        if any("valencia" in g.lower() for g in geos):
            print(f"  {i['id']}: {i['name']} -> {geos[:8]}")


def leer_eea(codigo):
    r = pedir(f"https://eeadmz1batchservice02.blob.core.windows.net/airquality-p/ES/SP_{codigo}_8_8.parquet")
    guardar(f"eea_no2_{codigo}.parquet", r.content)
    d = pd.read_parquet(io.BytesIO(r.content))
    d["Value"] = pd.to_numeric(d["Value"], errors="coerce")
    return d


def explorar_no2():
    titulo("Generalitat · últimos 2000 registros")
    esperado = pedir(
        f"{GVA}/api/3/action/datastore_search?resource_id={GVA_ULTIMOS}&limit=0",
        valido=lambda r: b'"total"' in r.content,
    ).json()["result"]["total"]

    def completo(r):
        return len(r.text.splitlines()) > esperado

    try:
        r = pedir(f"{GVA}/datastore/dump/{GVA_ULTIMOS}", valido=completo, intentos=5)
    except RuntimeError as e:
        print(f"  no llega completo tras 5 intentos: {e}")
    else:
        guardar("gva_ultimos.csv", r.content)
        d = pd.read_csv(io.BytesIO(r.content), dtype=str)
        print(f"  {len(d)} filas; {d.cd_estacion.nunique()} estaciones; {d.identificador.nunique()} parámetros")
        print(f"  cubre: {d.groupby(['fecha', 'hora']).size().to_dict()}")
    meta = pedir(f"{GVA}/api/3/action/resource_show?id={GVA_ULTIMOS}").json()["result"]
    print(f"  última actualización declarada: {meta['last_modified']}")

    titulo("Agencia Europea de Medio Ambiente · datos casi en tiempo real")
    dia = pd.Timestamp(DIA)
    urls = pedir(
        EEA,
        metodo="POST",
        json={
            "countries": ["ES"], "cities": [], "pollutants": [EEA_NO2], "dataset": 1,
            "dateTimeStart": f"{DIA}T00:00:00Z", "dateTimeEnd": f"{DIA}T23:59:59Z",
            "aggregationType": "hour",
        },
    ).text
    print(f"  {len(urls.split()) - 1} ficheros parquet de NO₂ en España")
    tablas = {}
    for codigo, (nombre, grupo) in ESTACIONES.items():
        d = leer_eea(codigo)
        buenos = d[(d.Validity >= 1) & (d.Value >= 0)].copy()
        # Start usa el mismo reloj que la Generalitat: se convierte a hora civil.
        civil = (buenos.Start.dt.tz_localize("UTC") - pd.Timedelta(hours=1)).dt.tz_convert(TZ)
        buenos.index = civil
        serie = buenos.Value[civil.dt.strftime("%Y-%m-%d").values == DIA]
        tablas[nombre] = pd.Series(serie.values, index=serie.index.hour).astype(float)
        print(f"  {nombre:32} {grupo:10} último válido {buenos.Start.max()} | {DIA}: {len(serie)}/24 horas")
    t = pd.DataFrame(tablas).reindex(range(24))
    urbanas = [n for n, g in ESTACIONES.values() if g == "urbana"]
    t["media urbana"] = t[urbanas].mean(axis=1)
    guardar(f"no2_civil_{DIA}.csv", t.to_csv().encode())
    print(f"\n  NO₂ (µg/m³) del {DIA} por hora civil de inicio:")
    print(t[urbanas + ["media urbana"]].round(1).to_string())

    titulo("Reloj de la red: comprobación")
    for f in (DIA, "2026-11-11"):
        print(f"  {f}, etiqueta 06 -> {etiqueta_a_civil(f, 6):%Y-%m-%d %H:%M %Z}")


def explorar_meteo():
    titulo("Open-Meteo · archivo")
    puntos = {"Castelló": (39.986, -0.04), "València": (39.47, -0.377)}
    for nombre, (lat, lon) in puntos.items():
        r = pedir(
            OPEN_METEO,
            params={
                "latitude": lat, "longitude": lon, "start_date": DIA, "end_date": DIA,
                "hourly": "temperature_2m,wind_speed_10m,precipitation", "timezone": TZ,
            },
        )
        guardar(f"openmeteo_{nombre.lower()}_{DIA}.json", r.content)
        j = r.json()
        h = pd.DataFrame(j["hourly"])
        print(f"  {nombre}: celda ({j['latitude']:.2f}, {j['longitude']:.2f}), {len(h)} horas, "
              f"{h.temperature_2m.min()}–{h.temperature_2m.max()} °C, "
              f"viento máx {h.wind_speed_10m.max()} km/h, lluvia {h.precipitation.sum():.1f} mm")


if __name__ == "__main__":
    print(f"Día explorado: {DIA} | descarga: {SELLO}")
    errores = []
    for paso in (explorar_ree, explorar_esios, explorar_no2, explorar_meteo):
        try:
            paso()
        except Exception as e:  # una fuente caída no debe tapar el resto
            errores.append(paso.__name__)
            print(f"  ERROR en {paso.__name__}: {e}")
    if errores:
        sys.exit(f"\nFuentes con error: {', '.join(errores)}")
