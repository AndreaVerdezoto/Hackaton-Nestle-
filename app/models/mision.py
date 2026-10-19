from enum import Enum

from app.models.agv import EstadoAGV
from app.models.solicitud import EstadoSolicitud


class EstadoMision(str, Enum):
    CREADA = "CREADA"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADA = "COMPLETADA"
    FALLIDA = "FALLIDA"


class Mision:
    """Representa una misión asignada a un AGV dentro del simulador."""

    def __init__(self, id_mision, solicitud, agv):
        self.id_mision = id_mision
        self.solicitud = solicitud
        self.agv = agv
        self.estado = EstadoMision.CREADA

        # Datos calculados por el reloj lógico del simulador.
        self.numero = id_mision
        self.tipo = None
        self.linea = None
        self.id_ciclo = None
        self.llegada_s = None
        self.inicio_s = None
        self.fin_s = None
        self.vacio = None
        self.cargado = None
        self.carga_s = 0.0
        self.descarga_s = 0.0
        self.duracion_servicio_s = None
        self.bateria_inicio = None
        self.bateria_fin = None
        self.espera_s = None
        self.ciclo_movimiento_s = None

    @property
    def pallet(self):
        return self.solicitud.pallet

    @property
    def id_pallet(self):
        return self.pallet.id_pallet

    @property
    def origen(self):
        return self.solicitud.origen

    @property
    def destino(self):
        return self.solicitud.destino

    @property
    def id_agv(self):
        return self.agv.id_agv

    def iniciar_simulacion(
        self,
        *,
        numero,
        tipo,
        linea,
        id_ciclo,
        llegada_s,
        inicio_s,
        fin_s,
        vacio,
        cargado,
        carga_s,
        descarga_s,
        duracion_servicio_s,
    ):
        self.numero = numero
        self.tipo = tipo
        self.linea = linea
        self.id_ciclo = id_ciclo
        self.llegada_s = llegada_s
        self.inicio_s = inicio_s
        self.fin_s = fin_s
        self.vacio = vacio
        self.cargado = cargado
        self.carga_s = carga_s
        self.descarga_s = descarga_s
        self.duracion_servicio_s = duracion_servicio_s

        self.estado = EstadoMision.EN_PROCESO
        self.solicitud.estado = EstadoSolicitud.EN_PROCESO
        self.agv.estado = EstadoAGV.TRANSPORTANDO
        self.agv.mision_actual = self

    def completar_simulacion(self, fin_s=None):
        if fin_s is not None:
            self.fin_s = fin_s
        self.estado = EstadoMision.COMPLETADA
        self.solicitud.estado = EstadoSolicitud.COMPLETADA
        self.agv.ubicacion = self.destino
        self.pallet.mover_a(self.destino)
        self.agv.estado = EstadoAGV.DISPONIBLE
        self.agv.mision_actual = None

    def calcular_metricas_simulacion(self):
        self.espera_s = self.inicio_s - self.llegada_s
        self.ciclo_movimiento_s = self.fin_s - self.llegada_s

    def a_dict_simulacion(self):
        """Serializa la misión con el contrato consumido por UI, KPIs y JSON."""
        datos = {
            "numero": self.numero,
            "id_pallet": self.id_pallet,
            "id_mision": self.id_mision,
            "id_ciclo": self.id_ciclo,
            "tipo": self.tipo,
            "linea": self.linea,
            "agv": self.id_agv,
            "origen": self.origen,
            "destino": self.destino,
            "llegada_s": self.llegada_s,
            "inicio_s": self.inicio_s,
            "fin_s": self.fin_s,
            "vacio": self.vacio,
            "cargado": self.cargado,
            "carga_s": self.carga_s,
            "descarga_s": self.descarga_s,
            "duracion_servicio_s": self.duracion_servicio_s,
        }
        if self.bateria_inicio is not None:
            datos["bateria_inicio"] = self.bateria_inicio
            datos["bateria_fin"] = self.bateria_fin
        if self.espera_s is not None:
            datos["espera_s"] = self.espera_s
            datos["ciclo_movimiento_s"] = self.ciclo_movimiento_s
        return datos

    def __str__(self):
        return (
            f"Misión {self.id_mision} | "
            f"{self.agv.id_agv} | "
            f"{self.solicitud.origen} -> "
            f"{self.solicitud.destino} | "
            f"{self.estado.value}"
        )
