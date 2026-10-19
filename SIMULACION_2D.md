# Simulación 2D

La pestaña **Simulación 2D** reproduce el mismo escenario que ya fue calculado desde Dimensionamiento. No vuelve a decidir rutas, prioridades ni asignaciones y no ejecuta una segunda simulación paralela.

## Fuente de verdad

El flujo es:

`Dimensionamiento → escenario guardado → Resultados / Simulación 2D / Néstor`

La vista 2D recibe las misiones, rutas, tiempos y eventos del simulador y los representa sobre el mapa del grafo JSON.

## Flujo visual vigente

Las líneas producen de forma independiente. Cuando termina un pallet:

`PRODUCIENDO → PALLET LISTO / SOLICITUD → AGV HACIA LÍNEA → CARGA → VIAJE AL ALMACÉN → DESCARGA`

No existen misiones de suministro de materia prima.

Los ControlPoint que antes estuvieron asociados a ese flujo siguen formando parte de la red y pueden ser atravesados por una ruta de Dijkstra; no se eliminan del grafo por dejar de ser origen/destino de una misión.

## Movimiento

La interpolación visual sigue la ruta calculada por Dijkstra y utiliza los tiempos del modelo cinemático del simulador. El AGV no se considera detenido en cada nodo intermedio: el trayecto operacional se calcula de origen a destino con aceleración y desaceleración.

La vista permite reproducir, pausar, reanudar, reiniciar y explorar instantes de la corrida. Pausar la reproducción congela el reloj visual; no altera el resultado calculado.

## Batería

La batería usa `app/models/bateria.py` como fuente de parámetros y `app/services/bateria_flota.py` para gestionar recargas.

Configuración actual del prototipo:

- autonomía nominal: 10 h;
- reserva operativa: 20 %;
- carga completa 0→100 %: 3 h;
- batería inicial: 100 %;
- consumo lineal con el tiempo simulado.

Una misión solo es elegible si puede finalizar conservando la reserva. Los cargadores configurados son:

- `ControlPoint31`
- `ControlPoint28`
- `ControlPoint32`
- `ControlPoint30`
- `ControlPoint29`

Cada cargador se modela como una plaza. La selección actual prioriza el cargador utilizable de menor distancia según la red.

En el escenario base de 215 pallets las misiones terminan antes de requerir una recarga, por lo que activar batería no modifica los resultados operativos de 2, 3, 4 o 5 AGV con los parámetros actuales.

## Alcance

La Simulación 2D es una representación operativa del modelo Python, no una simulación física 3D. No modela congestión real, interacción humana, sensores, motores ni colisiones físicas entre AGV.

FlexSim permanece como demostración 3D independiente y no interviene en el cálculo ni en la reproducción 2D.
