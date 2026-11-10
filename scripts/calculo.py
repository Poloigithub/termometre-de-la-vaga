"""Cálculo de la desviación y la banda de normalidad. Sin red ni ficheros, para poder probarlo."""
import pandas as pd

SIN_DATOS = "sin_datos"
SIN_DIFERENCIA = "sin_diferencia"
POR_DEBAJO = "por_debajo"
POR_ENCIMA = "por_encima"


def curva_del_dia(serie):
    """Serie de 5 minutos a listas: minuto del día y MW, con el último dato aparte."""
    return {
        "minutos": [t.hour * 60 + t.minute for t in serie.index],
        "mw": [round(float(v), 1) for v in serie.values],
        "ultimo_minuto": serie.index[-1].hour * 60 + serie.index[-1].minute,
        "ultimo_mw": round(float(serie.iloc[-1]), 1),
    }


def por_horas(serie):
    """Media de cada hora (0-23) de una serie de 5 minutos; None si la hora no tiene datos."""
    medias = serie.groupby(serie.index.hour).mean().reindex(range(24))
    return [None if pd.isna(v) else round(float(v), 1) for v in medias]


def dentro_de_banda(p):
    """True, False o None si esa hora no tiene desviación."""
    dentro = (p["desviacion_pct"] >= p["banda_inf_pct"]) & (p["desviacion_pct"] <= p["banda_sup_pct"])
    return dentro.astype(object).where(p["desviacion_pct"].notna(), None)


def perfil_horario(tabla, dia, referencias, minimo_dias=2, referencia_minima=0):
    """Compara un día con sus referencias, hora a hora.

    tabla: índice de hora (0-23), una columna por fecha.
    Referencia = mediana; banda = mínimo y máximo de los días de referencia.
    Con menos de minimo_dias, o una referencia inferior a referencia_minima,
    no hay desviación: el porcentaje no significaría nada.
    """
    t = tabla.reindex(range(24))
    refs = t[[d for d in referencias if d in t.columns]]
    p = pd.DataFrame(index=t.index)
    p["valor"] = t[dia] if dia in t.columns else float("nan")
    p["referencia"] = refs.median(axis=1)
    p["banda_min"] = refs.min(axis=1)
    p["banda_max"] = refs.max(axis=1)
    p["dias_referencia"] = refs.count(axis=1)

    fiable = (p["dias_referencia"] >= minimo_dias) & (p["referencia"] > 0) & (p["referencia"] >= referencia_minima)
    base = p["referencia"].where(fiable)
    p["desviacion_pct"] = (p["valor"] - base) / base * 100
    p["banda_inf_pct"] = (p["banda_min"] - base) / base * 100
    p["banda_sup_pct"] = (p["banda_max"] - base) / base * 100
    p["dentro_banda"] = dentro_de_banda(p)
    return p


def media_estaciones(perfiles):
    """Media de varias estaciones: primero la desviación de cada una y luego el
    promedio, para que una estación sin dato no mueva el número."""
    def juntar(columna):
        return pd.concat([x[columna] for x in perfiles.values()], axis=1)

    p = pd.DataFrame(index=range(24))
    for c in ["valor", "referencia", "banda_min", "banda_max", "desviacion_pct", "banda_inf_pct", "banda_sup_pct"]:
        p[c] = juntar(c).mean(axis=1)
    p["estaciones"] = juntar("desviacion_pct").count(axis=1)
    p["dias_referencia"] = juntar("dias_referencia").min(axis=1)
    p["dentro_banda"] = dentro_de_banda(p)
    return p


def resumen_franja(perfil, inicio, fin, margen_empirico=None):
    """Desviación media en [inicio, fin), con su margen de normalidad.

    El margen es la misma media aplicada a los extremos de la banda, ampliado
    con el margen empírico (min, max) de la calibración si lo hay: un rango de
    pocos días deja fuera a un día normal muy a menudo. Si el día cae dentro,
    el veredicto es que no hay diferencia, aunque salga negativo.
    """
    f = perfil[(perfil.index >= inicio) & (perfil.index < fin)]
    f = f[f["desviacion_pct"].notna()]
    if f.empty:
        return {"desviacion_pct": None, "margen_inf_pct": None, "margen_sup_pct": None,
                "horas": 0, "horas_fuera_banda": 0, "veredicto": SIN_DATOS}
    media = f["desviacion_pct"].mean()
    inferior = f["banda_inf_pct"].mean()
    superior = f["banda_sup_pct"].mean()
    if margen_empirico is not None:
        inferior = min(inferior, margen_empirico[0])
        superior = max(superior, margen_empirico[1])
    if media < inferior:
        veredicto = POR_DEBAJO
    elif media > superior:
        veredicto = POR_ENCIMA
    else:
        veredicto = SIN_DIFERENCIA
    return {
        "desviacion_pct": round(float(media), 1),
        "margen_inf_pct": round(float(inferior), 1),
        "margen_sup_pct": round(float(superior), 1),
        "horas": int(len(f)),
        "horas_fuera_banda": int((f["dentro_banda"] == False).sum()),  # noqa: E712
        "veredicto": veredicto,
    }


def cortes_del_dia(perfil, inicio, cortes):
    """Situación a cada hora de corte: la hora que acaba entonces y lo acumulado desde inicio.

    Un corte queda vacío (None) hasta que esa hora tiene dato.
    """
    salida = []
    for corte in cortes:
        tramo = perfil.loc[inicio:corte - 1]
        tramo = tramo[tramo["desviacion_pct"].notna()]
        if (corte - 1) not in tramo.index:
            salida.append({"hora": corte, "hora_pct": None, "acumulado_pct": None, "acumulado_gwh": None})
            continue
        salida.append({
            "hora": corte,
            "hora_pct": round(float(tramo.loc[corte - 1, "desviacion_pct"]), 1),
            "acumulado_pct": round(float(tramo["desviacion_pct"].mean()), 1),
            "acumulado_gwh": round(float((tramo["valor"] - tramo["referencia"]).sum()) / 1000, 1),
        })
    return salida


def indicadores(perfil, inicio, fin):
    """Cifras concretas del día frente a la referencia, solo con horas completas.

    diferencia_gwh: energía de más (+) o de menos (−) entre inicio y fin.
    diferencia_gw: lo mismo como potencia media.
    peor_hora y ultima_hora: hora (inicio del tramo) y desviación en %.
    """
    con = perfil[perfil["desviacion_pct"].notna()]
    franja = con[(con.index >= inicio) & (con.index < fin)]
    if con.empty:
        return None
    ultima = con.index.max()
    salida = {
        "ultima_hora": {"hora": int(ultima), "desviacion_pct": round(float(con.loc[ultima, "desviacion_pct"]), 1)},
        "diferencia_gwh": None, "diferencia_gw": None, "peor_hora": None,
    }
    if not franja.empty:
        dif = franja["valor"] - franja["referencia"]
        peor = franja["desviacion_pct"].idxmin()
        salida.update(
            diferencia_gwh=round(float(dif.sum()) / 1000, 1),
            diferencia_gw=round(float(dif.mean()) / 1000, 2),
            peor_hora={"hora": int(peor), "desviacion_pct": round(float(franja.loc[peor, "desviacion_pct"]), 1)},
        )
    return salida
