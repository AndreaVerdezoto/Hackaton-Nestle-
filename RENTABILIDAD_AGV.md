# Evaluación operativa y económica por escenario

## Abrir y presentar

Desde la carpeta del proyecto, en PowerShell:

```powershell
.\.venv-agv\Scripts\python.exe -m streamlit run interfaz.py
```

1. En **Análisis de flota**, elegir **2** en **Número de AGV a simular**.
2. Pulsar **Simular escenario**. Solo se ejecuta esa flota y la corrida queda guardada en la sesión.
3. Explicar cumplimiento, movimientos, tiempos, utilización y distancias.
4. Completar la línea base y los costos disponibles. Vacío significa pendiente; cero debe declararse explícitamente.
5. Pulsar **Guardar análisis de negocio** para incorporar esos supuestos a la corrida y usarlos de referencia en la siguiente. Editar campos solo cambia la vista previa hasta guardarlos.
6. Elegir **3** y pulsar **Simular escenario**. La corrida anterior conserva sus parámetros.
7. Pulsar **Comparar escenarios simulados** y seleccionar las corridas. La comparación no ejecuta simulaciones. Advierte si cambian parámetros, línea base o economía.
8. Exportar el JSON desde **Ver análisis técnico → Eventos y exportación**. El historial vive en la sesión Streamlit, no en una base persistente; cerrar/reiniciar la sesión puede perderlo.

La economía siempre utiliza la cantidad de vehículos de la corrida mostrada. Cambiar el selector para una futura simulación no modifica el resultado anterior. El guardado económico explícito actualiza únicamente la corrida seleccionada.

## Lectura operativa

Se conserva el simulador y sus fórmulas. La interfaz presenta 12 tarjetas; los detalles y eventos quedan en expanders. Solo la comparación solicitada muestra gráficos: movimientos, utilización y payback cuando existe un valor válido (máximo tres).

Los tiempos por fase se obtienen de inicio de servicio, viaje vacío, disponibilidad del retorno, carga, viaje cargado y descarga. Se recortan al final del turno. La suma de fases coincide con el tiempo ocupado. Ocupado y libre se suman entre AGV; su unidad es hora-AGV. Los porcentajes se dividen entre cantidad de AGV × duración del turno. Las distancias siguen correspondiendo a toda la demanda hasta terminarla.

El dato oficial es 215 pallets de producto terminado trasladados por turno. Los suministros son independientes, con valor base 0 por falta de dato; 40 suministros añaden 40 misiones y el total logístico es 255. Transportar producto existente no constituye producción adicional.

La comparación contra la operación manual exige confirmar el mismo turno y mezcla de movimientos:

- Movimientos adicionales atendidos = completados del escenario − movimientos de la línea base.
- Incremento logístico = diferencia / movimientos actuales × 100, solo con base mayor que cero.
- Horas logísticas recuperadas = volumen común × (servicio manual medio − servicio AGV medio) / 3600. El volumen común es el mínimo entre movimientos actuales y completados. No son horas de producción ni ahorro de nómina; el servicio debe incluir los mismos componentes en ambos casos.
- Reducción de espera media = espera manual informada − espera simulada. El promedio simulado abarca toda la demanda hasta finalizar, conforme al motor original.

La pérdida de producción por espera y los pallets producidos actuales quedan como contexto. Sin un modelo validado que vincule logística y producción no se deduce producción adicional. Los pallets extra usados en economía son una hipótesis ingresada, identificada como tal.

## Fórmulas económicas

Todos los importes se expresan en USD. Los costos no informados por Nestlé se etiquetan como SUPUESTO EDITABLE. No hay precios, salarios, márgenes, mantenimiento o energía predeterminados.

```text
Iniciales = integración + infraestructura + cargadores + otros iniciales
CAPEX = N × costo por AGV + Iniciales
T = turnos por día × días por año
Beneficio de producción anual = pallets extra por turno × margen por pallet × T
Ahorro anual = (operación manual sin personal + personal + otros costos actuales) × fracción evitable
OPEX anual = N × mantenimiento anual por AGV + energía anual + otros OPEX
Neto anual = beneficio de producción + ahorro − OPEX
Payback años = CAPEX / Neto, si Neto > 0
Payback meses = Payback años × 12
ROI anual = Neto / CAPEX × 100, si CAPEX > 0
```

Los costos actuales se registran una sola vez: operación manual excluye personal. El porcentaje evitable debe justificarse; no se supone que toda la nómina desaparece. Cero producción adicional permite evaluar solo ahorro, sin inventar margen por pallet. Un beneficio neto no positivo se muestra como **No rentable bajo los supuestos actuales.** El payback no aplica en ese caso y el ROI puede ser negativo.

Para un objetivo H (supuesto inicial editable: 3 años), manteniendo las demás variables:

```text
Pallets extra mínimos/turno = max(0, CAPEX/H + OPEX − ahorro) / (margen × T)
Margen mínimo/pallet = max(0, CAPEX/H + OPEX − ahorro) / (pallets extra × T)
Ahorro anual mínimo = max(0, CAPEX/H + OPEX − beneficio de producción)
Costo máximo/AGV = (Neto × H − Iniciales) / N
```

Se muestra también el mínimo entero de pallets redondeado hacia arriba. Con necesidad positiva y denominador cero no existe umbral finito. Si el objetivo ya está cubierto, el requisito adicional es cero. Un costo máximo negativo significa que ni vehículos gratuitos alcanzan el objetivo. Campos desconocidos quedan pendientes. Recuperación simple: no incluye descuento financiero, impuestos ni financiación.

## Datos que faltan de planta

Movimientos actuales, duración comparable de servicio manual, espera logística, producción perdida, pallets terminados, cotización de AGV e instalación, infraestructura, cargadores, mantenimiento, energía, personal y otros costos evitables; margen de contribución, producción adicional justificable, calendario de operación y calibración de distancias. Todos son editables; no se fabrican resultados económicos.

## Archivos y verificación

- `app/ui/analisis_panel.py`: ejecución individual, historial y detalle técnico.
- `app/ui/negocio_panel.py`: tarjetas, línea base, economía, resumen y comparación.
- `app/services/analisis_negocio.py`: fases, impacto, economía y copias independientes de escenarios.
- `tests/test_analisis_negocio.py`: 12 pruebas operativas/económicas.
- `tests/test_interfaz_analisis.py`: 6 pruebas de interfaz; se adapta el antiguo flujo automático al nuevo selector individual.

Resultado: **62 pruebas aprobadas, 0 fallos, 0 errores, 0 omitidas**, incluyendo las pruebas de escenario, simulador y `prueba_gestor`. FlexSim/TCP se sustituyen por dobles en las pruebas correspondientes. No se ejecutó una simulación real contra FlexSim.

Los resultados anteriores de dimensionamiento quedan invalidados por la corrección de demanda. Consulte RESULTADOS_215_PT.md para el recálculo de 2/3/4/5 AGV. La rentabilidad no convierte automáticamente producto transportado en producción adicional.

`git diff --stat` del repositorio incluye trabajo anterior y excluye los archivos sin seguimiento:

```text
 .gitignore                      |   4 +-
 app/models/solicitud.py         |  15 +-
 app/services/flexsim_cliente.py |  11 +-
 app/services/gestor_flota.py     |  79 +++++-
 interfaz.py                     | 580 ++--------------------------------------
 prueba_gestor.py                |  80 ++----
 6 files changed, 147 insertions(+), 622 deletions(-)
```

Los archivos de esta entrega están sin seguimiento en Git (incluidos los paneles que ya existían antes de esta solicitud). No se hizo commit ni staging. Este documento describe el flujo actual; `ANALISIS_FLOTA.md` conserva la entrega anterior.
