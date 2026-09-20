from datetime import datetime
import heapq

from app.models.agv import EstadoAGV
from app.models.solicitud import EstadoSolicitud, PrioridadSolicitud
from app.models.mision import Mision


class GestorFlota:

    def __init__(self):
        self.agvs = []
        self.solicitudes = []
        self.misiones = []

        self.grafo = {}

        self.construir_red()
        self.cargadores = ["CARGADOR_COOKIES","CARGADOR_ALMACEN","CARGADOR_CHOCOLATE","CARGADOR_WAFER"]

    def agregar_conexion(self, origen, destino, distancia):
        if origen not in self.grafo:
            self.grafo[origen] = []

        if destino not in self.grafo:
            self.grafo[destino] = []

        self.grafo[origen].append(
            (destino, distancia)
        )

        self.grafo[destino].append(
            (origen, distancia)
        )

    def construir_red(self):
        # Zona de almacenamiento y corredor principal
        self.agregar_conexion(
            "ALMACEN",
            "TRANSIT_4",
            5
        )

        self.agregar_conexion(
            "TRANSIT_4",
            "TRANSIT_3",
            6
        )

        self.agregar_conexion(
            "TRANSIT_3",
            "TRANSIT_2",
            6
        )

        self.agregar_conexion(
            "TRANSIT_2",
            "TRANSIT_1",
            6
        )

        # Líneas de producción
        self.agregar_conexion(
            "TRANSIT_1",
            "LINEA_1",
            10
        )

        self.agregar_conexion(
            "TRANSIT_2",
            "LINEA_2",
            8
        )

        self.agregar_conexion(
            "TRANSIT_3",
            "LINEA_3",
            8
        )

        # Cargadores

        self.agregar_conexion(
            "LINEA_1",
            "CARGADOR_COOKIES",
            3
        )

        self.agregar_conexion(
            "TRANSIT_1",
            "CARGADOR_ALMACEN",
            3
        )

        self.agregar_conexion(
            "LINEA_2",
            "CARGADOR_CHOCOLATE",
            3
        )

        self.agregar_conexion(
            "LINEA_3",
            "CARGADOR_WAFER",
            3
        )


    def registrar_agv(self, agv):
        self.agvs.append(agv)


    def registrar_solicitud(self, solicitud):
        self.solicitudes.append(solicitud)

    def calcular_score_solicitud(self, solicitud):

        puntos_prioridad = {
        PrioridadSolicitud.BAJA: 0,
        PrioridadSolicitud.NORMAL: 10,
        PrioridadSolicitud.ALTA: 20
        }

        tiempo_espera = datetime.now() - solicitud.fecha_creacion

        minutos_espera = tiempo_espera.total_seconds() / 60

        score = (
        puntos_prioridad[solicitud.prioridad]
        + minutos_espera
    )

        return score

    #Logica del algoritmo de dijstrak
    def obtener_distancia(self, origen, destino):

        if origen not in self.grafo:
            raise ValueError(
                f"La ubicación {origen} no existe en la red."
            )

        if destino not in self.grafo:
            raise ValueError(
                f"La ubicación {destino} no existe en la red."
            )

        if origen == destino:
            return 0

        distancias = {
            nodo: float("inf")
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

            if nodo_actual == destino:
                return distancia_actual

            if distancia_actual > distancias[nodo_actual]:
                continue

            for vecino, distancia in self.grafo[nodo_actual]:

                nueva_distancia = (
                    distancia_actual
                    + distancia
                )

                if nueva_distancia < distancias[vecino]:

                    distancias[vecino] = nueva_distancia

                    heapq.heappush(
                        pendientes,
                        (nueva_distancia, vecino)
                    )

        raise ValueError(
            f"No existe una ruta entre {origen} y {destino}."
        )

    def calcular_score_agv(self, agv, solicitud):

        distancia_mision = self.calcular_distancia_mision(
            agv,
            solicitud
        )

        penalizacion_bateria = (
            100 - agv.bateria
        ) * 0.1

        score = (
            distancia_mision
            + penalizacion_bateria
        )

        return score


    def buscar_mejor_agv(self, solicitud):

        mejor_agv = None
        mejor_score = None

        for agv in self.agvs:

            # 1. El AGV debe estar disponible
            if not agv.esta_disponible():
                continue

            # 2. Debe soportar el peso del pallet
            if not agv.puede_transportar(solicitud.peso):
                continue

            # 3. Calculamos la distancia TOTAL de la misión
            distancia_mision = self.calcular_distancia_mision(
                agv,
                solicitud
            )

            # 4. Verificamos si puede completar esa misión
            # y terminar con al menos 20% de batería
            if not agv.puede_completar_mision(distancia_mision):
                continue

            # 5. Calculamos qué tan conveniente es usar este AGV
            score = self.calcular_score_agv(
                agv,
                solicitud
            )

            if mejor_score is None or score < mejor_score:
                mejor_score = score
                mejor_agv = agv

        return mejor_agv


    def asignar_solicitud(self, solicitud):

        if solicitud.estado != EstadoSolicitud.PENDIENTE:
            return None

        agv = self.buscar_mejor_agv(solicitud)

        if agv is None:
            return None

        id_mision = f"M-{len(self.misiones) + 1:03d}"

        nueva_mision = Mision(
            id_mision=id_mision,
            solicitud=solicitud,
            agv=agv
        )

        solicitud.estado = EstadoSolicitud.ASIGNADA

        agv.estado = EstadoAGV.ASIGNADO
        agv.mision_actual = nueva_mision

        self.misiones.append(nueva_mision)

        return nueva_mision

    def obtener_solicitudes_pendientes_ordenadas(self):
        solicitudes_pendientes = []

        for solicitud in self.solicitudes:
            if solicitud.estado == EstadoSolicitud.PENDIENTE:
                solicitudes_pendientes.append(solicitud)

        solicitudes_pendientes.sort(
        key=self.calcular_score_solicitud,
        reverse=True
    )

        return solicitudes_pendientes

    def buscar_mision(self, id_mision):

        for mision in self.misiones:

            if mision.id_mision == id_mision:
                return mision

        return None


    def iniciar_mision(self, id_mision):

        mision = self.buscar_mision(id_mision)

        if mision is None:
            return None

        mision.iniciar()

        return mision


    def completar_mision(self, id_mision):

        mision = self.buscar_mision(id_mision)

        if mision is None:
            return None

        # Calculamos la distancia antes de completar la misión,s
        # porque todavía conocemos la ubicación inicial del AGV.
        distancia_mision = self.calcular_distancia_mision(
            mision.agv,
            mision.solicitud
        )

        # La misión actualiza estados y ubicación.
        mision.completar()

        # Descontamos la batería consumida durante el recorrido.
        mision.agv.consumir_bateria(
            distancia_mision
        )
        if mision.agv.necesita_recarga():
            self.enviar_agv_a_cargador(mision.agv)

        # Intentamos asignar las solicitudes que siguen pendientes.
        nuevas_misiones = self.procesar_solicitudes_pendientes()

        return mision, nuevas_misiones


    def procesar_solicitudes_pendientes(self):

        misiones_creadas = []

        solicitudes_ordenadas = (
            self.obtener_solicitudes_pendientes_ordenadas()
        )

        for solicitud in solicitudes_ordenadas:

            mision = self.asignar_solicitud(solicitud)

            if mision is not None:
                misiones_creadas.append(mision)

        return misiones_creadas
    
    def calcular_distancia_mision(self, agv, solicitud):

        distancia_hasta_origen = self.obtener_distancia(
            agv.ubicacion,
            solicitud.origen
        )

        distancia_traslado = self.obtener_distancia(
            solicitud.origen,
            solicitud.destino
        )

        distancia_total = (
            distancia_hasta_origen
            + distancia_traslado
        )

        return distancia_total

    def buscar_cargador_mas_cercano(self, agv):
        cargador_mas_cercano = None
        menor_distancia = float("inf")

        for cargador in self.cargadores:

            distancia = self.obtener_distancia(
                agv.ubicacion,
                cargador
            )

            if distancia < menor_distancia:
                menor_distancia = distancia
                cargador_mas_cercano = cargador

        return cargador_mas_cercano, menor_distancia

    def enviar_agv_a_cargador(self, agv):

        cargador, distancia = self.buscar_cargador_mas_cercano(
            agv
        )

        # El AGV consume batería durante el trayecto
        # desde su ubicación actual hasta el cargador.
        agv.consumir_bateria(
            distancia
        )

        # Actualizamos su ubicación al cargador seleccionado.
        agv.ubicacion = cargador

        # El AGV entra en estado de carga.
        agv.estado = EstadoAGV.CARGANDO

        # Registramos cuándo comenzó la recarga.
        agv.hora_inicio_recarga = datetime.now()

        return cargador
    
    def finalizar_recarga(self, id_agv):
        for agv in self.agvs:
            if agv.id_agv == id_agv:
                if agv.estado != EstadoAGV.CARGANDO:
                    raise ValueError(
                        f"El AGV {id_agv} no está cargando."
                    )

                agv.recargar()
                # La recarga ya terminó, por lo que eliminamos
                # el registro del tiempo de inicio.
                agv.hora_inicio_recarga = None

                nuevas_misiones = (self.procesar_solicitudes_pendientes())
                return agv, nuevas_misiones

        raise ValueError(
            f"No existe el AGV {id_agv}."
        )

#Prueba del funcionamiento de Dijstra 
if __name__ == "__main__":
    gestor = GestorFlota()

    distancia = gestor.obtener_distancia(
        "ALMACEN",
        "LINEA_1"
    )

    print("Distancia calculada:", distancia)