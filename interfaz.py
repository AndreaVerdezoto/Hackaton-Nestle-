"""Entrada Streamlit. Solo se ejecuta el contenido de la pestaña seleccionada."""
import streamlit as st

st.set_page_config(page_title="Dimensionamiento de flota AGV", page_icon="🤖", layout="wide")

# Identidad visual global: se carga en ambos modos para que la interfaz no
# cambie de tema al pasar de Análisis de flota a Simulación 2D.
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



# Navegación compatible entre Windows/macOS y distintas versiones de navegador.
# No dependemos del estado interno de st.tabs para decidir qué contenido construir.
analisis, visual = st.tabs(["Análisis de flota", "Simulación 2D"])

with analisis:
    from app.ui.analisis_panel import mostrar_analisis
    mostrar_analisis()

with visual:
    from app.ui.simulacion_2d import mostrar_2d
    mostrar_2d()

from app.ui.nestor_panel import mostrar_nestor_flotante
mostrar_nestor_flotante()
