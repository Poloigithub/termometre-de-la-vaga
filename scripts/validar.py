#!/usr/bin/env python3
"""Prueba de sensibilidad: un festivo entre semana debería salirse del margen."""
import json

from calculo import media_estaciones, perfil_horario, resumen_franja
from calibrar import tablas
from comun import PROCESADO, cargar_config


def linea(nombre, r):
    if r["desviacion_pct"] is None:
        return f"  {nombre:14} sin datos"
    return (f"  {nombre:14} {r['desviacion_pct']:+6.1f} %  margen [{r['margen_inf_pct']:+.1f}, {r['margen_sup_pct']:+.1f}]  "
            f"{r['horas']} h, {r['horas_fuera_banda']} fuera de banda  -> {r['veredicto']}")


def main():
    cfg = cargar_config()
    electricidad, por_estacion = tablas(cfg)
    calibracion = json.loads((PROCESADO / "calibracion.json").read_text(encoding="utf8"))
    v = cfg["validacion"]
    f = cfg["franja_resumen"]
    minimo = cfg["minimo_dias_referencia"]
    pe = perfil_horario(electricidad, v["festivo"], v["referencias"], minimo)
    pn = media_estaciones({
        c: perfil_horario(t, v["festivo"], v["referencias"], minimo, cfg["no2"]["referencia_minima"])
        for c, t in por_estacion.items()
    })
    margen = {k: (calibracion[k]["minimo"], calibracion[k]["maximo"]) for k in ("electricidad", "no2_urbano")}
    salida = {
        "festivo": v["festivo"],
        "electricidad": resumen_franja(pe, f["inicio"], f["fin"], margen["electricidad"]),
        "no2_urbano": resumen_franja(pn, f["inicio"], f["fin"], margen["no2_urbano"]),
    }
    print(f"Sensibilidad: festivo {v['festivo']} frente a {', '.join(v['referencias'])}")
    for nombre in ("electricidad", "no2_urbano"):
        print(linea(nombre, salida[nombre]))
    (PROCESADO / "validacion.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
