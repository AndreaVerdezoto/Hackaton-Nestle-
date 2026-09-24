"""Entrada Streamlit. Solo se ejecuta el contenido de la pestaña seleccionada."""
import streamlit as st

st.set_page_config(page_title="Dimensionamiento de flota AGV", page_icon="🤖", layout="wide")


def cambiar_modo():
    reloj = st.session_state.get("reloj_2d")
    if reloj and st.session_state.modo_principal != "Simulación 2D":
        reloj["ejecutando"] = False


MODOS_PRINCIPALES = ["Análisis de flota", "Simulación 2D"]
if st.session_state.get("modo_principal") not in MODOS_PRINCIPALES:
    st.session_state["modo_principal"] = "Análisis de flota"

analisis, visual = st.tabs(
    MODOS_PRINCIPALES,
    key="modo_principal", on_change=cambiar_modo,
)
if st.session_state.modo_principal == "Análisis de flota":
    with analisis:
        from app.ui.analisis_panel import mostrar_analisis
        mostrar_analisis()
if st.session_state.modo_principal == "Simulación 2D":
    with visual:
        from app.ui.simulacion_2d import mostrar_2d
        mostrar_2d()
from app.ui.nestor_panel import mostrar_nestor_flotante
mostrar_nestor_flotante()
