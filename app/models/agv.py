from enum import Enum
from app.models.bateria import AUTONOMIA_HORAS, VELOCIDAD_REFERENCIA_MS, RESERVA_PCT, MODELO_BATERIA


class EstadoAGV(str, Enum):
    DISPONIBLE = "DISPONIBLE"
    ASIGNADO = "ASIGNADO"
    TRANSPORTANDO = "TRANSPORTANDO"
    CARGANDO = "CARGANDO"
    FUERA_DE_SERVICIO = "FUERA_DE_SERVICIO"


class AGV:

    CAPACIDAD_MAXIMA_KG = 1000
    AUTONOMIA_HORAS = AUTONOMIA_HORAS
    VELOCIDAD_REFERENCIA_MS = VELOCIDAD_REFERENCIA_MS

    RESERVA_BATERIA = RESERVA_PCT
    UMBRAL_RECARGA = RESERVA_PCT

    def __init__(self, id_agv, bateria, ubicacion):
        self.id_agv = id_agv
        self.bateria = bateria
        self.ubicacion = ubicacion

        self.estado = EstadoAGV.DISPONIBLE
        self.mision_actual = None

        # Guarda el momento en que el AGV comienza a cargarse.
        # Nos permitirá simular automáticamente el tiempo de recarga.
        self.hora_inicio_recarga = None

        self.actualizar_estado_bateria()

    def puede_transportar(self, peso_pallet):
        return peso_pallet <= self.CAPACIDAD_MAXIMA_KG

    def esta_disponible(self):
        return self.estado == EstadoAGV.DISPONIBLE

    def calcular_tiempo_recorrido(self, distancia):
        return distancia / self.VELOCIDAD_REFERENCIA_MS

    def calcular_consumo_bateria(self, distancia):
        tiempo_segundos = self.calcular_tiempo_recorrido(distancia)

        return MODELO_BATERIA.consumo(tiempo_segundos)

    def puede_completar_mision(self, distancia):
        consumo = self.calcular_consumo_bateria(distancia)

        bateria_final = self.bateria - consumo

        return bateria_final >= self.RESERVA_BATERIA

    def consumir_bateria(self, distancia):
        consumo = self.calcular_consumo_bateria(distancia)

        self.bateria -= consumo

        if self.bateria < 0:
            self.bateria = 0

        self.actualizar_estado_bateria()

    def necesita_recarga(self):
        return self.bateria <= self.UMBRAL_RECARGA

    def recargar(self):
        self.bateria = 100
        self.actualizar_estado_bateria()

    def actualizar_estado_bateria(self):

        if self.necesita_recarga() and self.mision_actual is None:
            self.estado = EstadoAGV.CARGANDO

        elif (
            self.estado == EstadoAGV.CARGANDO
            and not self.necesita_recarga()
        ):
            self.estado = EstadoAGV.DISPONIBLE

    def __str__(self):
        return (
            f"AGV {self.id_agv} | "
            f"Estado: {self.estado.value} | "
            f"Batería: {self.bateria:.2f}% | "
            f"Ubicación: {self.ubicacion}"
        )
