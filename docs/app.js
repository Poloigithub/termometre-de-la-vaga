"use strict";

const ROJO = "#c8102e";
const TINTA = "#1f1f1f";
const TINTA_2 = "#55554f";
const VERDE = "#2e7d32";
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
}

function pintarTitular(datos) {
  if (datos.hoy) {
    pintarHoy(datos.hoy);
    return;
  }
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

function hoyPorHoras(hoy) {
  // El gráfico va por horas; la última puede estar a medias hasta el siguiente dato.
  const suma = HORAS.map(() => 0);
  const muestras = HORAS.map(() => 0);
  hoy.minutos.forEach((m, i) => {
    const h = Math.floor(m / 60);
    suma[h] += hoy.mw[i];
    muestras[h] += 1;
  });
  return HORAS.map((h) => (muestras[h] ? suma[h] / muestras[h] : null));
}

function pintarLeyenda(id, hayHuelga, hayHoy, hayPrevista) {
  const ul = document.getElementById(id);
  const piezas = [
    hayHoy ? ["hoy", "leyenda_hoy"] : ["huelga", hayHuelga ? "leyenda_huelga" : "leyenda_sin_huelga"],
    ...(hayPrevista ? [[`prevista ${hayHoy ? "hoy" : "huelga"}`, "leyenda_prevista"]] : []),
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

function pintarGrafico(id, perfil, factor, unidad, decimales, hoy = null, prevista = null) {
  // La prevista lleva el color del día que acompaña, en punteado.
  const colorPrevista = hoy ? VERDE : ROJO;
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
        { label: texto("tabla_min"), data: escalar(perfil.banda_min, factor), order: 5, borderWidth: 0, pointRadius: 0, pointHitRadius: 0, fill: false },
        { label: texto("tabla_max"), data: escalar(perfil.banda_max, factor), order: 4, borderWidth: 0, pointRadius: 0, pointHitRadius: 0, backgroundColor: BANDA, fill: "-1" },
        { label: texto("tabla_referencia"), data: escalar(perfil.referencia, factor), order: 3, borderColor: TINTA, borderWidth: 2, borderDash: [6, 4], pointRadius: 0, tension: 0.2 },
        ...(prevista ? [{ label: texto("tabla_prevista"), data: escalar(prevista, factor), order: 2, borderColor: colorPrevista, backgroundColor: colorPrevista, borderWidth: 2, borderDash: [2, 3], pointRadius: 0, pointHoverRadius: 4, tension: 0.2 }] : []),
        { label: texto("tabla_huelga"), data: escalar(perfil.valor, factor), order: 1, borderColor: ROJO, backgroundColor: ROJO, borderWidth: 3, pointRadius: 0, pointHoverRadius: 5, tension: 0.2 },
        ...(hoy ? [{ label: texto("leyenda_hoy"), data: escalar(hoy, factor), order: 0, borderColor: VERDE, backgroundColor: VERDE, borderWidth: 3, pointRadius: 0, pointHoverRadius: 5, tension: 0.2 }] : []),
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
          itemSort: (a, b) => a.dataset.order - b.dataset.order,
          backgroundColor: TINTA,
          displayColors: false,
          callbacks: {
            title: (e) => `${e[0].label} h`,
            label: (c) => `${c.dataset.label}: ${numero(c.parsed.y, decimales)} ${unidad}`,
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

function conSigno(x, decimales = 1) {
  return `${x > 0 ? "+" : ""}${numero(x, decimales)}`;
}

function tramo(h) {
  return `${h}–${h + 1} h`;
}

function pintarIndicadores(datos) {
  const seccion = document.getElementById("indicadores");
  const i = datos.electricidad.indicadores;
  const r = datos.electricidad.resumen;
  seccion.hidden = Boolean(datos.hoy) || !i || r.desviacion_pct === null;
  if (seccion.hidden) return;
  const cifras = [
    ["cifra_energia", `${conSigno(i.diferencia_gwh)} GWh`],
    ["cifra_potencia", `${conSigno(i.diferencia_gw, 2)} GW`],
    ["cifra_punta", r.horas_punta.desviacion_pct === null ? "—" : pct(r.horas_punta.desviacion_pct)],
    ["cifra_peor", i.peor_hora ? `${pct(i.peor_hora.desviacion_pct)} (${tramo(i.peor_hora.hora)})` : "—"],
    ["cifra_ultima", `${pct(i.ultima_hora.desviacion_pct)} (${tramo(i.ultima_hora.hora)})`],
  ];
  document.getElementById("cifras").replaceChildren(...cifras.map(([clave, valor]) => {
    const div = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = texto(clave);
    dd.textContent = valor;
    div.append(dt, dd);
    return div;
  }));
  // Hasta qué hora llega la media: la franja puede estar a medias durante el día.
  const p = datos.electricidad.perfil;
  const horas = HORAS.filter((h) => h >= datos.franja.inicio && h < datos.franja.fin && p.desviacion_pct[h] !== null);
  const hasta = Math.max(...horas) + 1;
  poner("cita-texto", texto(`cita_${r.veredicto}`, {
    hasta,
    x: numero(Math.abs(r.desviacion_pct)),
    xs: pct(r.desviacion_pct),
    gwh: numero(Math.abs(i.diferencia_gwh)),
  }));
}

async function copiarCita() {
  const boton = document.getElementById("cita-copiar");
  try {
    await navigator.clipboard.writeText(document.getElementById("cita-texto").textContent);
    boton.textContent = texto("copiado");
  } catch (e) {
    boton.textContent = texto("no_copiado");
  }
  setTimeout(() => { boton.textContent = texto("copiar"); }, 2000);
}

function pintarMeteo(datos) {
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
    () => pintarIndicadores(datos),
    () => {
      const p = datos.electricidad.perfil;
      const hoy = datos.hoy ? hoyPorHoras(datos.hoy) : null;
      const prevista = datos.prevista?.mw ?? null;
      document.getElementById("nota-hoy").hidden = !hoy;
      document.getElementById("nota-prevista").hidden = !prevista;
      pintarLeyenda("leyenda-electricidad", p.valor.some((v) => v !== null), Boolean(hoy), Boolean(prevista));
      pintarGrafico("grafico-electricidad", p, 0.001, texto("unidad_gw"), 1, hoy, prevista);
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
  document.getElementById("cita-copiar").addEventListener("click", copiarCita);
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
