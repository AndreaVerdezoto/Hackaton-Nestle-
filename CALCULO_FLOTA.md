### 1. Demanda y flujo encadenado

La meta operativa del escenario base es **215 pallets de producto terminado dentro de un turno de 8 horas**. El modelo usa un flujo **1:1**: cada pallet requiere primero un suministro de material a su línea y después un retiro de producto terminado hacia almacén.

Por tanto:

- **215 suministros** de material.
- **215 retiros** de producto terminado.
- **430 movimientos logísticos** en total.

La demanda se distribuye de forma equilibrada entre cinco líneas: COOKIE_1, COOKIE_2, COOKIE_3, CHOCOLATE y WAFER. En el escenario base son **43 pallets por línea**.

Las cinco líneas generan su primera necesidad de material al inicio del turno. Después, cada línea solicita el siguiente suministro con la misma cadencia del ciclo productivo. El ciclo base es **660 s (11 min) por pallet**, valor de prototipo que puede recalibrarse con datos reales de planta.

Cuando un suministro termina, ese pallet entra a producción. Cada línea procesa un pallet a la vez; si el siguiente material ya fue entregado, el siguiente ciclo puede comenzar inmediatamente al quedar libre la línea. El retiro de producto terminado **solo se genera cuando termina la producción** de ese pallet.

Un pallet se considera completado únicamente cuando el producto terminado ha sido descargado en almacén.

### 2. Asignación, rutas y movimiento

Todos los AGV parten por defecto desde `ControlPoint7`. Para cada solicitud pendiente, el gestor selecciona un AGV disponible y calcula las rutas sobre el grafo JSON actual.

La asignación usa las prioridades y el envejecimiento ya definidos en el gestor. Entre AGV disponibles, se selecciona el más cercano al origen de la misión según la distancia obtenida con **Dijkstra**; los empates se resuelven por ID de AGV.

Cada movimiento tiene dos trayectos:

1. **Vacío:** desde la posición actual del AGV hasta el punto de recogida.
2. **Cargado:** desde el punto de recogida hasta el destino.

Los suministros parten del almacén y terminan en la entrada de la línea correspondiente. Los retiros de producto terminado parten del final de la línea y terminan en `ControlPoint7`.

La escala base es **1 m por unidad del grafo**. Es un supuesto del prototipo y debe calibrarse con medidas reales de planta antes de una implementación.

### 3. Tiempo de desplazamiento y servicio

La velocidad de referencia del AGV es **1 m/s**, con aceleración y desaceleración base de **1 m/s²**. Cada trayecto operacional comienza y termina a velocidad cero; el AGV no se detiene en cada arista del grafo.

Para una distancia $D$, velocidad máxima $v$, aceleración $a$ y desaceleración $d$:

$$D_a=\frac{v^2}{2a},\qquad D_d=\frac{v^2}{2d}.$$

Si $D\ge D_a+D_d$, el perfil tiene aceleración, crucero y frenado:

$$t=\frac{v}{a}+\frac{D-D_a-D_d}{v}+\frac{v}{d}.$$

Si el trayecto es más corto y no alcanza la velocidad máxima:

$$v_p=\sqrt{\frac{2Dad}{a+d}},\qquad t=\frac{v_p}{a}+\frac{v_p}{d}.$$

El tiempo de una misión es:

`viaje vacío + carga + viaje cargado + descarga`

En el escenario base:

- **Carga:** 30 s.
- **Descarga:** 30 s.
- **Peso del pallet:** 500 kg.
- **Límite operativo del prototipo:** 800 kg.
- **Capacidad nominal de referencia del AGV:** 1000 kg.

El peso no modifica actualmente la cinemática del vehículo.

### 4. Batería y recarga

La simulación sí incluye batería. El modelo base usa:

- **Autonomía nominal:** 10 h.
- **Carga completa 0→100 %:** 3 h.
- **Reserva operativa:** 20 %.
- **Batería inicial:** 100 %.
- **Consumo:** lineal con el tiempo simulado.

Con esta ley, pasar de 100 % a la reserva del 20 % equivale a **8 horas de uso simulado**.

Antes de asignar una misión, el sistema comprueba que el AGV pueda terminarla sin bajar de la reserva. Si no puede, el AGV se dirige a un cargador disponible. Cada cargador admite un AGV a la vez.

El prototipo dispone de cinco cargadores: `ControlPoint31`, `ControlPoint28`, `ControlPoint32`, `ControlPoint30` y `ControlPoint29`.

En el escenario base actual, las flotas evaluadas completan la demanda antes del cierre del turno, por lo que la recarga no interrumpe el cumplimiento de las 8 horas.

### 5. Indicadores y corte del turno

El corte oficial del análisis es **8 horas = 28 800 s**.

Los principales indicadores se interpretan así:

- **Pallets completados:** producto terminado descargado en almacén antes o exactamente en el corte.
- **Pallets pendientes:** requeridos menos completados.
- **Cumplimiento:** `100 × pallets completados / pallets requeridos`.
- **Suministros completados:** suministros terminados dentro del turno.
- **Movimientos completados:** suministros + retiros terminados dentro del turno.
- **Solicitudes generadas:** movimientos cuya necesidad ya existe al corte.
- **Solicitudes pendientes:** solicitudes generadas que aún no han iniciado servicio.
- **Misiones activas:** movimientos iniciados pero todavía no terminados al corte.
- **Movimientos aún no generados:** movimientos cuya necesidad aparecerá después del corte.
- **Utilización en misiones:** porcentaje del turno que cada AGV pasa ejecutando misiones.
- **Cola máxima:** mayor cantidad de solicitudes esperando atención durante la simulación.

En el escenario base actual, **215 pallets completos implican 215 suministros + 215 retiros = 430 movimientos**.

La métrica histórica `capacidad_disponible_pct = 100 − utilización en misiones` debe interpretarse únicamente como tiempo no utilizado en misiones; no representa por sí sola capacidad productiva garantizada si un escenario incluye recargas u otras indisponibilidades.

Las distancias y ciertos promedios se calculan sobre la demanda completa hasta finalizar. En el escenario base actual la demanda termina dentro del turno, por lo que el horizonte coincide con el corte de 8 horas.

### 6. Alcance y limitaciones

El modelo es una **simulación de eventos discretos para dimensionamiento intralogístico**. Python es la fuente de verdad del cálculo; FlexSim es una demostración visual independiente y no alimenta los KPI del sistema.

El modelo no representa en detalle:

- congestión o conflictos físicos entre AGV;
- tráfico humano;
- fallas mecánicas;
- sensores y dinámica física 3D;
- máquinas internas de cada línea;
- microparadas productivas;
- variaciones reales de demanda por SKU o turno.

La producción se abstrae mediante un tiempo de ciclo por pallet y una capacidad de proceso por línea. Las rutas, distancias, tiempos productivos y demás parámetros deben recalibrarse con datos reales de planta antes de una implementación industrial.

La rentabilidad es un análisis separado. Cumplir **215 pallets por turno** no significa producir 215 pallets adicionales respecto a la operación actual; cualquier producción adicional, ahorro, CAPEX, OPEX, ROI o payback depende de datos económicos y de línea base configurados en la pestaña Rentabilidad.
