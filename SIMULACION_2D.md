# Simulación 2D y batería temporal

Abrir `interfaz.py` con Streamlit y elegir **Simulación 2D**. Seleccionar 2/3/4/5 AGV y pulsar Iniciar. Pausar congela el reloj y la batería; Reanudar continúa; Reiniciar permite otra flota. Velocidades de reproducción ×1/×2/×5/×10. En «Explorar instante y detalle» puede consultarse cualquier segundo de la corrida y pausar allí.

El motor existente calcula las misiones, rutas y recargas. La interfaz reproduce el resultado por tiempo simulado; no asigna misiones ni calcula una batería alternativa. El mapa usa coordenadas y aristas del JSON existente. La interpolación respeta el perfil cinemático y los pesos de ruta, sin saltar entre nodos. Las líneas entre coordenadas son una representación esquemática 2D.

La pestaña Análisis de flota conserva el modelo previo sin batería y sus parámetros; no deben mezclarse sus conclusiones con la nueva corrida 2D. La pestaña 2D usa la referencia solicitada de 1 m/s, 215 pallets, turno de 8 h, carga/descarga 30 s y 100% de batería inicial. Sigue calculando hasta terminar las misiones. La autonomía afecta realmente a la asignación y produce pausas de servicio durante la recarga.

## Fuente única y fórmulas

`app/models/bateria.py` centraliza las referencias y el modelo temporal:

- Consumo: 100/36000 puntos porcentuales por segundo simulado, tanto libre como ocupado, cargando/descargando pallet o esperando.
- Recarga conectado: 100/10800 puntos por segundo; no se descuenta simultáneamente consumo operativo.
- Uso restante hasta reserva: max(0, batería−20) × 36000/100 segundos.
- Tiempo restante de carga: (100−batería) × 10800/100 segundos.
- Se asigna misión solo si batería actual − consumo del servicio completo ≥20%. Se usan los tiempos cinemáticos existentes, incluida carga/descarga y disponibilidad de producto. Sin factor por peso.

Reserva 20% es política del prototipo. Autonomía y recarga lineales son simplificaciones, no telemetría ni un modelo eléctrico del fabricante. El 20% puede emplearse en el desplazamiento al cargador; nunca se planifica viaje/espera al cargador si la energía disponible no alcanza. El AGV permanece fuera de candidatos hasta el 100%.

72% equivale a 5 h 12 min de operación antes de reserva (redondeo a minutos). A 45%, la carga completa requiere 1 h 39 min. Al 100%, el uso antes de reserva es 8 h, no 10 h: las 10 h describen la descarga completa teórica.

## Cargadores confirmados

El usuario confirmó CP31, CP32, CP30 y CP29. Se conservan esos cuatro puntos en el mapa. El grafo dirigido permite llegar a CP30 pero no salir hacia almacén: se excluye del despacho de recargas y se identifica visualmente. No se modificó el grafo para resolverlo.

Se elige el cargador utilizable más cercano con Dijkstra, una plaza por cargador (supuesto). Si está ocupado, se espera y se consume batería. Las reservas de plaza evitan recargas simultáneas en el mismo punto. No hay carga parcial, opportunity charging ni planificación predictiva.

## Datos y separación

Se registran batería de inicio/fin de cada misión, itinerario hacia cargador, llegada, conexión, desconexión, batería inicial y de conexión. La consulta de estado devuelve batería actual, tiempos restantes, estado, misión, pallet actual y asignado, destino, distancia cargada/vacía, tiempo ocupado/libre/operativo/de recarga y cantidad de recargas iniciadas.

La utilización pequeña de la vista representa ocupación en misiones. El detalle separa recarga de tiempo libre. No se confunde carga de pallet con CARGANDO_BATERIA.

El análisis original y la demo conservan su comportamiento. El adaptador histórico de AGV por distancia delega su tasa a la misma ley temporal; no se reescribió GestorFlota ni se conectó FlexSim. No hay 3D ni agentes adicionales.

## Archivos

Nuevos: `app/models/bateria.py`, `app/services/bateria_flota.py`, `app/services/estado_visual.py`, `app/ui/simulacion_2d.py`, `tests/test_bateria_2d.py` y este documento.

Modificados: `app/models/agv.py` (referencias centralizadas), `app/services/simulador_flota.py` (modo de batería opcional y eventos), `interfaz.py` (pestaña y pausa al salir).

Verificación: 84 pruebas; ejemplos de tiempos restantes, consumo en reposo, reserva de misión, invariancia por peso, carga al 100%, exclusión de asignación durante recarga, interpolación, reloj pausado y controles Streamlit. Revisión real en navegador de mapa, tarjetas y recarga al segundo 23500.

Dijkstra, grafo, cliente TCP y panel Demo sin cambios; función cinemática idéntica mediante comparación del AST. Los cambios preexistentes del usuario en `.fsm` y el archivo XML no se tocaron. Sin commit.
