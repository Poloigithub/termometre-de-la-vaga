import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from calculo import (  # noqa: E402
    POR_DEBAJO, POR_ENCIMA, SIN_DATOS, SIN_DIFERENCIA, cortes_del_dia, curva_del_dia, indicadores, media_estaciones, perfil_horario, por_horas,
    resumen_franja,
)
from comun import anotar, etiqueta_a_civil  # noqa: E402

REFS = ["r1", "r2", "r3"]


def tabla(huelga, r1=90.0, r2=100.0, r3=120.0):
    return pd.DataFrame({"h": huelga, "r1": r1, "r2": r2, "r3": r3}, index=range(24))


def test_referencia_es_la_mediana_y_la_banda_los_extremos():
    p = perfil_horario(tabla(80.0), "h", REFS)
    assert p.loc[8, "referencia"] == 100
    assert p.loc[8, "banda_min"] == 90
    assert p.loc[8, "banda_max"] == 120


def test_desviacion_porcentual():
    p = perfil_horario(tabla(80.0), "h", REFS)
    assert p.loc[8, "desviacion_pct"] == pytest.approx(-20)
    assert p.loc[8, "banda_inf_pct"] == pytest.approx(-10)
    assert p.loc[8, "banda_sup_pct"] == pytest.approx(20)


def test_dentro_de_la_banda_no_hay_diferencia_aunque_sea_negativo():
    r = resumen_franja(perfil_horario(tabla(95.0), "h", REFS), 7, 21)
    assert r["desviacion_pct"] == pytest.approx(-5)
    assert r["veredicto"] == SIN_DIFERENCIA
    assert r["horas_fuera_banda"] == 0


def test_fuera_de_la_banda_por_abajo_y_por_arriba():
    assert resumen_franja(perfil_horario(tabla(80.0), "h", REFS), 7, 21)["veredicto"] == POR_DEBAJO
    assert resumen_franja(perfil_horario(tabla(130.0), "h", REFS), 7, 21)["veredicto"] == POR_ENCIMA


def test_los_limites_de_la_banda_cuentan_como_dentro():
    r = resumen_franja(perfil_horario(tabla(90.0), "h", REFS), 7, 21)
    assert r["veredicto"] == SIN_DIFERENCIA


def test_la_franja_excluye_la_hora_final():
    t = tabla(100.0)
    t.loc[21, "h"] = 10.0
    t.loc[6, "h"] = 10.0
    r = resumen_franja(perfil_horario(t, "h", REFS), 7, 21)
    assert r["horas"] == 14
    assert r["desviacion_pct"] == 0


def test_el_margen_empirico_amplia_el_de_la_banda_pero_nunca_lo_estrecha():
    p = perfil_horario(tabla(80.0), "h", REFS)
    assert resumen_franja(p, 7, 21, (-25.0, 8.0))["veredicto"] == SIN_DIFERENCIA
    r = resumen_franja(p, 7, 21, (-1.0, 1.0))
    assert (r["margen_inf_pct"], r["margen_sup_pct"]) == (-10, 20)


def test_dia_todavia_sin_datos():
    p = perfil_horario(tabla(100.0).drop(columns="h"), "h", REFS)
    assert p["desviacion_pct"].isna().all()
    assert resumen_franja(p, 7, 21)["veredicto"] == SIN_DATOS


def test_dia_a_medias_solo_cuenta_las_horas_publicadas():
    t = tabla(80.0)
    t.loc[10:, "h"] = float("nan")
    r = resumen_franja(perfil_horario(t, "h", REFS), 7, 21)
    assert r["horas"] == 3


def test_referencia_que_aun_no_existe_se_ignora():
    p = perfil_horario(tabla(80.0), "h", ["r1", "r2", "r3", "r4"])
    assert p.loc[8, "dias_referencia"] == 3


def test_con_un_solo_dia_de_referencia_no_hay_desviacion():
    p = perfil_horario(tabla(80.0), "h", ["r1"], minimo_dias=2)
    assert p["desviacion_pct"].isna().all()


def test_referencia_casi_nula_no_da_porcentaje():
    t = tabla(2.0, r1=1.0, r2=1.0, r3=1.0)
    p = perfil_horario(t, "h", REFS, referencia_minima=5)
    assert p["desviacion_pct"].isna().all()


def test_estacion_sin_dato_no_mueve_la_media():
    a = perfil_horario(tabla(80.0), "h", REFS)
    t = tabla(80.0)
    t.loc[8, "h"] = float("nan")
    b = perfil_horario(t, "h", REFS)
    m = media_estaciones({"a": a, "b": b})
    assert m.loc[8, "desviacion_pct"] == pytest.approx(-20)
    assert m.loc[8, "estaciones"] == 1
    assert m.loc[9, "estaciones"] == 2


def test_curva_del_dia_en_minutos():
    serie = pd.Series([20000.0, 20500.0], index=pd.to_datetime(["2026-11-01 00:00", "2026-11-01 07:25"]))
    c = curva_del_dia(serie)
    assert c["minutos"] == [0, 445]
    assert (c["ultimo_minuto"], c["ultimo_mw"]) == (445, 20500.0)


def test_hora_civil_en_invierno_y_en_verano():
    etiquetas = pd.Series(pd.to_datetime(["2026-11-11 06:00", "2026-10-21 06:00", "2026-10-20 23:00"]))
    civil = etiqueta_a_civil(etiquetas)
    assert civil[0].strftime("%Y-%m-%d %H") == "2026-11-11 06"
    assert civil[1].strftime("%Y-%m-%d %H") == "2026-10-21 07"
    assert civil[2].strftime("%Y-%m-%d %H") == "2026-10-21 00"


def test_una_fuente_correcta_no_guarda_el_mensaje_de_error():
    estado = {}
    anotar(estado, "fuente", False, error="caida")
    assert estado["fuente"]["error"] == "caida"
    anotar(estado, "fuente", True, error="Sin datos de ")
    assert estado["fuente"]["error"] is None


def test_por_horas_media_y_huecos():
    t = pd.date_range("2026-11-05 00:00", periods=24, freq="5min")  # solo 0 h y 1 h
    serie = pd.Series([100.0] * 12 + [200.0] * 12, index=t)
    h = por_horas(serie)
    assert h[0] == 100.0 and h[1] == 200.0
    assert len(h) == 24 and h[2] is None


def test_indicadores_energia_y_peor_hora():
    p = pd.DataFrame(index=range(24), columns=["valor", "referencia", "desviacion_pct"], dtype=float)
    p.loc[7] = [900.0, 1000.0, -10.0]
    p.loc[8] = [800.0, 1000.0, -20.0]
    p.loc[22] = [950.0, 1000.0, -5.0]  # fuera de la franja: cuenta para la última hora, no para la energía
    i = indicadores(p, 7, 21)
    assert i["diferencia_gwh"] == -0.3
    assert i["diferencia_gw"] == -0.15
    assert i["peor_hora"] == {"hora": 8, "desviacion_pct": -20.0}
    assert i["ultima_hora"] == {"hora": 22, "desviacion_pct": -5.0}


def test_indicadores_sin_datos():
    p = pd.DataFrame(index=range(24), columns=["valor", "referencia", "desviacion_pct"], dtype=float)
    assert indicadores(p, 7, 21) is None


def test_cortes_hora_y_acumulado():
    p = pd.DataFrame(index=range(24), columns=["valor", "referencia", "desviacion_pct"], dtype=float)
    p.loc[7] = [900.0, 1000.0, -10.0]
    p.loc[8] = [800.0, 1000.0, -20.0]
    nueve, doce = cortes_del_dia(p, 7, [9, 12])
    assert nueve == {"hora": 9, "hora_pct": -20.0, "acumulado_pct": -15.0, "acumulado_gwh": -0.3}
    assert doce["hora_pct"] is None  # la hora de 11 a 12 aún no ha llegado
