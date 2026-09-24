"""Widget flotante de Streamlit para consultar a Néstor."""
from pathlib import Path

import streamlit as st

from app.services.nestor import Nestor


NESTOR_AVATAR = Path(__file__).resolve().parent / "assets" / "nestor_avatar.png"
EJEMPLOS = (
    "¿Cómo está la flota?",
    "¿Hay alguna alerta?",
    "¿Cómo está la batería?",
)
_SIN_RESULTADO_EXPLICITO = object()


def mostrar_nestor_flotante(resultado_actual=_SIN_RESULTADO_EXPLICITO, escenario_id=None):
    if resultado_actual is _SIN_RESULTADO_EXPLICITO:
        resultado_actual, escenario_id = _resultado_desde_session_state()

    _inyectar_estilos()
    st.session_state.setdefault("nestor_abierto", False)
    st.session_state.setdefault("nestor_historial", [])

    with st.container(key="nestor_floating_widget", border=True):
        if st.session_state.nestor_abierto:
            _mostrar_panel_abierto(resultado_actual, escenario_id)
        else:
            _mostrar_burbuja()


def mostrar_nestor(resultado_actual=_SIN_RESULTADO_EXPLICITO, escenario_id=None):
    mostrar_nestor_flotante(resultado_actual, escenario_id)


def _resultado_desde_session_state():
    historial = st.session_state.get("escenarios_simulados") or []
    if not historial:
        return None, None

    activo = st.session_state.get("escenario_activo")
    escenario = None
    if activo is not None:
        escenario = next((item for item in historial if item.get("id") == activo), None)
    if escenario is None:
        escenario = historial[-1]
        activo = escenario.get("id")
    return escenario.get("resultado"), activo


def _mostrar_burbuja():
    if NESTOR_AVATAR.exists():
        st.image(str(NESTOR_AVATAR), width=74)
    else:
        st.warning("No se encontró la imagen de Néstor; el asistente sigue disponible.")
    st.button("Néstor", key="abrir_nestor", on_click=_abrir_nestor, width="stretch")


def _mostrar_panel_abierto(resultado_actual, escenario_id):
    encabezado_avatar, encabezado_texto, encabezado_cierre = st.columns([1, 3, 1])
    with encabezado_avatar:
        if NESTOR_AVATAR.exists():
            st.image(str(NESTOR_AVATAR), width=92)
        else:
            st.warning("No se encontró la imagen de Néstor; el asistente sigue disponible.")
    with encabezado_texto:
        st.markdown("**Néstor**")
        st.caption("Asistente inteligente de análisis intralogístico")
    with encabezado_cierre:
        st.button("Cerrar", key="cerrar_nestor", on_click=_cerrar_nestor)

    st.caption(
        "Néstor interpreta las métricas de la operación y ayuda a identificar "
        "desviaciones en el desempeño de la flota."
    )

    if resultado_actual is None:
        st.info("Ejecuta primero una simulación para que pueda analizar la operación.")
        return

    _mostrar_sugerencias(resultado_actual, escenario_id)
    _mostrar_formulario(resultado_actual, escenario_id)
    _mostrar_historial(escenario_id)


def _mostrar_sugerencias(resultado_actual, escenario_id):
    st.caption("Preguntas sugeridas")
    columnas = st.columns(len(EJEMPLOS))
    for indice, ejemplo in enumerate(EJEMPLOS):
        with columnas[indice]:
            if st.button(ejemplo, key=f"nestor_sugerencia_{indice}", width="stretch"):
                _registrar_respuesta(ejemplo, resultado_actual, escenario_id)


def _mostrar_formulario(resultado_actual, escenario_id):
    with st.form("formulario_nestor_flotante", clear_on_submit=True):
        pregunta = st.text_input("Pregunta para Néstor", key="nestor_pregunta")
        enviar = st.form_submit_button("Preguntar")

    if enviar and pregunta.strip():
        _registrar_respuesta(pregunta.strip(), resultado_actual, escenario_id)


def _mostrar_historial(escenario_id):
    historial = _historial_visible(st.session_state.get("nestor_historial", []), escenario_id)
    if not historial:
        st.caption("El historial se conservará mientras esta sesión esté abierta.")
        return

    for entrada in reversed(historial):
        st.markdown(f"**Gerente:** {entrada['pregunta']}")
        respuesta = entrada["respuesta"]
        st.markdown(f"**Néstor:** {respuesta['respuesta']}")
        acciones = respuesta.get("acciones_revision") or []
        if acciones:
            st.markdown("**Acciones de revisión**")
            for accion in acciones[:2]:
                st.write(f"- {accion}")
        limitaciones = respuesta.get("limitaciones") or []
        if limitaciones:
            st.markdown("**Información no disponible**")
            for limitacion in limitaciones:
                st.write(f"- {limitacion}")


def _registrar_respuesta(pregunta, resultado_actual, escenario_id):
    respuesta = Nestor(resultado=resultado_actual).responder(pregunta)
    st.session_state.nestor_historial.append({
        "escenario_id": escenario_id,
        "pregunta": pregunta,
        "respuesta": respuesta,
    })


def _historial_visible(historial, escenario_id):
    if escenario_id is None:
        return list(historial)
    return [
        entrada for entrada in historial
        if entrada.get("escenario_id") in (None, escenario_id)
    ]


def _abrir_nestor():
    st.session_state.nestor_abierto = True


def _cerrar_nestor():
    st.session_state.nestor_abierto = False


def _inyectar_estilos():
    st.markdown(
        """
        <style>
        .st-key-nestor_floating_widget {
            position: fixed;
            right: 1.25rem;
            bottom: 1.25rem;
            z-index: 1000;
            width: min(390px, calc(100vw - 2.5rem));
            background: rgba(255, 255, 255, 0.97);
            border: 1px solid rgba(49, 51, 63, 0.18);
            border-radius: 14px;
            box-shadow: 0 18px 46px rgba(15, 23, 42, 0.18);
            padding: 0.8rem;
        }
        .st-key-nestor_floating_widget img {
            border-radius: 999px;
            object-fit: cover;
        }
        .st-key-nestor_floating_widget [data-testid="stMarkdownContainer"] p {
            margin-bottom: 0.25rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
