# Fuentes: resultado de la exploración (fase 1)

Comprobado el 1 de noviembre de 2026 con `python scripts/explorar_fuentes.py 2026-10-21`.
Las respuestas originales quedan en `data/raw/fase1/`.

## Demanda eléctrica

| Fuente | Ámbito | Resolución | Retraso | Estado |
|---|---|---|---|---|
| REData | Comunitat Valenciana | Solo mes (hora y día dan error 400) | Datos hasta agosto de 2026 | No sirve para el indicador |
| REData | Península | Hora y día | Unos 2 días | Funciona, demasiado tarde para el 11N |
| Visor de demanda de REE (`demanda.ree.es`) | Península | 5 minutos, con historia | Unos 5 minutos | Funciona; endpoint público sin documentar |
| ESIOS, indicador 1293 «Demanda real Peninsular» | Península | 5 minutos, con historia | Unos 10 minutos | Funciona con token; API documentada |
| ESIOS | Comunitat Valenciana | No existe demanda | No aplica | No sirve para el indicador |

- **ESIOS no tiene demanda por comunidad.** De los 1982 indicadores se revisaron los 241 con demanda, consumo o referencias geográficas en el nombre. Los que incluyen la Comunitat Valenciana son generación y potencia instalada, casi todos mensuales; el único horario es el consumo de bombeo (1172), que no mide demanda. No respondió el 10350 (error 504), que por su nombre es de territorios no peninsulares.
- **El indicador 1293 de ESIOS y el visor son la misma serie:** correlación 1,0 y diferencia 0,0 % por hora el 21/10/2026. Hay 288 filas también el 12/11/2025. La web puede usar el visor sin token y ESIOS como respaldo documentado.
- El visor y REData **no son la misma serie**. El 21/10/2026 coinciden de noche y difieren hasta un 19,5 % en horas de sol (unos 5 GW a mediodía). La causa no está confirmada: restar la columna `aut` del visor no la elimina. Una misma comparación debe usar una sola serie.
- El visor responde a veces con un 200 y la lista vacía. Hay que validar que trae filas.

## NO₂

**No se publica en la web.** La validación mostró que no distingue un festivo de un día normal. Se sigue descargando y calculando en `data/`.

| Fuente | Contenido | Retraso | Estado |
|---|---|---|---|
| Generalitat, `med-cont-atmos-mh-v2-2026` (últimos 2000 registros) | Provisional; cubre unas 3 horas de toda la red | Lo último era del 30/10 a las 23:00 el 01/11 por la mañana | Se ha visto un solo estado; cadencia real sin medir |
| Generalitat, mismo dataset (ZIP mensual) | Provisional, largo por medición | Actualización irregular: octubre llega hasta el día 13 | Funciona |
| Generalitat, `med-cont-atmos-mh-2025` (CSV mensual) | Ancho, un mes por fichero | Unos 2 meses | Funciona; da el 12/11/2025 |
| Agencia Europea (parquet por estación) | Provisional, 2026 | Por lotes, de horas a días; lo último era del 30/10 a las 10:00 | Funciona; da todas las estaciones |
| Ministerio, `ica.miteco.es/datos/ica-ultima-hora.csv` | Solo índice por estación, sin concentración | Menos de 2 horas | No permite calcular la desviación |
| `rvvcca.pica.gva.es` | Portal de la Red Valenciana | Sin comprobar | Error 502 el 01/11 |
| `webcat-web.gva.es` | Visor antiguo | Sin comprobar | Host inexistente (NXDOMAIN), aunque la web de la Generalitat aún lo enlaza |

- El portal `dadesobertes.gva.es` corta descargas devolviendo 200: se detecta por el tamaño o por el número de filas, y hay que reintentar.
- **Las horas de la red no siguen el cambio de hora.** La etiqueta `L` cubre `[L-1, L)` UTC durante todo el año. Se ha comprobado con el pico de radiación solar (centroide 12,5 en julio y en enero) y con la temperatura de Open-Meteo (mejor correlación con etiqueta = UTC, en julio de 2025 y octubre de 2026). En horario de invierno la hora civil coincide con la etiqueta; en horario de verano es la etiqueta + 1. Afecta al 21/10/2026, y solo a ese día de referencia.
- La Agencia Europea y la Generalitat usan el mismo reloj: correlación 1,0 con desfase 0 en la estación de Grau (octubre de 2026).

## Meteorología

Open-Meteo responde sin clave para Castelló y València, en hora local. La celda de Castelló está centrada en (39,96, 0,00).

## Festivos

Ningún festivo local de Castelló, Almassora, Benicàssim, Borriana o L'Alcora cae en las fechas de 2026 (tabla publicada por Castellón Plaza, que remite al DOGV). Los festivos autonómicos de octubre y noviembre son 9/10 y 1/11 y los nacionales 12/10: ninguno es miércoles. No se han comprobado los festivos locales de 2025 para el 12/11/2025.

## Validación del método (fase 2)

Con `python scripts/actualizar.py`, a 1 de noviembre de 2026.

**Calibración.** Se han comparado 16 miércoles normales (otoño de 2025 y de 2026) con los tres miércoles anteriores, igual que se hará con el día de huelga.

| Indicador, franja 7–21 h | Margen de un día normal | Desviación típica | Festivo 12/10/2026 | ¿Lo detecta? |
|---|---|---|---|---|
| Electricidad peninsular | −8,2 % a +11,1 % | 3,2 % | −18,0 % | Sí |
| NO₂ urbano de Castelló | −68,1 % a +257,2 % | 34,2 % | −46,8 % | No |

- **El rango mínimo–máximo de pocos días no basta para afirmar un efecto.** Con 3 días de referencia, un día normal cae fuera de ese rango la mitad de las veces. Sirve para decir que no hay diferencia, no para decir que la hay.
- **Veredicto diario.** Solo se dice que hay diferencia si el día sale de la banda de referencia y también del margen de calibración. El margen usa días ya pasados, así que queda fijado antes de la huelga.
- **La electricidad detecta un festivo de sobra.** Una caída inferior al 8,2 % no se podrá distinguir de un miércoles normal.
- **El NO₂ de Castelló no supera la prueba:** ni un festivo nacional se distingue de un día normal, porque la meteorología domina el dato.
- En 2025 no hay NO₂ de CEIP La Marina, así que esa parte de la calibración usa dos estaciones.

**Pendiente de comprobar.** Que la serie «últimos 2000 registros» use el mismo reloj que la Agencia Europea (por ahora no se solapan; sí se ha comprobado con su ZIP mensual) y la cadencia real de la Generalitat, que se anota en `data/log/cadencia.csv`.
