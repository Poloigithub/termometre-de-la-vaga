#!/usr/bin/env python3
"""Genera data/processed/ desde data/raw/. Se puede borrar y regenerar sin perder nada."""
import json

import pandas as pd

from comun import (
    PROCESADO, RAW, cargar_config, dias_comparados, dias_medidos, etiqueta_a_civil,
    leer_demanda, sello_de, ultimo_raw,
)


def procesar_demanda(cfg):
    filas = []
    for dia in dias_medidos(cfg):
        ruta = ultimo_raw("electricidad", f"*_{dia}_*")
        if ruta is None:
            continue
        s = leer_demanda(ruta, dia)
        if s.empty:
            continue
        por_hora = s.resample("1h").agg(["mean", "count"])
        for t, f in por_hora.iterrows():
            if f["count"] >= cfg["muestras_minimas_hora"]:
                filas.append({
                    "fecha": dia, "hora": t.hour, "demanda_mw": round(f["mean"], 1),
                    "muestras": int(f["count"]), "fuente": ruta.name.split("_")[0],
                })
    return pd.DataFrame(filas, columns=["fecha", "hora", "demanda_mw", "muestras", "fuente"])


def leer_eea(cfg):
    partes = []
    for codigo in cfg["no2"]["estaciones"]:
        ruta = ultimo_raw("no2", f"eea_{codigo}_*")
        if ruta is None:
            continue
        d = pd.read_parquet(ruta)
        d["valor"] = pd.to_numeric(d["Value"], errors="coerce")
        d = d[(d["Validity"] >= 1) & (d["valor"] >= 0)]
        partes.append(pd.DataFrame({
            "estacion": codigo, "etiqueta": d["Start"], "valor": d["valor"].astype(float), "fuente": "agencia_europea",
        }))
    return partes


def leer_gva_ultimos(cfg):
    partes = []
    for ruta in sorted(RAW.glob("no2/gvaultimos_*.csv"), key=sello_de):
        d = pd.read_csv(ruta, dtype=str)
        d = d[(d["identificador"] == "NO2") & d["cd_estacion"].isin(cfg["no2"]["estaciones"])]
        partes.append(pd.DataFrame({
            "estacion": d["cd_estacion"],
            "etiqueta": pd.to_datetime(d["fecha"] + " " + d["hora"], format="%d/%m/%Y %H:%M"),
            "valor": pd.to_numeric(d["valor"].str.replace(",", "."), errors="coerce"),
            "fuente": "generalitat_provisional",
        }))
    return partes


def leer_gva_historico(cfg):
    partes = []
    for mes in cfg["calibracion"]["meses_generalitat"]:
        ruta = ultimo_raw("no2", f"gva{mes}_*")
        if ruta is None:
            continue
        d = pd.read_csv(ruta, sep=";", dtype=str)
        d = d[d["COD_ESTACION"].isin(cfg["no2"]["estaciones"])]
        partes.append(pd.DataFrame({
            "estacion": d["COD_ESTACION"],
            "etiqueta": pd.to_datetime(d["FECHA"] + " " + d["HORA"] + ":00"),
            "valor": pd.to_numeric(d["NO2"].str.replace(",", "."), errors="coerce"),
            "fuente": "generalitat_historico",
        }))
    return partes


def procesar_no2(cfg):
    # Orden de preferencia: dato histórico, Agencia Europea, últimos registros.
    # keep="first" conserva la mejor fuente disponible para cada hora.
    partes = leer_gva_historico(cfg) + leer_eea(cfg) + leer_gva_ultimos(cfg)
    columnas = ["fecha", "hora", "estacion", "nombre", "grupo", "no2_ugm3", "fuente"]
    if not partes:
        return pd.DataFrame(columns=columnas)
    d = pd.concat(partes).dropna(subset=["valor"])
    d = d.drop_duplicates(["estacion", "etiqueta"], keep="first")
    civil = etiqueta_a_civil(d["etiqueta"])
    d["fecha"] = civil.dt.strftime("%Y-%m-%d")
    d["hora"] = civil.dt.hour
    d = d[d["fecha"].isin(dias_medidos(cfg))].copy()
    estaciones = cfg["no2"]["estaciones"]
    d["nombre"] = d["estacion"].map(lambda c: estaciones[c]["nombre"])
    d["grupo"] = d["estacion"].map(lambda c: estaciones[c]["grupo"])
    d = d.rename(columns={"valor": "no2_ugm3"})
    return d[columnas].sort_values(["fecha", "hora", "estacion"])


def procesar_meteo(cfg):
    filas = []
    for punto in cfg["meteo"]["puntos"]:
        for dia in dias_comparados(cfg):
            ruta = ultimo_raw("meteo", f"*_{punto}_{dia}_*")
            if ruta is None:
                continue
            h = pd.DataFrame(json.loads(ruta.read_text(encoding="utf8"))["hourly"])
            h["t"] = pd.to_datetime(h["time"]).dt.tz_localize(cfg["zona_horaria"], ambiguous="NaT", nonexistent="NaT")
            # Las horas posteriores a la descarga son previsión, no observación.
            h = h[h["t"] < pd.Timestamp(sello_de(ruta))].dropna(subset=["temperature_2m"])
            for _, f in h.iterrows():
                filas.append({
                    "fecha": dia, "hora": f["t"].hour, "punto": punto, "temperatura_c": f["temperature_2m"],
                    "viento_kmh": f["wind_speed_10m"], "lluvia_mm": f["precipitation"],
                })
    return pd.DataFrame(filas, columns=["fecha", "hora", "punto", "temperatura_c", "viento_kmh", "lluvia_mm"])


def main():
    cfg = cargar_config()
    PROCESADO.mkdir(parents=True, exist_ok=True)
    procesar_demanda(cfg).to_csv(PROCESADO / "electricidad_horaria.csv", index=False)
    procesar_no2(cfg).to_csv(PROCESADO / "no2_horario.csv", index=False)
    procesar_meteo(cfg).to_csv(PROCESADO / "meteo_horaria.csv", index=False)


if __name__ == "__main__":
    main()
