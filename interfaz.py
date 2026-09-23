"""Entrada Streamlit. Solo se ejecuta el contenido de la pestaña seleccionada."""
import streamlit as st

st.set_page_config(page_title="Dimensionamiento de flota AGV", page_icon="🤖", layout="wide")


def cambiar_modo():
    reloj = st.session_state.get("reloj_2d")
    if reloj and st.session_state.modo_principal != "Simulación 2D":
        reloj["ejecutando"] = False
    escenario = st.session_state.get("escenario")
    if st.session_state.modo_principal == "Análisis de flota" and escenario is not None:
        escenario.detener()  # Cierra solo el seguimiento Python; no envía TCP.


st.session_state.setdefault("modo_principal", "Análisis de flota")

analisis, visual, demo = st.tabs(["Análisis de flota", "Simulación 2D", "Demo FlexSim"])
if st.session_state.modo_principal == "Análisis de flota":
    with analisis:
        from app.ui.analisis_panel import mostrar_analisis
        mostrar_analisis()
if st.session_state.modo_principal == "Simulación 2D":
    with visual:
        from app.ui.simulacion_2d import mostrar_2d
        mostrar_2d()
if st.session_state.modo_principal == "Demo FlexSim":
    with demo:
        st.info("Este modo permite validar visualmente que Python puede controlar los AGV en FlexSim. "
                "No interviene en el cálculo del dimensionamiento presentado en la pestaña Análisis de flota.")
        st.warning("Validación visual / demostración física. No se utiliza para calcular automáticamente el dimensionamiento de la flota.")
        st.caption("Al cambiar a Análisis se cierra la corrida demo activa. Las misiones físicas ya enviadas pueden continuar.")
        from app.ui.demo_panel import mostrar_demo
        mostrar_demo()

from app.ui.nestor_panel import mostrar_nestor_flotante
mostrar_nestor_flotante()
