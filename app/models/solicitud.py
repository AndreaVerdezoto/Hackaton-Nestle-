from enum import Enum
from datetime import datetime


class EstadoSolicitud(str, Enum):
    PENDIENTE = "PENDIENTE"
    ASIGNADA = "ASIGNADA"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADA = "COMPLETADA"
    CANCELADA = "CANCELADA"


class PrioridadSolicitud(str, Enum):
    BAJA = "BAJA"
    NORMAL = "NORMAL"
    ALTA = "ALTA"


class SolicitudTraslado:
    PESO_MAXIMO_PALLET = 800

    def __init__(
        self,
        id_tarea_wms,
        id_pallet,
        producto,
        peso,
        origen,
        destino,
        prioridad=PrioridadSolicitud.NORMAL
    ):
        if peso <= 0:
            raise ValueError("El peso del pallet debe ser mayor que 0.")

        if peso > self.PESO_MAXIMO_PALLET:
            raise ValueError(
                f"El pallet supera el peso máximo permitido de "
                f"{self.PESO_MAXIMO_PALLET} kg."
            )
        
        self.id_tarea_wms = id_tarea_wms
        self.id_pallet = id_pallet
        self.producto = producto
        self.peso = peso
        self.origen = origen
        self.destino = destino
        self.prioridad = prioridad

        self.estado = EstadoSolicitud.PENDIENTE
        self.fecha_creacion = datetime.now()

    def __str__(self):
        return (
            f"Solicitud {self.id_tarea_wms} | "
            f"Pallet {self.id_pallet} | "
            f"{self.origen} -> {self.destino} | "
            f"{self.estado.value}"
        )