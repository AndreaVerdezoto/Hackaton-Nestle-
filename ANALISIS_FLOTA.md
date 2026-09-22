> INFORME HISTÓRICO OBSOLETO PARA DIMENSIONAMIENTO. La interpretación anterior de demanda y sus resultados no son válidos. Consulte RESULTADOS_215_PT.md y CALCULO_FLOTA.md: la base oficial es 215 pallets terminados más suministros independientes. Demo FlexSim permanece separada.

# Entrega: análisis offline y demostración FlexSim

## Arquitectura encontrada

El proyecto tenía un gestor Python con grafo JSON (94 nodos y 109 aristas),
Dijkstra, prioridad de solicitudes, selección por distancia/batería y TCP.
`interfaz.py` mantenía objetos en session_state y consultaba ESTADO cada segundo.
El escenario anterior vinculaba idas y retornos, pero sus tiempos dependían de
la observación física y de un reloj real acelerado. Por ello no era un modelo
independiente para dimensionamiento. FastAPI/Pallet y el prototipo Tkinter eran
componentes independientes y no se modificaron.

## Arquitectura final y reutilización

```text
interfaz.py — pestañas con ejecución exclusiva
  Análisis de flota
    analisis_panel.py → simulador_flota.py → grafo / Dijkstra / prioridad
    sin FlexSimCliente, batería del prototipo, TCP ni esperas reales
  Demo FlexSim
    demo_panel.py → escenario_turno.py / GestorFlota → FlexSimCliente → TCP
```

`GestorFlota(habilitar_flexsim=False)` carga el grafo sin instanciar el cliente.
El simulador reutiliza `obtener_ruta`, mapeos, resolución de nodos,
`calcular_score_solicitud` y la validación de 800 kg de SolicitudTraslado.
No llama al asignador de batería ni a completar/iniciar misiones físicas.
La selección offline conserva el criterio de menor distancia; el trayecto
cargado es común a los candidatos y la batería se excluye explícitamente.

La lógica anterior de interfaz se trasladó a `mostrar_demo()` en demo_panel.py,
sin eliminar formularios, tablas, escenarios ni polling. Una guarda impide que
su fragmento consulte TCP en Análisis. Cambiar de Demo a Análisis cierra la
corrida Python activa sin enviar comandos físicos. Las pestañas se ejecutan
solo si están seleccionadas: no basta con ocultar visualmente la demo.

## Archivos de esta entrega

Nuevos:

- `app/services/simulador_flota.py`: parámetros, cinemática, demanda sustituible,
  simulador, KPIs, comparación y exportación JSON.
- `app/ui/analisis_panel.py`: parámetros, comparación, cuatro gráficos, detalle,
  interpretación, ejemplo calculado, presupuesto y sensibilidad.
- `app/ui/demo_panel.py`: interfaz anterior trasladada a una función.
- `tests/test_simulador_flota.py`: 18 pruebas del análisis y cinemática.
- `tests/test_interfaz_analisis.py`: 4 pruebas AppTest de Streamlit sin servidor/TCP.
- `CALCULO_FLOTA.md`: fórmulas y explicación mostradas dentro de Streamlit.
- `ANALISIS_FLOTA.md`: este informe de entrega y operación.
- `requirements.txt`: Streamlit 1.64.0, versión instalada y probada; el motor solo
  usa la biblioteca estándar. El API FastAPI independiente conserva su entorno.

Modificados en esta entrega:

- `interfaz.py`: entrada de dos pestañas, análisis principal y demo aislada.
- `app/services/gestor_flota.py`: opción para no crear el cliente FlexSim.
- `app/ui/escenario_panel.py`: título de demostración, sin llamarlo dimensionamiento.
- `ESCENARIO_AGV.md`: identificado como documentación exclusiva del modo demo.

Los cambios anteriores en `.gitignore`, SolicitudTraslado, FlexSimCliente,
GestorFlota, prueba_gestor y el escenario TCP permanecen sin commit. El diff
frente a HEAD incluye también esas entregas previas. No se modificó el archivo
autosave `.fsm` no rastreado que ya aparecía al retomar la solicitud.

## Método y fórmulas exactas

Ver `CALCULO_FLOTA.md`, también disponible en «¿Cómo se calcula?» en Streamlit.
Incluye las ecuaciones triangulares/trapezoidales, escala, tiempos de cada
componente y una tabla con todas las fórmulas de KPIs.

El reloj `heapq` salta a llegadas y finalizaciones. Cada AGV permanece reservado
desde el inicio de la ida hasta completar el retorno. Se calcula el tramo vacío
entrega→recogida por Dijkstra, sin atajos. El suministro adicional llega en su
instante uniforme, como exige la nueva distribución, sin la barrera global que
tenía la demo anterior. Al no haber vehículo disponible la demanda queda en cola.
Al terminar un ciclo el vehículo vuelve al almacén. Se procesa todo el trabajo,
incluso después del turno, y se registra cada inicio y finalización.

El tiempo total es la última finalización de **todos** los movimientos, no solo
del ID 215, que podría acabar antes de un retorno previo. Ambos tiempos se
exportan para que esa diferencia sea auditable. El corte es inclusivo (`fin <= T`).
Utilización y backlog corresponden al turno; distancias y promedios al trabajo
completo hasta terminar. La utilización incluye carga, descarga y espera de
disponibilidad, no supera el 100% y no supone que el AGV esté desplazándose siempre.

## Datos conocidos, supuestos y limitaciones

Datos de referencia: objetivo solicitado 215 movimientos/8 h; límite del código
800 kg; topología del grafo existente. Velocidad 2 m/s, aceleración 1 m/s² y
desaceleración 1 m/s² son la configuración comunicada por el usuario en esta
solicitud, no una lectura nueva del archivo `.fsm`.

Supuestos editables: llegadas uniformes, líneas round-robin, carga 30 s, descarga
30 s, disponibilidad de retorno 0 s, escala 1 m/unidad, peso 500 kg y todos los
AGV inicialmente en ControlPoint7. No son datos históricos de Nestlé. La espera
de retorno cero no representa tiempo de producción cero. El peso no modifica
velocidad/aceleración sin un modelo físico válido.

Se excluyen batería/recarga, fallas, congestión/colisiones entre AGV y tráfico
humano no validados. No se modelan motores, neumáticos, masa dinámica, sensores
ni producción. Es una simulación logística operacional, no física 3D. Se debe
calibrar escala, tiempos, demanda y demás supuestos con datos reales de planta.

## Resultados base realmente calculados

Configuración: 215 movimientos, 28800 s, v=2, a=d=1, carga/descarga 30 s,
espera retorno 0, escala 1, todos inicialmente en CP7, batería excluida.

| AGV | Completados al corte | Backlog | Mov/h | Espera media (s) | Utilización media |
| --- | --- | --- | --- | --- | --- |
| 2 | 215 | 0 | 26,875 | 0 | 58,57% |
| 3 | 215 | 0 | 26,875 | 0 | 39,04% |
| 4 | 215 | 0 | 26,875 | 0 | 29,28% |
| 5 | 215 | 0 | 26,875 | 0 | 23,43% |

Las cuatro terminan a 28663,4699 s (7 h 57 min 43 s), con margen 136,5301 s
(2,2755 min; 0,4741% del turno). Distancia vacía: 11741,2908 m; cargada:
28638,1883 m; total: 40379,4791 m, por flota para toda la demanda. No se forma
cola con los valores base. Las distancias y finalizaciones son iguales porque
añadir vehículos no adelanta las llegadas de demanda y se mantiene el criterio
de menor distancia. Las unidades adicionales pueden permanecer ociosas.

Entre las opciones evaluadas 2/3/4/5, el menor tamaño suficiente es **2 AGV bajo
estos supuestos**. No se evaluó una flota de 1 AGV y esto no es garantía real.
El margen depende también de que la última llegada se programa cerca del corte;
no equivale a una reserva genérica de capacidad.

La corrida auditada se guarda en `resultados/analisis_base.json` con timestamp,
parámetros, demanda, hash del grafo, KPIs, AGV, movimientos y traza. Los resultados
no están codificados en la interfaz: se recalculan al pulsar Comparar.

## Verificación

48 pruebas aprobadas: 25 del escenario demo, 18 de cinemática/simulador offline,
4 de interfaz Streamlit y una regresión manual del gestor. La compilación Python
no presenta errores. La traza completa está en `resultados/validacion_python.txt`.

Se verificaron: conteos/IDs/parejas/round-robin, perfil largo y corto, distancia
cero, validación, rutas dirigidas, falla clara de conectividad, demanda histórica,
prioridad, 2/3/4/5 AGV, exclusión mutua, mismo AGV en ambas piernas, inclusión
del corte exacto, drenaje posterior, utilizaciones/distancias/KPIs derivados de
eventos, reproducibilidad y comparación justa. Las pruebas bloquean la creación
del cliente TCP, sockets y `sleep` durante el análisis. AppTest prueba abrir y
comparar, parámetros, restablecimiento, errores visibles, presupuesto y sensibilidad.

Dijkstra conserva el mismo AST que HEAD. Grafo, puente y `.fsm` versionado
conservan los hashes Git de HEAD. No se hizo commit ni se ejecutó FlexSim o TCP
real. El modo análisis funciona sin FlexSim; su independencia está probada
bloqueando explícitamente cualquier intento de usar esos recursos.

## Abrir Streamlit y primera comparación

El entorno Windows `.venv-agv` ya está preparado con Streamlit. Ejecutar:

```powershell
Set-Location -LiteralPath 'C:\Users\Jorge\Desktop\hackathon nestle\git hub\Hackaton-Nestle-'
& .\.venv-agv\Scripts\python.exe -m streamlit run interfaz.py
```

1. Abrir en el navegador la dirección que indique Streamlit; FlexSim puede estar cerrado.
2. La pestaña inicial es **Análisis de flota**. Pulsar **Restablecer valores base**
   para usar la configuración de referencia y revisar el resumen.
3. Pulsar **Comparar 2, 3, 4 y 5 AGV**. Se ejecutan cuatro simulaciones Python
   inmediatamente; no se solicita conexión física ni factor de aceleración real.
4. Revisar tabla, cuatro gráficos y la interpretación. Expandir Ver detalle para
   cada flota y escoger un ciclo en Desglose de un movimiento.
5. Abrir **¿Cómo se calcula?** y **Datos conocidos / configurados actualmente y
   supuestos editables** para explicar cada resultado.
6. Descargar JSON. Opcionalmente ingresar costo unitario (0 no genera monto) o
   editar los tres escenarios de sensibilidad y pulsar Calcular sensibilidad.
7. Si se cambian parámetros, pulsar Comparar nuevamente; se advierte cuando los
   resultados guardados corresponden a una configuración anterior.

Para reconstruir el entorno en este equipo, solo si fuera necesario:

```powershell
$pythonAGV = 'C:\Users\Jorge\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $pythonAGV -m venv .venv-agv
& .\.venv-agv\Scripts\python.exe -m pip install -r requirements.txt
```

Para repetir las pruebas:

```powershell
& .\.venv-agv\Scripts\python.exe -m unittest discover -s tests -v -b
& .\.venv-agv\Scripts\python.exe -m unittest prueba_gestor -v -b
& .\.venv-agv\Scripts\python.exe -m compileall -q app interfaz.py tests prueba_gestor.py
```

Para usar solo el motor (sin Streamlit ni paquetes externos):

```python
from app.services.simulador_flota import ParametrosSimulacion, comparar_flotas
resultados = comparar_flotas(ParametrosSimulacion())
```

La demo y sus instrucciones físicas se conservan por separado en `ESCENARIO_AGV.md`.
