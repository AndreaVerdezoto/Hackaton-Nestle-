"""Marcas compartidas por los encabezados de las cuatro pestañas."""
import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st


ASSETS = Path(__file__).parent / "assets"


@lru_cache(maxsize=1)
def logotipos_html():
    """Incluye los PNG originales; solo cambia su tamaño de presentación."""
    proyecto = base64.b64encode((ASSETS / "Intramovelogo.png").read_bytes()).decode("ascii")
    nestle = base64.b64encode((ASSETS / "nestle_logo.png").read_bytes()).decode("ascii")
    return f"""
    <style>
    .marcas-proyecto {{
        display: flex; align-items: center; justify-content: flex-end;
        gap: 18px; width: 388px; max-width: 100%; min-width: 0;
    }}
    .marcas-proyecto img {{
        display: block; height: auto; object-fit: contain; min-width: 0;
    }}
    .marcas-proyecto .logo-intramove {{ width: 230px; }}
    .marcas-proyecto .logo-nestle {{ width: 140px; }}
    @media (max-width: 700px) {{
        .marcas-proyecto {{ width: 288px; gap: 12px; justify-content: flex-start; }}
        .marcas-proyecto .logo-intramove {{ width: 168px; }}
        .marcas-proyecto .logo-nestle {{ width: 108px; }}
    }}
    </style>
    <div class="marcas-proyecto" aria-label="Intramove y Nestlé">
        <img class="logo-intramove" src="data:image/png;base64,{proyecto}" alt="Intramove">
        <img class="logo-nestle" src="data:image/png;base64,{nestle}" alt="Nestlé">
    </div>
    """


def mostrar_encabezado(titulo):
    """Conserva el título nativo y permite pasar las marcas a la siguiente fila."""
    with st.container(horizontal=True, wrap=True, horizontal_alignment="distribute",
                      vertical_alignment="center", gap="medium"):
        st.title(titulo, width="content")
        st.html(logotipos_html(), width="content")
