# Corrección oficial: 215 pallets de producto terminado

## Capacidad logística y cierre físico: interpretación actualizada

Sin modificar ninguna llegada, misión, ruta ni tiempo de servicio, se añade el diagnóstico:

| AGV | Capacidad logística | Utilización | Espera media AGV | Espera máxima AGV | Pallets que esperaron | Cola máxima | Termina 215 | Exceso sobre 8 h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | SATURADA | 93,71% | 12,20 s | 30,50 s | 129 | 1 | 8 h 01 min 24,72 s | 84,72 s |
| 3 | SUFICIENTE | 62,51% | 0 s | 0 s | 0 | 0 | 8 h 00 min 54,22 s | 54,22 s |
| 4 | SUFICIENTE | 46,88% | 0 s | 0 s | 0 | 0 | 8 h 00 min 54,22 s | 54,22 s |
| 5 | SUFICIENTE | 37,51% | 0 s | 0 s | 0 | 0 | 8 h 00 min 54,22 s | 54,22 s |

**3 AGV es la menor flota evaluada que elimina la espera por vehículos.** Todas almacenan 214 pallets al corte, con 1 en servicio y 0 sin asignar; throughput al corte: 26,75 pallets/h. Este throughput mide salida física, no estabilidad de capacidad.

Criterio explícito para la corrida: INSUFICIENTE si el servicio total de todas las misiones supera AGV × duración del turno; SATURADA si ese trabajo cabe pero hay espera por AGV; SUFICIENTE si cabe y no hay espera. El trabajo requerido incluye los servicios después del corte; no es la utilización truncada a 8 h. No es una garantía a largo plazo ni un umbral industrial universal.

Las esperas de pallets se calculan como inicio − llegada sobre producto terminado. La cola máxima incluye toda la demanda logística pendiente después de los despachos. Viaje vacío, disponibilidad de producto, carga, viaje cargado y descarga son servicio físico; no espera de asignación de AGV.

En 3/4/5 el pallet pendiente fue liberado cerca del cierre y empezó sin esperar vehículo. En 2 también hubo espera por AGV. La interfaz separa ambos conceptos en dos bloques y deja las métricas secundarias en un expander. La comparación principal muestra esperas y cierre; se conserva el detalle económico en otro expander.

Validación: 75 pruebas aprobadas, cero fallos/errores/omisiones. Comparación exacta con la exportación anterior: mismas demandas, mismas misiones y mismos KPIs previos. Solo se agregan indicadores derivados. Los archivos protegidos y el AST cinemático permanecen iguales. Sin FlexSim real ni commit.

Archivos de esta actualización: `app/services/indicadores_capacidad.py` (nuevo), `app/services/simulador_flota.py` (incorporación de indicadores), `app/ui/negocio_panel.py`, `tests/test_indicadores_capacidad.py` (nuevo), `tests/test_interfaz_analisis.py`, `CALCULO_FLOTA.md`, este informe y `resultados_215_pt.json`.

El escenario base ahora genera **215 misiones independientes de producto terminado hacia ControlPoint7**, más los suministros configurados. Suministro base: 0, dato de planta pendiente. Con 40 suministros se generan 255 movimientos logísticos, de los cuales solo 215 son producto terminado. No existe relación 1:1 ni retorno generado automáticamente tras un suministro.

## Recálculo real, suministro = 0

Se ejecutaron de nuevo 2/3/4/5 AGV con turno 28800 s, velocidad 2 m/s, aceleración/desaceleración 1 m/s², carga/descarga 30 s, espera de disponibilidad 0 s y escala 1. La distribución uniforme y el round-robin son supuestos pendientes de validación; 43 pallets por línea. Exportación completa: `resultados_215_pt.json`.

| AGV | Almacenados al corte | Pendientes | Cumplimiento | Utilización | Tiempo libre/capacidad disponible | Tiempo para los 215 |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | 214/215 | 1 | 99.5349% | 93.7138% | 6.2862% | 8 h 01 min 24.72 s |
| 3 | 214/215 | 1 | 99.5349% | 62.5112% | 37.4888% | 8 h 00 min 54.22 s |
| 4 | 214/215 | 1 | 99.5349% | 46.8834% | 53.1166% | 8 h 00 min 54.22 s |
| 5 | 214/215 | 1 | 99.5349% | 37.5067% | 62.4933% | 8 h 00 min 54.22 s |

**Cierre físico: ninguna de las cuatro flotas almacena los 215 dentro de 8 h bajo estos supuestos. Esto no equivale a insuficiencia de capacidad logística.** No se reutilizaron porcentajes de la versión anterior. En 3/4/5 no hay espera en cola, pero el último pallet llega en el segundo 28666.046512; su servicio requiere 188.177700 s y termina después del corte. Tener más AGV no adelanta una llegada. En 2 AGV también aparece espera en cola. No se alteraron llegadas ni tiempos para forzar cumplimiento.

El porcentaje de capacidad disponible representa tiempo libre, no capacidad productiva garantizada. La corrección no atribuye producción adicional a los AGV ni cambia fórmulas económicas.

## Cambios

- `app/services/simulador_flota.py`: parámetros separados, DemandaMision, demandas independientes, posición real por misión, KPI exclusivo de producto terminado y versión v2.
- `app/ui/analisis_panel.py`: base oficial visible, suministro editable, sensibilidad claramente marcada y archivo separado de corridas obsoletas.
- `app/ui/negocio_panel.py`: resultado principal y comparación por pallets terminados, suministro separado y capacidad disponible.
- `app/services/analisis_negocio.py`: nombre del contador de producto terminado actualizado, sin cambiar fórmulas financieras.
- `tests/test_simulador_flota.py`, `tests/test_interfaz_analisis.py`, `tests/test_analisis_negocio.py`: regresiones adaptadas y pruebas nuevas.
- `CALCULO_FLOTA.md`, `RENTABILIDAD_AGV.md`, `ANALISIS_FLOTA.md`: documentación actualizada o identificada explícitamente como histórica obsoleta.
- `RESULTADOS_215_PT.md` y `resultados_215_pt.json`: informe y evidencia de las cuatro ejecuciones.

La distribución puede sustituirse pasando una secuencia de DemandaMision con datos reales al simulador. En la interfaz se conserva round-robin explícitamente identificado como supuesto. Cada viaje vacío y cargado utiliza Dijkstra y falla si falta ruta. Al terminar producto terminado, el AGV queda en ControlPoint7; al terminar suministro, queda en la entrada de la línea.

## Verificación

**75 pruebas aprobadas; 0 fallos, 0 errores, 0 omitidas.** Incluyen 215 misiones de producto terminado, 255 misiones con suministro 40, destinos, separación de conteos, corte inclusivo, cumplimiento aunque haya suministros pendientes, llegadas independientes, ausencia de solapamientos, límites de utilización, demanda inválida, archivo de corridas obsoletas y ejecución sin TCP.

Hashes idénticos para gestor/Dijkstra, cliente TCP, grafo, FlexSim, escenario demo y paneles demo. El AST de `tiempo_desplazamiento` coincide exactamente con la versión previa. No se ejecutó FlexSim real ni se hizo commit.

`git diff --stat` sigue incluyendo cambios anteriores y excluyendo archivos sin seguimiento:

```text
 .gitignore                      |   4 +-
 app/models/solicitud.py         |  15 +-
 app/services/flexsim_cliente.py |  11 +-
 app/services/gestor_flota.py    |  79 +++++-
 interfaz.py                     | 580 ++--------------------------------------
 prueba_gestor.py                |  80 ++----
 6 files changed, 147 insertions(+), 622 deletions(-)
```

Los archivos de esta corrección se encontraban sin seguimiento o son nuevos; no se hizo staging para alterar esa situación.
