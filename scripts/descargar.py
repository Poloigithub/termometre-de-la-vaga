#!/usr/bin/env python3
"""Descarga las fuentes a data/raw/. Un fallo se registra y nunca rompe lo ya guardado."""
import os
from datetime import datetime, timedelta, timezone

import requests

from comun import (
    LOG, anotar, cargar_config, dias_comparados, dias_disponibles, dias_medidos, escribir_estado,
    guardar_raw, leer_demanda, leer_estado, pedir, registrar, sello, ultimo_raw,
)

VISOR = "https://demanda.ree.es/WSvisionaMovilesPeninsulaRest/resources/demandaGeneracionPeninsula"
ESIOS = "https://api.esios.ree.es/indicators"
GVA = "https://dadesobertes.gva.es"
GVA_ULTIMOS = "20e3d8ff-ee72-47fe-95c6-c36a134648a5"
GVA_2025 = "med-cont-atmos-mh-2025"
EEA_BLOB = "https://eeadmz1batchservice02.blob.core.windows.net/airquality-p/ES/SP_{}_8_8.parquet"
PORTAL_RED = "https://rvvcca.pica.gva.es/es"
METEO_ARCHIVO = "https://archive-api.open-meteo.com/v1/archive"
METEO_RECIENTE = "https://api.open-meteo.com/v1/forecast"
DIAS_ARCHIVO = 6       # antes de este margen el archivo de Open-Meteo puede ir incompleto
MUESTRAS_DIA = 286     # de 288 valores de 5 minutos


def dia_cerrado(dia):
    """El día ya terminó hace rato: lo descargado no va a cambiar."""
    limite = datetime.now(timezone.utc) - timedelta(hours=26)
    return dia < limite.strftime("%Y-%m-%d")


def demanda_descargada(dia):
    ruta = ultimo_raw("electricidad", f"*_{dia}_*")
    return ruta is not None and len(leer_demanda(ruta, dia)) >= MUESTRAS_DIA


def descargar_demanda(cfg, estado, marca):
    dias = dias_disponibles(dias_medidos(cfg))
    pendientes = [d for d in dias if not (dia_cerrado(d) and demanda_descargada(d))]
    fallos = []
    for dia in pendientes:
        try:
            r = pedir(f"{VISOR}?curva=DEMANDAAU&fecha={dia}", valido=lambda x: b'"ts"' in x.content)
            guardar_raw("electricidad", f"visor_{dia}_{marca}.jsonp", r.content)
        except RuntimeError as e:
            registrar(f"visor {dia}: {e}")
            fallos.append(dia)
    anotar(estado, "visor_ree", not fallos, error=f"Sin datos de {', '.join(fallos)}", pendientes=len(pendientes))

    # ESIOS es la misma serie: solo se usa si el visor falla y hay token.
    token = os.environ.get("ESIOS_TOKEN")
    if not fallos or not token:
        return
    cabeceras = {"Accept": "application/json; application/vnd.esios-api-v1+json", "x-api-key": token}
    indicador = cfg["electricidad"]["indicador_esios"]
    fallos_esios = []
    for dia in fallos:
        try:
            r = pedir(
                f"{ESIOS}/{indicador}", headers=cabeceras,
                params={"start_date": f"{dia}T00:00", "end_date": f"{dia}T23:59"},
            )
            guardar_raw("electricidad", f"esios_{dia}_{marca}.json", r.content)
        except RuntimeError as e:
            registrar(f"esios {dia}: {e}")
            fallos_esios.append(dia)
    anotar(estado, "esios", not fallos_esios, error=f"Sin datos de {', '.join(fallos_esios)}")


def apuntar_cadencia(marca, fuente, ultima_modificacion):
    """Cuándo cambia cada fuente de aire: decide qué se puede prometer el 11N."""
    LOG.mkdir(parents=True, exist_ok=True)
    ruta = LOG / "cadencia.csv"
    if not ruta.exists():
        ruta.write_text("descarga,fuente,ultima_modificacion\n", encoding="utf8")
    with open(ruta, "a", encoding="utf8") as f:
        f.write(f"{marca},{fuente},{ultima_modificacion}\n")


def descargar_eea(cfg, estado, marca):
    fallos = []
    for codigo in cfg["no2"]["estaciones"]:
        fuente = f"eea_{codigo}"
        try:
            url = EEA_BLOB.format(codigo)
            cabecera = requests.head(url, timeout=30).headers.get("Last-Modified")
            apuntar_cadencia(marca, fuente, cabecera)
            if cabecera and estado.get("eea_modificado", {}).get(codigo) == cabecera:
                continue
            r = pedir(url)
            guardar_raw("no2", f"eea_{codigo}_{marca}.parquet", r.content)
            estado.setdefault("eea_modificado", {})[codigo] = cabecera
        except (RuntimeError, requests.RequestException) as e:
            registrar(f"{fuente}: {type(e).__name__}")
            fallos.append(codigo)
    anotar(estado, "agencia_europea", not fallos, error=f"Estaciones sin descargar: {', '.join(fallos)}")


def descargar_gva_ultimos(estado, marca):
    meta = pedir(f"{GVA}/api/3/action/resource_show?id={GVA_ULTIMOS}").json()["result"]
    modificado = meta["last_modified"]
    apuntar_cadencia(marca, "gva_ultimos", modificado)
    if estado.get("gva_ultimos", {}).get("modificado") == modificado:
        anotar(estado, "gva_ultimos", True, modificado=modificado)
        return
    total = pedir(
        f"{GVA}/api/3/action/datastore_search?resource_id={GVA_ULTIMOS}&limit=0",
        valido=lambda x: b'"total"' in x.content,
    ).json()["result"]["total"]
    r = pedir(
        f"{GVA}/datastore/dump/{GVA_ULTIMOS}", intentos=6,
        valido=lambda x: len(x.text.splitlines()) > total,
    )
    guardar_raw("no2", f"gvaultimos_{marca}.csv", r.content)
    anotar(estado, "gva_ultimos", True, modificado=modificado)


def descargar_gva_2025(cfg, estado, marca):
    """Los CSV validados dan el control y la calibración de 2025. Basta una vez."""
    meses = [m for m in cfg["calibracion"]["meses_generalitat"] if ultimo_raw("no2", f"gva{m}_*") is None]
    if not meses:
        return
    recursos = pedir(f"{GVA}/api/3/action/package_show?id={GVA_2025}", valido=lambda x: x.content.rstrip().endswith(b"}")).json()
    for mes in meses:
        url = next(x["url"] for x in recursos["result"]["resources"] if x["url"].endswith(f"{mes}.csv"))
        guardar_raw("no2", f"gva{mes}_{marca}.csv", pedir(url, intentos=6).content)
    anotar(estado, "gva_historico", True)


def comprobar_portal_red(marca):
    """El portal estaba caído: si vuelve, puede ofrecer un acceso horario."""
    try:
        codigo = requests.get(PORTAL_RED, timeout=20).status_code
    except requests.RequestException as e:
        codigo = type(e).__name__
    apuntar_cadencia(marca, "portal_red_valenciana", codigo)


def descargar_meteo(cfg, estado, marca):
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    limite = (datetime.now(timezone.utc) - timedelta(days=DIAS_ARCHIVO)).strftime("%Y-%m-%d")
    fallos = []
    variables = "temperature_2m,wind_speed_10m,precipitation"
    for punto, p in cfg["meteo"]["puntos"].items():
        for dia in dias_disponibles(dias_comparados(cfg)):
            if dia <= limite and ultimo_raw("meteo", f"archivo_{punto}_{dia}_*") is not None:
                continue
            base = METEO_ARCHIVO if dia <= limite else METEO_RECIENTE
            nombre = "archivo" if dia <= limite else "reciente"
            try:
                r = pedir(base, params={
                    "latitude": p["latitud"], "longitude": p["longitud"],
                    "start_date": dia, "end_date": dia, "hourly": variables, "timezone": cfg["zona_horaria"],
                })
                guardar_raw("meteo", f"{nombre}_{punto}_{dia}_{marca}.json", r.content)
            except RuntimeError as e:
                registrar(f"meteo {punto} {dia}: {e}")
                fallos.append(dia)
    anotar(estado, "open_meteo", not fallos, error=f"Sin datos de {', '.join(sorted(set(fallos)))}", hoy=hoy)


def main():
    cfg = cargar_config()
    estado = leer_estado()
    marca = sello()
    pasos = [
        ("visor_ree", lambda: descargar_demanda(cfg, estado, marca)),
        ("agencia_europea", lambda: descargar_eea(cfg, estado, marca)),
        ("gva_ultimos", lambda: descargar_gva_ultimos(estado, marca)),
        ("gva_historico", lambda: descargar_gva_2025(cfg, estado, marca)),
        ("open_meteo", lambda: descargar_meteo(cfg, estado, marca)),
    ]
    for fuente, paso in pasos:
        try:
            paso()
        except Exception as e:  # una fuente caída no debe impedir las demás
            registrar(f"{fuente}: {type(e).__name__}: {str(e)[:200]}")
            anotar(estado, fuente, False, error=type(e).__name__)
        escribir_estado(estado)
    comprobar_portal_red(marca)


if __name__ == "__main__":
    main()
