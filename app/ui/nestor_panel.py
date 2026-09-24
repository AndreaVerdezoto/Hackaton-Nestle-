"""Widget flotante de Streamlit para consultar a Néstor."""
import base64
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

    with st.container(key="nestor_floating_widget", border=False):
        if st.session_state.nestor_abierto:
            _mostrar_panel_abierto(resultado_actual, escenario_id)
            _mostrar_burbuja("nestor_avatar_abierto", _cerrar_nestor)
        else:
            _mostrar_burbuja("abrir_nestor", _abrir_nestor)


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


def _mostrar_burbuja(key, accion):
    if not NESTOR_AVATAR.exists():
        st.warning("No se encontró la imagen de Néstor; el asistente sigue disponible.")
    st.button("Néstor", key=key, on_click=accion, help="Hablar con Néstor")


def _mostrar_panel_abierto(resultado_actual, escenario_id):
    with st.container(key="nestor_chat_panel", border=False):
        encabezado_avatar, encabezado_texto, encabezado_cierre = st.columns([1, 4, 1])
        with encabezado_avatar:
            if NESTOR_AVATAR.exists():
                st.image(str(NESTOR_AVATAR), width=42)
        with encabezado_texto:
            st.markdown("**Néstor**")
            st.caption("Asistente inteligente de análisis intralogístico")
        with encabezado_cierre:
            st.button("×", key="cerrar_nestor", on_click=_cerrar_nestor, help="Cerrar")

        st.caption(
            "Néstor interpreta las métricas de la operación y ayuda a identificar "
            "desviaciones en el desempeño de la flota."
        )

        if resultado_actual is None:
            st.info("Ejecuta primero una simulación para que pueda analizar la operación.")
            return

        _mostrar_historial(resultado_actual, escenario_id)
        _mostrar_formulario(resultado_actual, escenario_id)


def _mostrar_sugerencias(resultado_actual, escenario_id):
    st.caption("Preguntas sugeridas")
    columnas = st.columns(len(EJEMPLOS))
    for indice, ejemplo in enumerate(EJEMPLOS):
        with columnas[indice]:
            if st.button(ejemplo, key=f"nestor_sugerencia_{indice}", width="stretch"):
                _registrar_respuesta(ejemplo, resultado_actual, escenario_id)
                st.rerun()


def _mostrar_formulario(resultado_actual, escenario_id):
    with st.form("formulario_nestor_flotante", clear_on_submit=True):
        pregunta = st.text_input("Pregunta para Néstor", key="nestor_pregunta")
        enviar = st.form_submit_button("Preguntar")

    if enviar and pregunta.strip():
        _registrar_respuesta(pregunta.strip(), resultado_actual, escenario_id)
        st.rerun()


def _mostrar_historial(resultado_actual, escenario_id):
    historial = _historial_visible(st.session_state.get("nestor_historial", []), escenario_id)
    with st.container(key="nestor_history_scroll", height=320, border=False):
        if not historial:
            _mostrar_sugerencias(resultado_actual, escenario_id)
            st.caption("El historial se conservará mientras esta sesión esté abierta.")
            return

        for entrada in historial:
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
    avatar = _avatar_css_background()
    st.html(
        """
        <style>
        .st-key-nestor_floating_widget {
            position: fixed;
            right: 1.25rem;
            bottom: 1.25rem;
            z-index: 1000;
            width: 74px;
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            padding: 0 !important;
        }
        .st-key-nestor_floating_widget:has(.st-key-nestor_chat_panel) {
            width: min(410px, calc(100vw - 2rem));
        }
        .st-key-nestor_chat_panel {
            width: min(410px, calc(100vw - 2rem));
            max-height: min(550px, calc(100vh - 7rem));
            background: rgba(255, 255, 255, 0.98);
            border: 1px solid rgba(49, 51, 63, 0.16);
            border-radius: 16px;
            box-shadow: 0 18px 46px rgba(15, 23, 42, 0.20);
            padding: 0.85rem 0.95rem 0.75rem;
            margin-bottom: 0.75rem;
            overflow: hidden;
        }
        .st-key-nestor_history_scroll {
            overflow-y: auto !important;
            padding-right: 0.25rem;
            border-top: 1px solid rgba(49, 51, 63, 0.08);
            border-bottom: 1px solid rgba(49, 51, 63, 0.08);
            margin: 0.55rem 0 0.65rem;
        }
        .st-key-abrir_nestor,
        .st-key-nestor_avatar_abierto {
            display: flex;
            justify-content: flex-end;
        }
        .st-key-abrir_nestor button,
        .st-key-nestor_avatar_abierto button {
            width: 72px !important;
            min-width: 72px !important;
            height: 72px !important;
            border-radius: 999px !important;
            padding: 0 !important;
            border: 2px solid rgba(255, 255, 255, 0.96) !important;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.26) !important;
            background-color: #f8fafc !important;
            __AVATAR_BACKGROUND__
            background-size: cover !important;
            background-position: center !important;
            color: transparent !important;
            font-size: 0 !important;
        }
        .st-key-abrir_nestor button:hover,
        .st-key-nestor_avatar_abierto button:hover {
            transform: translateY(-1px);
            box-shadow: 0 15px 34px rgba(15, 23, 42, 0.30) !important;
            border-color: rgba(196, 35, 54, 0.35) !important;
        }
        .st-key-abrir_nestor button p,
        .st-key-nestor_avatar_abierto button p {
            font-size: 0 !important;
            line-height: 0 !important;
        }
        .st-key-cerrar_nestor button {
            width: 32px !important;
            height: 32px !important;
            min-width: 32px !important;
            border-radius: 999px !important;
            padding: 0 !important;
            font-size: 1.05rem !important;
        }
        .st-key-nestor_chat_panel img {
            border-radius: 999px;
            object-fit: cover;
        }
        .st-key-nestor_chat_panel [data-testid="stForm"] {
            border: 0;
            padding: 0;
        }
        .st-key-nestor_chat_panel [data-testid="stMarkdownContainer"] p {
            margin-bottom: 0.25rem;
        }
        @media (max-width: 520px) {
            .st-key-nestor_floating_widget,
            .st-key-nestor_floating_widget:has(.st-key-nestor_chat_panel) {
                right: 0.75rem;
                bottom: 0.75rem;
                width: min(390px, calc(100vw - 1.5rem));
            }
            .st-key-nestor_chat_panel {
                width: min(390px, calc(100vw - 1.5rem));
            }
        }
        </style>
        """.replace("__AVATAR_BACKGROUND__", avatar),
    )


def _avatar_css_background():
    if not NESTOR_AVATAR.exists():
        return ""
    contenido = base64.b64encode(NESTOR_AVATAR.read_bytes()).decode("ascii")
    return f"background-image: url('data:image/png;base64,{contenido}') !important;"
