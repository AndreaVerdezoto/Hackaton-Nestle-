"""Presentación del análisis: no modifica parámetros base, fórmulas ni simulador."""
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from app.models.bateria import CARGADORES, VELOCIDAD_REFERENCIA_MS
from app.services.escenarios import crear_escenario
from app.ui.encabezado import mostrar_encabezado
from app.services.simulador_flota import (
    ParametrosSimulacion, SimuladorFlota,
    exportar_json, SUPUESTOS, LIMITACIONES, VERSION_MODELO, LINEAS, META_PALLETS_TURNO,
)

BASE = asdict(ParametrosSimulacion())


def restablecer():
    for nombre, valor in BASE.items():
        st.session_state[f"ana_{nombre}"] = valor
    st.session_state.pop("analisis_resultados", None)
    st.session_state.pop("sensibilidad_resultados", None)
    st.session_state["ana_minutos_produccion"] = 7.0
    st.session_state["ana_personalizar_lineas"] = False
    for linea in LINEAS:
        st.session_state[f"ana_minutos_{linea}"] = 7.0


def _inicializar_parametros():
    for nombre, valor in BASE.items():
        st.session_state.setdefault(f"ana_{nombre}", valor)
    st.session_state.setdefault("ana_minutos_produccion", 7.0)
    st.session_state.setdefault("ana_personalizar_lineas", False)
    for linea in LINEAS:
        st.session_state.setdefault(f"ana_minutos_{linea}", 7.0)
    # La referencia del prototipo es fija: 1 m/s. Evita conservar 2 m/s de sesiones anteriores.
    st.session_state["ana_velocidad_maxima_ms"] = VELOCIDAD_REFERENCIA_MS


def _sincronizar_tiempos_lineas():
    if st.session_state["ana_personalizar_lineas"]:
        for linea in LINEAS:
            st.session_state[f"ana_minutos_{linea}"] = st.session_state["ana_minutos_produccion"]


def _valores_parametros():
    valores = {k: st.session_state[f"ana_{k}"] for k in BASE}
    valores["tiempo_produccion_s"] = st.session_state["ana_minutos_produccion"] * 60
    valores["tiempos_produccion_lineas_s"] = (
        {linea: st.session_state[f"ana_minutos_{linea}"] * 60 for linea in LINEAS}
        if st.session_state["ana_personalizar_lineas"] else None
    )
    return valores


def _historial_vigente():
    historial = st.session_state.setdefault("escenarios_simulados", [])
    versiones_vigentes = {VERSION_MODELO, VERSION_MODELO + "_bateria"}
    antiguos = [e for e in historial if e["resultado"].get("version_modelo") not in versiones_vigentes]
    if antiguos:
        st.session_state.setdefault("escenarios_obsoletos", []).extend(antiguos)
        historial[:] = [e for e in historial if e["resultado"].get("version_modelo") in versiones_vigentes]
        st.session_state.pop("escenario_activo", None)
    return historial


def _mostrar_obsoletos():
    if st.session_state.get("escenarios_obsoletos"):
        st.warning("Las corridas anteriores usaban otra demanda y no son válidas para este dimensionamiento. Vuelve a simular las flotas.")
        with st.expander("Archivo de corridas obsoletas (solo exportación)"):
            st.download_button("Exportar corridas obsoletas", exportar_json(st.session_state.escenarios_obsoletos),
                               file_name="corridas_obsoletas.json", mime="application/json")


def _escenario_seleccionado():
    historial = _historial_vigente()
    if not historial:
        return None, None, {}
    ids = [e["id"] for e in historial]
    etiquetas = {e["id"]: f"Corrida {i+1} · {e['resultado']['numero_agv']} AGV" for i, e in enumerate(historial)}
    activo = st.selectbox("Escenario simulado", ids, format_func=etiquetas.get, key="escenario_activo")
    return next(e for e in historial if e["id"] == activo), activo, etiquetas


def mostrar_dimensionamiento():
    mostrar_encabezado("Dimensionamiento")
    st.caption("Configura el escenario y ejecuta la simulación Python que alimenta Resultados, Simulación 2D y Néstor.")
    _inicializar_parametros()
    _mostrar_obsoletos()
    st.caption(f"Meta fija: {META_PALLETS_TURNO} pallets entregados al almacén. Las entregas adicionales cuentan como extra.")

    cantidad = st.selectbox("Número de AGV a simular", [2, 3, 4, 5], key="flota_elegida")
    columnas = st.columns(3)
    principales = [
        ("duracion_turno_s", "Duración del turno (s)", 1.0, "28800 segundos equivalen a 8 horas."),
        ("velocidad_maxima_ms", "Velocidad máxima (m/s)", 0.01, "Referencia fija del prototipo: 1 m/s."),
        ("tiempo_carga_s", "Carga (s)", 0.0, "Tiempo por pallet."),
        ("tiempo_descarga_s", "Descarga (s)", 0.0, "Tiempo por pallet."),
    ]
    for i, (campo, etiqueta, minimo, ayuda) in enumerate(principales):
        with columnas[i % 3]:
            st.number_input(
                etiqueta,
                min_value=minimo,
                key=f"ana_{campo}",
                help=ayuda,
                disabled=campo == "velocidad_maxima_ms",
            )

    st.number_input("Producción por pallet · todas las líneas (min)", min_value=0.1, step=0.5,
                    key="ana_minutos_produccion", help="Valor inicial: 7 minutos. No cambia la meta de 215 pallets.")
    with st.expander("Avanzado · producción por línea", expanded=False):
        st.checkbox("Personalizar tiempos de cada línea", key="ana_personalizar_lineas",
                    on_change=_sincronizar_tiempos_lineas)
        if st.session_state["ana_personalizar_lineas"]:
            for linea in LINEAS:
                st.number_input(f"{linea} (min/pallet)", min_value=0.1, step=0.5,
                                key=f"ana_minutos_{linea}")
        else:
            st.caption("Todas las líneas usan el tiempo general.")

    with st.expander("Parámetros avanzados", expanded=False):
        izquierda, derecha = st.columns(2)
        with izquierda:
            st.number_input("Aceleración (m/s²)", min_value=0.01, key="ana_aceleracion_ms2",
                            help="Configuración de referencia: 1 m/s². Controla cuánto tarda en ganar velocidad.")
            st.number_input("Desaceleración (m/s²)", min_value=0.01, key="ana_desaceleracion_ms2",
                            help="Configuración de referencia: 1 m/s². Controla el tiempo de frenado.")
            st.number_input("Factor de escala (m/unidad)", min_value=0.001, key="ana_factor_escala_metros_por_unidad",
                            help="Convierte la distancia del grafo a metros. Calibrar con medidas reales de planta.")
            st.number_input("Peso por pallet (kg)", min_value=1.0, max_value=800.0, key="ana_peso_pallet_kg",
                            help="Supuesto: 500 kg; máximo 800 kg. El peso no modifica la cinemática.")
            st.caption("Escenario base: 500 kg · Límite operativo: 800 kg · Capacidad nominal AGV: 1000 kg")
        with derecha:
            st.text_input("Ubicación inicial común", key="ana_ubicacion_inicial",
                          help="Supuesto: todos los AGV parten de ControlPoint7, en almacén. Debe ser un nodo válido.")
    st.button("Restablecer valores base", on_click=restablecer)

    valores = _valores_parametros()
    st.caption(f"{META_PALLETS_TURNO} pallets de meta · {valores['duracion_turno_s']/3600:g} h · "
               f"{valores['velocidad_maxima_ms']:g} m/s · carga {valores['tiempo_carga_s']:g} s · "
               f"descarga {valores['tiempo_descarga_s']:g} s · escala {valores['factor_escala_metros_por_unidad']:g}")

    historial = _historial_vigente()
    if st.button("Simular escenario", type="primary", width="stretch"):
        try:
            resultado = SimuladorFlota(ParametrosSimulacion(**valores)).ejecutar(
                cantidad, simular_bateria=True, cargadores=CARGADORES
            )
            escenario = crear_escenario(resultado)
            historial.append(escenario)
            st.session_state["escenario_activo"] = escenario["id"]
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
    if st.session_state.get("escenario_activo"):
        escenario = next((e for e in historial if e["id"] == st.session_state["escenario_activo"]), None)
        if escenario:
            r = escenario["resultado"]
            p = r["parametros"]
            st.success("Simulación completada. Consulta los indicadores en Resultados o visualiza el escenario en Simulación 2D.")
            st.caption(f"Escenario simulado: {r['numero_agv']} AGV · {p['pallets_terminados']} pallets producidos · meta {META_PALLETS_TURNO} · {p['duracion_turno_s']/3600:g} h")


def mostrar_resultados():
    mostrar_encabezado("Resultados")
    st.caption("Indicadores operativos generados por la simulación ya ejecutada.")
    escenario, activo, etiquetas = _escenario_seleccionado()
    if escenario is None:
        st.info("Ejecuta primero un escenario en Dimensionamiento para generar resultados.")
        return
    resultado = escenario["resultado"]
    valores = _valores_parametros() if all(f"ana_{k}" in st.session_state for k in BASE) else None
    if valores and (any(resultado["parametros"].get(k) != v for k, v in valores.items() if k != "pallets_terminados")
                   or resultado["numero_agv"] != st.session_state.get("flota_elegida")):
        st.info("Se muestra una corrida guardada. Ejecuta nuevamente desde Dimensionamiento para evaluar parámetros distintos.")

    mostrar_resumen_operativo(resultado)
    mostrar_gestion_solicitudes(resultado)
    mostrar_estado_flota(resultado)
    mostrar_comparacion_resultados(_historial_vigente(), etiquetas)
    mostrar_analisis_tecnico(resultado)



def _numero(valor, unidad="", decimales=1):
    if valor is None:
        return "Pendiente de datos de planta"
    if isinstance(valor, int) or (isinstance(valor, float) and valor.is_integer()):
        return f"{int(valor):,}{unidad}"
    return f"{valor:,.{decimales}f}{unidad}"


def _tarjetas(datos, columnas=3):
    for inicio in range(0, len(datos), columnas):
        for columna, (titulo, valor) in zip(st.columns(columnas), datos[inicio:inicio+columnas]):
            columna.metric(titulo, valor)


def mostrar_resumen_operativo(resultado):
    k, p, n = resultado["kpis"], resultado["parametros"], resultado["numero_agv"]
    st.subheader("Resumen operativo")
    almacenados = k["pallets_terminados_turno"]
    meta = k.get("meta_pallets_turno", META_PALLETS_TURNO)
    extras = k.get("pallets_extra_meta", max(0, almacenados - meta))
    if almacenados >= meta:
        st.success(f"Meta {'superada' if extras else 'cumplida'}: {almacenados} pallets entregados al almacén "
                   f"de {meta} requeridos" + (f" · **+{extras} extra**" if extras else ""))
    else:
        st.warning(f"Meta pendiente: {almacenados}/{meta} pallets entregados al almacén.")
    st.progress(min(1.0, almacenados / meta), text=f"{k['cumplimiento_pct']:.1f} % de la meta")
    espera = k.get("espera_agv_media_pt_s", k.get("espera_media_s"))
    _tarjetas([
        ("Meta de Nestlé", meta),
        ("Pallets almacenados", almacenados),
        ("Pallets extra", extras),
        ("Pallets por almacenar", k.get("pallets_terminados_pendientes", 0)),
        ("Espera retiro PT", _numero(espera, " s")),
        ("Utilización en misiones", _numero(k.get("utilizacion_media_pct"), " %")),
    ])
    st.caption("Utilización: tiempo en misiones dentro del turno. Espera retiro PT: promedio de toda la corrida. Cambiar de pestaña no recalcula la simulación.")


def mostrar_gestion_solicitudes(resultado):
    k, p = resultado["kpis"], resultado["parametros"]
    st.subheader("Gestión de solicitudes")
    limite_turno = p["duracion_turno_s"]
    movimientos = resultado["movimientos"]
    total = k.get("movimientos_logisticos_totales", len(movimientos))
    generadas = k.get(
        "solicitudes_generadas_turno",
        sum(m["llegada_s"] <= limite_turno for m in movimientos),
    )
    completadas = k.get(
        "solicitudes_completadas_turno",
        sum(m["fin_s"] <= limite_turno for m in movimientos),
    )
    pendientes = k.get(
        "solicitudes_pendientes_turno",
        sum(m["llegada_s"] <= limite_turno < m["inicio_s"] for m in movimientos),
    )
    activas = k.get(
        "solicitudes_activas_turno",
        sum(m["inicio_s"] <= limite_turno < m["fin_s"] for m in movimientos),
    )
    no_generadas = k.get(
        "solicitudes_no_generadas_turno",
        sum(m["llegada_s"] > limite_turno for m in movimientos),
    )
    _tarjetas([
        ("Solicitudes generadas", generadas),
        ("Solicitudes completadas", completadas),
        ("Solicitudes pendientes", pendientes),
        ("Misiones activas al cierre", activas),
        ("Pallets aún en producción", no_generadas),
    ], columnas=5)
    st.caption(
        f"Plan logístico total: {total} solicitudes de retiro. Al cierre: {generadas} solicitudes generadas = "
        f"{completadas} completadas + {pendientes} pendientes + {activas} activas; "
        f"{no_generadas} pallets aún seguían en producción y todavía no habían generado solicitud."
    )
    with st.expander("Ver detalle de solicitudes", expanded=False):
        filas = []
        for m in movimientos:
            if m["fin_s"] <= limite_turno:
                estado = "Completada"
            elif m["inicio_s"] <= limite_turno:
                estado = "Activa al cierre"
            elif m["llegada_s"] <= limite_turno:
                estado = "Pendiente al cierre"
            else:
                estado = "No generada al cierre"
            filas.append({
                "ID": f"M-{m['numero']:03d}",
                "Tipo": m["tipo"],
                "Línea": m["linea"],
                "Origen": m["origen"],
                "Destino": m["destino"],
                "AGV": m["agv"],
                "Llegada (s)": round(m["llegada_s"], 2),
                "Inicio (s)": round(m["inicio_s"], 2),
                "Fin (s)": round(m["fin_s"], 2),
                "Espera (s)": round(m.get("espera_s", m["inicio_s"] - m["llegada_s"]), 2),
                "Estado": estado,
            })
        st.dataframe(filas, hide_index=True, width="stretch")


def mostrar_estado_flota(resultado):
    st.subheader("Estado de la flota")
    filas = []
    for agv in resultado["por_agv"]:
        filas.append({
            "AGV": agv["agv"],
            "Retiros turno": agv["movimientos_turno"],
            "Retiros totales": agv["movimientos_totales"],
            "Pallets almacenados": agv["pallets_terminados_turno"],
            "Utilización (%)": round(agv["utilizacion_pct"], 1),
            "Tiempo ocupado (h)": round(agv["ocupado_turno_s"] / 3600, 2),
            "Tiempo libre (h)": round(agv["libre_turno_s"] / 3600, 2),
            "Distancia vacía (m)": round(agv["distancia_vacia_m"], 1),
            "Distancia cargada (m)": round(agv["distancia_cargada_m"], 1),
            "Distancia total (m)": round(agv["distancia_total_m"], 1),
            "Posición final": agv["posicion_final"],
        })
    st.dataframe(filas, hide_index=True, width="stretch")
    if resultado.get("recargas"):
        total_recargas = sum(len(recargas) for recargas in resultado["recargas"].values())
        st.caption(f"Recargas registradas en este escenario: {total_recargas}.")
    else:
        st.caption("Datos de batería no disponibles para este escenario.")


def mostrar_comparacion_resultados(historial, etiquetas):
    st.subheader("Comparación de escenarios")
    if len(historial) < 2:
        st.caption("Ejecuta más de un escenario para comparar resultados sin volver a simular.")
        return
    seleccion = st.multiselect(
        "Corridas a comparar",
        [e["id"] for e in historial],
        default=[e["id"] for e in historial],
        format_func=etiquetas.get,
        key="comparacion_resultados",
    )
    escenarios = [e for e in historial if e["id"] in seleccion]
    if len(escenarios) < 2:
        st.info("Selecciona al menos dos corridas ya ejecutadas.")
        return
    filas = []
    for escenario in escenarios:
        r, k = escenario["resultado"], escenario["resultado"]["kpis"]
        filas.append({
            "Escenario": etiquetas[escenario["id"]],
            "AGV": r["numero_agv"],
            "Pallets almacenados": k["pallets_terminados_turno"],
            "Meta alcanzada (%)": round(k["cumplimiento_pct"], 1),
            "Extra sobre 215": k.get("pallets_extra_meta", 0),
            "Pallets por almacenar": k["pallets_terminados_pendientes"],
            "Espera retiro PT (s)": round(k.get("espera_agv_media_pt_s", k["espera_media_s"]), 2),
            "Utilización en misiones (%)": round(k["utilizacion_media_pct"], 1),
            "Capacidad disponible (%)": round(k["capacidad_disponible_pct"], 1),
        })
    st.dataframe(filas, hide_index=True, width="stretch")



def mostrar_metodologia():
    mostrar_encabezado("Metodología")
    st.caption("Supuestos, flujo de simulación y alcance técnico del prototipo.")
    with st.expander("Datos conocidos y configurados", expanded=True):
        st.write("Meta operativa: al menos 215 pallets de producto terminado trasladados al almacén en un turno de 8 horas.")
        st.write("El prototipo usa el grafo JSON del proyecto para rutas y distancias. FlexSim permanece como simulación independiente.")
        st.write("Datos de referencia del AGV: capacidad máxima 1000 kg, velocidad máxima 1 m/s, autonomía conservadora de 10 h y recarga de 3 h.")
    with st.expander("Supuestos editables", expanded=False):
        mostrar_supuestos()
    with st.expander("Flujo de simulación", expanded=False):
        st.write("Dimensionamiento crea un escenario con los parámetros seleccionados y lo guarda en la sesión.")
        st.write("Resultados, Simulación 2D y Néstor leen ese escenario guardado; no ejecutan una nueva corrida al cambiar de pestaña.")
        st.write("Las rutas se calculan sobre el grafo existente y la asignación se mantiene en los servicios actuales.")
    with st.expander("Limitaciones del modelo", expanded=False):
        for texto in LIMITACIONES:
            st.write(texto)
    mostrar_documentacion()


def mostrar_analisis_tecnico(resultado):
    with st.expander("Ver análisis técnico", expanded=False):
        st.caption("Detalle completo de la corrida seleccionada. Esta sección reutiliza el resultado guardado y no ejecuta una nueva simulación.")
        k = resultado["kpis"]
        campos_kpi = [
            ("pallets_terminados_turno", "Pallets almacenados dentro del turno"),
            ("pallets_terminados_pendientes", "Pallets por almacenar"),
            ("cumplimiento_pct", "Cumplimiento respecto a la meta de 215 (%)"),
            ("meta_pallets_turno", "Meta de Nestlé (pallets)"),
            ("pallets_extra_meta", "Pallets extra entregados al almacén"),
            ("pallets_producidos_turno", "Pallets producidos en el turno"),
            ("tiempo_producto_terminado_s", "Tiempo hasta almacenar el último pallet (s)"),
            ("completados_turno", "Retiros completados"),
            ("solicitudes_generadas_turno", "Solicitudes generadas al cierre"),
            ("solicitudes_pendientes_turno", "Solicitudes pendientes al cierre"),
            ("solicitudes_activas_turno", "Misiones activas al cierre"),
            ("solicitudes_no_generadas_turno", "Pallets aún en producción al cierre"),
            ("backlog_corte", "Pallets por almacenar al cierre"),
            ("throughput_mov_h", "Retiros por hora"),
            ("espera_media_s", "Espera media (s)"),
            ("ciclo_medio_s", "Tiempo de ciclo medio (s)"),
            ("backlog_maximo", "Cola máxima"),
            ("utilizacion_media_pct", "Utilización media (%)"),
            ("distancia_vacia_m", "Distancia vacía (m)"),
            ("distancia_cargada_m", "Distancia cargada (m)"),
            ("distancia_total_m", "Distancia total (m)"),
        ]
        st.markdown("**Métricas completas**")
        st.dataframe([{"Métrica": etiqueta, "Valor": k[campo]}
                      for campo, etiqueta in campos_kpi if campo in k],
                     hide_index=True, width="stretch")
        st.markdown("**Detalle por AGV**")
        st.dataframe(resultado["por_agv"], hide_index=True, width="stretch")
        st.markdown("**Desglose de retiros**")
        movimientos = resultado["movimientos"]
        if movimientos:
            elegido = st.selectbox(
                "Retiro del ejemplo",
                [m["numero"] for m in movimientos],
                format_func=lambda n: f"M-{n:03d}",
                key=f"movimiento_tecnico_{resultado['numero_agv']}_{resultado['timestamp']}",
            )
            m = next(m for m in movimientos if m["numero"] == elegido)
            st.write(f"{m['linea']} · {m['tipo']} · {m['id_pallet']} · {m['agv']}")
            st.caption(f"{m['origen']} → {m['destino']} · llegada {m['llegada_s']:.2f} s · inicio {m['inicio_s']:.2f} s · fin {m['fin_s']:.2f} s")
            st.dataframe([
                {"Componente": "Desplazamiento vacío hasta la línea", "Tiempo (s)": m["vacio"]["tiempo_s"]},
                {"Componente": "Carga", "Tiempo (s)": m["carga_s"]},
                {"Componente": "Viaje cargado", "Tiempo (s)": m["cargado"]["tiempo_s"]},
                {"Componente": "Descarga", "Tiempo (s)": m["descarga_s"]},
                {"Componente": "Total de servicio", "Tiempo (s)": m["duracion_servicio_s"]},
            ], hide_index=True, width="stretch")
        st.markdown("**Eventos y exportación**")
        st.dataframe(resultado["eventos"], hide_index=True, width="stretch")
        st.download_button("Descargar escenarios JSON", exportar_json(_historial_vigente()),
                           file_name="escenarios_agv.json", mime="application/json")
        st.json(resultado["parametros"], expanded=False)


def mostrar_supuestos():
    for texto in SUPUESTOS:
        st.write(texto)
    st.caption("Valores base: carga 30 s, descarga 30 s, escala 1 m/unidad, "
               "peso 500 kg y todos los AGV inicialmente en ControlPoint7.")


def mostrar_documentacion():
    with st.expander("¿Cómo se calcula?", expanded=False):
        texto = Path(__file__).resolve().parents[2] / "CALCULO_FLOTA.md"
        st.markdown(texto.read_text(encoding="utf-8"))
    with st.expander("Datos conocidos vs supuestos", expanded=False):
        st.markdown("**Datos conocidos/configurados del proyecto**")
        st.write("Dato de Nestlé: al menos 215 pallets de producto terminado trasladados al almacén en 8 h. Máximo: 800 kg. "
                 f"Velocidad de referencia del AGV: {VELOCIDAD_REFERENCIA_MS:g} m/s; aceleración/desaceleración: 1 m/s², 1 m/s². "
                 "Topología: grafo JSON del proyecto. Los valores cinemáticos no se extrajeron del .fsm.")
        st.markdown("**Supuestos editables**")
        mostrar_supuestos()
        st.markdown("**Limitaciones del modelo**")
        for texto in LIMITACIONES:
            st.write(texto)
