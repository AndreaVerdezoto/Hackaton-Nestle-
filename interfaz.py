"""Entrada Streamlit organizada por secciones ejecutivas."""
import streamlit as st

st.set_page_config(page_title="Dimensionamiento de flota AGV", page_icon="🤖", layout="wide")

# Identidad visual global.
st.html("""
<style>
[data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background: #f5f6f8;
}
[data-testid="stTabs"] [role="tablist"] {
    gap: 1.15rem;
    border-bottom: 1px solid #dfe4ea;
}
[data-testid="stTabs"] button[role="tab"] {
    background: transparent !important;
    color: #536174 !important;
    font-weight: 600;
}
[data-testid="stTabs"] button[role="tab"] p {
    color: inherit !important;
}
[data-testid="stTabs"] button[role="tab"]:hover {
    color: #a91f31 !important;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #c42336 !important;
}
</style>
""")



st.session_state.setdefault("modo_principal", "Dimensionamiento")

dimensionamiento, resultados, simulacion, rentabilidad, metodologia = st.tabs([
    "Dimensionamiento", "Resultados", "Simulación 2D", "Rentabilidad", "Metodología"
])

from app.ui.analisis_panel import (
    mostrar_dimensionamiento, mostrar_resultados,
    mostrar_rentabilidad, mostrar_metodologia,
)

with dimensionamiento:
    mostrar_dimensionamiento()

with resultados:
    mostrar_resultados()

with simulacion:
    from app.ui.simulacion_2d import mostrar_2d
    mostrar_2d()

with rentabilidad:
    mostrar_rentabilidad()

with metodologia:
    mostrar_metodologia()

from app.ui.nestor_panel import mostrar_nestor_flotante
mostrar_nestor_flotante()
