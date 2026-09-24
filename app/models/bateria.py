"""Única ley temporal de batería del prototipo; porcentajes y segundos simulados."""
from dataclasses import dataclass
import math

VELOCIDAD_REFERENCIA_MS = 1.0
AUTONOMIA_HORAS = 8.0
CARGA_COMPLETA_HORAS = 3.0
RESERVA_PCT = 20.0  # Regla del prototipo, no requisito del fabricante.
CARGA_PALLET_S = 30.0
DESCARGA_PALLET_S = 30.0
CARGADORES = ("ControlPoint31", "ControlPoint28", "ControlPoint32", "ControlPoint30", "ControlPoint29")


@dataclass(frozen=True)
class ModeloBateria:
    autonomia_s: float = AUTONOMIA_HORAS * 3600
    carga_completa_s: float = CARGA_COMPLETA_HORAS * 3600
    reserva_pct: float = RESERVA_PCT

    def __post_init__(self):
        if (not all(math.isfinite(v) for v in (self.autonomia_s, self.carga_completa_s, self.reserva_pct))
                or self.autonomia_s <= 0 or self.carga_completa_s <= 0 or not 0 <= self.reserva_pct < 100):
            raise ValueError("Parámetros de batería inválidos.")

    def consumo(self, segundos):
        return max(0.0, segundos) * 100 / self.autonomia_s

    def nivel(self, inicial, segundos, cargando=False):
        cambio = max(0.0, segundos) * 100 / self.carga_completa_s if cargando else -self.consumo(segundos)
        return min(100.0, max(0.0, inicial + cambio))

    def uso_restante_s(self, bateria):
        return max(0.0, min(100.0, bateria) - self.reserva_pct) * self.autonomia_s / 100

    def carga_restante_s(self, bateria):
        return (100 - min(100.0, max(0.0, bateria))) * self.carga_completa_s / 100

    def admite_mision(self, bateria, servicio_s):
        return bateria - self.consumo(servicio_s) >= self.reserva_pct - 1e-9


MODELO_BATERIA = ModeloBateria()
