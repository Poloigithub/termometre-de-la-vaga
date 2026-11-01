"use strict";

const ROJO = "#c8102e";
const TINTA = "#1f1f1f";
const TINTA_2 = "#55554f";
const BANDA = "#e2e1dc";
const LINEA = "#e4e3de";
const HORAS = Array.from({ length: 24 }, (_, h) => h);

let idioma = "es";
let graficos = {};
let ultimosDatos = null;

function texto(clave, valores = {}) {
  const base = (window.TEXTOS[idioma] || {})[clave] ?? window.TEXTOS.es[clave] ?? clave;
  return base.replace(/\{(\w+)\}/g, (_, k) => valores[k] ?? "");
}

function numero(x, decimales = 1) {
  return x.toLocaleString(idioma === "va" ? "ca-ES" : "es-ES", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  }).replace("-", "−");
}

function pct(x) {
  return `${x > 0 ? "+" : ""}${numero(x)} %`;
}

function fecha(iso, conHora = true) {
  const opciones = conHora
    ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Madrid" }
    : { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" };
  return new Date(iso).toLocaleString(idioma === "va" ? "ca-ES" : "es-ES", opciones);
}

function poner(id, contenido) {
  document.getElementById(id).textContent = contenido;
}

function lista(id, elementos) {
  const ul = document.getElementById(id);
  ul.replaceChildren(...elementos.map((t) => {
    const li = document.createElement("li");
    li.textContent = t;
    return li;
  }));
}

function mediana(valores) {
  const v = [...valores].sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

function pintarTitular(datos) {
  const r = datos.electricidad.resumen;
  const c = datos.calibracion?.electricidad;
  const num = document.getElementById("titular-numero");
  const hay = r.desviacion_pct !== null;
  num.textContent = hay ? pct(r.desviacion_pct) : texto("pendiente");
  num.classList.toggle("pendiente", !hay);
  let veredicto = hay ? texto(r.veredicto) : texto("sin_dato_aun");
  const totalHoras = datos.franja.fin - datos.franja.inicio;
  if (hay && r.horas < totalHoras) veredicto += `. ${texto("parcial", { h: r.horas, t: totalHoras })}`;
  poner("titular-veredicto", veredicto);
  const inf = hay ? r.margen_inf_pct : c?.minimo;
  const sup = hay ? r.margen_sup_pct : c?.maximo;
  poner("titular-margen", inf == null ? "" : texto("margen", { inf: pct(inf), sup: pct(sup) }));

  const n = datos.no2.resumen;
  poner("titular-no2", n.desviacion_pct === null
    ? texto("no2_pendiente")
    : texto("no2_valor", { v: pct(n.desviacion_pct), texto: texto(`no2_${n.veredicto}`) }));
}

function pintarLeyenda(id, hayHuelga) {
  const ul = document.getElementById(id);
  const piezas = [
    ["huelga", hayHuelga ? "leyenda_huelga" : "leyenda_sin_huelga"],
    ["referencia", "leyenda_referencia"],
    ["banda", "leyenda_banda"],
  ];
  ul.replaceChildren(...piezas.map(([clase, clave]) => {
    const li = document.createElement("li");
    const muestra = document.createElement("span");
    muestra.className = `muestra ${clase}`;
    li.append(muestra, texto(clave));
    return li;
  }));
}

function escalar(serie, factor) {
  return serie.map((v) => (v === null ? null : v * factor));
}

function pintarGrafico(id, perfil, factor, unidad, decimales) {
  graficos[id]?.destroy();
  if (!window.Chart) return;  // sin la librería quedan las tablas y los resúmenes
  const eje = {
    grid: { color: LINEA, drawTicks: false },
    border: { display: false },
    ticks: { color: TINTA_2, font: { size: 12 }, padding: 6 },
  };
  graficos[id] = new Chart(document.getElementById(id), {
    type: "line",
    data: {
      labels: HORAS,
      datasets: [
        // En Chart.js el `order` más bajo queda encima: la banda va al fondo.
        { data: escalar(perfil.banda_min, factor), order: 4, borderWidth: 0, pointRadius: 0, pointHitRadius: 0, fill: false },
        { data: escalar(perfil.banda_max, factor), order: 3, borderWidth: 0, pointRadius: 0, pointHitRadius: 0, backgroundColor: BANDA, fill: "-1" },
        { data: escalar(perfil.referencia, factor), order: 2, borderColor: TINTA, borderWidth: 2, borderDash: [6, 4], pointRadius: 0, tension: 0.2 },
        { data: escalar(perfil.valor, factor), order: 1, borderColor: ROJO, backgroundColor: ROJO, borderWidth: 3, pointRadius: 0, pointHoverRadius: 5, tension: 0.2 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ...eje, grid: { display: false }, ticks: { ...eje.ticks, maxTicksLimit: 9, callback: (v) => `${v} h` } },
        y: { ...eje, title: { display: true, text: unidad, color: TINTA_2, font: { size: 12 } } },
      },
      plugins: {
        legend: { display: false },
        filler: { drawTime: "beforeDatasetsDraw" },
        tooltip: {
          itemSort: (a, b) => b.datasetIndex - a.datasetIndex,
          backgroundColor: TINTA,
          displayColors: false,
          callbacks: {
            title: (e) => `${e[0].label} h`,
            label: (c) => {
              const nombres = [texto("tabla_min"), texto("tabla_max"), texto("tabla_referencia"), texto("tabla_huelga")];
              return `${nombres[c.datasetIndex]}: ${numero(c.parsed.y, decimales)} ${unidad}`;
            },
          },
        },
      },
    },
  });
}

function celda(fila, valor, etiqueta = "td") {
  const c = document.createElement(etiqueta);
  c.textContent = valor;
  fila.append(c);
}

function pintarTabla(id, perfil, factor, decimales) {
  const tabla = document.getElementById(id);
  const cabecera = document.createElement("tr");
  ["tabla_hora", "tabla_huelga", "tabla_referencia", "tabla_min", "tabla_max", "tabla_desv"]
    .forEach((c) => celda(cabecera, texto(c), "th"));
  const filas = HORAS.map((h) => {
    const f = document.createElement("tr");
    const v = (s) => (s[h] === null ? "—" : numero(s[h] * factor, decimales));
    celda(f, `${h} h`);
    [perfil.valor, perfil.referencia, perfil.banda_min, perfil.banda_max].forEach((s) => celda(f, v(s)));
    celda(f, perfil.desviacion_pct[h] === null ? "—" : pct(perfil.desviacion_pct[h]));
    return f;
  });
  tabla.replaceChildren(cabecera, ...filas);
}

function pintarNo2(datos) {
  const n = datos.no2;
  const r = n.resumen;
  const c = datos.calibracion?.no2_urbano;
  if (r.desviacion_pct === null) {
    poner("no2-resultado", texto("no2_sin_resultado"));
  } else {
    const inf = c?.minimo ?? r.margen_inf_pct;
    const sup = c?.maximo ?? r.margen_sup_pct;
    let t = texto("no2_resultado", { v: pct(r.desviacion_pct), inf: pct(inf), sup: pct(sup) });
    const punta = r.horas_punta;
    if (punta?.desviacion_pct != null) t += ` ${texto("no2_punta", { v: pct(punta.desviacion_pct) })}`;
    poner("no2-resultado", t);
  }

  const tabla = document.getElementById("tabla-estaciones");
  const cabecera = document.createElement("tr");
  ["est_nombre", "est_grupo", "est_desv"].forEach((k) => celda(cabecera, texto(k), "th"));
  const filas = Object.values(n.estaciones).map((e) => {
    const f = document.createElement("tr");
    celda(f, e.nombre);
    celda(f, texto(`est_${e.grupo}`));
    celda(f, e.resumen.desviacion_pct === null ? "—" : pct(e.resumen.desviacion_pct));
    return f;
  });
  tabla.replaceChildren(cabecera, ...filas);
}

function pintarMeteo(datos) {
  const dia = datos.dia_huelga;
  const fila = (punto, variable, decimales, clave, extra = {}) => {
    const dias = datos.meteo.puntos[punto]?.dias ?? {};
    const refs = datos.dias_referencia.filter((d) => dias[d]).map((d) => dias[d][variable]);
    if (!refs.length) return null;
    const h = dias[dia] ? texto("meteo_huelga", { v: numero(dias[dia][variable], decimales) }) : "";
    return texto(clave, { h, r: numero(mediana(refs), decimales), ...extra });
  };
  lista("meteo-electricidad", ["castello", "valencia"]
    .map((p) => fila(p, "temperatura_c", 1, "meteo_temp", { p: texto(`punto_${p}`) }))
    .filter(Boolean));
  lista("meteo-no2", [
    fila("castello", "viento_kmh", 1, "meteo_viento"),
    fila("castello", "lluvia_mm", 1, "meteo_lluvia"),
  ].filter(Boolean));

  const avisos = datos.meteo.avisos;
  lista("avisos-electricidad", avisos.filter((a) => a.tipo === "temperatura").map((a) =>
    texto("aviso_temperatura", { d: numero(a.diferencia_c), p: texto(`punto_${a.punto}`) })));
  lista("avisos-no2", avisos.filter((a) => a.tipo !== "temperatura").map((a) => (a.tipo === "viento"
    ? texto("aviso_viento", { d: numero(a.diferencia_kmh) })
    : texto("aviso_lluvia", { l: numero(a.lluvia_mm) }))));
}

function pintarMetodologia(datos) {
  const disponibles = Object.keys(datos.electricidad.dias);
  const anioHuelga = datos.dia_huelga.slice(0, 4);
  poner("dias-referencia", datos.dias_referencia.map((d) => {
    let t = fecha(d, false);
    if (!d.startsWith(anioHuelga)) t += ` ${texto("dia_control")}`;
    if (!disponibles.includes(d)) t += ` ${texto("dia_pendiente")}`;
    return t;
  }).join(" · "));
  const c = datos.calibracion;
  if (!c) return;
  const linea = (clave, m) => texto(clave, { inf: pct(m.minimo), sup: pct(m.maximo), n: m.dias });
  poner("margenes", `${linea("margen_elec", c.electricidad)} ${linea("margen_no2", c.no2_urbano)}`);
}

function pintarEstado(datos) {
  const ul = document.getElementById("estado");
  ul.replaceChildren(...["visor_ree", "agencia_europea", "gva_ultimos", "open_meteo"].map((fuente) => {
    const e = datos.estado[fuente] ?? {};
    const li = document.createElement("li");
    const nombre = document.createElement("span");
    nombre.textContent = texto(`fuente_${fuente}`);
    const situacion = document.createElement("span");
    const ultima = e.ultima_correcta ? fecha(e.ultima_correcta) : texto("estado_nunca");
    if (e.error || !e.ultima_correcta) {
      situacion.className = "fallo";
      situacion.textContent = texto("estado_fallo", { e: e.error ?? "—", f: ultima });
    } else {
      situacion.textContent = texto("estado_ok", { f: ultima });
    }
    li.append(nombre, situacion);
    return li;
  }));
  poner("generado", texto("generado", { f: fecha(datos.generado) }));
}

function pintar(datos) {
  ultimosDatos = datos;
  // Cada bloque es independiente: un dato raro no debe dejar la página en blanco.
  const bloques = [
    () => pintarTitular(datos),
    () => {
      const p = datos.electricidad.perfil;
      pintarLeyenda("leyenda-electricidad", p.valor.some((v) => v !== null));
      pintarGrafico("grafico-electricidad", p, 0.001, texto("unidad_gw"), 1);
      pintarTabla("tabla-electricidad", p, 0.001, 1);
    },
    () => {
      const p = datos.no2.perfil;
      pintarLeyenda("leyenda-no2", p.valor.some((v) => v !== null));
      pintarGrafico("grafico-no2", p, 1, texto("unidad_no2"), 0);
      pintarTabla("tabla-no2", p, 1, 1);
      pintarNo2(datos);
    },
    () => pintarMeteo(datos),
    () => pintarMetodologia(datos),
    () => pintarEstado(datos),
  ];
  bloques.forEach((b) => {
    try {
      b();
    } catch (e) {
      console.error(e);
    }
  });
}

function aplicarIdioma(nuevo) {
  idioma = nuevo;
  document.documentElement.lang = idioma === "va" ? "ca" : "es";
  const textos = window.TEXTOS[idioma];
  document.querySelectorAll("[data-t]").forEach((el) => {
    el.dataset.original ??= el.innerHTML;
    el.innerHTML = textos[el.dataset.t] ?? el.dataset.original;
  });
  const boton = document.getElementById("idioma");
  boton.textContent = idioma === "es" ? "Valencià" : "Castellano";
  if (ultimosDatos) pintar(ultimosDatos);
}

async function iniciar() {
  const boton = document.getElementById("idioma");
  if (Object.keys(window.TEXTOS.va).length) {
    boton.hidden = false;
    boton.addEventListener("click", () => aplicarIdioma(idioma === "es" ? "va" : "es"));
    aplicarIdioma("es");
  }
  try {
    const r = await fetch("data/resumen.json", { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    pintar(await r.json());
  } catch (e) {
    console.error(e);
    document.getElementById("fallo-carga").hidden = false;
  }
}

iniciar();
