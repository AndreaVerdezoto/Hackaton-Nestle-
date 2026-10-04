### 1. Demanda y flujo actual

La meta operativa del escenario base es **215 pallets de producto terminado dentro de un turno de 8 horas**.

El flujo actual es deliberadamente simple:

`producción → pallet terminado → solicitud de retiro → AGV → almacén`

Cada pallet terminado genera **una sola misión logística de retiro** desde el final de su línea hasta `ControlPoint7` (almacén). Por tanto, en el escenario base:

- **215 pallets terminados**.
- **215 solicitudes de retiro**.
- **215 misiones logísticas**.

La demanda se distribuye de forma equilibrada entre cinco líneas: `COOKIE_1`, `COOKIE_2`, `COOKIE_3`, `CHOCOLATE` y `WAFER`. Con 215 pallets corresponden **43 pallets por línea**.

Las cinco líneas empiezan a producir desde el inicio del turno. El tiempo de ciclo base es **660 s (11 min) por pallet**, valor de prototipo que puede recalibrarse con datos reales de planta. La solicitud de retiro nace exactamente cuando termina el pallet.

Un pallet se considera cumplido únicamente cuando el AGV lo descarga en el almacén.

### 2. Prioridad, asignación y rutas

Las solicitudes pendientes se ordenan con el criterio actual:

`score = puntos de prioridad + minutos de espera`

La espera hace que una solicitud gane prioridad con el tiempo. Si existe empate, el orden queda determinado por el identificador de la solicitud.

Para la solicitud que corresponde atender, el sistema considera los AGV disponibles y, si la batería está activada, descarta los que no puedan completar la misión conservando la reserva. Entre los AGV válidos se selecciona el que tenga **menor distancia desde su posición actual hasta el origen de la solicitud**.

Las rutas se calculan sobre el grafo JSON mediante **Dijkstra**. Los ControlPoint siguen formando parte de la red aunque no todos sean origen o destino de una misión.

Cada misión contiene dos desplazamientos:

1. **Vacío:** posición actual del AGV → final de la línea.
2. **Cargado:** final de la línea → almacén.

La escala base es **1 m por unidad del grafo**. Debe calibrarse con medidas reales antes de una implementación industrial.

### 3. Tiempo de desplazamiento y servicio

La velocidad de referencia es **1 m/s**, con aceleración y desaceleración base de **1 m/s²**. Cada trayecto operacional comienza y termina a velocidad cero; el AGV no se detiene en cada arista intermedia del grafo.

Para distancia $D$, velocidad máxima $v$, aceleración $a$ y desaceleración $d$:

$$D_a=\frac{v^2}{2a},\qquad D_d=\frac{v^2}{2d}.$$

Si $D\ge D_a+D_d$, se usa perfil trapezoidal:

$$t=\frac{v}{a}+\frac{D-D_a-D_d}{v}+\frac{v}{d}.$$

Si el trayecto es más corto, se usa perfil triangular:

$$v_p=\sqrt{\frac{2Dad}{a+d}},\qquad t=\frac{v_p}{a}+\frac{v_p}{d}.$$

El tiempo de una misión es:

`viaje vacío + carga + viaje cargado + descarga`

Valores base:

- **Carga:** 30 s.
- **Descarga:** 30 s.
- **Peso del pallet:** 500 kg.
- **Límite operativo configurado:** 800 kg.
- **Capacidad nominal de referencia del AGV:** 1000 kg.

El peso no modifica actualmente la cinemática.

### 4. Batería y recarga

El modelo de batería es temporal y parametrizable. La configuración actual usa:

- **Autonomía nominal:** 10 h.
- **Carga completa 0→100 %:** 3 h.
- **Reserva operativa:** 20 %.
- **Batería inicial:** 100 %.
- **Consumo:** lineal con el tiempo simulado.

Antes de asignar una misión se comprueba que el AGV pueda terminarla conservando la reserva. Si no puede, queda fuera de esa asignación y puede dirigirse a recarga.

Los cargadores configurados son `ControlPoint31`, `ControlPoint28`, `ControlPoint32`, `ControlPoint30` y `ControlPoint29`. Cada cargador admite un AGV a la vez.

Estos valores son de prototipo y se sustituirán cuando se defina el modelo definitivo de AGV.

### 5. Indicadores y corte del turno

El corte oficial es **8 horas = 28 800 s**.

Los indicadores principales se interpretan así:

- **Pallets almacenados:** pallets descargados en almacén antes o exactamente en el corte.
- **Pallets por almacenar:** requeridos menos almacenados.
- **Cumplimiento:** `100 × pallets almacenados / pallets requeridos`.
- **Solicitudes generadas:** pallets cuya producción ya terminó y ya solicitaron retiro.
- **Solicitudes pendientes:** solicitudes generadas que todavía no iniciaron servicio.
- **Misiones activas:** retiros iniciados pero no terminados al corte.
- **Pallets aún en producción:** pallets planificados cuya solicitud todavía no existe al corte.
- **Utilización en misiones:** porcentaje del turno que los AGV pasan ejecutando misiones.
- **Cola máxima:** máximo de solicitudes simultáneamente esperando AGV.
- **Distancia vacía:** recorrido hasta el punto de recogida sin pallet.
- **Distancia cargada:** recorrido desde la línea hasta el almacén transportando el pallet.

Con 215 pallets, el plan logístico actual contiene **215 retiros**, no 430 movimientos.

Algunas métricas se calculan sobre toda la demanda hasta que termina, incluso si una parte supera el corte de 8 horas. El cumplimiento del turno, en cambio, solo cuenta los pallets almacenados dentro de las 8 horas.

### 6. Alcance y limitaciones

El modelo es una **simulación de eventos discretos para dimensionamiento intralogístico**. Python es la fuente de verdad del cálculo; FlexSim queda como demostración 3D independiente.

El modelo no representa en detalle:

- congestión o conflictos físicos entre AGV;
- tráfico humano;
- fallas mecánicas;
- sensores y dinámica física 3D;
- máquinas internas de cada línea;
- microparadas productivas;
- variaciones reales de demanda por SKU o turno.

La producción se abstrae mediante un tiempo de ciclo por pallet. Rutas, distancias, tiempos productivos y parámetros del AGV deben recalibrarse con datos reales antes de una implementación industrial.

La **rentabilidad queda fuera del programa** y se investigará por separado cuando se defina la solución técnica y el modelo de AGV definitivo.
