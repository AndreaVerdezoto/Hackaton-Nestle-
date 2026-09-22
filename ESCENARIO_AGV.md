# Escenario de demostración FlexSim (modo físico)

**Este documento describe únicamente la demo TCP conservada.** Para dimensionar
la flota use la pestaña principal Análisis de flota, el motor offline
`app/services/simulador_flota.py` y los documentos `ANALISIS_FLOTA.md` y
`CALCULO_FLOTA.md`. Los tiempos observados por TCP no intervienen en ese cálculo.
La política de reloj, batería y posiciones descrita aquí pertenece solo a la demo.

## Arquitectura encontrada

`interfaz.py` mantiene un `GestorFlota` en `st.session_state` y un fragmento cada
segundo consulta `ESTADO`. El gestor ya ordena solicitudes por prioridad y edad,
selecciona AGV por distancia/batería/capacidad y calcula rutas con Dijkstra sobre
`data/red_agv_grafo_actualizado.json`. Mantiene solicitudes, misiones y AGV en memoria.
`SolicitudTraslado` limita el pallet a 800 kg; la capacidad del modelo AGV es 1000 kg.
Se conserva la restricción de solicitud de 800 kg.

El API FastAPI de `app/main.py` registra objetos Pallet de forma independiente; la
ventana Tkinter es un prototipo. Ninguno alimentaba el gestor Streamlit. El flujo
de misiones usa el identificador de pallet de la solicitud, no requiere crear un
registro paralelo en el API. La única prueba original era un script con destino
obsoleto `LINEA_1`: fallaba antes de conectar. Ahora comprueba el flujo manual con
`CHOCOLATE` y un cliente simulado, sin conexiones TCP.

## Archivos y cambios

Nuevos:

- `app/services/escenario_turno.py`: configuración, eventos, reloj, ejecución,
  observación de misiones, KPIs y resultados JSON.
- `app/ui/escenario_panel.py`: controles y visualización Streamlit.
- `tests/test_escenario_turno.py`: pruebas con reloj y TCP simulados.
- `ESCENARIO_AGV.md`: operación y límites del experimento.

Modificados:

- `app/services/flexsim_cliente.py`: `crear_pallet` exige `OK|PALLET_CREADO`.
- `app/models/solicitud.py`: estaciones físicas opcionales, conservando los
  valores por defecto manuales y validaciones de peso.
- `app/services/gestor_flota.py`: mapeos AGV_04/05, filtro de flota activa, reloj
  inyectable para la edad de solicitudes, observación de misiones y control de
  reasignación. Validación exacta de ACK y prevención de doble inicio.
- `interfaz.py`: incorpora el panel y aprovecha el fragmento existente. No hay
  threads; el escenario persiste en session_state. La entrada manual está
  temporalmente deshabilitada mientras existe una corrida para no contaminarla.
- `prueba_gestor.py`: regresión manual reproducible, sin FlexSim.
- `.gitignore`: excluye `resultados/`.

Dijkstra, grafo, modelos AGV/Mision/Pallet, archivos `.fsm` y puente TCP permanecen
sin cambios. No se añaden dependencias ni se hace commit.

## Supuestos reproducibles (no son datos proporcionados por Nestlé)

- Turno base: **107 ciclos de ida y retorno + un suministro final**, 215 piernas
  con IDs distintos PALLET_001...PALLET_215: 108 suministros y 107 retornos.
- Se programa el inicio nominal de cada ciclo en `k * 28800 / 108`, k=0...107.
  Los retornos **no tienen un disparador temporal independiente**: se habilitan
  únicamente con LIBRE de la ida. Su `tiempo_programado` es la referencia nominal
  del ciclo; `hora_habilitacion` registra la finalización física observada de la ida.
  `id_ciclo` y `depende_de` permiten auditar cada pareja.
- Round-robin **por ciclo**: COOKIE_1, COOKIE_2, COOKIE_3, CHOCOLATE, WAFER.
  Totales por línea: 44/44/43/42/42 movimientos. Cada tipo conserva una diferencia
  máxima de uno entre líneas. No se fuerza 43 por línea porque rompería las parejas.
- El movimiento 215 es suministro COOKIE_3; solo se crea tras completar los 107
  retornos y alcanzar su instante nominal. Si no ocurre antes del corte, queda
  pendiente/no lanzado, sin falsificar la finalización de los ciclos anteriores.
- Peso constante 500 kg y prioridad NORMAL; la fórmula de prioridad existente
  conserva sus puntos y envejecimiento, con segundos lógicos durante el escenario.
- Posiciones heredadas: AGV_01 TRANSIT_4 (CP7), AGV_02 TRANSIT_2 (CP11), AGV_03
  TRANSIT_1 (CP13). Verificarlas físicamente antes de iniciar.
- Posiciones AGV_04/05: **sin valor por defecto**. Para 4/5 AGV, la interfaz exige
  elegir el nodo real inicial. Se guardan en el resultado.
- Baterías iniciales del prototipo: 85/70/95%; AGV_04/05 se suponen al 100%.
  Constantes centralizadas en `escenario_turno.py`, junto al peso y el factor.
- Prueba pequeña separada: 6 movimientos durante 600 segundos: suministro y retorno
  COOKIE_1 (movimientos 1/2), COOKIE_2 (3/4), COOKIE_3 (5/6).
  Se identifica como `prueba_pequena`, no como turno base.

## Protocolo y responsabilidad

Python crea el pallet mediante `CREAR_PALLET`, registra la solicitud, aplica la
cola/selección/rutas y envía `MISION`. Las solicitudes automáticas usan:

| Tipo | Estación de creación/carga | Estación de descarga |
| --- | --- | --- |
| Suministro | spawn_almacen | entrada_material_<línea> |
| Producto terminado | spawn_<línea> | pallet_transit4 |

Los campos origen/destino del comando MISION siguen siendo los ControlPoints
existentes; los últimos dos campos especifican las estaciones anteriores.
Las solicitudes manuales siguen usando pallet_transit4 y fin_linea_* como antes.

Al asignar una ida, el gestor reserva el AGV por `id_ciclo`. La selección conserva
su puntuación original y comprueba autonomía para ida + desplazamiento desde la
entrada al spawn de retorno + retorno al almacén, usando las distancias existentes.
Al recibir LIBRE, primero actualiza ubicación y batería, mantiene el AGV reservado
y notifica al escenario. Python crea inmediatamente OTRO pallet en el spawn de
esa misma línea y asigna su retorno exclusivamente al AGV reservado. El nuevo
pallet representa producto terminado ya disponible, no transformación del suministro.
Solo el LIBRE del retorno libera la reserva; la cola de nuevas idas vuelve a
evaluarse por prioridad. Los demás AGV pueden realizar otros ciclos en paralelo.
Los números de movimiento identifican las parejas; no imponen ejecución global
serial entre diferentes ciclos.

Python calcula las rutas y distancias con el grafo actual. El protocolo MISION
solo transmite extremos: **no puede imponer la secuencia de nodos Dijkstra a
FlexSim**. FlexSim ejecuta su navegación física. Verificar coherencia entre grafo
y modelo antes de interpretar las distancias.

## Reloj y KPIs

`t_lógico = min(duración, (time.monotonic() - inicio_real) * factor)`.
No se adelanta el reloj por cada rerun ni se inventan duraciones de viaje. El
factor queda fijo durante la corrida. Pausar FlexSim no pausa este reloj.
La velocidad efectiva de FlexSim debe corresponder al factor elegido; el puente
no ofrece reloj simulado ni mecanismo de sincronización para comprobarlo.

Cada evento guarda tiempo programado, ACK de creación, asignación/reserva antes
de enviar MISION y primera observación de LIBRE. Los tiempos son segundos lógicos.
La espera es asignación menos creación; el ciclo es finalización menos creación.
La espera promedio incluye solo asignados y el ciclo solo completados; los tamaños
de muestra se exportan. Estos promedios siguen siendo por pierna, no por pareja.
El retraso máximo de lanzamiento usa el tiempo nominal para idas y el instante
LIBRE habilitante para retornos. El backlog máximo cuenta pallets creados sin asignar, incluido el
instante previo al despacho.

Ocupación por AGV: suma de intervalos desde asignación de la ida hasta LIBRE del
retorno (o del suministro final), truncados al corte. Incluye el tiempo de crear
el pallet de retorno y cualquier espera entre ambas piernas, sin doble conteo.
Utilización = ocupado / tiempo observado. Libre = observado - ocupado:
significa **sin misión reservada**, no necesariamente disponible (incluye recarga).
Los fallos de envío pueden dejar reservas inciertas: corridas ERROR no son
válidas para comparar capacidad. Distancias por AGV y total son **estimaciones
del grafo para misiones completadas**, incluyendo aproximación al origen. Se
excluyen trayectos parciales en curso; no existe odometría física en el protocolo.

Al llegar a 28800 s se congela un resultado: completados, pendientes (incluye
no lanzados, en cola y en curso), backlog máximo, promedios, utilización, tiempos
y distancias. Una respuesta LIBRE observada al corte o después no cuenta como
finalización dentro del turno. Tras cerrar solo se observa el drenaje de misiones
confirmadas; no se crean pallets ni se asigna trabajo nuevo. DETENIDO usa su
tiempo real de corte, no simula que transcurrieron las ocho horas.

Los JSON se guardan automáticamente en `resultados/<fecha>_<uuid>.json`, con
timestamp UTC, tamaño de flota, configuración inicial, escenario, factor, estado,
KPIs y eventos. También pueden descargarse desde Streamlit. Un error al escribir
se muestra y permite reintentar sin repetir la corrida.

## Límites de operación

- Cada consulta tiene la latencia TCP y el muestreo del fragmento (aproximadamente
  un segundo real, amplificado por el factor). No son timestamps de FlexSim.
- Los 215 eventos siempre se programan. Si no se ejecuta el fragmento durante
  suficiente tiempo, o TCP consume el turno, pueden quedar eventos sin lanzar.
  Se contabilizan como pendientes/no lanzados; no se envían fuera del horizonte.
- Mantener una sola sesión/pestaña controladora activa. No hay coordinador entre
  sesiones, recuperación de proceso ni persistencia continua de estado en ejecución.
- No hay CANCELAR, RESET ni consulta de existencia de pallet. Ante timeout o
  respuesta inesperada se cierra la corrida; no se reenvían escrituras ambiguas.
  El operador debe restablecer FlexSim antes de reiniciar y reutilizar PALLET_001.
- Batería y recarga siguen siendo modelos Python del prototipo, no telemetría.
  Se conserva la recarga original de cinco segundos reales (5 * factor lógicos).
  La regla existente puede rechazar misiones por reserva de batería aunque el
  AGV aún no haya llegado al umbral de recarga; ese bloqueo permanece visible
  como backlog. No se ha cambiado la política de batería/asignación.

## Pruebas y primera corrida pequeña

Pruebas sin conexión TCP (Python 3.9+):

```powershell
python -m unittest discover -s tests -v -b
python -m unittest prueba_gestor -v -b
python -m compileall -q app interfaz.py prueba_gestor.py tests
```

En el equipo revisado, `.venv` contiene un entorno Linux Python 3.9 que no se
puede ejecutar como `.venv\Scripts\python.exe`. El Python disponible para las
pruebas es `C:\Users\Jorge\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.
Ese intérprete no tiene Streamlit; la interfaz requiere el entorno donde ya
se ejecutaba Streamlit o instalar esa dependencia existente en un entorno Windows.
No se necesita ninguna librería nueva para el escenario ni las pruebas.

Si se usa este mismo equipo Windows sin un entorno Streamlit funcional, estos
comandos preparan uno aislado con la dependencia que ya utiliza el proyecto
(instalación requiere conexión a Internet; no se ejecutó durante esta entrega):

```powershell
Set-Location -LiteralPath 'C:\Users\Jorge\Desktop\hackathon nestle\git hub\Hackaton-Nestle-'
$pythonAGV = 'C:\Users\Jorge\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $pythonAGV -m venv .venv-agv
& .\.venv-agv\Scripts\python.exe -m pip install streamlit
& .\.venv-agv\Scripts\python.exe -m streamlit run interfaz.py
```

Resultado de validación de esta entrega: 25 pruebas del escenario y una regresión manual
correctas con Python 3.12.14; compilación de app/interfaz/pruebas correcta.
Comparación AST de Dijkstra idéntica y hashes Git de grafo/puente/FSM sin cambios.
`git diff --check` sin errores. No se validó Streamlit en ejecución ni FlexSim físico.

1. Desde la raíz del repositorio, en el entorno con Streamlit y `st.fragment`:
   `python -m streamlit run interfaz.py`.
2. Restablecer el modelo FlexSim, quitar pallets de pruebas previas y verificar
   AGV_01 en CP7, AGV_02 en CP11, AGV_03 en CP13. Sin Sources que generen demanda.
   Iniciar el modelo con el puente existente en 127.0.0.1:5056.
3. Elegir **3 AGV**, **Prueba pequeña: 6 movimientos / 600 s** y **factor 10**;
   usar velocidad efectiva x10 en FlexSim. Marcar la verificación física y pulsar
   **Iniciar escenario**. Son aproximadamente 60 segundos reales; pallets
   de suministro programados a 0/200/400 segundos lógicos. Los retornos se crean
   solo al recibir LIBRE de sus respectivas idas y usan el mismo AGV.
4. Revisar carga en spawn_*, descarga en las entradas o pallet_transit4,
   contadores y cola. Pendientes al corte pueden ser un resultado válido, no se
   fuerzan seis completados. Confirmar ausencia de errores TCP.
5. Revisar/descargar el JSON. Para abortar, **Detener escenario**; permitir que
   terminen las misiones ya enviadas o restablecer el modelo físicamente.
6. Antes de repetir, restablecer FlexSim, confirmar la casilla correspondiente
   y pulsar **Reiniciar / volver al modo manual**.
7. Solo después elegir **Turno base: 215 movimientos / 28800 s**. Repetir con
   2/3/4/5 AGV y mismo factor, configuración y condiciones físicas. A x60 el
   horizonte son 480 segundos reales. Verificar primero que FlexSim sostenga
   esa velocidad; factores altos amplifican el error de muestreo.

Durante la implementación no se ejecuta ninguna simulación física ni se generan
resultados de capacidad de flota; los clientes de las pruebas son simulados.
