from datetime import datetime
# Importamos Streamlit para construir la interfaz web
import streamlit as st

# Importamos las clases del backend que ya construimos
from app.models.agv import AGV, EstadoAGV
# Importamos los estados, prioridades y la clase que representa
# una solicitud de traslado proveniente del WMS.
from app.models.solicitud import (
    SolicitudTraslado,
    EstadoSolicitud,
    PrioridadSolicitud
)
from app.services.gestor_flota import GestorFlota


# ---------------------------------------------------------
# CONFIGURACIÓN GENERAL DE LA PÁGINA
# ---------------------------------------------------------

# Configuramos el nombre de la pestaña, el ícono y el ancho
# de la interfaz.
st.set_page_config(
    page_title="Gestión de Flota AGV",
    page_icon="🤖",
    layout="wide"
)


# ---------------------------------------------------------
# CREACIÓN DEL GESTOR Y LOS AGV
# ---------------------------------------------------------

# Streamlit vuelve a ejecutar este archivo cada vez que ocurre
# una interacción, por ejemplo cuando se presiona un botón.
#
# Por eso usamos session_state:
# así el GestorFlota se crea una sola vez y no se reinician
# los AGV cada vez que la página se actualiza.
if "gestor" not in st.session_state:

    # Creamos el objeto encargado de administrar
    # AGV, solicitudes y misiones.
    gestor = GestorFlota()

    # Creamos algunos AGV iniciales para el prototipo.
    agv_1 = AGV(
        id_agv="AGV_01",
        bateria=85,
        ubicacion="TRANSIT_4"
    )

    agv_2 = AGV(
        id_agv="AGV_02",
        bateria=70,
        ubicacion="TRANSIT_2"
    )

    agv_3 = AGV(
        id_agv="AGV_03",
        bateria=95,
        ubicacion="TRANSIT_1"
    )

    # Registramos los AGV dentro del gestor de flota.
    gestor.registrar_agv(agv_1)
    gestor.registrar_agv(agv_2)
    gestor.registrar_agv(agv_3)

    # Guardamos el gestor dentro de la sesión de Streamlit.
    st.session_state.gestor = gestor


# Recuperamos el gestor almacenado en la sesión.
gestor = st.session_state.gestor

# ---------------------------------------------------------
# ACTUALIZACIÓN AUTOMÁTICA DEL SISTEMA
# ---------------------------------------------------------

# Este fragmento se ejecuta automáticamente cada segundo.
# Simula los eventos que en una implementación real llegarían
# desde los AGV o desde la simulación de la planta.
@st.fragment(run_every="1s")
def actualizar_sistema():

    hubo_cambios = False

    # -----------------------------------------------------
    # 1. CONSULTAR ESTADO REAL EN FLEXSIM
    # -----------------------------------------------------

    if gestor.actualizar_misiones_flexsim():
        hubo_cambios = True



    # -----------------------------------------------------
    # 2. FINALIZAR RECARGAS AUTOMÁTICAMENTE
    # -----------------------------------------------------

    for agv in gestor.agvs:

        # Solo revisamos AGV que actualmente están cargando
        # y que tienen registrada su hora de inicio de recarga.
        if (
            agv.estado == EstadoAGV.CARGANDO
            and agv.hora_inicio_recarga is not None
        ):

            tiempo_recargando = (
                datetime.now() - agv.hora_inicio_recarga
            ).total_seconds()

            # Para el prototipo simulamos una recarga
            # completa en 5 segundos.
            if tiempo_recargando >= 5:

                # Finalizar_recarga lleva la batería a 100 %
                # y vuelve a revisar solicitudes pendientes.
                resultado = gestor.finalizar_recarga(
                    agv.id_agv
                )

                agv_recargado, nuevas_misiones = resultado

                # Si después de recargar se pudo asignar
                # una solicitud pendiente, también comenzamos
                # esa misión automáticamente.
                for nueva_mision in nuevas_misiones:

                    gestor.iniciar_mision(
                        nueva_mision.id_mision
                    )

                hubo_cambios = True


    # Si ocurrió algún cambio de estado,
    # actualizamos toda la interfaz.
    if hubo_cambios:

        st.rerun()


# Activamos la actualización automática del sistema.
actualizar_sistema()


# ---------------------------------------------------------
# TÍTULO DEL SISTEMA
# ---------------------------------------------------------

st.title(
    "Sistema Inteligente de Gestión de Flota AGV"
)

st.write(
    "Prototipo para planificación y optimización "
    "del transporte interno de materiales."
)


# ---------------------------------------------------------
# CÁLCULO DE INDICADORES DEL DASHBOARD
# ---------------------------------------------------------

# Contamos cuántos AGV se encuentran disponibles.
agv_disponibles = sum(
    1
    for agv in gestor.agvs
    if agv.estado == EstadoAGV.DISPONIBLE
)


# Contamos las solicitudes que todavía no han sido asignadas.
solicitudes_pendientes = sum(
    1
    for solicitud in gestor.solicitudes
    if solicitud.estado == EstadoSolicitud.PENDIENTE
)


# Contamos las misiones que todavía están activas.
#
# Una misión se considera activa si fue creada
# o ya se encuentra en proceso.
misiones_activas = sum(
    1
    for mision in gestor.misiones
    if mision.estado.value in [
        "CREADA",
        "EN_PROCESO"
    ]
)


# ---------------------------------------------------------
# INDICADORES PRINCIPALES
# ---------------------------------------------------------

# Dividimos la pantalla en tres columnas.
col1, col2, col3 = st.columns(3)


# Primera columna:
# muestra cuántos AGV están disponibles.
with col1:

    st.metric(
        label="AGV disponibles",
        value=agv_disponibles
    )


# Segunda columna:
# muestra las solicitudes pendientes.
with col2:

    st.metric(
        label="Solicitudes pendientes",
        value=solicitudes_pendientes
    )


# Tercera columna:
# muestra las misiones activas.
with col3:

    st.metric(
        label="Misiones activas",
        value=misiones_activas
    )

# ---------------------------------------------------------
# TABLA DE AGV
# ---------------------------------------------------------

# Agregamos una separación visual entre los indicadores
# principales y la información detallada de los AGV.
st.divider()

st.subheader("Estado de la flota")


# Creamos una lista con la información que queremos
# mostrar de cada AGV.
datos_agvs = []

for agv in gestor.agvs:

    datos_agvs.append(
        {
            "AGV": agv.id_agv,
            "Estado": agv.estado.value,
            "Batería (%)": round(agv.bateria, 2),
            "Ubicación": agv.ubicacion
        }
    )


# Mostramos los datos en una tabla interactiva.
st.dataframe(
    datos_agvs,
    use_container_width=True,
    hide_index=True
)

# ---------------------------------------------------------
# CREACIÓN DE SOLICITUDES DE TRASLADO
# ---------------------------------------------------------

st.divider()

st.subheader("Nueva solicitud de traslado")

st.write(
    "Esta sección simula la recepción de una tarea proveniente "
    "del sistema WMS."
)


# ---------------------------------------------------------
# SELECCIÓN DEL PRODUCTO Y TIPO DE TRASLADO
# ---------------------------------------------------------

producto = st.selectbox(
    "Producto",
    [
        "Cookies",
        "Chocolate",
        "Wafer"
    ]
)

tipo_traslado = st.selectbox(
    "Tipo de traslado",
    [
        "Suministro a producción",
        "Producto terminado a almacén"
    ]
)


# Líneas disponibles para cada producto.
destinos_por_producto = {
    "Cookies": [
        "COOKIE_1",
        "COOKIE_2",
        "COOKIE_3"
    ],
    "Chocolate": [
        "CHOCOLATE"
    ],
    "Wafer": [
        "WAFER"
    ]
}


# Obtenemos las líneas correspondientes
# al producto seleccionado.
lineas_producto = destinos_por_producto[producto]


# Dependiendo del tipo de traslado,
# definimos origen y destino.
if tipo_traslado == "Suministro a producción":

    origenes_disponibles = [
        "ALMACEN"
    ]

    destinos_disponibles = lineas_producto

else:

    origenes_disponibles = lineas_producto

    destinos_disponibles = [
        "ALMACEN"
    ]


# ---------------------------------------------------------
# FORMULARIO DE SOLICITUD
# ---------------------------------------------------------

with st.form("formulario_solicitud"):

    col1, col2 = st.columns(2)

    with col1:

        id_tarea = st.text_input(
            "ID de tarea WMS",
            value=f"TAREA_{len(gestor.solicitudes) + 1:03d}"
        )

        id_pallet = st.text_input(
            "ID del pallet",
            value=f"PALLET_{len(gestor.solicitudes) + 1:03d}"
        )

        peso = st.number_input(
            "Peso del pallet (kg)",
            min_value=1,
            max_value=800,
            value=500
        )


    with col2:

        origen = st.selectbox(
            "Origen",
            origenes_disponibles
        )

        destino = st.selectbox(
            "Destino",
            destinos_disponibles
        )

        prioridad_texto = st.selectbox(
            "Prioridad",
            [
                "NORMAL",
                "ALTA",
                "BAJA"
            ]
        )


    registrar = st.form_submit_button(
        "Registrar solicitud"
    )

# ---------------------------------------------------------
# PROCESAMIENTO DEL FORMULARIO
# ---------------------------------------------------------

if registrar:

    # Convertimos la prioridad seleccionada en la interfaz
    # al Enum utilizado por nuestro backend.
    prioridad = PrioridadSolicitud[
        prioridad_texto
    ]

    # Creamos la solicitud.
    # En el prototipo el formulario simula los datos
    # que posteriormente llegarían desde WMS/SAP.
    nueva_solicitud = SolicitudTraslado(
        id_tarea_wms=id_tarea,
        id_pallet=id_pallet,
        producto=producto,
        peso=peso,
        origen=origen,
        destino=destino,
        prioridad=prioridad
    )

    # El GestorFlota recibe la solicitud.
    gestor.registrar_solicitud(
        nueva_solicitud
    )

    # El sistema intenta asignarla automáticamente.
    nuevas_misiones = (
        gestor.procesar_solicitudes_pendientes()
    )

    # Las nuevas misiones comienzan automáticamente.
    # Esto simula que el AGV recibe la orden desde
    # el sistema de gestión.
    for mision in nuevas_misiones:

        gestor.iniciar_mision(
            mision.id_mision
        )


    # Informamos qué ocurrió.
    if nuevas_misiones:

        st.session_state.mensaje_solicitud = (
            f"Solicitud {id_tarea} recibida. "
            f"AGV asignado y misión iniciada automáticamente."
        )

    else:

        st.session_state.mensaje_solicitud = (
            f"Solicitud {id_tarea} recibida. "
            f"Permanece pendiente hasta que exista "
            f"un AGV compatible disponible."
        )

    st.rerun()

# Mostramos el resultado del registro y asignación.
if "mensaje_solicitud" in st.session_state:

    st.success(
        st.session_state.mensaje_solicitud
    )

    del st.session_state.mensaje_solicitud

# ---------------------------------------------------------
# TABLA DE SOLICITUDES
# ---------------------------------------------------------

st.divider()

st.subheader("Solicitudes de traslado")


# Creamos una lista con la información de cada solicitud
# registrada dentro del GestorFlota.
datos_solicitudes = []

for solicitud in gestor.solicitudes:

    datos_solicitudes.append(
        {
            "Tarea WMS": solicitud.id_tarea_wms,
            "Pallet": solicitud.id_pallet,
            "Producto": solicitud.producto,
            "Peso (kg)": solicitud.peso,
            "Origen": solicitud.origen,
            "Destino": solicitud.destino,
            "Prioridad": solicitud.prioridad.value,
            "Estado": solicitud.estado.value
        }
    )


# Si existen solicitudes, las mostramos en una tabla.
if datos_solicitudes:

    st.dataframe(
        datos_solicitudes,
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "Todavía no existen solicitudes registradas."
    )


# ---------------------------------------------------------
# TABLA DE MISIONES
# ---------------------------------------------------------

st.divider()

st.subheader("Misiones de transporte")


# Creamos una lista con la información de cada misión
# generada automáticamente por el GestorFlota.
datos_misiones = []

for mision in gestor.misiones:

    datos_misiones.append(
        {
            "Misión": mision.id_mision,
            "AGV asignado": mision.agv.id_agv,
            "Tarea WMS": mision.solicitud.id_tarea_wms,
            "Pallet": mision.solicitud.id_pallet,
            "Origen": mision.solicitud.origen,
            "Destino": mision.solicitud.destino,
            "Estado": mision.estado.value
        }
    )


# Si ya existen misiones, mostramos su información.
if datos_misiones:

    st.dataframe(
        datos_misiones,
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "Todavía no existen misiones generadas."
    )

def mostrar_dashboard_prototipo():

    st.divider()

    st.markdown("## 📊 Monitoreo operativo")
    st.caption("Prototipo visual del rendimiento de la flota durante el turno.")

    # ---------------------------------------------------------
    # DATOS FICTICIOS
    # ---------------------------------------------------------

    pallets_transportados = 148
    peso_transportado = 112400
    pallets_por_hora = 18.5

    tiempo_promedio_mision = 4.2
    distancia_total = 3.8
    movimientos_vacios = 12

    bateria_agv = 76
    misiones_agv = 31
    utilizacion_agv = 82


    # ---------------------------------------------------------
    # INDICADORES DEL TURNO
    # ---------------------------------------------------------

    st.markdown("### Indicadores del turno")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "📦 Pallets transportados",
            pallets_transportados
        )

    with col2:
        st.metric(
            "⚖️ Peso movilizado",
            f"{peso_transportado:,} kg"
        )

    with col3:
        st.metric(
            "⏱️ Pallets por hora",
            pallets_por_hora
        )


    col4, col5, col6 = st.columns(3)

    with col4:
        st.metric(
            "Tiempo promedio por misión",
            f"{tiempo_promedio_mision} min"
        )

    with col5:
        st.metric(
            "Distancia recorrida",
            f"{distancia_total} km"
        )

    with col6:
        st.metric(
            "Movimientos vacíos",
            f"{movimientos_vacios} %"
        )


    # ---------------------------------------------------------
    # ESTADO DEL AGV
    # ---------------------------------------------------------

    st.markdown("### 🚚 Estado de la flota")

    with st.container(border=True):

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("#### AGV-01")
            st.write("**Estado:** TRANSPORTANDO")
            st.write("**Ubicación:** LINEA_2")
            st.write("**Misión actual:** M-031")

        with col2:
            st.metric(
                "🔋 Batería",
                f"{bateria_agv} %"
            )

            st.progress(bateria_agv)

        with col3:
            st.metric(
                "Misiones realizadas",
                misiones_agv
            )

            st.metric(
                "Utilización",
                f"{utilizacion_agv} %"
            )


    # ---------------------------------------------------------
    # SOLICITUDES
    # ---------------------------------------------------------

    st.markdown("### 📋 Solicitudes de traslado")

    solicitudes = [
        {
            "ID": "S-031",
            "Origen": "LINEA_1",
            "Destino": "ALMACEN",
            "Estado": "COMPLETADA",
            "AGV": "AGV-01"
        },
        {
            "ID": "S-032",
            "Origen": "ALMACEN",
            "Destino": "LINEA_2",
            "Estado": "EN PROCESO",
            "AGV": "AGV-01"
        },
        {
            "ID": "S-033",
            "Origen": "LINEA_3",
            "Destino": "ALMACEN",
            "Estado": "PENDIENTE",
            "AGV": "-"
        }
    ]

    st.dataframe(
        solicitudes,
        use_container_width=True,
        hide_index=True
    )


    # ---------------------------------------------------------
    # RESUMEN
    # ---------------------------------------------------------

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("✅ Atendidas", "31")

    with col2:
        st.metric("⏳ Pendientes", "2")

    with col3:
        st.metric("🔄 En proceso", "1")

mostrar_dashboard_prototipo()