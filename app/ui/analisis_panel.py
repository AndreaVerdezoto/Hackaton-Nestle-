"""Presentación del análisis: no modifica parámetros base, fórmulas ni simulador."""
from dataclasses import asdict
from pathlib import Path

import streamlit as st

from app.models.bateria import CARGADORES, VELOCIDAD_REFERENCIA_MS
from app.services.simulador_flota import (
    ParametrosSimulacion, SimuladorFlota,
    exportar_json, SUPUESTOS, LIMITACIONES, VERSION_MODELO,
)

BASE = asdict(ParametrosSimulacion())


def restablecer():
    for nombre, valor in BASE.items():
        st.session_state[f"ana_{nombre}"] = valor
    st.session_state.pop("analisis_resultados", None)
    st.session_state.pop("sensibilidad_resultados", None)


def duracion_texto(segundos):
    segundos = round(segundos)
    return f"{segundos // 3600} h {(segundos % 3600) // 60:02d} min {segundos % 60:02d} s"


def margen_texto(kpis):
    if kpis["exceso_tiempo_s"] > 0:
        return f"Exceso: {kpis['exceso_tiempo_s']/60:.1f} min"
    return f"Margen: {kpis['margen_tiempo_s']/60:.1f} min"


def mostrar_analisis():
    mostrar_dimensionamiento()


def _inicializar_parametros():
    for nombre, valor in BASE.items():
        st.session_state.setdefault(f"ana_{nombre}", valor)
    # La referencia del prototipo es fija: 1 m/s. Evita conservar 2 m/s de sesiones anteriores.
    st.session_state["ana_velocidad_maxima_ms"] = VELOCIDAD_REFERENCIA_MS


def _valores_parametros():
    return {k: st.session_state[f"ana_{k}"] for k in BASE}


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
    st.title("Dimensionamiento")
    st.caption("Configura el escenario y ejecuta la simulación Python que alimenta Resultados, Simulación 2D, Néstor y Rentabilidad.")
    _inicializar_parametros()
    _mostrar_obsoletos()
    st.info("Meta de Nestlé: al menos 215 pallets de producto terminado por turno de 8 horas.")

    cantidad = st.selectbox("Número de AGV a simular", [2, 3, 4, 5], key="flota_elegida")
    columnas = st.columns(3)
    principales = [
        ("pallets_terminados", "Pallets terminados por turno", 1, "Demanda de producto terminado del escenario."),
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
        with derecha:
            st.number_input("Espera por producto terminado (s)", min_value=0.0, key="ana_espera_disponibilidad_retorno_s",
                            help="Espera por producto terminado al llegar a recogerlo. Cero no significa producción instantánea.")
            st.number_input("Movimientos de suministro por turno", min_value=0, key="ana_movimientos_suministro",
                            help="Demanda independiente opcional de almacén hacia líneas.")
            st.text_input("Ubicación inicial común", key="ana_ubicacion_inicial",
                          help="Supuesto: todos los AGV parten de ControlPoint7, en almacén. Debe ser un nodo válido.")
    st.button("Restablecer valores base", on_click=restablecer)

    valores = _valores_parametros()
    st.caption(f"{valores['pallets_terminados']} pallets terminados + {valores['movimientos_suministro']} suministros · {valores['duracion_turno_s']/3600:g} h · "
               f"{valores['velocidad_maxima_ms']:g} m/s · carga {valores['tiempo_carga_s']:g} s · "
               f"descarga {valores['tiempo_descarga_s']:g} s · escala {valores['factor_escala_metros_por_unidad']:g}")

    from app.services.analisis_negocio import crear_escenario, LineaBase, ParametrosEconomicos
    historial = _historial_vigente()
    if st.button("Simular escenario", type="primary", width="stretch"):
        try:
            resultado = SimuladorFlota(ParametrosSimulacion(**valores)).ejecutar(
                cantidad, simular_bateria=True, cargadores=CARGADORES
            )
            escenario = crear_escenario(resultado,
                LineaBase(**st.session_state.get("base_guardada", {})),
                ParametrosEconomicos(**st.session_state.get("economia_guardada", {})))
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
            st.caption(f"Escenario simulado: {r['numero_agv']} AGV · {p['pallets_terminados']} pallets · {p['duracion_turno_s']/3600:g} h · {p['velocidad_maxima_ms']:g} m/s")


def mostrar_resultados():
    st.title("Resultados")
    st.caption("Indicadores operativos generados por la simulación ya ejecutada.")
    escenario, activo, etiquetas = _escenario_seleccionado()
    if escenario is None:
        st.info("Ejecuta primero un escenario en Dimensionamiento para generar resultados.")
        return
    resultado = escenario["resultado"]
    valores = _valores_parametros() if all(f"ana_{k}" in st.session_state for k in BASE) else None
    if valores and (resultado["parametros"] != valores or resultado["numero_agv"] != st.session_state.get("flota_elegida")):
        st.info("Se muestra una corrida guardada. Ejecuta nuevamente desde Dimensionamiento para evaluar parámetros distintos.")

    mostrar_resumen_operativo(resultado)
    mostrar_gestion_solicitudes(resultado)
    mostrar_estado_flota(resultado)
    mostrar_comparacion_resultados(_historial_vigente(), etiquetas)
    mostrar_analisis_tecnico(resultado)


def _escenario_activo_guardado():
    historial = _historial_vigente()
    if not historial:
        return None
    activo = st.session_state.get("escenario_activo")
    escenario = next((e for e in historial if e["id"] == activo), None)
    if escenario is None:
        escenario = historial[-1]
        st.session_state["escenario_activo"] = escenario["id"]
    return escenario


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
    st.write(
        f"Con {n} AGV se atendieron {k['pallets_terminados_turno']} de "
        f"{p['pallets_terminados']} pallets de producto terminado durante el escenario simulado."
    )
    espera = k.get("espera_agv_media_pt_s", k.get("espera_media_s"))
    _tarjetas([
        ("Pallets requeridos", p["pallets_terminados"]),
        ("Pallets completados", k["pallets_terminados_turno"]),
        ("Cumplimiento", _numero(k.get("cumplimiento_pct"), " %")),
        ("Utilización promedio", _numero(k.get("utilizacion_media_pct"), " %")),
        ("Espera promedio", _numero(espera, " s")),
        ("Pendientes al cierre", k.get("backlog_corte", 0)),
    ])
    st.caption("Resumen del escenario ya ejecutado; cambiar de pestaña no recalcula la simulación.")


def mostrar_gestion_solicitudes(resultado):
    k, p = resultado["kpis"], resultado["parametros"]
    st.subheader("Gestión de solicitudes")
    total = k.get("movimientos_logisticos_totales", len(resultado["demanda"]))
    completadas = k.get("completados_turno", 0)
    pendientes = k.get("backlog_corte", 0)
    cola_maxima = k.get("backlog_maximo", k.get("backlog_maximo_agv", 0))
    _tarjetas([
        ("Solicitudes generadas", total),
        ("Solicitudes completadas", completadas),
        ("Solicitudes pendientes", pendientes),
        ("Cola máxima", cola_maxima),
    ], columnas=4)
    with st.expander("Ver detalle de solicitudes", expanded=False):
        filas = []
        limite_turno = p["duracion_turno_s"]
        for m in resultado["movimientos"]:
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
                "Estado": "Completada" if m["fin_s"] <= limite_turno else "Pendiente al cierre",
            })
        st.dataframe(filas, hide_index=True, width="stretch")


def mostrar_estado_flota(resultado):
    st.subheader("Estado de la flota")
    filas = []
    for agv in resultado["por_agv"]:
        filas.append({
            "AGV": agv["agv"],
            "Movimientos turno": agv["movimientos_turno"],
            "Movimientos totales": agv["movimientos_totales"],
            "Pallets terminados": agv["pallets_terminados_turno"],
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
            "Pallets completados": k["pallets_terminados_turno"],
            "Cumplimiento (%)": round(k["cumplimiento_pct"], 1),
            "Pendientes": k["backlog_corte"],
            "Espera promedio (s)": round(k.get("espera_agv_media_pt_s", k["espera_media_s"]), 2),
            "Utilización (%)": round(k["utilizacion_media_pct"], 1),
            "Capacidad disponible (%)": round(k["capacidad_disponible_pct"], 1),
        })
    st.dataframe(filas, hide_index=True, width="stretch")


def mostrar_rentabilidad():
    from app.services.analisis_negocio import LineaBase, ParametrosEconomicos, crear_escenario, comparar_linea_base
    from app.ui.negocio_panel import numero, tarjetas, campos, entradas_rentabilidad, mostrar_equilibrio

    st.title("Rentabilidad")
    escenario = _escenario_activo_guardado()
    if escenario is None:
        st.info("Ejecuta primero un escenario en Dimensionamiento para analizar rentabilidad.")
        return
    r = escenario["resultado"]
    n = r["numero_agv"]
    st.caption(f"Escenario activo: {n} AGV. Los campos vacíos se mantienen como dato pendiente, no como cero.")
    economia_guardada = escenario["economia"]
    st.subheader("Resumen económico")
    payback_guardado = ("No aplicable" if economia_guardada["beneficio_neto_anual"] is not None and economia_guardada["beneficio_neto_anual"] <= 0
                        else numero(economia_guardada["payback_anios"], " años"))
    roi_guardado = "No aplicable (CAPEX cero)" if economia_guardada["capex"] == 0 else numero(economia_guardada["roi_anual_pct"], " %")
    tarjetas([
        ("Inversión", numero(economia_guardada["capex"], " USD")),
        ("Beneficio anual", numero(economia_guardada["beneficio_neto_anual"], " USD")),
        ("ROI", roi_guardado),
        ("Payback", payback_guardado),
    ])
    try:
        with st.expander("Situación actual / Línea base", expanded=False):
            st.caption("Dato de planta / supuesto editable. Completa únicamente los datos disponibles.")
            base = campos(escenario, LineaBase, "base", {
                "movimientos_turno": "Movimientos actuales por turno",
                "tiempo_manual_movimiento_s": "Tiempo manual por movimiento (s)",
                "perdida_produccion_turno_s": "Producción perdida por espera logística (s/turno)",
                "pallets_terminados_turno": "Pallets terminados actuales por turno",
                "espera_logistica_media_s": "Espera logística actual media por movimiento (s)",
            })
        impacto = comparar_linea_base(r, base)
        st.subheader("Impacto operativo frente a línea base")
        tarjetas([
            ("Actual: movimientos/turno", numero(base.movimientos_turno)),
            ("Simulada: movimientos/turno", r["kpis"]["completados_turno"]),
            ("Movimientos adicionales atendidos", numero(impacto["movimientos_adicionales_atendidos"])),
            ("Incremento logístico", numero(impacto["incremento_logistico_pct"], " %")),
            ("Horas logísticas recuperadas", numero(impacto["horas_logisticas_recuperadas"], " h")),
            ("Reducción de espera media", numero(impacto["reduccion_espera_media_s"], " s")),
        ])
        with st.expander("Completar datos económicos", expanded=False):
            economia = entradas_rentabilidad(escenario, n)
        borrador = crear_escenario(r, base, economia)
    except (ValueError, OverflowError) as exc:
        st.error(str(exc))
        return

    e = borrador["economia"]
    st.subheader("Resultado financiero")
    payback_texto = ("No aplicable" if e["beneficio_neto_anual"] is not None and e["beneficio_neto_anual"] <= 0
                     else numero(e["payback_anios"], " años"))
    roi_texto = "No aplicable (CAPEX cero)" if e["capex"] == 0 else numero(e["roi_anual_pct"], " %")
    tarjetas([
        ("Inversión inicial", numero(e["capex"], " USD")),
        ("Beneficio neto anual", numero(e["beneficio_neto_anual"], " USD")),
        ("ROI anual", roi_texto),
        ("Payback", payback_texto),
    ])
    if e["capex"] is not None and e["beneficio_neto_anual"] is not None:
        st.write(e["estado"])
    else:
        st.info("Aún no hay información suficiente para calcular ROI y payback.")
    with st.expander("Punto de equilibrio", expanded=False):
        mostrar_equilibrio(e, economia, n)
    with st.expander("¿Cómo se calcula la rentabilidad?", expanded=False):
        st.code("CAPEX = AGV × costo_AGV + integración + infraestructura + cargadores + otros_iniciales\n"
                "Producción anual = pallets_adicionales/turno × margen/pallet × turnos/día × días/año\n"
                "Ahorro anual = estimación directa; si está vacía, usar desglose avanzado × %evitable / 100\n"
                "OPEX anual = AGV × mantenimiento_por_AGV + energía + otros_opex\n"
                "Neto anual = producción anual + ahorro anual − OPEX anual\n"
                "Payback años = CAPEX / neto anual (neto > 0); meses = años × 12\n"
                "ROI anual (%) = neto anual / CAPEX × 100 (CAPEX > 0)", language=None)
        st.caption("Recuperación simple, sin descuento, impuestos ni financiación. Vacío es dato pendiente; cero debe introducirse explícitamente.")
    cambios = any(borrador[c] != escenario[c] for c in ("linea_base", "parametros_economicos"))
    if cambios:
        st.info("Vista previa con supuestos editados. Guárdalos para incluirlos en la comparación.")
    if st.button("Guardar análisis de negocio", key=f"guardar_rentabilidad_{escenario['id']}"):
        for campo in ("linea_base", "parametros_economicos", "impacto", "economia"):
            escenario[campo] = borrador[campo]
        st.session_state.base_guardada = asdict(base)
        st.session_state.economia_guardada = asdict(economia)
        st.success("Supuestos guardados para esta corrida y como punto de partida de la próxima simulación.")


def mostrar_metodologia():
    st.title("Metodología")
    st.caption("Supuestos, flujo de simulación y alcance técnico del prototipo.")
    with st.expander("Datos conocidos y configurados", expanded=True):
        st.write("Meta operativa: al menos 215 pallets de producto terminado trasladados al almacén en un turno de 8 horas.")
        st.write("El prototipo usa el grafo JSON del proyecto para rutas y distancias. FlexSim permanece como simulación independiente.")
        st.write("Datos de referencia del AGV: capacidad máxima 1000 kg, velocidad máxima 1 m/s, autonomía conservadora de 8 h y recarga de 3 h.")
    with st.expander("Supuestos editables", expanded=False):
        mostrar_supuestos()
    with st.expander("Flujo de simulación", expanded=False):
        st.write("Dimensionamiento crea un escenario con los parámetros seleccionados y lo guarda en la sesión.")
        st.write("Resultados, Simulación 2D, Rentabilidad y Néstor leen ese escenario guardado; no ejecutan una nueva corrida al cambiar de pestaña.")
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
            ("pallets_terminados_turno", "Pallets terminados almacenados dentro del turno"),
            ("pallets_terminados_pendientes", "Pallets terminados pendientes"),
            ("cumplimiento_pct", "Cumplimiento de producto terminado (%)"),
            ("tiempo_producto_terminado_s", "Tiempo para producto terminado (s)"),
            ("suministros_turno", "Suministros completados dentro del turno"),
            ("suministros_pendientes", "Suministros pendientes"),
            ("completados_turno", "Movimientos completados"),
            ("backlog_corte", "Movimientos pendientes al terminar el turno"),
            ("throughput_mov_h", "Movimientos por hora"),
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
        st.markdown("**Desglose de movimientos**")
        movimientos = resultado["movimientos"]
        if movimientos:
            elegido = st.selectbox(
                "Movimiento del ejemplo",
                [m["numero"] for m in movimientos],
                format_func=lambda n: f"M-{n:03d}",
                key=f"movimiento_tecnico_{resultado['numero_agv']}_{resultado['timestamp']}",
            )
            m = next(m for m in movimientos if m["numero"] == elegido)
            st.write(f"{m['linea']} · {m['tipo']} · {m['id_pallet']} · {m['agv']}")
            st.caption(f"{m['origen']} → {m['destino']} · llegada {m['llegada_s']:.2f} s · inicio {m['inicio_s']:.2f} s · fin {m['fin_s']:.2f} s")
            st.dataframe([
                {"Componente": "Reposicionamiento / entrega → recogida", "Tiempo (s)": m["vacio"]["tiempo_s"]},
                {"Componente": "Disponibilidad de producto terminado", "Tiempo (s)": m["espera_disponibilidad_s"]},
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
    st.caption("Valores base: carga 30 s, descarga 30 s, espera de retorno 0 s, escala 1 m/unidad, "
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


def mostrar_metricas_completas(resultados):
    with st.expander("Ver métricas completas", expanded=False):
        st.caption("Completados, pendientes y utilización: dentro del turno. Promedios y distancias: toda la demanda hasta terminar.")
        campos = [
            ("pallets_terminados_turno", "Pallets terminados almacenados dentro del turno"),
            ("pallets_terminados_pendientes", "Pallets terminados pendientes"),
            ("cumplimiento_pct", "Cumplimiento de producto terminado (%)"),
            ("tiempo_producto_terminado_s", "Tiempo para producto terminado (s)"),
            ("suministros_turno", "Suministros completados dentro del turno"),
            ("suministros_pendientes", "Suministros pendientes"),
            ("completados_turno", "Movimientos completados"),
            ("backlog_corte", "Movimientos pendientes al terminar el turno"),
            ("throughput_mov_h", "Movimientos por hora"), ("espera_media_s", "Espera media (s)"),
            ("ciclo_medio_s", "Tiempo de ciclo medio (s)"), ("muestra_promedios", "Movimientos incluidos en los promedios"),
            ("backlog_maximo", "Cola máxima"), ("utilizacion_media_pct", "Utilización media (%)"),
            ("tiempo_total_s", "Tiempo total (s)"), ("hora_fin_movimiento_ultimo_id_s", "Fin del último ID de movimiento (s)"),
            ("margen_tiempo_s", "Margen (s)"), ("margen_turno_pct", "Margen del turno (%)"),
            ("exceso_tiempo_s", "Exceso (s)"), ("distancia_vacia_m", "Distancia vacía (m)"),
            ("distancia_cargada_m", "Distancia cargada (m)"), ("distancia_total_m", "Distancia total (m)"),
        ]
        st.dataframe([{"Métrica": etiqueta, **{f"{r['numero_agv']} AGV": r["kpis"][campo] for r in resultados}}
                      for campo, etiqueta in campos], hide_index=True, width="stretch")
        st.caption("Distancia vacía: recorrido sin pallet. Distancia cargada: recorrido transportando un pallet.")


def mostrar_detalle_agv(resultados):
    with st.expander("Ver detalle por AGV", expanded=False):
        flota = st.selectbox("Flota del detalle", [r["numero_agv"] for r in resultados])
        r = next(r for r in resultados if r["numero_agv"] == flota)
        st.caption("Movimientos y pallets terminados al corte y totales. Tiempos dentro del turno; distancias hasta terminar toda la demanda.")
        campos = [("movimientos_turno", "Movimientos dentro del turno"), ("movimientos_totales", "Movimientos totales"),
                  ("pallets_terminados_turno", "Pallets terminados dentro del turno"), ("pallets_terminados_totales", "Pallets terminados totales"),
                  ("utilizacion_pct", "Utilización (%)"), ("ocupado_turno_s", "Tiempo ocupado (s)"),
                  ("libre_turno_s", "Tiempo libre (s)"), ("distancia_vacia_m", "Distancia vacía (m)"),
                  ("distancia_cargada_m", "Distancia cargada (m)"), ("distancia_total_m", "Distancia total (m)")]
        st.dataframe([{"Métrica": etiqueta, **{a["agv"]: a[campo] for a in r["por_agv"]}}
                      for campo, etiqueta in campos], hide_index=True, width="stretch")
        st.dataframe([{campo: m[campo] for campo in ("numero", "id_mision", "tipo", "linea", "agv", "llegada_s", "inicio_s", "fin_s", "espera_s")}
                      for m in r["movimientos"]], hide_index=True)


def mostrar_desglose(resultados):
    flota = st.selectbox("Flota del ejemplo", [r["numero_agv"] for r in resultados])
    r = next(r for r in resultados if r["numero_agv"] == flota)
    ciclo = st.selectbox("Misión del ejemplo", [c["id_mision"] for c in r["demanda"]])
    for m in (m for m in r["movimientos"] if m["id_mision"] == ciclo):
        st.markdown(f"**{m['linea']} · {m['tipo']} · {m['id_pallet']} · {m['agv']}**")
        st.caption(f"{m['origen']} → {m['destino']} · llegada {m['llegada_s']:.2f} s · inicio {m['inicio_s']:.2f} s · fin {m['fin_s']:.2f} s")
        st.dataframe([
            {"Componente": "Reposicionamiento / entrega → recogida", "Tiempo (s)": m["vacio"]["tiempo_s"]},
            {"Componente": "Disponibilidad de producto terminado", "Tiempo (s)": m["espera_disponibilidad_s"]},
            {"Componente": "Carga", "Tiempo (s)": m["carga_s"]},
            {"Componente": "Viaje cargado", "Tiempo (s)": m["cargado"]["tiempo_s"]},
            {"Componente": "Descarga", "Tiempo (s)": m["descarga_s"]},
            {"Componente": "Total de servicio", "Tiempo (s)": m["duracion_servicio_s"]},
        ], hide_index=True)
        st.dataframe([{"Trayecto": nombre, "Distancia grafo": m[campo]["distancia_grafo"],
                       "Escala (m/unidad)": r["parametros"]["factor_escala_metros_por_unidad"],
                       "Distancia (m)": m[campo]["distancia_m"]}
                      for campo, nombre in (("vacio", "Sin pallet"), ("cargado", "Con pallet"))], hide_index=True)
