#!/usr/bin/env python3
"""Mide cuánto se desvía un miércoles normal y fija el margen empírico.

Cada miércoles de los periodos de calibración se compara con los anteriores,
igual que se comparará el día de huelga. El margen es el mínimo y el máximo de
esas desviaciones. Solo usa días pasados, así que no depende del resultado.
"""
import json

import pandas as pd

from calculo import media_estaciones, perfil_horario
from comun import PROCESADO, cargar_config, periodos_calibracion


def tablas(cfg):
    """Tabla de electricidad y tablas de NO₂ de las estaciones urbanas."""
    e = pd.read_csv(PROCESADO / "electricidad_horaria.csv", dtype={"fecha": str})
    n = pd.read_csv(PROCESADO / "no2_horario.csv", dtype={"fecha": str, "estacion": str})
    electricidad = e.pivot_table(index="hora", columns="fecha", values="demanda_mw", aggfunc="first").reindex(range(24))
    urbanas = [c for c, v in cfg["no2"]["estaciones"].items() if v["grupo"] == "urbana"]
    por_estacion = {
        c: n[n["estacion"] == c].pivot_table(index="hora", columns="fecha", values="no2_ugm3", aggfunc="first").reindex(range(24))
        for c in urbanas
    }
    return electricidad, por_estacion


def desviacion(perfil, horas):
    return perfil.loc[horas, "desviacion_pct"].mean()


def calibrar(cfg, electricidad, por_estacion):
    previos = cfg["calibracion"]["dias_previos"]
    minimo = cfg["minimo_dias_referencia"]
    franja = list(range(cfg["franja_resumen"]["inicio"], cfg["franja_resumen"]["fin"]))
    punta = [h for ini, fin in cfg["horas_punta"] for h in range(ini, fin)]
    filas = []
    for periodo in periodos_calibracion(cfg):
        for i in range(previos, len(periodo)):
            dia, refs = periodo[i], periodo[i - previos : i]
            pe = perfil_horario(electricidad, dia, refs, minimo)
            pn = media_estaciones({
                c: perfil_horario(t, dia, refs, minimo, cfg["no2"]["referencia_minima"])
                for c, t in por_estacion.items()
            })
            filas.append({
                "dia": dia,
                "electricidad": desviacion(pe, franja),
                "electricidad_punta": desviacion(pe, punta),
                "no2_urbano": desviacion(pn, franja),
                "no2_urbano_punta": desviacion(pn, punta),
            })
    return pd.DataFrame(filas).set_index("dia")


def main():
    cfg = cargar_config()
    electricidad, por_estacion = tablas(cfg)
    d = calibrar(cfg, electricidad, por_estacion)
    salida = {"dias": d.round(1).astype(object).where(d.notna(), None).reset_index().to_dict("records")}
    for c in d.columns:
        s = d[c].dropna()
        salida[c] = {
            "minimo": round(float(s.min()), 1) if len(s) else None,
            "maximo": round(float(s.max()), 1) if len(s) else None,
            "mediana_absoluta": round(float(s.abs().median()), 1) if len(s) else None,
            "dias": int(len(s)),
        }
        print(f"{c:22} {len(s)} miércoles: margen [{salida[c]['minimo']:+.1f}, {salida[c]['maximo']:+.1f}], "
              f"desviación típica {salida[c]['mediana_absoluta']:.1f}")
    (PROCESADO / "calibracion.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
