"""Demanda y reloj Python. No ejecuta comandos TCP al importar este módulo."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import time
from uuid import uuid4

from app.models.agv import AGV, EstadoAGV
from app.models.solicitud import SolicitudTraslado, PrioridadSolicitud


DURACION_TURNO = 28_800
MOVIMIENTOS_TURNO = 215
FACTOR_ACELERACION = 1.0
PESO_PALLET_KG = 500
LINEAS = ("COOKIE_1", "COOKIE_2", "COOKIE_3", "CHOCOLATE", "WAFER")
# Se conservan los valores del prototipo. 04/05 requieren configuración explícita.
UBICACIONES_INICIALES = {
    "AGV_01": "TRANSIT_4", "AGV_02": "TRANSIT_2", "AGV_03": "TRANSIT_1",
    "AGV_04": None, "AGV_05": None,
}
BATERIAS_INICIALES = {
    "AGV_01": 85, "AGV_02": 70, "AGV_03": 95, "AGV_04": 100, "AGV_05": 100,
}
DIRECTORIO_RESULTADOS = Path(__file__).resolve().parents[2] / "resultados"


@dataclass
class EventoTurno:
    numero_movimiento: int
    tiempo_programado: float
    id_pallet: str
    tipo: str
    linea: str
    producto: str
    origen: str
    destino: str
    estacion_creacion: str
    estacion_destino: str
    id_ciclo: int
    depende_de: int | None = None
    hora_habilitacion: float | None = None
    prioridad: str = "NORMAL"
    estado: str = "PROGRAMADO"
    hora_creacion: float | None = None
    hora_asignacion: float | None = None
    hora_finalizacion: float | None = None
    agv: str | None = None
    distancia_planificada_m: float = 0.0


def generar_eventos(cantidad=MOVIMIENTOS_TURNO, duracion=DURACION_TURNO):
    """Idas uniformes por ciclo; retornos condicionados al LIBRE de la misma ida.

    tiempo_programado del retorno es la referencia nominal del ciclo, no un
    disparador. Su habilitación efectiva se registra al terminar físicamente la ida.
    """
    if not isinstance(cantidad, int) or not 1 <= cantidad <= MOVIMIENTOS_TURNO:
        raise ValueError("Cantidad debe estar entre 1 y 215.")
    if not math.isfinite(duracion) or not 0 < duracion <= DURACION_TURNO:
        raise ValueError("Duración debe estar entre 0 y 28800 segundos.")
    eventos = []
    for i in range(cantidad):
        linea = LINEAS[(i // 2) % len(LINEAS)]
        suministro = i % 2 == 0
        eventos.append(EventoTurno(
            numero_movimiento=i + 1,
            tiempo_programado=(i // 2) * duracion / ((cantidad + 1) // 2),
            id_pallet=f"PALLET_{i + 1:03d}",
            tipo="suministro" if suministro else "producto_terminado",
            linea=linea,
            producto="Cookies" if linea.startswith("COOKIE") else linea.title(),
            origen="ALMACEN" if suministro else linea,
            destino=linea if suministro else "ALMACEN",
            estacion_creacion="spawn_almacen" if suministro else f"spawn_{linea.lower()}",
            estacion_destino=f"entrada_material_{linea.lower()}" if suministro else "pallet_transit4",
            id_ciclo=i // 2 + 1,
            depende_de=None if suministro else i,
            estado="PROGRAMADO" if suministro else "ESPERANDO_IDA",
        ))
    return eventos


def preparar_flota(gestor, cantidad, ubicaciones=None):
    """Solo sobre un gestor limpio, después de restablecer físicamente FlexSim."""
    if gestor.agvs or gestor.solicitudes or gestor.misiones:
        raise ValueError("Prepare la corrida con un gestor nuevo.")
    if cantidad not in (2, 3, 4, 5):
        raise ValueError("Seleccione 2, 3, 4 o 5 AGV.")
    posiciones = {**UBICACIONES_INICIALES, **(ubicaciones or {})}
    ids = [f"AGV_{i:02d}" for i in range(1, cantidad + 1)]
    for id_agv in ids:
        if not posiciones[id_agv]:
            raise ValueError(f"Configure la ubicación inicial real de {id_agv}.")
        gestor.resolver_nodo(posiciones[id_agv])
    for id_agv in ids:
        gestor.registrar_agv(AGV(id_agv, BATERIAS_INICIALES[id_agv], posiciones[id_agv]))
    gestor.configurar_flota_activa(cantidad)


class EscenarioTurno:
    def __init__(self, gestor, factor=FACTOR_ACELERACION,
                 cantidad=MOVIMIENTOS_TURNO, duracion=DURACION_TURNO,
                 reloj=time.monotonic, directorio=DIRECTORIO_RESULTADOS):
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError("El factor debe ser finito y mayor que cero.")
        if gestor.solicitudes or gestor.misiones or not gestor.agvs_activos:
            raise ValueError("El escenario requiere gestor limpio y flota activa configurada.")
        self.gestor = gestor
        self.factor = float(factor)
        self.duracion = duracion
        self.eventos = generar_eventos(cantidad, duracion)
        self.por_pallet = {e.id_pallet: e for e in self.eventos}
        self.retornos = {e.id_ciclo: e for e in self.eventos if e.tipo == "producto_terminado"}
        self.reloj = reloj
        self.directorio = Path(directorio)
        self.id_corrida = uuid4().hex
        self.timestamp = datetime.now(timezone.utc)
        self.inicio_real = None
        self.estado = "PREPARADO"
        self.error = None
        self.error_guardado = None
        self.backlog_maximo = 0
        self.resultado = None
        self.ruta_resultado = None
        self.configuracion_inicial = [
            {"agv": a.id_agv, "ubicacion": a.ubicacion, "bateria": a.bateria}
            for a in gestor.agvs if gestor.agv_activo(a)
        ]

    @property
    def tiempo_logico(self):
        if self.resultado is not None:
            return self.resultado["tiempo_logico_s"]
        if self.inicio_real is None:
            return 0.0
        return min(self.duracion, max(0.0, (self.reloj() - self.inicio_real) * self.factor))

    def iniciar(self):
        if self.estado != "PREPARADO":
            raise ValueError("La corrida ya fue iniciada.")
        # Lectura únicamente: rechazar flota física ocupada antes de generar demanda.
        for a in self.gestor.agvs:
            if self.gestor.agv_activo(a):
                respuesta = self.gestor.flexsim.obtener_estado(self.gestor.resolver_agv_flexsim(a.id_agv))
                if respuesta != "OK|LIBRE":
                    raise RuntimeError(f"{a.id_agv} no confirmó disponibilidad: {respuesta}")
        self.inicio_real = self.reloj()
        self.estado = "EJECUTANDO"
        self.gestor.asignacion_automatica = False
        self.gestor.observador_misiones = self._observar_mision
        self.gestor.ahora = lambda: datetime(2000, 1, 1) + timedelta(seconds=self.tiempo_logico)

    def _observar_mision(self, cambio, mision):
        evento = self.por_pallet[mision.solicitud.id_pallet]
        retorno = self.retornos.get(evento.id_ciclo)
        if cambio == "completada" and (evento.tipo == "producto_terminado" or retorno is None):
            self.gestor.reservas_ciclo.pop(mision.agv.id_agv, None)
            mision.agv.estado = EstadoAGV.DISPONIBLE
        # El resultado al corte es inmutable aunque luego se drenen misiones físicas.
        if self.resultado is not None or self.tiempo_logico >= self.duracion:
            return
        if cambio == "iniciada":
            evento.estado = "EN_PROCESO"
        elif cambio == "completada":
            evento.estado = "COMPLETADO"
            evento.hora_finalizacion = self.tiempo_logico
            if evento.tipo == "suministro" and retorno is not None:
                # Dentro del callback de LIBRE y antes de evaluar cualquier otra solicitud.
                retorno.hora_habilitacion = evento.hora_finalizacion
                solicitud = self._crear_solicitud(retorno, mision.agv.id_agv)
                if self.tiempo_logico < self.duracion:
                    self._despachar(solicitud)

    def _crear_solicitud(self, evento, agv_reservado=None):
        evento.estado = "CREACION_ENVIADA"
        # No reintentar escrituras: el protocolo no tiene idempotencia/consulta de pallet.
        self.gestor.flexsim.crear_pallet(evento.id_pallet, evento.estacion_creacion)
        evento.hora_creacion = self.tiempo_logico
        evento.estado = "PENDIENTE"
        distancia_retorno = 0.0
        if evento.tipo == "suministro" and evento.id_ciclo in self.retornos:
            entrada = self.gestor.NODOS_SUMINISTRO[evento.linea]
            salida = self.gestor.NODOS_PRODUCTO_TERMINADO[evento.linea]
            distancia_retorno = (self.gestor.obtener_distancia(entrada, salida)
                                 + self.gestor.obtener_distancia(salida, "ALMACEN"))
        solicitud = SolicitudTraslado(
            f"{self.id_corrida}_{evento.numero_movimiento:03d}", evento.id_pallet,
            evento.producto, PESO_PALLET_KG, evento.origen, evento.destino,
            PrioridadSolicitud[evento.prioridad],
            estacion_origen=evento.estacion_creacion,
            estacion_destino=evento.estacion_destino,
            id_ciclo=evento.id_ciclo, agv_reservado=agv_reservado,
            distancia_retorno=distancia_retorno,
        )
        solicitud.fecha_creacion = self.gestor.ahora()
        self.gestor.registrar_solicitud(solicitud)
        self._registrar_backlog()
        return solicitud

    def _despachar(self, solicitud):
        mision = self.gestor.asignar_solicitud(solicitud)
        if mision is None:
            return
        evento = self.por_pallet[solicitud.id_pallet]
        evento.hora_asignacion = self.tiempo_logico
        evento.agv = mision.agv.id_agv
        evento.distancia_planificada_m = self.gestor.calcular_distancia_mision(mision.agv, solicitud)
        evento.estado = "MISION_ENVIADA"
        self.gestor.iniciar_mision(mision.id_mision)

    def _registrar_backlog(self):
        self.backlog_maximo = max(self.backlog_maximo, sum(
            e.estado == "PENDIENTE" for e in self.eventos
        ))

    def actualizar(self):
        if self.estado != "EJECUTANDO":
            # Solo observar misiones confirmadas; jamás asignar al detener o cerrar.
            try:
                self.gestor.actualizar_misiones_flexsim()
            except (OSError, RuntimeError) as exc:
                self.error = str(exc)
            return
        if self.tiempo_logico >= self.duracion:
            self._cerrar("FINALIZADO")
            return
        try:
            self.gestor.actualizar_misiones_flexsim()
            for evento in self.eventos:
                t = self.tiempo_logico
                if t >= self.duracion:
                    break
                if evento.estado != "PROGRAMADO" or evento.tiempo_programado > t:
                    continue
                # El suministro impar final solo aparece tras completar todos los ciclos.
                if evento.id_ciclo not in self.retornos and any(
                    r.hora_finalizacion is None for r in self.retornos.values()
                ):
                    continue
                evento.hora_habilitacion = t
                self._crear_solicitud(evento)
            # Reutilizar orden de prioridad y asignador, comprobando el corte antes de cada envío.
            for solicitud in self.gestor.obtener_solicitudes_pendientes_ordenadas():
                if self.tiempo_logico >= self.duracion:
                    break
                self._despachar(solicitud)
        except (OSError, RuntimeError, ValueError) as exc:
            self.error = str(exc)
            self._cerrar("ERROR")
            return
        if self.tiempo_logico >= self.duracion:
            self._cerrar("FINALIZADO")

    def detener(self):
        if self.estado == "EJECUTANDO":
            self._cerrar("DETENIDO")

    def indicadores(self):
        ocupados = sum(a.mision_actual is not None or a.id_agv in self.gestor.reservas_ciclo
                      for a in self.gestor.agvs if self.gestor.agv_activo(a))
        return {
            "Programados": len(self.eventos),
            "Lanzados": sum(e.hora_creacion is not None for e in self.eventos),
            "Completados": sum(e.hora_finalizacion is not None for e in self.eventos),
            "Pendientes": sum(e.hora_finalizacion is None for e in self.eventos),
            "Backlog": sum(e.estado == "PENDIENTE" for e in self.eventos),
            "AGV ocupados": ocupados,
            "AGV libres": sum(a.esta_disponible() and a.id_agv not in self.gestor.reservas_ciclo
                              for a in self.gestor.agvs if self.gestor.agv_activo(a)),
        }

    def kpis(self):
        t = self.tiempo_logico
        asignados = [e for e in self.eventos if e.hora_asignacion is not None]
        completados = [e for e in self.eventos if e.hora_finalizacion is not None]
        por_agv = {}
        for agv in sorted(self.gestor.agvs_activos):
            eventos = [e for e in asignados if e.agv == agv]
            # Un intervalo por ciclo: incluye la creación/espera del retorno, sin doble conteo.
            ocupado = 0.0
            for ida in (e for e in eventos if e.tipo == "suministro"):
                ultima = self.retornos.get(ida.id_ciclo, ida)
                fin = ultima.hora_finalizacion if ultima.hora_finalizacion is not None else t
                ocupado += max(0.0, fin - ida.hora_asignacion)
            por_agv[agv] = {
                "tiempo_ocupado_s": ocupado,
                "tiempo_libre_s": max(0.0, t - ocupado),
                "utilizacion": ocupado / t if t else 0.0,
                "distancia_estimada_completada_m": sum(e.distancia_planificada_m for e in eventos
                                                       if e.hora_finalizacion is not None),
            }
        return {
            "movimientos_completados": len(completados),
            "movimientos_pendientes_al_corte": len(self.eventos) - len(completados),
            "no_lanzados": sum(e.hora_creacion is None for e in self.eventos),
            "backlog_maximo": self.backlog_maximo,
            "espera_promedio_s": sum(e.hora_asignacion - e.hora_creacion for e in asignados) / len(asignados) if asignados else None,
            "ciclo_promedio_s": sum(e.hora_finalizacion - e.hora_creacion for e in completados) / len(completados) if completados else None,
            "muestra_espera": len(asignados), "muestra_ciclo": len(completados),
            "retraso_maximo_lanzamiento_s": max(
                (e.hora_creacion - (e.hora_habilitacion if e.depende_de is not None else e.tiempo_programado)
                 for e in self.eventos if e.hora_creacion is not None),
                default=0.0,
            ),
            "por_agv": por_agv,
            "distancia_total_estimada_m": sum(a["distancia_estimada_completada_m"] for a in por_agv.values()),
        }

    def _cerrar(self, estado):
        t = self.tiempo_logico
        self.estado = estado
        self.resultado = {
            "id_corrida": self.id_corrida, "timestamp": self.timestamp.isoformat(),
            "escenario": "turno_base_215" if len(self.eventos) == 215 and self.duracion == DURACION_TURNO else "prueba_pequena",
            "estado": estado, "error": self.error,
            "numero_agv": len(self.gestor.agvs_activos),
            "factor_aceleracion": self.factor, "duracion_programada_s": self.duracion,
            "tiempo_logico_s": t,
            "tiempo_real_transcurrido_s": self.reloj() - self.inicio_real,
            "configuracion_inicial": self.configuracion_inicial,
            "peso_pallet_kg": PESO_PALLET_KG,
            "organizacion": "ciclos_ida_retorno_mismo_agv_v2",
            "kpis": self.kpis(), "eventos": [asdict(e) for e in self.eventos],
            "metodo": "Tiempo lógico = monotonic transcurrido * factor, limitado al turno. "
                      "Finalización observada por ESTADO. Distancia estimada por Dijkstra solo de misiones completas; "
                      "no es telemetría física. Ocupación incluye reserva del ciclo completo; libre incluye recarga. "
                      "Espera y ciclo promedio medidos por pierna, no por pareja. Errores TCP invalidan comparación.",
        }
        self.guardar_resultado()

    def guardar_resultado(self):
        if self.resultado is None:
            return
        try:
            self.directorio.mkdir(parents=True, exist_ok=True)
            ruta = self.directorio / f"{self.timestamp.strftime('%Y%m%dT%H%M%S')}_{self.id_corrida}.json"
            temporal = ruta.with_suffix(".tmp")
            temporal.write_text(json.dumps(self.resultado, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            temporal.replace(ruta)
            self.ruta_resultado = str(ruta)
            self.error_guardado = None
        except OSError as exc:
            self.error_guardado = str(exc)
