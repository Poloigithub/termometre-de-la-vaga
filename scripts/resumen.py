#!/usr/bin/env python3
"""Calcula los indicadores y escribe data/processed/resumen.json, que lee la web."""
import json
import shutil
from datetime import datetime, timezone

import pandas as pd

from calculo import curva_del_dia, indicadores, media_estaciones, perfil_horario, por_horas, resumen_franja
from comun import ESTADO, PROCESADO, RAIZ, cargar_config, hoy_local, leer_demanda, leer_prevista, ultimo_raw

MAPA_PUNTA = "horas_punta"
WEB_DATOS = RAIZ / "docs" / "data"
FUENTES_WEB = ("visor_ree", "esios", "open_meteo")


def tabla_de(d, valor):
    if d.empty:
        return pd.DataFrame(index=range(24))
    return d.pivot_table(index="hora", columns="fecha", values=valor, aggfunc="first").reindex(range(24))


def limpio(x):
    """Pasa series a listas JSON, con null donde no hay dato."""
    return [None if pd.isna(v) else (round(float(v), 2) if not isinstance(v, bool) else v) for v in x]


def serie_perfil(p):
    columnas = ["valor", "referencia", "banda_min", "banda_max", "desviacion_pct", "banda_inf_pct", "banda_sup_pct"]
    return {c: limpio(p[c]) for c in columnas}


def margen_de(calibracion, clave):
    if calibracion is None or calibracion[clave]["minimo"] is None:
        return None
    return calibracion[clave]["minimo"], calibracion[clave]["maximo"]


def resumenes(p, cfg, calibracion=None, indicador=None):
    franja = cfg["franja_resumen"]
    res = resumen_franja(p, franja["inicio"], franja["fin"], margen_de(calibracion, indicador) if indicador else None)
    horas = [h for ini, fin in cfg[MAPA_PUNTA] for h in range(ini, fin)]
    punta = margen_de(calibracion, f"{indicador}_punta") if indicador else None
    res["horas_punta"] = resumen_franja(p[p.index.isin(horas)], 0, 24, punta)
    return res


def calcular_electricidad(cfg, calibracion):
    d = pd.read_csv(PROCESADO / "electricidad_horaria.csv", dtype={"fecha": str})
    d = d[d["fecha"].isin([cfg["dia_huelga"], *cfg["dias_referencia"]])]
    t = tabla_de(d, "demanda_mw")
    p = perfil_horario(t, cfg["dia_huelga"], cfg["dias_referencia"], cfg["minimo_dias_referencia"])
    p.rename_axis("hora").to_csv(PROCESADO / "perfil_electricidad.csv")
    return {
        "resumen": resumenes(p, cfg, calibracion, "electricidad"),
        "indicadores": indicadores(p, cfg["franja_resumen"]["inicio"], cfg["franja_resumen"]["fin"]),
        "perfil": serie_perfil(p),
        "dias": {c: limpio(t[c]) for c in t.columns},
    }


def calcular_no2(cfg, calibracion):
    d = pd.read_csv(PROCESADO / "no2_horario.csv", dtype={"fecha": str, "estacion": str})
    d = d[d["fecha"].isin([cfg["dia_huelga"], *cfg["dias_referencia"]])]
    minima = cfg["no2"]["referencia_minima"]
    perfiles, tablas = {}, {}
    for codigo in cfg["no2"]["estaciones"]:
        t = tabla_de(d[d["estacion"] == codigo], "no2_ugm3")
        tablas[codigo] = t
        perfiles[codigo] = perfil_horario(t, cfg["dia_huelga"], cfg["dias_referencia"], cfg["minimo_dias_referencia"], minima)
    estaciones = cfg["no2"]["estaciones"]
    urbanas = {c: p for c, p in perfiles.items() if estaciones[c]["grupo"] == "urbana"}
    media = media_estaciones(urbanas)
    media.rename_axis("hora").to_csv(PROCESADO / "perfil_no2_urbano.csv")
    largo = pd.concat(
        [p.assign(estacion=c, nombre=estaciones[c]["nombre"]).rename_axis("hora").reset_index() for c, p in perfiles.items()]
    )
    largo.to_csv(PROCESADO / "perfil_no2_estaciones.csv", index=False)
    return {
        "resumen": resumenes(media, cfg, calibracion, "no2_urbano"),
        "perfil": serie_perfil(media),
        "estaciones_por_hora": [int(x) for x in media["estaciones"]],
        "estaciones": {
            c: {
                "nombre": estaciones[c]["nombre"], "grupo": estaciones[c]["grupo"],
                "resumen": resumenes(p, cfg), "perfil": serie_perfil(p),
                "horas_por_dia": {f: int(tablas[c][f].notna().sum()) for f in tablas[c].columns},
            }
            for c, p in perfiles.items()
        },
    }


def calcular_meteo(cfg):
    d = pd.read_csv(PROCESADO / "meteo_horaria.csv", dtype={"fecha": str})
    franja = cfg["franja_resumen"]
    f = d[(d["hora"] >= franja["inicio"]) & (d["hora"] < franja["fin"])]
    m = cfg["meteo"]
    dia = cfg["dia_huelga"]
    salida = {"puntos": {}, "avisos": []}
    for punto in m["puntos"]:
        x = f[f["punto"] == punto].groupby("fecha").agg(
            temperatura_c=("temperatura_c", "mean"), viento_kmh=("viento_kmh", "mean"), lluvia_mm=("lluvia_mm", "sum"),
        )
        salida["puntos"][punto] = {
            "dias": {k: {c: round(float(v[c]), 1) for c in x.columns} for k, v in x.iterrows()},
            "horario": {
                k: {c: limpio(g.set_index("hora")[c].reindex(range(24))) for c in ["temperatura_c", "viento_kmh", "lluvia_mm"]}
                for k, g in d[d["punto"] == punto].groupby("fecha")
            },
        }
        refs = x[x.index.isin(cfg["dias_referencia"])]
        if dia not in x.index or refs.empty:
            continue
        dif = x.loc[dia, "temperatura_c"] - refs["temperatura_c"].median()
        if abs(dif) > m["aviso_temperatura"]:
            salida["avisos"].append({"tipo": "temperatura", "punto": punto, "diferencia_c": round(float(dif), 1)})
        if punto == "castello":
            viento = x.loc[dia, "viento_kmh"]
            base = refs["viento_kmh"].median()
            dv = viento - base
            if abs(dv) >= m["aviso_viento_absoluto"] and abs(dv) >= m["aviso_viento_relativo"] * base:
                salida["avisos"].append({"tipo": "viento", "punto": punto, "diferencia_kmh": round(float(dv), 1)})
            if x.loc[dia, "lluvia_mm"] >= m["aviso_lluvia"] and refs["lluvia_mm"].median() < m["aviso_lluvia"]:
                salida["avisos"].append({"tipo": "lluvia", "punto": punto, "lluvia_mm": round(float(x.loc[dia, "lluvia_mm"]), 1)})
    return salida


def calcular_hoy(cfg):
    """Curva de hoy para la portada. El día de huelga la portada pasa a medirla."""
    hoy = hoy_local()
    ruta = ultimo_raw("electricidad", f"*_{hoy}_*")
    if hoy >= cfg["dia_huelga"] or ruta is None:
        return None
    serie = leer_demanda(ruta, hoy)
    if serie.empty:
        return None
    return {"fecha": hoy, **curva_del_dia(serie)}


def calcular_prevista(cfg):
    """Prevista de REE del día que enseña el gráfico: hoy, y el de huelga a partir del 11N.
    Solo es contexto: REE ya prevé los festivos, así que no sirve de referencia."""
    dia = min(hoy_local(), cfg["dia_huelga"])
    ruta = ultimo_raw("prevista", f"*_{dia}_*")
    if ruta is None:
        return None
    serie = leer_prevista(ruta, dia)
    return {"fecha": dia, "mw": por_horas(serie)} if not serie.empty else None


def publicar(resumen):
    """GitHub Pages solo publica docs/. El NO₂ se sigue recogiendo, pero no se publica."""
    shutil.rmtree(WEB_DATOS, ignore_errors=True)
    WEB_DATOS.mkdir(parents=True)
    for nombre in ("electricidad_horaria.csv", "meteo_horaria.csv", "perfil_electricidad.csv"):
        shutil.copy2(PROCESADO / nombre, WEB_DATOS / nombre)
    web = {k: v for k, v in resumen.items() if k != "no2"}
    web["estado"] = {k: v for k, v in resumen["estado"].items() if k in FUENTES_WEB}
    calibracion = {k: v for k, v in (resumen["calibracion"] or {}).items() if "no2" not in k}
    calibracion["dias"] = [
        {k: v for k, v in d.items() if "no2" not in k} for d in calibracion.get("dias", [])
    ]
    web["calibracion"] = calibracion
    (WEB_DATOS / "resumen.json").write_text(json.dumps(web, ensure_ascii=False, indent=1) + "\n", encoding="utf8")
    (WEB_DATOS / "calibracion.json").write_text(json.dumps(calibracion, ensure_ascii=False, indent=1) + "\n", encoding="utf8")


def main():
    cfg = cargar_config()
    ruta = PROCESADO / "calibracion.json"
    calibracion = json.loads(ruta.read_text(encoding="utf8")) if ruta.exists() else None
    electricidad = calcular_electricidad(cfg, calibracion)
    resumen = {
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "dia_huelga": cfg["dia_huelga"],
        "dias_referencia": cfg["dias_referencia"],
        "franja": cfg["franja_resumen"],
        "hoy": calcular_hoy(cfg),
        "prevista": calcular_prevista(cfg),
        "electricidad": electricidad,
        "no2": calcular_no2(cfg, calibracion),
        "calibracion": calibracion,
        "meteo": calcular_meteo(cfg),
        "estado": json.loads(ESTADO.read_text(encoding="utf8")) if ESTADO.exists() else {},
    }
    (PROCESADO / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf8")
    publicar(resumen)


if __name__ == "__main__":
    main()
