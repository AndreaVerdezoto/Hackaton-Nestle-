# Resultados actuales — 215 pallets de producto terminado

## Escenario base vigente

El simulador actual modela únicamente el retiro de producto terminado desde las cinco líneas hacia el almacén. No existen misiones de suministro de materia prima.

Parámetros base: 215 pallets, 5 líneas (43 pallets por línea), turno de 28 800 s, ciclo productivo de 660 s por pallet y por línea, velocidad máxima de 1 m/s, aceleración/desaceleración de 1 m/s², carga y descarga de 30 s y escala de 1 m/unidad.

El último ciclo productivo termina en `43 × 660 = 28 380 s`, por lo que quedan 420 s del turno para retirar el último pallet.

| AGV | Capacidad logística | Almacenados | Cumplimiento | Utilización media | Espera media | Espera máxima | Pallets que esperaron | Cola máxima | Fin último pallet | Margen |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | AJUSTADA | 215/215 | 100% | 37.85% | 83.78 s | 202.77 s | 129 | 3 | 28 670.87 s | 129.13 s |
| 3 | AJUSTADA | 215/215 | 100% | 25.23% | 43.22 s | 108.06 s | 86 | 2 | 28 582.77 s | 217.23 s |
| 4 | AJUSTADA | 215/215 | 100% | 18.92% | 18.94 s | 94.71 s | 43 | 1 | 28 562.81 s | 237.19 s |
| 5 | SUFICIENTE | 215/215 | 100% | 15.14% | 0 s | 0 s | 0 | 0 | 28 488.06 s | 311.94 s |

`INSUFICIENTE` significa que al menos un pallet no se almacenó dentro del turno. `AJUSTADA` significa que la corrida cumple el turno pero existió espera por disponibilidad de AGV. `SUFICIENTE` significa que cumple y ninguna solicitud esperó un AGV. Esta clasificación describe la corrida simulada; no es una garantía industrial a largo plazo.

## Coherencia matemática verificada

Para 2, 3, 4 y 5 AGV, con y sin batería habilitada, se verificó que cada ruta de Dijkstra suma sus aristas, los tiempos de trayecto coinciden con la cinemática triangular/trapezoidal, `duración misión = vacío + carga + cargado + descarga`, `fin = inicio + duración`, `espera = inicio - llegada`, no existen misiones solapadas por AGV, `distancia total = vacía + cargada` y los KPIs de completados, pendientes y cumplimiento coinciden con las 215 misiones.

Con los parámetros base actuales, la batería no modifica estos resultados porque las 215 misiones terminan antes del umbral temporal de reserva.
