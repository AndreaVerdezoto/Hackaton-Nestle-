"""Controles Streamlit; la planificación permanece en escenario_turno."""

from dataclasses import asdict
import json
import streamlit as st

from app.models.solicitud import EstadoSolicitud
from app.services.gestor_flota import GestorFlota
from app.services.escenario_turno import EscenarioTurno, preparar_flota, FACTOR_ACELERACION


def controles_escenario():
    st.subheader("Escenario de demostración FlexSim")
    escenario = st.session_state.get("escenario")
    if escenario is not None:
        if st.button("Detener escenario", disabled=escenario.estado != "EJECUTANDO"):
            escenario.detener()
        st.caption("Detener cierra y guarda la corrida; las misiones físicas ya enviadas pueden continuar.")
        restablecido = st.checkbox(
            "Restablecí FlexSim, eliminé pallets de la corrida y coloqué los AGV en sus posiciones iniciales",
            key="reset_fisico_confirmado",
        )
        if st.button("Reiniciar / volver al modo manual", disabled=escenario.estado == "EJECUTANDO" or not restablecido):
            # El protocolo no tiene RESET/CANCELAR. Solo el operador puede restablecer lo físico.
            del st.session_state.escenario
            del st.session_state.gestor
            st.session_state.pop("inicio_fisico_confirmado", None)
            st.session_state.pop("reset_fisico_confirmado", None)
            st.rerun()
        return

    with st.expander("Configurar corrida", expanded=True):
        cantidad_agv = st.selectbox("AGV activos", [2, 3, 4, 5], index=1)
        factor = st.number_input("Factor de aceleración Python", min_value=0.1,
                                 value=FACTOR_ACELERACION, step=1.0)
        modo = st.selectbox("Escenario", ["Prueba pequeña: 6 movimientos / 600 s", "Turno base: 215 movimientos / 28800 s"])
        ubicaciones = {}
        for i in range(4, cantidad_agv + 1):
            agv = f"AGV_{i:02d}"
            ubicaciones[agv] = st.selectbox(
                f"Ubicación lógica inicial real de {agv}",
                [None] + sorted(st.session_state.gestor.grafo),
                format_func=lambda valor: "Seleccione una ubicación verificada" if valor is None else valor,
            )
        st.caption("107 ciclos de ida/retorno en la misma línea y con el mismo AGV, más un suministro final. "
                   "Prueba pequeña: ida/retorno COOKIE_1, COOKIE_2 y COOKIE_3. "
                   "Supuestos: 500 kg/pallet, prioridad NORMAL e idas programadas por ciclo en round-robin; no son datos de Nestlé. "
                   "AGV_01/02/03 parten de TRANSIT_4/2/1. Baterías iniciales: 85/70/95/100/100 %. "
                   "Ajuste FlexSim a la misma velocidad efectiva que el factor Python; el protocolo no sincroniza relojes.")
        confirmado = st.checkbox("FlexSim restablecido y ejecutándose, sin generación por Sources; posiciones iniciales verificadas",
                                 key="inicio_fisico_confirmado")
        if st.button("Iniciar escenario", disabled=not confirmado):
            anterior = st.session_state.gestor
            if any(a.mision_actual for a in anterior.agvs) or any(
                s.estado == EstadoSolicitud.PENDIENTE for s in anterior.solicitudes
            ):
                st.error("Termine las misiones y solicitudes manuales pendientes antes de iniciar.")
                return
            try:
                nuevo = GestorFlota()
                preparar_flota(nuevo, cantidad_agv, ubicaciones)
                pequeno = modo.startswith("Prueba")
                corrida = EscenarioTurno(nuevo, factor=factor,
                                        cantidad=6 if pequeno else 215,
                                        duracion=600 if pequeno else 28800)
                corrida.iniciar()
            except (ValueError, RuntimeError, OSError) as exc:
                st.error(str(exc))
                return
            st.session_state.gestor = nuevo
            st.session_state.escenario = corrida
            st.rerun()


def mostrar_escenario(escenario):
    st.write(f"Estado de corrida: **{escenario.estado}**")
    st.progress(escenario.tiempo_logico / escenario.duracion,
                text=f"{escenario.tiempo_logico:.1f} / {escenario.duracion} segundos lógicos")
    columnas = st.columns(7)
    for columna, (nombre, valor) in zip(columnas, escenario.indicadores().items()):
        columna.metric(nombre, valor)
    st.caption("Pendientes = programados sin completar; backlog = pallets creados esperando asignación. "
               "Al corte se congelan los eventos/KPIs; los contadores de AGV siguen mostrando el drenaje físico.")
    if escenario.error:
        st.error(f"Corrida interrumpida / error de consulta: {escenario.error}")
    if escenario.error_guardado:
        st.error(f"No se pudo guardar el resultado: {escenario.error_guardado}")
        if st.button("Reintentar guardar resultado"):
            escenario.guardar_resultado()
    if escenario.ruta_resultado:
        st.success(f"Resultado guardado: {escenario.ruta_resultado}")
    with st.expander("KPIs y eventos de la corrida"):
        st.json(escenario.resultado["kpis"] if escenario.resultado else escenario.kpis())
        st.dataframe([asdict(e) for e in escenario.eventos], hide_index=True)
    if escenario.resultado:
        st.download_button("Descargar resultado JSON", json.dumps(escenario.resultado, ensure_ascii=False, indent=2),
                           file_name=f"corrida_{escenario.id_corrida}.json", mime="application/json")
