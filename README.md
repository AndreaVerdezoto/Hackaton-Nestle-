# Gestor de flota AGV — Hackathon Nestlé

## Estado actual

El programa principal es una simulación de eventos discretos para dimensionar y visualizar una flota de AGV encargada únicamente del **retiro de producto terminado** desde las líneas de producción hasta el almacén.

Flujo vigente:

`producción → pallet terminado → solicitud de retiro → selección de AGV → misión → almacén`

Las líneas producen de forma independiente. El AGV no suministra materia prima en el modelo actual.

## Organización del código

- `app/models/`: objetos del dominio (`AGV`, `Pallet`, `SolicitudTraslado`, `Mision`, batería).
- `app/services/`: lógica del sistema (grafo/Dijkstra, simulación, batería, KPIs, WMS, Néstor).
- `app/ui/`: interfaz Streamlit y Simulación 2D.
- `data/red_agv_grafo_actualizado.json`: red oficial usada por Dijkstra.
- `wms_mock.py`: WMS simulado como programa independiente.
- `flexsim/`: archivos de demostración 3D independientes; no intervienen en los cálculos Python.

## Ejecución actual

```bash
streamlit run interfaz.py
```

La interfaz tiene cuatro secciones: **Dimensionamiento**, **Resultados**, **Simulación 2D** y **Metodología**. Néstor utiliza el mismo escenario guardado en la sesión.

## Criterios que se conservan

- Rutas mínimas: Dijkstra sobre el grafo del proyecto.
- Prioridad de solicitudes: `puntos de prioridad + minutos de espera`.
- Selección de AGV: disponible, con batería suficiente y menor distancia hasta el origen de la solicitud.
- Movimiento: cinemática con aceleración/desaceleración y perfiles triangular/trapezoidal.
- Una misión logística por pallet terminado.
- El retiro usa un único punto de entrada (`crear_solicitud_retiro`): hoy lo llama la producción simulada y queda preparado para que en el futuro un sensor pueda generar la misma solicitud cuando un pallet alcance su límite de cajas.

## Documentos vigentes

- `CALCULO_FLOTA.md`: fórmulas, supuestos y alcance del modelo.
- `RESULTADOS_215_PT.md`: resultados actuales con meta fija de 215 y producción base de 340 pallets.
- `SIMULACION_2D.md`: funcionamiento de la visualización y batería.
- `RENTABILIDAD_AGV.md`: plantilla de investigación económica futura; no forma parte del programa.

Los informes históricos de arquitecturas anteriores fueron retirados para evitar mezclar el flujo actual con el antiguo suministro de materia prima o con la integración TCP de FlexSim.

## Producción configurable y meta logística

La meta fija es **215 pallets entregados al almacén** dentro de un turno de 8 horas. El simulador calcula cuántos pallets se producen por línea según el tiempo de ciclo (7 minutos por defecto, personalizable de manera general o individual). Con cinco líneas de 7 minutos el escenario genera 340 solicitudes de retiro. Solo se contabilizan los pallets que los AGV descargaron en almacén; los pallets por encima de 215 son extras y las solicitudes pendientes no cuentan como entregadas.
