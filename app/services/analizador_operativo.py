"""Analisis operativo de resultados ya producidos por SimuladorFlota.

No modifica el despacho ni ejecuta integraciones externas. Los umbrales por
defecto son parametros configurables del prototipo, no limites validados de
planta.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from app.models.bateria import RESERVA_PCT
from app.services.indicadores_capacidad import calcular_capacidad


@dataclass(frozen=True)
class UmbralesAnalizadorOperativo:
    backlog_elevado: float = 0.0
    espera_elevada_s: float = 60.0
    utilizacion_alta_pct: float = 85.0
    bateria_baja_pct: float = RESERVA_PCT
    desplazamiento_vacio_alto_pct: float = 50.0


class AnalizadorOperativo:
    def __init__(self, resultado, umbrales=None):
        if not isinstance(resultado, dict):
            raise TypeError("El resultado debe ser un diccionario generado por SimuladorFlota.")
        self.resultado = resultado
        self.umbrales = umbrales or UmbralesAnalizadorOperativo()

    def obtener_metricas(self):
        kpis = self._kpis()
        distancia_total = self._numero(kpis.get("distancia_total_m"))
        distancia_vacia = self._numero(kpis.get("distancia_vacia_m"))
        distancia_cargada = self._numero(kpis.get("distancia_cargada_m"))
        porcentaje_vacio = (
            100 * distancia_vacia / distancia_total
            if distancia_total and distancia_vacia is not None
            else None
        )
        niveles_bateria = self._niveles_bateria()
        return {
            "misiones_completadas": self._numero(kpis.get("completados_turno")),
            "solicitudes_pendientes_backlog": self._numero(
                kpis.get("solicitudes_pendientes_turno", kpis.get("backlog_corte"))
            ),
            "backlog_maximo": self._numero(kpis.get("backlog_maximo_agv", kpis.get("backlog_maximo"))),
            "tiempo_promedio_espera_s": self._numero(kpis.get("espera_media_s")),
            "tiempo_promedio_ciclo_s": self._numero(kpis.get("ciclo_medio_s")),
            "utilizacion_flota_pct": self._numero(kpis.get("utilizacion_media_pct")),
            "utilizacion_por_agv_pct": self._utilizacion_por_agv(),
            "distancia_total_m": distancia_total,
            "distancia_cargada_m": distancia_cargada,
            "distancia_vacia_m": distancia_vacia,
            "porcentaje_desplazamiento_vacio": porcentaje_vacio,
            "bateria_promedio_pct": (
                math.fsum(niveles_bateria) / len(niveles_bateria)
                if niveles_bateria
                else None
            ),
            "bateria_minima_pct": min(niveles_bateria) if niveles_bateria else None,
            "cantidad_recargas": self._cantidad_recargas(),
            "fallos_errores": self._fallos_errores(),
        }

    def metricas_no_disponibles(self):
        metricas = self.obtener_metricas()
        razones = {}
        if metricas["bateria_promedio_pct"] is None:
            razones["bateria_promedio_pct"] = (
                "El resultado no contiene bateria_inicio/bateria_fin en movimientos. "
                "Se obtiene solo con simular_bateria=True."
            )
        if metricas["bateria_minima_pct"] is None:
            razones["bateria_minima_pct"] = (
                "El resultado no contiene niveles de bateria por movimiento."
            )
        if metricas["cantidad_recargas"] is None:
            razones["cantidad_recargas"] = (
                "El resultado no contiene el campo recargas. Se obtiene solo con simular_bateria=True."
            )
        if metricas["fallos_errores"] is None:
            razones["fallos_errores"] = (
                "SimuladorFlota no serializa fallos en corridas exitosas; los errores se elevan como excepciones."
            )
        return razones

    def detectar_problemas(self):
        metricas = self.obtener_metricas()
        problemas = []
        self._agregar_si(
            problemas,
            metricas["solicitudes_pendientes_backlog"] is not None
            and metricas["solicitudes_pendientes_backlog"] > self.umbrales.backlog_elevado,
            "BACKLOG_ELEVADO",
            "ALTA",
            "Existen solicitudes pendientes al corte de la simulacion.",
            {
                "solicitudes_pendientes_backlog": metricas["solicitudes_pendientes_backlog"],
                "umbral_backlog_elevado": self.umbrales.backlog_elevado,
                "backlog_maximo": metricas["backlog_maximo"],
            },
        )
        self._agregar_si(
            problemas,
            metricas["tiempo_promedio_espera_s"] is not None
            and metricas["tiempo_promedio_espera_s"] > self.umbrales.espera_elevada_s,
            "ESPERA_ELEVADA",
            "MEDIA",
            "El tiempo promedio de espera supera el umbral configurable del prototipo.",
            {
                "tiempo_promedio_espera_s": metricas["tiempo_promedio_espera_s"],
                "umbral_espera_elevada_s": self.umbrales.espera_elevada_s,
            },
        )
        self._agregar_si(
            problemas,
            metricas["utilizacion_flota_pct"] is not None
            and metricas["utilizacion_flota_pct"] >= self.umbrales.utilizacion_alta_pct,
            "UTILIZACION_ALTA",
            "MEDIA",
            "La utilizacion promedio de la flota alcanza o supera el umbral configurable.",
            {
                "utilizacion_flota_pct": metricas["utilizacion_flota_pct"],
                "umbral_utilizacion_alta_pct": self.umbrales.utilizacion_alta_pct,
            },
        )
        self._agregar_si(
            problemas,
            metricas["bateria_minima_pct"] is not None
            and metricas["bateria_minima_pct"] <= self.umbrales.bateria_baja_pct,
            "BATERIA_BAJA",
            "ALTA",
            "Al menos un AGV registra bateria minima igual o inferior al umbral configurable.",
            {
                "bateria_minima_pct": metricas["bateria_minima_pct"],
                "umbral_bateria_baja_pct": self.umbrales.bateria_baja_pct,
                "bateria_promedio_pct": metricas["bateria_promedio_pct"],
            },
        )
        self._agregar_si(
            problemas,
            metricas["porcentaje_desplazamiento_vacio"] is not None
            and metricas["porcentaje_desplazamiento_vacio"] >= self.umbrales.desplazamiento_vacio_alto_pct,
            "DESPLAZAMIENTO_VACIO_ALTO",
            "MEDIA",
            "La proporcion de distancia recorrida sin carga supera el umbral configurable.",
            {
                "porcentaje_desplazamiento_vacio": metricas["porcentaje_desplazamiento_vacio"],
                "umbral_desplazamiento_vacio_alto_pct": self.umbrales.desplazamiento_vacio_alto_pct,
                "distancia_vacia_m": metricas["distancia_vacia_m"],
                "distancia_total_m": metricas["distancia_total_m"],
            },
        )
        if problemas:
            return problemas
        return [{
            "codigo": "SIN_PROBLEMAS",
            "severidad": "INFO",
            "descripcion": "No se detectaron problemas con las reglas configuradas del prototipo.",
            "metricas": {"umbrales": asdict(self.umbrales)},
        }]

    def _kpis(self):
        kpis = dict(self.resultado.get("kpis") or {})
        requeridos = {
            "capacidad_logistica",
            "espera_agv_media_pt_s",
            "espera_agv_maxima_pt_s",
            "backlog_maximo_agv",
        }
        if requeridos <= set(kpis):
            return kpis
        parametros = self.resultado.get("parametros") or {}
        movimientos = self.resultado.get("movimientos")
        eventos = self.resultado.get("eventos")
        cantidad_agv = self.resultado.get("numero_agv")
        turno_s = parametros.get("duracion_turno_s")
        if movimientos is not None and eventos is not None and turno_s is not None and cantidad_agv is not None:
            kpis.update(calcular_capacidad(movimientos, eventos, turno_s, cantidad_agv))
        return kpis

    def _utilizacion_por_agv(self):
        valores = {}
        for item in self.resultado.get("por_agv") or []:
            agv = item.get("agv")
            utilizacion = self._numero(item.get("utilizacion_pct"))
            if agv is not None and utilizacion is not None:
                valores[agv] = utilizacion
        return valores or None

    def _niveles_bateria(self):
        ultimos = {}
        for movimiento in self.resultado.get("movimientos") or []:
            if "bateria_fin" not in movimiento:
                continue
            agv = movimiento.get("agv")
            fin = self._numero(movimiento.get("fin_s"))
            nivel = self._numero(movimiento.get("bateria_fin"))
            if agv is None or fin is None or nivel is None:
                continue
            if agv not in ultimos or fin >= ultimos[agv][0]:
                ultimos[agv] = (fin, nivel)
        return [nivel for _, nivel in ultimos.values()]

    def _cantidad_recargas(self):
        recargas = self.resultado.get("recargas")
        if recargas is None:
            return None
        if isinstance(recargas, dict):
            return sum(len(items) for items in recargas.values())
        if isinstance(recargas, list):
            return len(recargas)
        return None

    def _fallos_errores(self):
        conocidos = []
        for campo in ("error", "errores", "fallos"):
            if campo not in self.resultado:
                continue
            valor = self.resultado.get(campo)
            if valor in (None, "", []):
                continue
            if isinstance(valor, list):
                conocidos.extend(valor)
            else:
                conocidos.append(valor)
        if self.resultado.get("estado") == "ERROR" and not conocidos:
            conocidos.append("Estado ERROR sin detalle registrado.")
        return conocidos if conocidos else None

    @staticmethod
    def _numero(valor):
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            return None
        return valor

    @staticmethod
    def _agregar_si(problemas, condicion, codigo, severidad, descripcion, metricas):
        if condicion:
            problemas.append({
                "codigo": codigo,
                "severidad": severidad,
                "descripcion": descripcion,
                "metricas": metricas,
            })
