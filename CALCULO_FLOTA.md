### 1. Demanda independiente de producto terminado y suministro

Dato de Nestlé: al menos **215 pallets de producto terminado por turno de 8 horas**, desde producción hasta almacén. Cada pallet genera una misión propia. Los suministros tienen un parámetro independiente, inicialmente 0 por falta de dato de planta; 40 suministros producen 255 movimientos logísticos, sin aumentar la cantidad de pallets terminados requerida.

Distribución equilibrada/round-robin: supuesto editable por falta de distribución real por línea. El escenario base asigna 43 pallets a cada línea: COOKIE_1, COOKIE_2, COOKIE_3, CHOCOLATE y WAFER. La API acepta una secuencia explícita `DemandaMision` para reemplazar líneas, prioridades y timestamps cuando existan datos reales.

Llegadas distribuidas uniformemente durante el turno por falta de histórico de demanda. Para cada flujo de N misiones: `llegada_i = i × T / N`, i desde 0 hasta N−1. Los 215 pallets terminados tienen intervalo 133,953488 s. Los suministros tienen su propio intervalo, sin generar retornos implícitos. No existe relación 1:1 ni reserva de AGV para una pareja.

Todos los AGV parten por defecto de ControlPoint7. Las solicitudes usan prioridad y envejecimiento existentes; empates por ID de misión. Se elige el AGV disponible más cercano al origen de la misión mediante Dijkstra, con desempate por ID. Se excluye batería no validada.

### 2. Rutas y escala

Recogidas de producto terminado: COOKIE_1 → ControlPoint24; COOKIE_2 → ControlPoint25; COOKIE_3 → ControlPoint26; CHOCOLATE → ControlPoint18; WAFER → ControlPoint15. Todas terminan en ControlPoint7 (almacén).

Cada misión calcula por Dijkstra el desplazamiento vacío desde la posición real del AGV al origen y el viaje cargado hasta el destino. Al terminar producto terminado queda en almacén; tras un suministro queda en la entrada de la línea. No se sustituye una ruta inexistente por distancia cero. Dijkstra y el grafo permanecen sin cambios.

`Distancia en metros = distancia del grafo × factor de escala`. El factor base 1 m/unidad es supuesto y requiere calibración.

### 3. Tiempo cinemático, de reposo a reposo

El modelo es una **simulación de eventos discretos con modelo cinemático
operacional para dimensionamiento intralogístico**. Cada trayecto importante
empieza y termina a velocidad cero; no se impone una parada en cada arista.
No es una simulación dinámica 3D.

Para distancia $D$, velocidad máxima $v$, aceleración $a$ y desaceleración $d$:

$$D_a=\frac{v^2}{2a},\qquad D_d=\frac{v^2}{2d}.$$

Si $D\ge D_a+D_d$, hay aceleración, crucero y frenado:

$$t=\frac{v}{a}+\frac{D-D_a-D_d}{v}+\frac{v}{d}.$$

Si el trayecto es más corto, no alcanza la velocidad máxima:

$$v_p=\sqrt{\frac{2Dad}{a+d}},\qquad t=\frac{v_p}{a}+\frac{v_p}{d}.$$

Con $D=0$, el tiempo es cero. Se rechazan distancia negativa, valores no finitos
y velocidad/aceleración/desaceleración no positivas. La referencia comunicada
en la solicitud es $v=2$ m/s, $a=d=1$ m/s². Todos son editables.

### 4. Servicio y eventos

`Servicio = viaje vacío + espera de disponibilidad + carga + viaje cargado + descarga`.

La espera de disponibilidad solo aplica a producto terminado, antes de cargar. Cero indica producto disponible; no generación instantánea. Carga y descarga base 30 s, peso 500 kg, máximo 800 kg. No se modifica la cinemática según peso.

Al finalizar cada misión se actualiza la posición y se libera el AGV. Cualquier misión pendiente elegible puede atenderse a continuación. No se crea otro pallet como consecuencia del suministro.

El reloj de eventos salta entre llegadas y finalizaciones sin reloj real, TCP ni FlexSim. Procesa eventos simultáneos antes del despacho. Se continúa después del corte para medir el tiempo hasta finalizar; una finalización exactamente en el corte cuenta como completada.

### 5. Indicadores

- Pallets terminados almacenados: cuenta exclusivamente misiones de producto terminado con fin ≤ T.
- Pendientes de producto terminado = requeridos − almacenados al corte.
- Cumplimiento = 100 × almacenados / requeridos; cumple únicamente con pendientes de producto terminado iguales a cero.
- Tiempo para producto terminado = máximo fin de sus misiones. Puede diferir del tiempo para toda la logística si hay suministros.
- Pallets terminados/h = almacenados al corte / horas del turno.
- Suministros completados y pendientes se presentan por separado.
- Total logístico requerido = pallets terminados + suministros configurados; no equivale a pallets producidos.
- Ocupado por AGV = suma de max(0, min(fin,T) − inicio) de sus misiones; utilización = 100 × ocupado/T.
- Capacidad disponible = 100 − utilización media: porcentaje de tiempo libre, no capacidad productiva garantizada.
- Distancias y promedios de espera/servicio incluyen toda la demanda hasta finalizar. Ocupación y tiempo libre se recortan al turno.
- Las métricas técnicas de completados, pendientes y throughput logístico incluyen ambos tipos y no deciden el cumplimiento de producto terminado.

### 6. Interpretación

El cierre físico exige cero pallets terminados pendientes; la función histórica `minimo_suficiente` conserva exclusivamente ese criterio. La capacidad logística se interpreta aparte: SUFICIENTE si no hay espera y el servicio requerido cabe en las horas-AGV del turno; SATURADA si cabe pero hay esperas; INSUFICIENTE si el trabajo de servicio supera esas horas. Es un diagnóstico de la corrida, no garantía de estabilidad futura. Espera por AGV = inicio de servicio − llegada; no incluye transporte físico. No se garantiza operación real sin calibrar tiempos, escala y distribución. Más AGV no adelantan la disponibilidad de pallets: una llegada cercana al corte puede terminar después incluso sin cola.

Producción adicional y rentabilidad siguen siendo supuestos independientes. Transportar 215 pallets no implica producir 215 pallets extra. Ver las fórmulas económicas en Rentabilidad.

No se modelan congestión, colisiones, fallas, recarga ni proceso productivo. Demo FlexSim es una demostración separada y conserva su lógica anterior; no dimensiona este escenario.
