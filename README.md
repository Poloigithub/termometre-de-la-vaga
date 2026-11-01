# Termòmetre de la vaga

Mide la huella de la huelga general del 11 de noviembre de 2026 con datos públicos: la demanda eléctrica peninsular como indicador principal y el NO₂ de Castelló como indicio secundario. Cada dato se compara con miércoles normales a la misma hora.

La web está en `docs/`. El detalle de las fuentes y de cómo se ha validado el método está en [FUENTES.md](FUENTES.md).

## Reproducirlo desde cero

Hace falta Python 3.9 o superior.

```bash
pip install -r requirements.txt
```

```bash
python scripts/actualizar.py
```

El comando descarga lo que falte a `data/raw/` y regenera el resto. Para ver la web en local:

```bash
python -m http.server 8000 --directory docs
```

Para pasar los tests:

```bash
pytest
```

## Cómo está organizado

| Ruta | Contenido |
|---|---|
| `config.yaml` | Días de referencia, franjas, estaciones y umbrales |
| `data/raw/` | Respuesta original de cada fuente, con la fecha de descarga en el nombre. No se modifica nunca |
| `data/processed/` | Series limpias y cálculos. Se puede borrar y regenerar desde `data/raw/` |
| `data/log/` | Errores de descarga (`descargas.log`) y cuándo cambia cada fuente de aire (`cadencia.csv`) |
| `data/estado.json` | Última descarga correcta de cada fuente |
| `docs/` | Web estática. `docs/data/` es la copia de los datos que se publica |
| `scripts/descargar.py` | Descarga las fuentes |
| `scripts/procesar.py` | Limpia los datos y los pasa a hora civil |
| `scripts/calibrar.py` | Mide cuánto se desvía un miércoles normal |
| `scripts/calculo.py` | Desviación, banda y veredicto |
| `scripts/resumen.py` | Genera `resumen.json` para la web |
| `scripts/validar.py` | Prueba de sensibilidad con un festivo |
| `scripts/explorar_fuentes.py` | Exploración inicial de las fuentes |

## Cómo se calcula

Para cada hora, la referencia es la mediana de los días de referencia y la banda va de su mínimo a su máximo. La desviación es `(valor − referencia) / referencia × 100`. El resumen del día es la media entre las 7 y las 21 h.

El veredicto solo dice que hay diferencia si el día sale de la banda y también del margen empírico, que `scripts/calibrar.py` mide con miércoles ya pasados.

## Notas para el mantenimiento

- **Horas de la red de aire:** no siguen el cambio de hora. La etiqueta `L` cubre `[L-1, L)` UTC todo el año, y `etiqueta_a_civil` la convierte.
- **ESIOS:** es opcional. Si el visor de REE falla y existe la variable `ESIOS_TOKEN`, se usa el indicador 1293, que es la misma serie.
- **Valenciano:** rellena `va` en `docs/textos.js` con las claves de ese fichero y las de los atributos `data-t` de `docs/index.html`. El selector de idioma aparece solo.
