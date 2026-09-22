"""Presentación del análisis: no modifica parámetros base, fórmulas ni simulador."""
from dataclasses import asdict
from pathlib import Path

import streamlit as st

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
    st.title("Dimensionamiento de flota AGV")
    st.write("¿Cuántos AGV quieres evaluar? Elige una flota, simula y explica su impacto.")
    for nombre, valor in BASE.items():
        st.session_state.setdefault(f"ana_{nombre}", valor)
    st.markdown("**Pallets terminados por turno: 215 — Dato de Nestlé**")
    st.caption("Escenario base oficial: producción → almacén, turno de 8 horas.")
    # Sin control visible: evita reutilizar un suministro de una sesión anterior.
    st.session_state["ana_movimientos_suministro"] = 0
    cantidad = st.selectbox("Número de AGV a simular", [2, 3, 4, 5], key="flota_elegida")
    st.subheader("Parámetros de operación")
    columnas = st.columns(3)
    campos = [
        ("duracion_turno_s", "Duración del turno (s)", 1.0, "28800 segundos equivalen a 8 horas. Se conserva la precisión del modelo."),
        ("velocidad_maxima_ms", "Velocidad máxima (m/s)", 0.01, "Velocidad límite del AGV; el modelo también considera aceleración y frenado."),
        ("tiempo_carga_s", "Carga (s)", 0.0, "Tiempo por pallet. Supuesto editable: 30 segundos."),
        ("tiempo_descarga_s", "Descarga (s)", 0.0, "Tiempo por pallet. Supuesto editable: 30 segundos."),
        ("factor_escala_metros_por_unidad", "Factor de escala (m/unidad)", 0.001, "Convierte la distancia del grafo a metros. Calibrar con medidas reales de planta."),
    ]
    for i, (campo, etiqueta, minimo, ayuda) in enumerate(campos):
        with columnas[i % 3]:
            limites = {}
            st.number_input(etiqueta, min_value=minimo, key=f"ana_{campo}", help=ayuda, **limites)
    with st.expander("Parámetros avanzados", expanded=False):
        st.number_input("Pallets terminados (sensibilidad; base oficial: 215)", min_value=1, max_value=10000,
                        key="ana_pallets_terminados")
        if st.session_state.ana_pallets_terminados != 215:
            st.warning("Análisis de sensibilidad: esta demanda difiere del escenario oficial de 215 pallets terminados.")
        izquierda, derecha = st.columns(2)
        with izquierda:
            st.number_input("Aceleración (m/s²)", min_value=0.01, key="ana_aceleracion_ms2",
                            help="Configuración de referencia: 1 m/s². Controla cuánto tarda en ganar velocidad.")
            st.number_input("Desaceleración (m/s²)", min_value=0.01, key="ana_desaceleracion_ms2",
                            help="Configuración de referencia: 1 m/s². Controla el tiempo de frenado.")
            st.number_input("Peso por pallet (kg)", min_value=1.0, max_value=800.0, key="ana_peso_pallet_kg",
                            help="Supuesto: 500 kg; máximo 800 kg. El peso no modifica la cinemática.")
        with derecha:
            st.number_input("Espera por producto terminado (s)", min_value=0.0, key="ana_espera_disponibilidad_retorno_s",
                            help="Espera por producto terminado al llegar a recogerlo. Cero no significa producción instantánea.")
            st.text_input("Ubicación inicial común", key="ana_ubicacion_inicial",
                          help="Supuesto: todos los AGV parten de ControlPoint7, en almacén. Debe ser un nodo válido.")
    st.button("Restablecer valores base", on_click=restablecer)
    st.info("**Supuestos del escenario**\n\nDemanda distribuida uniformemente y por líneas en round-robin. "
            "Las distancias del grafo requieren calibración con medidas reales de planta.")
    with st.expander("Ver todos los supuestos", expanded=False):
        mostrar_supuestos()
    valores = {k: st.session_state[f"ana_{k}"] for k in BASE}
    st.caption(f"{valores['pallets_terminados']} pallets terminados + {valores['movimientos_suministro']} suministros · {valores['duracion_turno_s']/3600:g} h · "
               f"{valores['velocidad_maxima_ms']:g} m/s · carga {valores['tiempo_carga_s']:g} s · "
               f"descarga {valores['tiempo_descarga_s']:g} s · escala {valores['factor_escala_metros_por_unidad']:g}")
    from app.ui.negocio_panel import mostrar_negocio, comparar_guardados
    from app.services.analisis_negocio import crear_escenario, LineaBase, ParametrosEconomicos
    historial = st.session_state.setdefault("escenarios_simulados", [])
    antiguos = [e for e in historial if e["resultado"].get("version_modelo") != VERSION_MODELO]
    if antiguos:
        st.session_state.setdefault("escenarios_obsoletos", []).extend(antiguos)
        historial[:] = [e for e in historial if e["resultado"].get("version_modelo") == VERSION_MODELO]
        st.session_state.pop("escenario_activo", None)
    if st.session_state.get("escenarios_obsoletos"):
        st.warning("Las corridas anteriores usaban otra demanda y no son válidas para este dimensionamiento. Vuelve a simular las flotas.")
        with st.expander("Archivo de corridas obsoletas (solo exportación)"):
            st.download_button("Exportar corridas obsoletas", exportar_json(st.session_state.escenarios_obsoletos),
                               file_name="corridas_obsoletas.json", mime="application/json")
    if st.button("Simular escenario", type="primary", width="stretch"):
        try:
            resultado = SimuladorFlota(ParametrosSimulacion(**valores)).ejecutar(cantidad)
            escenario = crear_escenario(resultado,
                LineaBase(**st.session_state.get("base_guardada", {})),
                ParametrosEconomicos(**st.session_state.get("economia_guardada", {})))
            historial.append(escenario)
            st.session_state["escenario_activo"] = escenario["id"]
        except (ValueError, RuntimeError, OSError) as exc:
            st.error(str(exc))
    if historial:
        ids = [e["id"] for e in historial]
        etiquetas = {e["id"]: f"Corrida {i+1} · {e['resultado']['numero_agv']} AGV" for i, e in enumerate(historial)}
        activo = st.selectbox("Escenario guardado", ids, format_func=etiquetas.get, key="escenario_activo")
        escenario = next(e for e in historial if e["id"] == activo)
        resultado = escenario["resultado"]
        if resultado["parametros"] != valores or resultado["numero_agv"] != cantidad:
            st.info("Se muestra una corrida guardada. Pulsa Simular escenario para evaluar la selección actual.")
        mostrar_negocio(escenario)
        comparar_guardados(historial, etiquetas)
        with st.expander("Ver análisis técnico"):
            mostrar_metricas_completas([resultado])
            mostrar_detalle_agv([resultado])
            mostrar_documentacion()
            with st.expander("Desglose de un movimiento"):
                mostrar_desglose([resultado])
            with st.expander("Eventos y exportación"):
                st.dataframe(resultado["eventos"], hide_index=True)
                st.download_button("Descargar escenarios JSON", exportar_json(historial),
                                   file_name="escenarios_agv.json", mime="application/json")
                st.json(resultado["parametros"], expanded=False)
    else:
        mostrar_documentacion()
    st.markdown("**Cómo funciona el flujo**")
    st.write("Producto terminado: línea → almacén. Suministro independiente y opcional: almacén → línea.")
    st.caption("Python calcula rutas, tiempos y asignación de AGV. FlexSim se utiliza únicamente como demostración visual.")


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
                 "Velocidad/aceleración/desaceleración comunicadas por el usuario: 2 m/s, 1 m/s², 1 m/s². "
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

