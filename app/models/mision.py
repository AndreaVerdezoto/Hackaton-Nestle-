from enum import Enum
from datetime import datetime

from app.models.agv import EstadoAGV
from app.models.solicitud import EstadoSolicitud


class EstadoMision(str, Enum):
    CREADA = "CREADA"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADA = "COMPLETADA"
    FALLIDA = "FALLIDA"


class Mision:

    def __init__(
        self,
        id_mision,
        solicitud,
        agv
    ):
        self.id_mision = id_mision
        self.solicitud = solicitud
        self.agv = agv

        self.estado = EstadoMision.CREADA

        self.hora_asignacion = datetime.now()
        self.hora_inicio = None
        self.hora_fin = None


    def iniciar(self):
        self.estado = EstadoMision.EN_PROCESO
        self.hora_inicio = datetime.now()

        self.solicitud.estado = EstadoSolicitud.EN_PROCESO

        self.agv.estado = EstadoAGV.TRANSPORTANDO
        self.agv.mision_actual = self

    # Cuando el AGV llega al destino de la solicitud
    def completar(self):
        self.estado = EstadoMision.COMPLETADA
        self.hora_fin = datetime.now()

        self.solicitud.estado = EstadoSolicitud.COMPLETADA

        self.agv.ubicacion = self.solicitud.destino
        self.agv.estado = EstadoAGV.DISPONIBLE
        self.agv.mision_actual = None


    def __str__(self):
        return (
            f"Misión {self.id_mision} | "
            f"{self.agv.id_agv} | "
            f"{self.solicitud.origen} -> "
            f"{self.solicitud.destino} | "
            f"{self.estado.value}"
        )