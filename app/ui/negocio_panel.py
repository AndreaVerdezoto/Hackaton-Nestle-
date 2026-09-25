"""Presentación de escenarios ejecutados y supuestos económicos explícitos."""
from dataclasses import asdict
import streamlit as st
from app.services.indicadores_capacidad import calcular_capacidad
from app.services.analisis_negocio import (
    LineaBase, ParametrosEconomicos, crear_escenario, son_comparables, comparar_linea_base,
)

PENDIENTE = "Pendiente de datos de planta"


def numero(valor, unidad="", decimales=2):
    return PENDIENTE if valor is None else f"{valor:,.{decimales}f}{unidad}"


def tarjetas(datos):
    for inicio in range(0, len(datos), 3):
        for columna, (titulo, valor) in zip(st.columns(3), datos[inicio:inicio+3]):
            columna.metric(titulo, valor)


def campos(escenario, clase, prefijo, etiquetas):
    valores = {}
    columnas = st.columns(2)
    origen = escenario["linea_base" if prefijo == "base" else "parametros_economicos"]
    for i, (campo, etiqueta) in enumerate(etiquetas.items()):
        with columnas[i % 2]:
            valores[campo] = st.number_input(etiqueta, min_value=0.01 if campo == "payback_objetivo_anios" else 0.0,
                value=None if origen[campo] is None else float(origen[campo]),
                key=f"{prefijo}_{escenario['id']}_{campo}", placeholder="Dato de planta pendiente",
                help="SUPUESTO EDITABLE. Vacío = pendiente; 0 = costo o beneficio explícitamente nulo.")
    if clase is LineaBase:
        valores["comparacion_equivalente"] = st.checkbox(
            "La línea base corresponde al mismo turno y mezcla de movimientos",
            value=origen["comparacion_equivalente"], key=f"equivalente_{escenario['id']}")
    return clase(**valores)


def entradas_rentabilidad(escenario, cantidad):
    st.subheader("Rentabilidad")
    st.caption(f"{cantidad} AGV · USD. Introduce datos de planta cuando estén disponibles; hasta validarlos son supuestos editables.")
    origen = escenario["parametros_economicos"]
    valores = {campo: origen.get(campo) for campo in ("pallets_adicionales_turno", "margen_pallet")}

    def entrada(campo, etiqueta, opcional=False):
        valor = origen.get(campo)
        valores[campo] = st.number_input(etiqueta,
            min_value=0.01 if campo == "payback_objetivo_anios" else 0.0,
            value=None if valor is None else float(valor),
            key=f"eco_{escenario['id']}_{campo}", placeholder="Sin informar",
            help="Vacío no equivale a cero. Introduce 0 únicamente si se ha confirmado que no aplica.")
        st.caption("Opcional · Supuesto editable" if opcional else "Dato de planta / Supuesto editable")

    for titulo, etiquetas in [
        ("Inversión", [("costo_agv", "Costo por AGV (USD)"), ("integracion", "Instalación / integración (USD)")]),
        ("Beneficio", [("ahorro_anual_estimado", "Ahorro anual estimado (USD/año)")]),
        ("Operación", [("turnos_dia", "Turnos por día"), ("dias_anio", "Días operativos por año")]),
        ("Objetivo", [("payback_objetivo_anios", "Payback deseado (años)")]),
    ]:
        st.markdown(f"**{titulo}**")
        for columna, (campo, etiqueta) in zip(st.columns(len(etiquetas)), etiquetas):
            with columna:
                entrada(campo, etiqueta, opcional=campo in {"pallets_adicionales_turno", "margen_pallet"})
    st.caption("El ahorro anual es el ahorro evitable antes del OPEX de los AGV; sustituye el desglose avanzado, no se suma a él.")
    with st.expander("Costos avanzados", expanded=False):
        st.caption("Opcionales para introducir un ahorro directo; los costos iniciales y OPEX sí deben confirmarse para obtener ROI exacto. "
                   "Un campo vacío no se considera costo cero. Operación manual excluye personal para evitar duplicación.")
        etiquetas = {
            "infraestructura": "Infraestructura (USD)", "cargadores": "Cargadores (USD)",
            "otros_iniciales": "Otros costos iniciales (USD)",
            "mantenimiento_anual_agv": "Mantenimiento por AGV (USD/año)", "energia_anual": "Energía de la flota (USD/año)",
            "otros_opex_anuales": "Otros costos AGV (USD/año)",
            "operacion_manual_anual": "Operación manual sin personal (USD/año)",
            "personal_transporte_anual": "Personal de transporte (USD/año)",
            "otros_actuales_anuales": "Otros costos actuales (USD/año)",
            "porcentaje_evitable": "Porcentaje de costos actuales evitable (%)",
        }
        columnas = st.columns(2)
        for i, (campo, etiqueta) in enumerate(etiquetas.items()):
            with columnas[i % 2]:
                entrada(campo, etiqueta, opcional=True)
        confirmar = st.checkbox("Confirmo que los costos iniciales adicionales y OPEX sin informar no aplican (0)",
                                key=f"sin_costos_{escenario['id']}")
        if confirmar:
            for campo in ("infraestructura", "cargadores", "otros_iniciales", "mantenimiento_anual_agv", "energia_anual", "otros_opex_anuales"):
                if valores[campo] is None:
                    valores[campo] = 0.0
    return ParametrosEconomicos(**valores)


def mostrar_equilibrio(e, parametros, cantidad):
    st.markdown("**Punto de equilibrio**")
    st.write(f"Para recuperar la inversión en {parametros.payback_objetivo_anios:g} años:")
    umbrales = [
        ("Beneficio neto anual mínimo", e["beneficio_neto_anual_minimo"], " USD/año"),
        ("Ahorro operativo anual mínimo", e["ahorro_anual_minimo"], " USD/año"),
        ("Pallets adicionales mínimos/turno", e["pallets_minimos_turno"], ""),
        ("Margen mínimo por pallet", e["margen_minimo_pallet"], " USD"),
        ("Costo máximo por AGV", e["costo_maximo_agv"], " USD"),
    ]
    disponibles = [(titulo, numero(valor, unidad)) for titulo, valor, unidad in umbrales if valor is not None]
    if disponibles:
        tarjetas(disponibles)
        st.caption("Cada requisito mantiene los demás supuestos. Beneficio neto mínimo = CAPEX / payback deseado, después del OPEX. "
                   "No equivale al ahorro bruto mínimo. Sin denominador positivo no hay umbral finito salvo que el objetivo ya esté cubierto.")
    elif parametros.costo_agv is not None:
        conocidos = cantidad * parametros.costo_agv + sum(v for v in (
            parametros.integracion, parametros.infraestructura, parametros.cargadores, parametros.otros_iniciales) if v is not None)
        st.metric("Límite inferior del beneficio neto anual necesario", numero(conocidos / parametros.payback_objetivo_anios, " USD/año"))
        st.caption("Solo considera la inversión informada. Los costos iniciales pendientes pueden elevar este requisito; no se han supuesto iguales a cero. No es un ROI ni un payback calculado.")
    else:
        st.caption("Introduce el costo por AGV para obtener un límite inferior del beneficio anual necesario. "
                   "Confirma instalación y costos adicionales para el requisito exacto; margen y calendario permiten evaluar pallets mínimos.")
    if e["objetivo_imposible_incluso_agv_gratis"]:
        st.warning("El objetivo no se alcanza incluso con costo de vehículo cero bajo estos supuestos.")


def mostrar_negocio(escenario):
    from app.ui.analisis_panel import duracion_texto, margen_texto
    r, o = escenario["resultado"], escenario["operacion"]
    k, p, n = r["kpis"], r["parametros"], r["numero_agv"]
    k.update(calcular_capacidad(r["movimientos"], r["eventos"], p["duracion_turno_s"], n))
    st.subheader(f"Resultado con {n} AGV")
    st.markdown("**Capacidad de la flota**")
    mensaje = f"Capacidad logística: {k['capacidad_logistica']}"
    if k["capacidad_logistica"] == "SUFICIENTE":
        st.success(mensaje)
    else:
        st.warning(mensaje)
    tarjetas([
        ("Espera promedio por AGV", numero(k["espera_agv_media_pt_s"], " s")),
        ("Espera máxima por AGV", numero(k["espera_agv_maxima_pt_s"], " s")),
        ("Pallets que esperaron AGV", k["pallets_esperaron_agv"]),
        ("Cola máxima por falta de AGV", k["backlog_maximo_agv"]),
        ("Utilización promedio", numero(k["utilizacion_media_pct"], " %")),
        ("Pallets almacenados por hora de turno", numero(k["throughput_pt_h"])),
    ])
    with st.expander("¿Cómo se interpreta la capacidad?", expanded=False):
        st.write("SUFICIENTE: sin espera por AGV y trabajo requerido dentro de las horas disponibles. "
                 "SATURADA: aparecen esperas aunque el trabajo total cabe en las horas-AGV del turno. "
                 "INSUFICIENTE: el servicio total requerido supera las horas-AGV disponibles. "
                 "Es un diagnóstico de esta corrida, no una garantía de estabilidad futura.")
        st.caption("Las esperas incluyen los retiros de producto terminado de toda la corrida. La cola máxima y la carga de trabajo incluyen también los suministros 1:1. "
                   "La espera por AGV termina al asignar vehículo; no incluye viaje vacío, carga, viaje cargado ni descarga.")
        st.write(f"Trabajo requerido / horas-AGV disponibles: {k['carga_trabajo_requerida_pct']:.2f} %.")
    st.markdown("**Cierre físico del turno**")
    tarjetas([
        ("Producto terminado almacenado", f"{k['pallets_terminados_turno']} / {p['pallets_terminados']} pallets"),
        ("Pallets terminados pendientes al finalizar el turno", k["pallets_terminados_pendientes"]),
        ("Finalización del último pallet", duracion_texto(k["tiempo_producto_terminado_s"])),
    ])
    st.caption(f"Exceso después del turno: {k['exceso_pt_s']:.2f} s · "
               f"En servicio al corte: {k['pt_en_servicio_corte']} · Sin AGV asignado al corte: {k['pt_sin_asignar_corte']}. "
               "En servicio incluye desplazamiento vacío, carga, traslado y descarga.")
    if k["pt_tardios_sin_espera_agv"]:
        st.info("El pallet pendiente no se debe necesariamente a falta de capacidad de flota; fue liberado demasiado cerca del cierre del turno para completar físicamente su transporte.")
    with st.expander("Detalle del último pallet y otras métricas", expanded=False):
        st.write(f"Liberación: {duracion_texto(k['ultimo_pt_llegada_s'])}; espera por falta de AGV: "
                 f"{k['ultimo_pt_espera_agv_s']:.2f} s; servicio físico: {k['ultimo_pt_servicio_s']:.2f} s. "
                 "Fin = liberación + espera por AGV + servicio físico.")
        tarjetas([
            ("Pallets terminados requeridos", p["pallets_terminados"]),
            ("Cumplimiento físico al corte", numero(k["cumplimiento_pct"], " %")),
            ("Capacidad disponible", numero(k["capacidad_disponible_pct"], " %")),
            ("Tiempo ocupado total", numero(o["ocupado_s"]/3600, " h-AGV")),
            ("Tiempo libre total", numero(o["libre_s"]/3600, " h-AGV")),
            ("Distancia cargada", numero(k["distancia_cargada_m"], " m")),
            ("Distancia vacía", numero(k["distancia_vacia_m"], " m")),
            ("Suministros requeridos", k["suministros_requeridos"]),
            ("Suministros realizados dentro del turno", k["suministros_turno"]),
            ("Movimientos logísticos totales", k["movimientos_logisticos_totales"]),
        ])
    st.caption("Capacidad disponible = porcentaje de tiempo libre de la flota; no garantiza producción adicional. "
               f"Suministros pendientes al finalizar el turno: {k['suministros_pendientes']}.")
    st.caption("Tiempos ocupados y libres: suma de los AGV dentro del turno. Distancias: toda la demanda hasta terminar.")
    with st.expander("¿En qué emplean el tiempo?"):
        fases = {"viaje_cargado": "Viaje con carga", "viaje_vacio": "Viaje vacío",
                 "espera_retorno": "Espera por disponibilidad del retorno", "carga": "Carga", "descarga": "Descarga", "libre": "Libre"}
        st.dataframe([{"Actividad": label, "Horas-AGV": o[f"{campo}_s"]/3600,
                       "% del tiempo disponible": o[f"{campo}_pct"]} for campo, label in fases.items()], hide_index=True)
        st.caption("Ocupado = viajes + espera de retorno + carga + descarga. Los porcentajes usan AGV × duración del turno. "
                   "La espera de solicitudes en cola es distinta del tiempo de un AGV esperando producto.")
    st.write("Una utilización muy baja puede indicar sobredimensionamiento. Una utilización alta junto con colas puede indicar falta de capacidad.")
    st.subheader("Impacto operativo")
    st.info(f"{p['pallets_terminados']} pallets requeridos implican {k['suministros_requeridos']} suministros y "
            f"{p['pallets_terminados']} retiros de producto terminado = {k['movimientos_logisticos_totales']} movimientos logísticos. "
            "El retiro solo se genera cuando la producción de ese pallet termina.")
    try:
        with st.expander("Situación actual / Línea base"):
            st.caption("Dato de planta / supuesto editable. Complete únicamente los datos disponibles.")
            base = campos(escenario, LineaBase, "base", {
                "movimientos_turno": "Movimientos actuales por turno",
                "tiempo_manual_movimiento_s": "Tiempo manual por movimiento (s)",
                "perdida_produccion_turno_s": "Producción perdida por espera logística (s/turno)",
                "pallets_terminados_turno": "Pallets terminados actuales por turno",
                "espera_logistica_media_s": "Espera logística actual media por movimiento (s)",
            })
        impacto = comparar_linea_base(r, base)
        st.markdown("**Capacidad actual frente a capacidad simulada**")
        tarjetas([("Actual: movimientos/turno", numero(base.movimientos_turno)),
                  ("Simulada: movimientos/turno", k["completados_turno"]),
                  ("Movimientos adicionales atendidos", numero(impacto["movimientos_adicionales_atendidos"])),
                  ("Incremento logístico", numero(impacto["incremento_logistico_pct"], " %")),
                  ("Horas logísticas recuperadas", numero(impacto["horas_logisticas_recuperadas"], " h")),
                  ("Reducción de espera media", numero(impacto["reduccion_espera_media_s"], " s"))])
        st.caption("Capacidad atendida bajo la demanda introducida; no es capacidad máxima de producción. "
                   "Horas recuperadas: diferencia de tiempo de servicio para el volumen común, sumada por movimiento; "
                   "no equivale a horas de producción ni ahorro de personal. La espera simulada promedia toda la demanda hasta finalizar.")
        st.write("Se necesitan datos de producción/manuales para convertir la mejora logística en producción adicional.")
        economia = entradas_rentabilidad(escenario, n)
        borrador = crear_escenario(r, base, economia)
    except (ValueError, OverflowError) as exc:
        st.error(str(exc))
        return
    impacto, e = borrador["impacto"], borrador["economia"]
    payback_texto = ("No aplicable" if e["beneficio_neto_anual"] is not None and e["beneficio_neto_anual"] <= 0 else numero(e["payback_anios"], " años"))
    roi_texto = "No aplicable (CAPEX cero)" if e["capex"] == 0 else numero(e["roi_anual_pct"], " %")
    completo = e["capex"] is not None and e["beneficio_neto_anual"] is not None
    if completo:
        st.write(e["estado"])
        for columna, (titulo, valor) in zip(st.columns(4), [
            ("Inversión inicial", numero(e["capex"], " USD")),
            ("Beneficio neto anual", numero(e["beneficio_neto_anual"], " USD")),
            ("ROI anual", roi_texto), ("Payback", payback_texto),
        ]):
            columna.metric(titulo, valor)
        with st.expander("Punto de equilibrio", expanded=False):
            mostrar_equilibrio(e, economia, n)
    else:
        st.info("Aún no hay información suficiente para calcular ROI y payback.")
        if e["beneficio_neto_anual"] is not None and e["beneficio_neto_anual"] <= 0:
            st.write("No rentable bajo los supuestos actuales.")
        mostrar_equilibrio(e, economia, n)
    with st.expander("¿Cómo se calcula la rentabilidad?"):
        st.code("CAPEX = AGV × costo_AGV + integración + infraestructura + cargadores + otros_iniciales\n"
                "Producción anual = pallets_adicionales/turno × margen/pallet × turnos/día × días/año\n"
                "Ahorro anual = estimación directa; si está vacía, usar desglose avanzado × %evitable / 100\n"
                "OPEX anual = AGV × mantenimiento_por_AGV + energía + otros_opex\n"
                "Neto anual = producción anual + ahorro anual − OPEX anual\n"
                "Payback años = CAPEX / neto anual (neto > 0); meses = años × 12\n"
                "ROI anual (%) = neto anual / CAPEX × 100 (CAPEX > 0)\n"
                "H = payback deseado; T = turnos/día × días/año\n"
                "Pallets mínimos/turno = max(0, CAPEX/H + OPEX − ahorro) / (margen × T)\n"
                "Margen mínimo = max(0, CAPEX/H + OPEX − ahorro) / (pallets_extra × T)\n"
                "Ahorro mínimo = max(0, CAPEX/H + OPEX − beneficio_producción)\n"
                "Costo máximo/AGV = (neto × H − costos_iniciales_sin_vehículos) / AGV", language=None)
        st.caption("Recuperación simple, sin descuento, impuestos ni financiación. Vacío es dato pendiente; cero debe introducirse explícitamente.")
    cambios = any(borrador[c] != escenario[c] for c in ("linea_base", "parametros_economicos"))
    if cambios:
        st.info("Vista previa con supuestos editados. Guárdalos para incluirlos en la comparación; las demás corridas conservarán sus datos.")
    if st.button("Guardar análisis de negocio", key=f"guardar_{escenario['id']}"):
        for campo in ("linea_base", "parametros_economicos", "impacto", "economia"):
            escenario[campo] = borrador[campo]
        st.session_state.base_guardada = asdict(base)
        st.session_state.economia_guardada = asdict(economia)
        st.success("Supuestos guardados para esta corrida. Se usarán también como punto de partida de la próxima simulación.")
    st.subheader(f"Resumen ejecutivo — {n} AGV")
    st.write(f"**Producto terminado:** {k['pallets_terminados_turno']}/{p['pallets_terminados']} pallets almacenados. "
             f"**Tiempo:** {duracion_texto(k['tiempo_producto_terminado_s'])}. **Utilización:** {k['utilizacion_media_pct']:.1f} %. "
             f"**Tiempo libre:** {o['libre_pct']:.1f} %.")
    st.write(f"**Capacidad adicional:** {numero(impacto['incremento_logistico_pct'], ' %')}. "
             f"**Producción adicional (supuesto ingresado):** {numero(economia.pallets_adicionales_turno, ' pallets/turno')}.")
    if completo:
        st.write(f"**Beneficio neto anual:** {numero(e['beneficio_neto_anual'], ' USD')}. "
                 f"**Inversión:** {numero(e['capex'], ' USD')}. **Payback:** {payback_texto}. **ROI anual:** {roi_texto}.")
    else:
        st.caption("Rentabilidad: aún no hay información suficiente para calcular ROI y payback.")



def comparar_guardados(historial, etiquetas):
    from app.ui.analisis_panel import duracion_texto
    if st.button("Comparar escenarios simulados"):
        st.session_state["ver_comparacion"] = True
    if not st.session_state.get("ver_comparacion"):
        return
    st.subheader("Comparación de escenarios simulados")
    st.caption("Solo corridas ejecutadas y sus supuestos guardados. El historial se conserva durante esta sesión; exporta JSON para conservarlo fuera de ella.")
    elegidos = st.multiselect("Corridas a comparar", list(etiquetas), default=list(etiquetas), format_func=etiquetas.get)
    escenarios = [e for e in historial if e["id"] in elegidos]
    if len(escenarios) < 2:
        st.info("Selecciona al menos dos corridas ejecutadas para comparar.")
        return
    comparables = son_comparables(escenarios)
    if not comparables:
        st.warning("Los parámetros operativos, la línea base o los supuestos económicos difieren. Las diferencias no se pueden atribuir únicamente al número de AGV.")
    filas = []
    for s in escenarios:
        r, e = s["resultado"], s["economia"]
        k = r["kpis"]
        k.update(calcular_capacidad(r["movimientos"], r["eventos"], r["parametros"]["duracion_turno_s"], r["numero_agv"]))
        filas.append({"Escenario": etiquetas[s["id"]], "AGV": r["numero_agv"], "Pallets terminados": k["pallets_terminados_turno"],
                      "Capacidad logística": k["capacidad_logistica"],
                      "Espera promedio (s)": k["espera_agv_media_pt_s"], "Espera máxima (s)": k["espera_agv_maxima_pt_s"],
                      "Backlog máximo": k["backlog_maximo_agv"],
                      "Termina todos los pallets": duracion_texto(k["tiempo_producto_terminado_s"]),
                      "Exceso sobre turno (s)": k["exceso_pt_s"],
                      "Pendientes": k["pallets_terminados_pendientes"], "Cumplimiento (%)": k["cumplimiento_pct"],
                      "Capacidad disponible (%)": k["capacidad_disponible_pct"],
                      "Utilización (%)": k["utilizacion_media_pct"], "Tiempo libre (h-AGV)": s["operacion"]["libre_s"]/3600,
                      "Tiempo para producto terminado (h)": k["tiempo_producto_terminado_s"]/3600,
                      "Producción adicional (supuesto)": numero(s["parametros_economicos"]["pallets_adicionales_turno"]),
                      "CAPEX": numero(e["capex"]), "Beneficio anual": numero(e["beneficio_neto_anual"]),
                      "Payback (años)": numero(e["payback_anios"])})
    principales = ("Escenario", "AGV", "Capacidad logística", "Utilización (%)", "Espera promedio (s)",
                   "Espera máxima (s)", "Backlog máximo", "Termina todos los pallets", "Exceso sobre turno (s)")
    st.dataframe([{c: f[c] for c in principales} for f in filas], hide_index=True, width="stretch")
    st.caption("Termina todos los pallets: tiempo desde el inicio de la simulación. Exceso respecto a la duración de turno configurada (8 h en la base).")
    with st.expander("Detalle operativo y económico de la comparación", expanded=False):
        st.dataframe(filas, hide_index=True, width="stretch")
    for campo in ("Espera promedio (s)", "Utilización (%)"):
        st.bar_chart(filas, x="Escenario", y=campo)
    financieros = [{"Escenario": etiquetas[s["id"]], "Payback (años)": s["economia"]["payback_anios"]}
                   for s in escenarios if s["economia"]["payback_anios"] is not None]
    if financieros:
        st.bar_chart(financieros, x="Escenario", y="Payback (años)")
    if comparables:
        orden = sorted(escenarios, key=lambda e: e["resultado"]["numero_agv"])
        for a, b in zip(orden, orden[1:]):
            x, y = a["resultado"], b["resultado"]
            if x["numero_agv"] == y["numero_agv"]:
                continue
            delta = y["kpis"]["pallets_terminados_turno"] - x["kpis"]["pallets_terminados_turno"]
            st.write(f"Pasar de {x['numero_agv']} a {y['numero_agv']} AGV cambia los pallets terminados almacenados en {delta:+d} "
                     f"y la utilización de {x['kpis']['utilizacion_media_pct']:.1f} % a {y['kpis']['utilizacion_media_pct']:.1f} %.")
            st.caption(f"Espera por AGV: {x['kpis']['espera_agv_media_pt_s']:.2f} → {y['kpis']['espera_agv_media_pt_s']:.2f} s; "
                       f"cola máxima: {x['kpis']['backlog_maximo_agv']} → {y['kpis']['backlog_maximo_agv']}. "
                       "El mismo cierre físico puede coexistir con menor espera por vehículos.")
