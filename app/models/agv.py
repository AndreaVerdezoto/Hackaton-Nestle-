from enum import Enum


class EstadoAGV(str, Enum):
    DISPONIBLE = "DISPONIBLE"
    ASIGNADO = "ASIGNADO"
    TRANSPORTANDO = "TRANSPORTANDO"
    CARGANDO = "CARGANDO"
    FUERA_DE_SERVICIO = "FUERA_DE_SERVICIO"


class AGV:
    """Representa el estado operativo de un vehículo de la flota."""

    CAPACIDAD_MAXIMA_KG = 1000

    def __init__(self, id_agv, bateria, ubicacion):
        self.id_agv = id_agv
        self.bateria = bateria
        self.ubicacion = ubicacion
        self.estado = EstadoAGV.DISPONIBLE
        self.mision_actual = None

    def puede_transportar(self, peso_pallet):
        return peso_pallet <= self.CAPACIDAD_MAXIMA_KG

    def esta_disponible(self):
        return self.estado == EstadoAGV.DISPONIBLE and self.mision_actual is None

    def __str__(self):
        return (
            f"AGV {self.id_agv} | "
            f"Estado: {self.estado.value} | "
            f"Batería: {self.bateria:.2f}% | "
            f"Ubicación: {self.ubicacion}"
        )
