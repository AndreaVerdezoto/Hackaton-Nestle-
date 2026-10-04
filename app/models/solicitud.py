from enum import Enum
from datetime import datetime

from app.models.pallet import Pallet


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
        prioridad=PrioridadSolicitud.NORMAL,
        id_ciclo=None,
        pallet=None,
    ):
        peso_pallet = pallet.peso if pallet is not None else peso
        if peso_pallet <= 0:
            raise ValueError("El peso del pallet debe ser mayor que 0.")

        if peso_pallet > self.PESO_MAXIMO_PALLET:
            raise ValueError(
                f"El pallet supera el peso máximo permitido de "
                f"{self.PESO_MAXIMO_PALLET} kg."
            )

        self.id_tarea_wms = id_tarea_wms
        self.pallet = pallet or Pallet(
            id_pallet=id_pallet,
            producto=producto,
            lote=None,
            cantidad_cajas=None,
            peso=peso,
            altura=None,
            ubicacion=origen,
        )
        self.origen = origen
        self.destino = destino
        self.prioridad = prioridad
        self.id_ciclo = id_ciclo
        self.estado = EstadoSolicitud.PENDIENTE
        self.fecha_creacion = datetime.now()

    @property
    def id_pallet(self):
        return self.pallet.id_pallet

    @property
    def producto(self):
        return self.pallet.producto

    @property
    def peso(self):
        return self.pallet.peso

    def __str__(self):
        return (
            f"Solicitud {self.id_tarea_wms} | "
            f"Pallet {self.id_pallet} | "
            f"{self.origen} -> {self.destino} | "
            f"{self.estado.value}"
        )
