"""Widget flotante de Streamlit para consultar a Néstor."""
import base64
from pathlib import Path

import streamlit as st

from app.services.nestor import Nestor, formatear_duracion
from app.services.preguntas_nestor import CATEGORIAS, PREGUNTAS, obtener_pregunta
from app.services.alertas_linea import (
    UMBRAL_DEMO_S, consultar_alertas, actualizar_registro, historial_visible, nuevas_sin_leer,
)
from app.services.exportacion_nestor import exportar_corrida_nestor


NESTOR_AVATAR = Path(__file__).resolve().parent / "assets" / "nestor_avatar.png"
_SIN_RESULTADO_EXPLICITO = object()


def mostrar_nestor_flotante(resultado_actual=_SIN_RESULTADO_EXPLICITO, escenario_id=None):
    if resultado_actual is _SIN_RESULTADO_EXPLICITO:
        resultado_actual, escenario_id = _resultado_desde_session_state()

    _inyectar_estilos()
    st.session_state.setdefault("nestor_abierto", False)
    st.session_state.setdefault("nestor_historial", [])
    st.session_state.setdefault("nestor_umbral_alertas_s", UMBRAL_DEMO_S)
    st.session_state["nestor_escenario_renderizado"] = escenario_id

    with st.container(key="nestor_floating_widget", border=False):
        if st.session_state.nestor_abierto:
            _mostrar_panel_abierto(resultado_actual, escenario_id)
            _mostrar_burbuja("nestor_avatar_abierto", _cerrar_nestor)
        else:
            _mostrar_alertas_automaticas(resultado_actual, escenario_id, cerrado=True)
            _mostrar_burbuja("abrir_nestor", _abrir_nestor)


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
        with st.container(key="nestor_header", border=False):
            _mostrar_encabezado()
            if resultado_actual is not None:
                _mostrar_alertas_automaticas(resultado_actual, escenario_id)

        if resultado_actual is None:
            st.info("Ejecuta primero una simulación para que pueda analizar la operación.")
            return

        with st.container(key="nestor_conversation", border=False):
            st.caption("Historial de conversación")
            _mostrar_historial(resultado_actual, escenario_id)
        _mostrar_sugerencias(resultado_actual, escenario_id)
        with st.expander("Escribir otra pregunta (opcional)", key="nestor_texto_libre"):
            _mostrar_formulario(resultado_actual, escenario_id)


def _mostrar_encabezado():
    encabezado_avatar, encabezado_texto, encabezado_cierre = st.columns([1, 4, 1])
    with encabezado_avatar:
        if NESTOR_AVATAR.exists():
            st.image(str(NESTOR_AVATAR), width=42)
    with encabezado_texto:
        st.markdown("**Néstor**")
        st.caption("Asistente de operaciones")
    with encabezado_cierre:
        st.button("×", key="cerrar_nestor", on_click=_cerrar_nestor, help="Cerrar")


def _actualizar_alertas_session(resultado, escenario_id, *, leidas=False):
    """Resuelve el escenario en cada tick; nunca captura una corrida obsoleta del panel."""
    if st.session_state.get("escenarios_simulados"):
        resultado, escenario_id = _resultado_desde_session_state()
    reloj = st.session_state.get("reloj_2d") or {}
    tiempo_s = reloj.get("tiempo_s") if st.session_state.get("escenario_2d_activo") == escenario_id else None
    consulta = consultar_alertas(resultado, tiempo_s, st.session_state["nestor_umbral_alertas_s"])
    registros = st.session_state.setdefault("nestor_alertas_registros", {})
    if escenario_id is not None and tiempo_s is not None:
        registros[escenario_id] = actualizar_registro(
            registros.get(escenario_id), escenario_id, consulta,
            revision=reloj.get("revision", 0), leidas=leidas,
        )
    return consulta, registros.get(escenario_id), escenario_id


@st.fragment(run_every=0.5)
def _mostrar_alertas_automaticas(resultado, escenario_id, cerrado=False):
    if cerrado:
        consulta, registro, _ = _actualizar_alertas_session(resultado, escenario_id)
        nuevas = nuevas_sin_leer(registro, consulta["tiempo_s"])
        with st.container(key="nestor_alertas_badge", border=False):
            if nuevas:
                st.html(f'<span role="status">{nuevas} nuevas demoras</span>')
        return
    with st.container(key="nestor_alertas_area", border=False):
        resumen = st.empty()
        with st.popover("Alertas · configuración e historial", width="stretch", key="nestor_alertas_detalle"):
            umbral = st.number_input(
                "Umbral de espera sin asignación (segundos)", min_value=0.0,
                value=float(st.session_state["nestor_umbral_alertas_s"]),
                step=10.0, key="_nestor_umbral_input",
            )
            st.session_state["nestor_umbral_alertas_s"] = umbral
            st.caption("Parámetro configurable del prototipo. 120 s es una demostración, no un criterio validado por Nestlé.")
            st.caption("Cambiarlo reevalúa las activas; conserva los avisos anteriores sin duplicarlos ni reclasificar atendidas anteriores al cambio.")
            detalles = st.container()
        consulta, registro, activo = _actualizar_alertas_session(resultado, escenario_id, leidas=True)
        # Un selector dentro del fragmento 2D puede cambiar la corrida sin redibujar el chat.
        if (st.session_state.get("escenarios_simulados") and activo != st.session_state.get("nestor_escenario_renderizado")
                and consulta["tiempo_s"] is not None):
            st.rerun()
        with resumen.container(gap=None):
            grupos = consulta["por_linea"]
            if grupos:
                st.markdown(f"**⚠ Demoras de retiro · {len(consulta['activas'])} solicitudes**")
                lineas = [f"{g['nombre']}: {g['cantidad']} · máx. {formatear_duracion(g['espera_maxima_s'])}"
                          for g in grupos[:2]]
                if len(grupos) > 2:
                    lineas.append(f"+{len(grupos) - 2} líneas en el detalle")
                st.caption(" | ".join(lineas))
            elif consulta["limitaciones"]:
                st.caption("Demoras por línea: información incompleta o reloj no disponible.")
            else:
                st.caption("Sin demoras de retiro por encima del umbral configurado.")
        with detalles:
            st.caption(f"Reloj 2D consultado: {formatear_duracion(consulta['tiempo_s'])} · umbral: {formatear_duracion(umbral)}")
            resultado_exportar = resultado
            if st.session_state.get("escenarios_simulados"):
                resultado_exportar, _ = _resultado_desde_session_state()
            reloj_exportar = dict(st.session_state.get("reloj_2d") or {})
            reloj_exportar["tiempo_s"] = consulta["tiempo_s"]
            st.download_button(
                "Descargar corrida y alertas (JSON)",
                exportar_corrida_nestor(resultado_exportar, activo, registro,
                                       reloj=reloj_exportar, umbral_s=umbral),
                file_name=f"nestor_corrida_{activo or 'sin_id'}.json", mime="application/json",
                key="nestor_descargar_corrida", on_click="ignore", width="stretch",
            )
            st.caption("Incluye toda la simulación y los avisos observados durante esta sesión. Los tiempos se guardan en segundos, sin redondear.")
            if consulta["activas"]:
                st.write("Revisar las solicitudes sin asignar de estas líneas y el estado actual de los AGV.")
                with st.container(height=180, border=False):
                    for grupo in consulta["por_linea"]:
                        st.markdown(f"**{grupo['nombre']}**")
                        for solicitud in grupo["solicitudes"]:
                            st.write(f"Solicitud {solicitud['solicitud']} · pallet {solicitud['id_pallet'] or 'sin dato'} · espera {formatear_duracion(solicitud['espera_s'])}")
            for limitacion in consulta["limitaciones"]:
                st.caption(limitacion)
            with st.expander("Historial de alertas anteriores"):
                eventos = historial_visible(registro, consulta["tiempo_s"])
                if not eventos:
                    st.caption("Sin alertas registradas hasta este instante.")
                else:
                    with st.container(height=180, border=False):
                        for evento in eventos:
                            estado = "Atendida: comenzó la misión" if evento["estado"] == "ATENDIDA" else "Pendiente de asignación; consultar condiciones activas arriba"
                            st.write(f"{evento['nombre']} · solicitud {evento.get('solicitud', 'sin dato')} · {estado}.")
                            st.caption(f"Umbral superado desde: {formatear_duracion(evento.get('supera_desde_s'))} · Aviso detectado en: {formatear_duracion(evento.get('detectada_s'))} · Umbral del aviso: {formatear_duracion(evento.get('umbral_s'))}.")
                            st.caption(f"Espera observada al generar el aviso: {formatear_duracion(evento.get('espera_observada_s'))}.")
                            if evento["estado"] == "ATENDIDA":
                                st.caption(f"Espera final sin asignación: {formatear_duracion(evento.get('espera_final_s'))}.")
                            st.caption(f"Origen del aviso: {evento.get('origen') or 'no disponible'}.")
            st.caption("El cruce indica la frontera llegada + umbral. Se exige una espera mayor, con tolerancia numérica de 0,000001 s; la detección puede ser posterior.")


def _mostrar_sugerencias(resultado_actual, escenario_id):
    with st.container(key="nestor_question_bank", border=False):
        st.markdown("**Banco de preguntas**")
        categoria = st.selectbox("Categoría de preguntas", CATEGORIAS,
                                key="nestor_categoria", label_visibility="collapsed")
        preguntas = [p.id for p in PREGUNTAS if p.categoria == categoria]
        pregunta_id = st.selectbox(
            "Pregunta sugerida", preguntas, key="nestor_pregunta_banco",
            format_func=lambda identificador: obtener_pregunta(identificador).texto,
            label_visibility="collapsed",
        )
        if st.button("Consultar", key="nestor_consultar_banco", width="stretch"):
            pregunta = obtener_pregunta(pregunta_id)
            _registrar_respuesta(pregunta.texto, resultado_actual, escenario_id,
                                pregunta_id=pregunta.id)
            st.rerun()


def _mostrar_alternativas(resultado_actual, escenario_id):
    historial = _historial_visible(st.session_state.get("nestor_historial", []), escenario_id)
    if not historial:
        return
    respuesta = historial[-1]["respuesta"]
    if respuesta.get("tipo") != "NO_RECONOCIDA":
        return
    st.caption("Puedes continuar con una de estas preguntas:")
    for pregunta_id in respuesta.get("preguntas_alternativas", []):
        pregunta = obtener_pregunta(pregunta_id)
        if st.button(pregunta.texto, key=f"nestor_alternativa_{pregunta.id}", width="stretch"):
            _registrar_respuesta(pregunta.texto, resultado_actual, escenario_id,
                                pregunta_id=pregunta.id)
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
    with st.container(key="nestor_history_scroll", height=220, border=False, autoscroll=True):
        if not historial:
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
        # Las alternativas también pertenecen a la conversación, no agrandan el banco fijo.
        _mostrar_alternativas(resultado_actual, escenario_id)


def _registrar_respuesta(pregunta, resultado_actual, escenario_id, *, pregunta_id=None):
    # Leer al enviar: el fragmento 2D puede haber avanzado desde que se abrió el chat.
    # No extrapolar con monotonic(): se consulta exactamente el reloj ya mostrado.
    tiempo_s = _tiempo_desde_session_state(escenario_id)
    nestor = Nestor(resultado=resultado_actual, tiempo_s=tiempo_s,
                    umbral_alertas_s=st.session_state.get("nestor_umbral_alertas_s", UMBRAL_DEMO_S))
    respuesta = (nestor.responder_sugerida(pregunta_id) if pregunta_id is not None
                 else nestor.responder(pregunta))
    if pregunta_id is not None:
        pregunta = obtener_pregunta(pregunta_id).texto
    st.session_state.nestor_historial.append({
        "escenario_id": escenario_id,
        "tiempo_s": respuesta.get("tiempo_s"),
        "alcance": respuesta.get("alcance"),
        "pregunta_id": pregunta_id,
        "pregunta": pregunta,
        "respuesta": respuesta,
    })


def _tiempo_desde_session_state(escenario_id):
    if escenario_id is None or st.session_state.get("escenario_2d_activo") != escenario_id:
        return 0.0
    return (st.session_state.get("reloj_2d") or {}).get("tiempo_s", 0.0)


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
    # st.html envía el CSS aislado a un contenedor de eventos que los fragmentos
    # pueden reemplazar. El marcador lo mantiene en la vista principal del chat.
    st.html(
        """
        <span hidden aria-hidden="true" id="nestor_panel_styles"></span>
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
            height: min(600px, calc(100dvh - 12rem));
            max-height: calc(100dvh - 12rem);
            box-sizing: border-box;
            flex: none;
            display: grid;
            align-items: stretch;
            justify-content: stretch;
            grid-template-rows: auto minmax(0, 1fr) auto auto;
            gap: 0.5rem;
            background: rgba(255, 255, 255, 0.98);
            border: 1px solid rgba(49, 51, 63, 0.16);
            border-radius: 16px;
            box-shadow: 0 18px 46px rgba(15, 23, 42, 0.20);
            padding: 0.85rem 0.95rem 0.75rem;
            margin-bottom: 0.75rem;
            overflow: hidden;
        }
        .st-key-nestor_chat_panel > [data-testid="stLayoutWrapper"] {
            min-height: 0;
            min-width: 0;
        }
        .st-key-nestor_header {
            max-height: min(250px, 35dvh);
            overflow-y: auto;
            gap: 0.3rem;
        }
        .st-key-nestor_alertas_area {
            gap: 0.2rem;
        }
        .st-key-nestor_alertas_badge {
            position: absolute;
            bottom: 78px;
            right: 0;
            width: max-content;
            pointer-events: none;
        }
        .st-key-nestor_alertas_badge span {
            display: inline-block;
            background: #a61b2b;
            color: white;
            border-radius: 12px;
            padding: 0.2rem 0.5rem;
            font-size: 0.8rem;
        }
        .st-key-nestor_conversation {
            flex: none;
            height: 100%;
            min-height: 0;
            display: grid;
            align-items: stretch;
            grid-template-rows: auto minmax(0, 1fr);
            gap: 0.25rem;
        }
        .st-key-nestor_conversation > [data-testid="stLayoutWrapper"] {
            min-height: 0;
            height: auto !important;
        }
        .st-key-nestor_history_scroll {
            flex: none;
            height: 100% !important;
            min-height: 0;
            overflow-y: auto !important;
            overscroll-behavior: contain;
            scrollbar-gutter: stable;
            padding-right: 0.25rem;
            border-top: 1px solid rgba(49, 51, 63, 0.08);
            border-bottom: 1px solid rgba(49, 51, 63, 0.08);
            margin: 0;
        }
        .st-key-nestor_question_bank {
            gap: 0.25rem;
            min-width: 0;
        }
        .st-key-nestor_question_bank button {
            min-height: 30px;
            padding: 0.2rem 0.5rem;
        }
        .st-key-nestor_texto_libre {
            max-height: min(150px, 25dvh);
            overflow-y: auto;
        }
        .st-key-nestor_texto_libre summary p {
            font-size: 0.85rem;
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
                padding: 0.6rem;
            }
        }
        @media (max-height: 600px) {
            .st-key-nestor_chat_panel {
                height: calc(100dvh - 7rem);
                max-height: calc(100dvh - 7rem);
                padding: 0.5rem;
                margin-bottom: 0;
                gap: 0.25rem;
            }
            .st-key-nestor_floating_widget {
                bottom: 0.75rem;
                gap: 0.5rem;
            }
            .st-key-nestor_avatar_abierto button {
                width: 40px !important;
                min-width: 40px !important;
                height: 40px !important;
            }
            .st-key-nestor_header [data-testid="stCaptionContainer"] {
                display: none;
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
