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

function hora(minutos) {
  const m = String(minutos % 60).padStart(2, "0");
  return `${String(Math.floor(minutos / 60)).padStart(2, "0")}:${m}`;
}

function pintarHoy(hoy) {
  const opciones = { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" };
  const dia = new Date(hoy.fecha).toLocaleDateString(idioma === "va" ? "ca-ES" : "es-ES", opciones);
  poner("titular-etiqueta", texto("hoy_etiqueta", { d: dia }));
  const num = document.getElementById("titular-numero");
  num.textContent = `${numero(hoy.ultimo_mw / 1000)} ${texto("unidad_gw")}`;
  num.classList.remove("pendiente");
  poner("titular-veredicto", texto("hoy_ultimo", { h: hora(hoy.ultimo_minuto) }));
  poner("titular-margen", "");
  document.getElementById("marco-hoy").hidden = false;
  document.getElementById("nota-hoy").hidden = false;
  graficos["grafico-hoy"]?.destroy();
  if (!window.Chart) return;
  const eje = { border: { display: false }, ticks: { color: TINTA_2, font: { size: 12 }, padding: 6 } };
  graficos["grafico-hoy"] = new Chart(document.getElementById("grafico-hoy"), {
    type: "line",
    data: {
      datasets: [{
        data: hoy.minutos.map((m, i) => ({ x: m, y: hoy.mw[i] / 1000 })),
        borderColor: ROJO, backgroundColor: ROJO, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "nearest", axis: "x", intersect: false },
      scales: {
        x: {
          ...eje, type: "linear", min: 0, max: 1440, grid: { display: false },
          ticks: { ...eje.ticks, stepSize: 180, callback: (v) => `${v / 60} h` },
        },
        y: { ...eje, grid: { color: LINEA, drawTicks: false }, title: { display: true, text: texto("unidad_gw"), color: TINTA_2, font: { size: 12 } } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: TINTA,
          displayColors: false,
          callbacks: {
            title: (e) => hora(e[0].parsed.x),
            label: (c) => `${numero(c.parsed.y)} ${texto("unidad_gw")}`,
          },
        },
      },
    },
  });
}

function pintarTitular(datos) {
  if (datos.hoy) {
    pintarHoy(datos.hoy);
    return;
  }
  document.getElementById("marco-hoy").hidden = true;
  document.getElementById("nota-hoy").hidden = true;
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
  lista("avisos-electricidad", datos.meteo.avisos.filter((a) => a.tipo === "temperatura").map((a) =>
    texto("aviso_temperatura", { d: numero(a.diferencia_c), p: texto(`punto_${a.punto}`) })));
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
  const m = c.electricidad;
  poner("margenes", texto("margen_elec", { inf: pct(m.minimo), sup: pct(m.maximo), n: m.dias }));
}

function pintarEstado(datos) {
  const ul = document.getElementById("estado");
  ul.replaceChildren(...["visor_ree", "open_meteo"].map((fuente) => {
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
