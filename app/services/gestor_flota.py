from datetime import datetime
from pathlib import Path
import heapq
import json

from app.models.agv import EstadoAGV
from app.models.solicitud import EstadoSolicitud, PrioridadSolicitud
from app.models.mision import Mision
from app.services.flexsim_cliente import FlexSimCliente


class GestorFlota:
    MAPEO_UBICACIONES = {
        "ALMACEN": "ControlPoint7",

        "TRANSIT_4": "ControlPoint7",
        "TRANSIT_3": "ControlPoint8",
        "TRANSIT_2": "ControlPoint11",
        "TRANSIT_1": "ControlPoint13",

        "COOKIE_1": "ControlPoint26",
        "COOKIE_2": "ControlPoint25",
        "COOKIE_3": "ControlPoint24",

        "CHOCOLATE": "ControlPoint18",

        "WAFER": "ControlPoint15",
    }

    MAPEO_ESTACIONES = {
        "ALMACEN": "pallet_transit4",

        "COOKIE_1": "fin_linea_cookie_1",
        "COOKIE_2": "fin_linea_cookie_2",
        "COOKIE_3": "fin_linea_cookie_3",

        "CHOCOLATE": "fin_linea_chocolate",

        "WAFER": "fin_linea_wafer",
    }

    MAPEO_AGVS = {
        "AGV_01": "agv_01",
        "AGV_02": "agv_02",
        "AGV_03": "agv_03",
    }

    def __init__(self):
        self.agvs = []
        self.solicitudes = []
        self.misiones = []
        self.grafo = {}
        self.flexsim = FlexSimCliente()

        self.construir_red()

    # ---------------------------------------------------------
    # RED / GRAFO
    # ---------------------------------------------------------

    def construir_red(self):
        ruta = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "red_agv_grafo_actualizado.json"
        )

        if not ruta.exists():
            raise FileNotFoundError(
                "Falta data/red_agv_grafo_actualizado.json"
            )

        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)

        for nodo in datos["nodos"]:
            self.grafo[nodo["id"]] = []

        for arista in datos["aristas"]:
            origen = arista["origen"]
            destino = arista["destino"]
            distancia = float(arista["distancia_m"])

            self.grafo[origen].append(
                (destino, distancia)
            )

            if arista["bidireccional"]:
                self.grafo[destino].append(
                    (origen, distancia)
                )

    def resolver_nodo(self, ubicacion):
        if ubicacion in self.grafo:
            return ubicacion

        if ubicacion in self.MAPEO_UBICACIONES:
            return self.MAPEO_UBICACIONES[ubicacion]

        raise ValueError(
            f"No existe mapeo para {ubicacion}"
        )

    def resolver_agv_flexsim(self, id_agv):
        if id_agv not in self.MAPEO_AGVS:
            raise ValueError(
                f"{id_agv} no existe fisicamente en FlexSim"
            )

        return self.MAPEO_AGVS[id_agv]

    # ---------------------------------------------------------
    # REGISTRO
    # ---------------------------------------------------------

    def registrar_agv(self, agv):
        self.agvs.append(agv)

    def registrar_solicitud(self, solicitud):
        self.solicitudes.append(solicitud)

    # ---------------------------------------------------------
    # PRIORIDAD DE SOLICITUDES
    # ---------------------------------------------------------

    def calcular_score_solicitud(self, solicitud):
        puntos = {
            PrioridadSolicitud.BAJA: 0,
            PrioridadSolicitud.NORMAL: 10,
            PrioridadSolicitud.ALTA: 20,
        }

        minutos = (
            datetime.now() - solicitud.fecha_creacion
        ).total_seconds() / 60

        return puntos[solicitud.prioridad] + minutos

    # ---------------------------------------------------------
    # DIJKSTRA
    # ---------------------------------------------------------

    def obtener_ruta(self, origen, destino):
        origen = self.resolver_nodo(origen)
        destino = self.resolver_nodo(destino)

        distancias = {
            nodo: float("inf")
            for nodo in self.grafo
        }

        anteriores = {
            nodo: None
            for nodo in self.grafo
        }

        distancias[origen] = 0

        pendientes = [
            (0, origen)
        ]

        while pendientes:
            distancia_actual, nodo_actual = heapq.heappop(
                pendientes
            )

            if distancia_actual > distancias[nodo_actual]:
                continue

            if nodo_actual == destino:
                break

            for vecino, distancia in self.grafo[nodo_actual]:
                nueva_distancia = (
                    distancia_actual + distancia
                )

                if nueva_distancia < distancias[vecino]:
                    distancias[vecino] = nueva_distancia
                    anteriores[vecino] = nodo_actual

                    heapq.heappush(
                        pendientes,
                        (nueva_distancia, vecino)
                    )

        if distancias[destino] == float("inf"):
            raise ValueError(
                f"No existe ruta entre {origen} y {destino}"
            )

        ruta = []
        actual = destino

        while actual is not None:
            ruta.append(actual)
            actual = anteriores[actual]

        ruta.reverse()

        return ruta, distancias[destino]

    def obtener_distancia(self, origen, destino):
        return self.obtener_ruta(
            origen,
            destino
        )[1]

    # ---------------------------------------------------------
    # DISTANCIA DE MISIÓN
    # ---------------------------------------------------------

    def calcular_distancia_mision(
        self,
        agv,
        solicitud
    ):
        distancia_agv_origen = self.obtener_distancia(
            agv.ubicacion,
            solicitud.origen
        )

        distancia_origen_destino = self.obtener_distancia(
            solicitud.origen,
            solicitud.destino
        )

        return (
            distancia_agv_origen
            + distancia_origen_destino
        )

    # ---------------------------------------------------------
    # SELECCIÓN DEL MEJOR AGV
    # ---------------------------------------------------------

    def calcular_score_agv(
        self,
        agv,
        solicitud
    ):
        distancia = self.calcular_distancia_mision(
            agv,
            solicitud
        )

        penalizacion_bateria = (
            100 - agv.bateria
        ) * 0.1

        return (
            distancia
            + penalizacion_bateria
        )

    def buscar_mejor_agv(
        self,
        solicitud
    ):
        mejor_agv = None
        mejor_score = None

        for agv in self.agvs:

            # Solo AGV disponibles.
            if not agv.esta_disponible():
                continue

            # Debe existir físicamente en FlexSim.
            if agv.id_agv not in self.MAPEO_AGVS:
                continue

            # Debe soportar el peso del pallet.
            if not agv.puede_transportar(
                solicitud.peso
            ):
                continue

            # Comprobamos que realmente exista una ruta.
            try:
                distancia = self.calcular_distancia_mision(
                    agv,
                    solicitud
                )

            except ValueError:
                # Este AGV no puede realizar esta misión
                # debido a la dirección de la red.
                continue

            # Comprobamos autonomía/batería.
            if not agv.puede_completar_mision(
                distancia
            ):
                continue

            penalizacion_bateria = (
                100 - agv.bateria
            ) * 0.1

            score = (
                distancia
                + penalizacion_bateria
            )

            if (
                mejor_score is None
                or score < mejor_score
            ):
                mejor_score = score
                mejor_agv = agv

        return mejor_agv

    # ---------------------------------------------------------
    # ASIGNACIÓN DE SOLICITUDES
    # ---------------------------------------------------------

    def asignar_solicitud(
        self,
        solicitud
    ):
        if (
            solicitud.estado
            != EstadoSolicitud.PENDIENTE
        ):
            return None

        agv = self.buscar_mejor_agv(
            solicitud
        )

        if agv is None:
            return None

        mision = Mision(
            id_mision=(
                f"M-{len(self.misiones) + 1:03d}"
            ),
            solicitud=solicitud,
            agv=agv,
        )

        solicitud.estado = (
            EstadoSolicitud.ASIGNADA
        )

        agv.estado = (
            EstadoAGV.ASIGNADO
        )

        agv.mision_actual = mision

        self.misiones.append(
            mision
        )

        return mision

    # ---------------------------------------------------------
    # COLA DE SOLICITUDES
    # ---------------------------------------------------------

    def obtener_solicitudes_pendientes_ordenadas(
        self
    ):
        pendientes = [
            solicitud
            for solicitud in self.solicitudes
            if solicitud.estado
            == EstadoSolicitud.PENDIENTE
        ]

        pendientes.sort(
            key=self.calcular_score_solicitud,
            reverse=True
        )

        return pendientes

    # ---------------------------------------------------------
    # BÚSQUEDA DE MISIÓN
    # ---------------------------------------------------------

    def buscar_mision(
        self,
        id_mision
    ):
        for mision in self.misiones:
            if mision.id_mision == id_mision:
                return mision

        return None

    # ---------------------------------------------------------
    # INICIAR MISIÓN EN FLEXSIM
    # ---------------------------------------------------------

    def iniciar_mision(
        self,
        id_mision
    ):
        mision = self.buscar_mision(
            id_mision
        )

        if mision is None:
            return None

        agv_flexsim = self.resolver_agv_flexsim(
            mision.agv.id_agv
        )

        origen = self.resolver_nodo(
            mision.solicitud.origen
        )

        destino = self.resolver_nodo(
            mision.solicitud.destino
        )

        estacion_origen = self.MAPEO_ESTACIONES[
            mision.solicitud.origen
        ]

        estacion_destino = self.MAPEO_ESTACIONES[
            mision.solicitud.destino
        ]

        try:
            respuesta = self.flexsim.ejecutar_mision(
                agv_flexsim,
                origen,
                destino,
                mision.solicitud.id_pallet,
                estacion_origen,
                estacion_destino,
            )

        except OSError:
            mision.solicitud.estado = (
                EstadoSolicitud.PENDIENTE
            )

            mision.agv.estado = (
            EstadoAGV.DISPONIBLE
            )

            mision.agv.mision_actual = None

            self.misiones.remove(
                mision
            )

            raise

        if not respuesta.startswith("OK"):
            mision.solicitud.estado = (
                EstadoSolicitud.PENDIENTE
            )

            mision.agv.estado = (
                EstadoAGV.DISPONIBLE
            )

            mision.agv.mision_actual = None

            self.misiones.remove(
                mision
            )

            raise RuntimeError(
                f"FlexSim rechazo la mision: {respuesta}"
            )

        mision.iniciar()

        return mision

    # ---------------------------------------------------------
    # CONSULTAR ESTADO REAL EN FLEXSIM
    # ---------------------------------------------------------

    def actualizar_misiones_flexsim(
        self
    ):
        hubo_cambios = False

        for mision in list(
            self.misiones
        ):

            if (
                mision.estado.value
                != "EN_PROCESO"
            ):
                continue

            try:
                respuesta = self.flexsim.obtener_estado(
                    self.resolver_agv_flexsim(
                        mision.agv.id_agv
                    )
                )

            except OSError:
                continue

            if respuesta == "OK|LIBRE":

                resultado = self.completar_mision(
                    mision.id_mision
                )

                if resultado is None:
                    continue

                _, nuevas_misiones = resultado

                for nueva_mision in nuevas_misiones:
                    self.iniciar_mision(
                        nueva_mision.id_mision
                    )

                hubo_cambios = True

        return hubo_cambios

    # ---------------------------------------------------------
    # COMPLETAR MISIÓN
    # ---------------------------------------------------------

    def completar_mision(
        self,
        id_mision
    ):
        mision = self.buscar_mision(
            id_mision
        )

        if mision is None:
            return None

        # Calculamos la distancia antes de cambiar
        # la ubicación del AGV al destino.
        distancia = self.calcular_distancia_mision(
            mision.agv,
            mision.solicitud,
        )

        mision.completar()

        mision.agv.consumir_bateria(
            distancia
        )

        if mision.agv.necesita_recarga():
            mision.agv.estado = (
                EstadoAGV.CARGANDO
            )

            mision.agv.hora_inicio_recarga = (
                datetime.now()
            )

        nuevas_misiones = (
            self.procesar_solicitudes_pendientes()
        )

        return (
            mision,
            nuevas_misiones
        )

    # ---------------------------------------------------------
    # PROCESAR SOLICITUDES PENDIENTES
    # ---------------------------------------------------------

    def procesar_solicitudes_pendientes(
        self
    ):
        creadas = []

        solicitudes = (
            self.obtener_solicitudes_pendientes_ordenadas()
        )

        for solicitud in solicitudes:

            mision = self.asignar_solicitud(
                solicitud
            )

            if mision is not None:
                creadas.append(
                    mision
                )

        return creadas

    # ---------------------------------------------------------
    # RECARGA
    # ---------------------------------------------------------

    def finalizar_recarga(
        self,
        id_agv
    ):
        for agv in self.agvs:

            if agv.id_agv != id_agv:
                continue

            if agv.estado != EstadoAGV.CARGANDO:
                raise ValueError(
                    f"El AGV {id_agv} no esta cargando"
                )

            agv.recargar()
            agv.hora_inicio_recarga = None

            nuevas_misiones = (
                self.procesar_solicitudes_pendientes()
            )

            return (
                agv,
                nuevas_misiones
            )

        raise ValueError(
            f"No existe el AGV {id_agv}"
        )