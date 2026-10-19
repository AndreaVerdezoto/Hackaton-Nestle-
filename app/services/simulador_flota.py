"""Análisis offline: eventos discretos, sin cliente TCP ni reloj de pared."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import heapq
import json
import math
from pathlib import Path

from app.models.agv import AGV
from app.models.mision import Mision
from app.models.pallet import Pallet
from app.models.solicitud import SolicitudTraslado, PrioridadSolicitud
from app.services.solicitudes_retiro import crear_solicitud_retiro
from app.models.bateria import VELOCIDAD_REFERENCIA_MS
from app.services.gestor_flota import GestorFlota
from app.services.indicadores_capacidad import calcular_capacidad

VERSION_MODELO = "produccion_7min_meta215_v9"

LINEAS = tuple(GestorFlota.NODOS_PRODUCTO_TERMINADO)
TIEMPO_PRODUCCION_BASE_S = 420.0  # 7 min por pallet en el escenario base.
META_PALLETS_TURNO = 215  # Meta logística fija, independiente de la producción.
SUPUESTOS = [
    "Las cinco líneas producen de forma independiente; la flota AGV interviene únicamente cuando un pallet de producto terminado queda listo para retiro.",
    "Por defecto las cinco líneas tienen el mismo ciclo. Los tiempos individuales se pueden configurar sin cambiar el despacho de AGV.",
    "Las cinco líneas comienzan a producir al inicio del turno y generan una solicitud de retiro al completar cada pallet.",
    "El tiempo de producción base es 420 s (7 min) por pallet; es un supuesto calibrable del prototipo. La meta logística sigue siendo 215 entregas al almacén.",
    "Carga y descarga duran 30 s en el escenario base; velocidad, peso, escala y posición inicial siguen siendo parámetros del prototipo.",
    "Cada trayecto operacional comienza y termina a velocidad cero; no se detiene en cada arista del grafo.",
]
LIMITACIONES = [
    "No es simulación física 3D: no modela motores, neumáticos, masa dinámica ni sensores.",
    "No incluye congestión, conflictos entre AGV, tráfico humano ni fallas.",
    "La producción se representa con un tiempo de ciclo por pallet y una sola capacidad de proceso por línea; no modela máquinas internas ni microparadas.",
    "Las distancias se derivan del grafo escalado del modelo y deben contrastarse con medidas reales de planta antes de una implementación.",
    "El dimensionamiento depende de distancias, tiempos de carga/descarga, producción, demanda y demás parámetros utilizados. Debe recalibrarse con datos reales de planta antes de una implementación.",
]


def _numero(nombre, valor, cero=False):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
        raise ValueError(f"{nombre}: se requiere un número finito.")
    if valor < 0 or (valor == 0 and not cero):
        raise ValueError(f"{nombre}: debe ser {'mayor o igual a' if cero else 'mayor que'} cero.")


def tiempo_desplazamiento(distancia, velocidad, aceleracion, desaceleracion):
    """Perfil trapezoidal o triangular de reposo a reposo, en metros/segundos."""
    for nombre, valor in (("velocidad", velocidad), ("aceleración", aceleracion),
                          ("desaceleración", desaceleracion)):
        _numero(nombre, valor)
    _numero("distancia", distancia, cero=True)
    umbral = velocidad ** 2 / (2 * aceleracion) + velocidad ** 2 / (2 * desaceleracion)
    if distancia >= umbral:
        return velocidad / aceleracion + (distancia - umbral) / velocidad + velocidad / desaceleracion
    pico = math.sqrt(2 * distancia * aceleracion * desaceleracion / (aceleracion + desaceleracion))
    return pico / aceleracion + pico / desaceleracion


@dataclass(frozen=True)
class ParametrosSimulacion:
    # None: producir tantos pallets como permitan los ciclos hasta el cierre.
    # Un número explícito permite escenarios controlados de prueba.
    pallets_terminados: int | None = None
    duracion_turno_s: float = 28800.0
    velocidad_maxima_ms: float = VELOCIDAD_REFERENCIA_MS
    aceleracion_ms2: float = 1.0
    desaceleracion_ms2: float = 1.0
    tiempo_carga_s: float = 30.0
    tiempo_descarga_s: float = 30.0
    tiempo_produccion_s: float = TIEMPO_PRODUCCION_BASE_S
    # Sobrescrituras opcionales por línea (en segundos).
    tiempos_produccion_lineas_s: dict[str, float] | None = None
    factor_escala_metros_por_unidad: float = 1.0
    ubicacion_inicial: str = "ControlPoint7"
    peso_pallet_kg: float = 500.0

    @property
    def movimientos(self):
        # Una sola misión de retiro por cada pallet producido durante el turno.
        return self.pallets_terminados if self.pallets_terminados is not None else sum(
            math.floor((self.duracion_turno_s + 1e-9) / self.ciclo_linea_s(linea))
            for linea in LINEAS
        )

    @property
    def tiempo_produccion_efectivo_s(self):
        return self.tiempo_produccion_s

    def ciclo_linea_s(self, linea):
        if self.tiempos_produccion_lineas_s is None:
            return self.tiempo_produccion_s
        return self.tiempos_produccion_lineas_s.get(linea, self.tiempo_produccion_s)

    def __post_init__(self):
        if self.pallets_terminados is not None and (
            type(self.pallets_terminados) is not int or self.pallets_terminados < 1
        ):
            raise ValueError("Pallets terminados debe ser un entero positivo o None (automático).")
        for nombre in ("duracion_turno_s", "velocidad_maxima_ms", "aceleracion_ms2",
                       "desaceleracion_ms2", "factor_escala_metros_por_unidad", "peso_pallet_kg"):
            _numero(nombre, getattr(self, nombre))
        for nombre in ("tiempo_carga_s", "tiempo_descarga_s"):
            _numero(nombre, getattr(self, nombre), cero=True)
        _numero("tiempo_produccion_s", self.tiempo_produccion_s)
        if self.tiempos_produccion_lineas_s is not None:
            if not isinstance(self.tiempos_produccion_lineas_s, dict):
                raise ValueError("Tiempos por línea debe ser un diccionario.")
            for linea, ciclo in self.tiempos_produccion_lineas_s.items():
                if linea not in LINEAS:
                    raise ValueError(f"Línea de producción desconocida: {linea}.")
                _numero(f"tiempo de {linea}", ciclo)
        # Impide simular millones de eventos por una configuración accidental.
        if sum(math.floor((self.duracion_turno_s + 1e-9) / self.ciclo_linea_s(linea))
               for linea in LINEAS) > 20000:
            raise ValueError("Demasiados ciclos de producción para este escenario (máximo 20 000).")
        if self.movimientos == 0:
            raise ValueError("Ninguna línea completa un pallet dentro del turno con estos tiempos.")
        if self.peso_pallet_kg > SolicitudTraslado.PESO_MAXIMO_PALLET:
            raise ValueError("El peso máximo del pallet es 800 kg.")
        if not isinstance(self.ubicacion_inicial, str) or not self.ubicacion_inicial:
            raise ValueError("Indique una ubicación inicial del grafo.")


@dataclass(frozen=True)
class DemandaMision:
    id_mision: int
    llegada_s: float
    linea: str
    tipo: str = "producto_terminado"
    prioridad: PrioridadSolicitud = PrioridadSolicitud.NORMAL
    id_pallet: str | None = None
    id_ciclo: int | None = None


def generar_demanda(parametros):
    """Solicitudes de retiro generadas al terminar cada ciclo productivo."""
    eventos = sorted(
        (ciclo * parametros.ciclo_linea_s(linea), orden, linea)
        for orden, linea in enumerate(LINEAS)
        for ciclo in range(1, math.floor(
            (parametros.duracion_turno_s + 1e-9) / parametros.ciclo_linea_s(linea)
        ) + 1)
    )
    if parametros.pallets_terminados is not None:
        if len(eventos) < parametros.pallets_terminados:
            raise ValueError("La producción configurada no alcanza esa cantidad de pallets dentro del turno.")
        eventos = eventos[:parametros.pallets_terminados]
    return tuple(
        DemandaMision(i, instante, linea, "producto_terminado", PrioridadSolicitud.NORMAL,
                      f"PALLET_{i:03d}", i)
        for i, (instante, _, linea) in enumerate(eventos, start=1)
    )


class SimuladorFlota:
    def __init__(self, parametros=None, demanda=None):
        self.parametros = parametros or ParametrosSimulacion()
        self.demanda = tuple(demanda) if demanda is not None else generar_demanda(self.parametros)
        self.red = GestorFlota()
        self._rutas = {}
        p = self.parametros
        if len(self.demanda) != p.movimientos:
            raise ValueError("La demanda debe contener una solicitud de retiro por cada pallet requerido.")
        for i, c in enumerate(self.demanda):
            _numero("llegada", c.llegada_s, cero=True)
            if (c.id_mision != i + 1 or c.linea not in LINEAS or c.llegada_s > p.duracion_turno_s
                    or c.tipo != "producto_terminado" or not isinstance(c.prioridad, PrioridadSolicitud)):
                raise ValueError("Demanda inválida: cada pallet debe generar un retiro de producto terminado dentro del turno.")
        # Validación anticipada: jamás sustituir una ruta inexistente por distancia cero.
        self.trayecto(p.ubicacion_inicial, "ALMACEN")
        for c in self.demanda:
            origen, destino = self.extremos(c)
            self.trayecto(p.ubicacion_inicial, origen)
            self.trayecto(origen, destino)

    def extremos(self, mision):
        return self.red.NODOS_PRODUCTO_TERMINADO[mision.linea], "ControlPoint7"

    def trayecto(self, origen, destino):
        clave = (origen, destino)
        if clave not in self._rutas:
            try:
                ruta, unidades = self.red.obtener_ruta(origen, destino)
            except (ValueError, KeyError) as exc:
                raise ValueError(f"No se puede calcular el escenario: falta conectividad {origen} -> {destino}. {exc}") from exc
            metros = unidades * self.parametros.factor_escala_metros_por_unidad
            self._rutas[clave] = {
                "ruta": ruta, "distancia_grafo": unidades, "distancia_m": metros,
                "tiempo_s": tiempo_desplazamiento(metros, self.parametros.velocidad_maxima_ms,
                                                  self.parametros.aceleracion_ms2, self.parametros.desaceleracion_ms2),
            }
        return self._rutas[clave]

    def ejecutar(self, cantidad_agv, *, simular_bateria=False, cargadores=()):
        if type(cantidad_agv) is not int or cantidad_agv not in (2, 3, 4, 5):
            raise ValueError("Seleccione una flota de 2, 3, 4 o 5 AGV.")
        p = self.parametros
        # La flota se representa con objetos AGV. El diccionario solo permite
        # acceder rápidamente por identificador sin duplicar el estado del vehículo.
        vehiculos = {
            f"AGV_{i:02d}": AGV(f"AGV_{i:02d}", 100.0, p.ubicacion_inicial)
            for i in range(1, cantidad_agv + 1)
        }
        eventos, pendientes, movimientos, traza = [], [], {}, []
        solicitudes = {}
        trabajos = {}
        pallets = {}
        producciones = []
        produccion_por_ciclo = {}
        reloj = 0.0
        secuencia = 0
        backlog_maximo = 0
        finalizados = 0
        self.red.ahora = lambda: datetime(2000, 1, 1) + timedelta(seconds=reloj)

        def programar(t, tipo, identificador):
            nonlocal secuencia
            secuencia += 1
            # Los finales y eventos de producción se procesan antes que nuevas llegadas
            # cuando comparten instante.
            prioridad_evento = 1 if tipo == "llegada" else 0
            heapq.heappush(eventos, (t, prioridad_evento, secuencia, tipo, identificador))

        def preparar_trabajo(c, programar_llegada=True):
            origen, destino = self.extremos(c)
            id_pallet = c.id_pallet or f"PALLET_{c.id_ciclo or c.id_mision:03d}"
            pallet = pallets.get(id_pallet)
            if pallet is None:
                pallet = Pallet(
                    id_pallet=id_pallet,
                    producto=c.linea,
                    lote=None,
                    cantidad_cajas=None,
                    peso=p.peso_pallet_kg,
                    altura=None,
                    ubicacion=origen,
                )
                pallets[id_pallet] = pallet
            solicitudes[c.id_mision] = crear_solicitud_retiro(
                id_tarea=c.id_mision,
                pallet=pallet,
                linea=c.linea,
                prioridad=c.prioridad,
                id_ciclo=c.id_ciclo,
            )
            solicitudes[c.id_mision].fecha_creacion = datetime(2000, 1, 1) + timedelta(seconds=c.llegada_s)
            trabajos[c.id_mision] = c
            if programar_llegada:
                programar(c.llegada_s, "llegada", c.id_mision)

        # La producción existe por sí sola. Cada línea inicia su primer ciclo en t=0
        # y la solicitud de retiro aparece exactamente cuando termina el pallet.
        for c in self.demanda:
            preparar_trabajo(c)
            ciclo_s = p.ciclo_linea_s(c.linea)
            inicio = c.llegada_s - ciclo_s
            produccion = {
                "id_ciclo": c.id_ciclo,
                "id_pallet": c.id_pallet,
                "linea": c.linea,
                "inicio_s": inicio,
                "fin_s": c.llegada_s,
                "duracion_s": ciclo_s,
                "movimiento_producto_terminado": c.id_mision,
            }
            producciones.append(produccion)
            produccion_por_ciclo[c.id_ciclo] = produccion
            programar(inicio, "inicio_produccion", c.id_ciclo)
            programar(c.llegada_s, "fin_produccion", c.id_ciclo)

        bateria = None
        cargadores_no_utilizables = []
        if simular_bateria:
            from app.services.bateria_flota import BateriaFlota
            utilizables = []
            origenes_posibles = {"ControlPoint7"}
            origenes_posibles.update(self.red.NODOS_PRODUCTO_TERMINADO.values())
            for nodo in cargadores:
                try:
                    self.trayecto(p.ubicacion_inicial, nodo)
                    self.trayecto(nodo, "ControlPoint7")
                    for origen in origenes_posibles:
                        self.trayecto(nodo, origen)
                except ValueError:
                    cargadores_no_utilizables.append(nodo)
                else:
                    utilizables.append(nodo)
            bateria = BateriaFlota(vehiculos, utilizables, self.trayecto, programar)

        def servicio(c, agv):
            origen, destino = self.extremos(c)
            return (self.trayecto(vehiculos[agv].ubicacion, origen)["tiempo_s"] +
                    self.trayecto(origen, destino)["tiempo_s"] +
                    p.tiempo_carga_s + p.tiempo_descarga_s)

        def iniciar(c, agv):
            numero = c.id_mision
            origen, destino = self.extremos(c)
            vacio = self.trayecto(vehiculos[agv].ubicacion, origen)
            cargado = self.trayecto(origen, destino)
            duracion = vacio["tiempo_s"] + p.tiempo_carga_s + cargado["tiempo_s"] + p.tiempo_descarga_s
            fin = reloj + duracion
            if not math.isfinite(fin):
                raise ValueError("Los parámetros producen un tiempo no finito.")
            id_ciclo = c.id_ciclo or c.id_mision
            id_pallet = c.id_pallet or f"PALLET_{id_ciclo:03d}"
            mision = Mision(numero, solicitudes[numero], vehiculos[agv])
            mision.iniciar_simulacion(
                numero=numero,
                tipo=c.tipo,
                linea=c.linea,
                id_ciclo=id_ciclo,
                llegada_s=c.llegada_s,
                inicio_s=reloj,
                fin_s=fin,
                vacio=vacio,
                cargado=cargado,
                carga_s=p.tiempo_carga_s,
                descarga_s=p.tiempo_descarga_s,
                duracion_servicio_s=duracion,
            )
            if bateria:
                mision.bateria_inicio = bateria.nivel(agv, reloj)
                mision.bateria_fin = bateria.nivel(agv, fin)
            movimientos[numero] = mision
            traza.append({"tiempo_s": reloj, "evento": "inicio", "movimiento": numero,
                          "tipo": c.tipo, "pallet": id_pallet, "agv": agv})
            programar(fin, "fin", numero)

        while eventos:
            if finalizados == p.movimientos:
                break
            reloj = eventos[0][0]
            while eventos and eventos[0][0] == reloj:
                _, _, _, tipo, identificador = heapq.heappop(eventos)
                if bateria and bateria.evento(tipo, identificador, reloj, finalizados < p.movimientos):
                    continue
                if tipo == "llegada":
                    pendientes.append(identificador)
                    c = trabajos[identificador]
                    traza.append({"tiempo_s": reloj, "evento": "llegada", "mision": identificador,
                                  "tipo": c.tipo, "pallet": c.id_pallet})
                elif tipo == "inicio_produccion":
                    prod = produccion_por_ciclo[identificador]
                    traza.append({"tiempo_s": reloj, "evento": "inicio_produccion",
                                  "ciclo": identificador, "pallet": prod["id_pallet"], "linea": prod["linea"]})
                elif tipo == "fin_produccion":
                    prod = produccion_por_ciclo[identificador]
                    traza.append({"tiempo_s": reloj, "evento": "fin_produccion",
                                  "ciclo": identificador, "pallet": prod["id_pallet"], "linea": prod["linea"]})
                elif tipo == "fin":
                    finalizados += 1
                    mision = movimientos[identificador]
                    agv = mision.id_agv
                    mision.completar_simulacion(reloj)
                    traza.append({"tiempo_s": reloj, "evento": "fin", "movimiento": identificador,
                                  "tipo": mision.tipo, "pallet": mision.id_pallet, "agv": agv})

            if bateria and finalizados < p.movimientos:
                for agv, v in vehiculos.items():
                    if (v.esta_disponible()
                            and bateria.modelo.necesita_recarga(bateria.nivel(agv, reloj))):
                        bateria.recargar(agv, reloj)

            pendientes.sort(key=lambda i: (-self.red.calcular_score_solicitud(solicitudes[i]), i))
            while pendientes:
                c = trabajos[pendientes[0]]
                solicitud = solicitudes[c.id_mision]
                disponibles = [
                    a for a, v in vehiculos.items()
                    if v.esta_disponible() and v.puede_transportar(solicitud.peso)
                ]
                if bateria:
                    candidatos = []
                    for a in disponibles:
                        duracion = servicio(c, a)
                        if bateria.modelo.admite_mision(bateria.nivel(a, reloj), duracion):
                            candidatos.append(a)
                        else:
                            if not bateria.modelo.admite_mision(100, duracion):
                                origen, destino = self.extremos(c)
                                mejores = [
                                    self.trayecto(nodo, origen)["tiempo_s"] +
                                    self.trayecto(origen, destino)["tiempo_s"] +
                                    p.tiempo_carga_s + p.tiempo_descarga_s
                                    for nodo in bateria.libres
                                ]
                                if not any(bateria.modelo.admite_mision(100, d) for d in mejores):
                                    raise ValueError("La misión excede la autonomía disponible conservando la reserva.")
                            bateria.recargar(a, reloj)
                    disponibles = candidatos
                if not disponibles:
                    break
                origen = self.extremos(c)[0]
                agv = min(disponibles, key=lambda a: (
                    self.trayecto(vehiculos[a].ubicacion, origen)["distancia_m"], a
                ))
                pendientes.pop(0)
                iniciar(c, agv)
            backlog_maximo = max(backlog_maximo, len(pendientes))
            traza.append({"tiempo_s": reloj, "evento": "cola", "pendientes": len(pendientes)})

        if pendientes or len(movimientos) != p.movimientos or finalizados != p.movimientos:
            raise RuntimeError("La simulación terminó con demanda sin procesar.")

        misiones_ordenadas = sorted(movimientos.values(), key=lambda m: (m.inicio_s, m.numero))
        for mision in misiones_ordenadas:
            mision.calcular_metricas_simulacion()
        # La UI, los KPIs y los JSON conservan exactamente el mismo contrato externo.
        lista = [mision.a_dict_simulacion() for mision in misiones_ordenadas]
        terminados = [m for m in lista if m["fin_s"] <= p.duracion_turno_s]
        generadas_turno = [m for m in lista if m["llegada_s"] <= p.duracion_turno_s]
        activas_corte = [
            m for m in generadas_turno
            if m["inicio_s"] <= p.duracion_turno_s < m["fin_s"]
        ]
        pendientes_cola_corte = [
            m for m in generadas_turno
            if m["llegada_s"] <= p.duracion_turno_s < m["inicio_s"]
        ]
        no_generadas_corte = [m for m in lista if m["llegada_s"] > p.duracion_turno_s]

        detalle = []
        for agv in vehiculos:
            propios = [m for m in lista if m["agv"] == agv]
            ocupado = min(p.duracion_turno_s, math.fsum(
                max(0.0, min(m["fin_s"], p.duracion_turno_s) - m["inicio_s"]) for m in propios
            ))
            vacia = sum(m["vacio"]["distancia_m"] for m in propios)
            cargada = sum(m["cargado"]["distancia_m"] for m in propios)
            detalle.append({
                "agv": agv, "movimientos_totales": len(propios),
                "movimientos_turno": sum(m["fin_s"] <= p.duracion_turno_s for m in propios),
                "pallets_terminados_totales": len(propios),
                "pallets_terminados_turno": sum(m["fin_s"] <= p.duracion_turno_s for m in propios),
                "ocupado_turno_s": ocupado, "libre_turno_s": p.duracion_turno_s - ocupado,
                "utilizacion_pct": 100 * ocupado / p.duracion_turno_s,
                "distancia_vacia_m": vacia, "distancia_cargada_m": cargada, "distancia_total_m": vacia + cargada,
                "posicion_final": vehiculos[agv].ubicacion,
            })

        total = max(m["fin_s"] for m in lista)
        movimientos_restantes_corte = p.movimientos - len(terminados)
        kpis = {
            "completados_turno": len(terminados),
            # Compatibilidad: backlog_corte representa movimientos del plan que aún no
            # terminaron, incluidos los que todavía no se habían generado al corte.
            "backlog_corte": movimientos_restantes_corte,
            "movimientos_restantes_plan_corte": movimientos_restantes_corte,
            "solicitudes_generadas_turno": len(generadas_turno),
            "solicitudes_completadas_turno": len(terminados),
            "solicitudes_pendientes_turno": len(pendientes_cola_corte),
            "solicitudes_activas_turno": len(activas_corte),
            "solicitudes_no_generadas_turno": len(no_generadas_corte),
            "throughput_mov_h": len(terminados) / (p.duracion_turno_s / 3600),
            "espera_media_s": sum(m["espera_s"] for m in lista) / len(lista),
            "ciclo_medio_s": sum(m["ciclo_movimiento_s"] for m in lista) / len(lista),
            "muestra_promedios": len(lista), "backlog_maximo": backlog_maximo,
            "utilizacion_media_pct": sum(a["utilizacion_pct"] for a in detalle) / cantidad_agv,
            "tiempo_total_s": total, "hora_fin_movimiento_ultimo_id_s": lista[-1]["fin_s"],
            "margen_tiempo_s": max(0.0, p.duracion_turno_s - total),
            "margen_turno_pct": 100 * max(0.0, p.duracion_turno_s - total) / p.duracion_turno_s,
            "exceso_tiempo_s": max(0.0, total - p.duracion_turno_s),
            "distancia_vacia_m": sum(a["distancia_vacia_m"] for a in detalle),
            "distancia_cargada_m": sum(a["distancia_cargada_m"] for a in detalle),
            "distancia_total_m": sum(a["distancia_total_m"] for a in detalle),
            "tiempo_produccion_pallet_s": p.tiempo_produccion_efectivo_s,
        }

        pt = lista
        pt_turno = sum(m["fin_s"] <= p.duracion_turno_s for m in pt)
        fin_pt = max(m["fin_s"] for m in pt)
        kpis.update({
            "pallets_terminados_requeridos": p.movimientos,
            "meta_pallets_turno": META_PALLETS_TURNO,
            "pallets_producidos_turno": len(self.demanda),
            "pallets_extra_meta": max(0, pt_turno - META_PALLETS_TURNO),
            "faltantes_meta": max(0, META_PALLETS_TURNO - pt_turno),
            "retiro_produccion_pct": 100 * pt_turno / len(self.demanda),
            "pallets_terminados_turno": pt_turno,
            "pallets_terminados_pendientes": p.movimientos - pt_turno,
            "cumplimiento_pct": 100 * pt_turno / META_PALLETS_TURNO,
            "cumple": pt_turno >= META_PALLETS_TURNO,
            "tiempo_producto_terminado_s": fin_pt,
            "throughput_pt_h": pt_turno / (p.duracion_turno_s / 3600),
            "capacidad_disponible_pct": 100 - kpis["utilizacion_media_pct"],
            "movimientos_logisticos_totales": p.movimientos,
            "margen_pt_s": max(0, p.duracion_turno_s - fin_pt),
            "exceso_pt_s": max(0, fin_pt - p.duracion_turno_s),
        })
        kpis.update(calcular_capacidad(lista, traza, p.duracion_turno_s, cantidad_agv, META_PALLETS_TURNO))
        grafo = Path(__file__).resolve().parents[2] / "data/red_agv_grafo_actualizado.json"
        parametros_salida = asdict(p)
        parametros_salida["pallets_terminados"] = p.movimientos  # Compatibilidad con UI y exportación.
        parametros_salida["meta_pallets_turno"] = META_PALLETS_TURNO
        return {
            **({"modelo_bateria": {"autonomia_s": bateria.modelo.autonomia_s,
                "carga_completa_s": bateria.modelo.carga_completa_s, "reserva_pct": bateria.modelo.reserva_pct},
                "recargas": bateria.recargas, "cargadores": list(cargadores),
                "cargadores_no_utilizables": cargadores_no_utilizables} if bateria else {}),
            "version_modelo": VERSION_MODELO + ("_bateria" if bateria else ""), "modo": "analisis_python",
            "timestamp": datetime.now(timezone.utc).isoformat(), "numero_agv": cantidad_agv,
            "parametros": parametros_salida, "demanda": [asdict(c) for c in self.demanda],
            "producciones": sorted(producciones, key=lambda x: x["id_ciclo"]),
            "grafo_sha256": hashlib.sha256(grafo.read_bytes()).hexdigest(),
            "supuestos": SUPUESTOS + (["Batería lineal temporal: autonomía 10 h, carga completa 3 h, reserva operativa 20%; batería inicial 100%. Una plaza por cargador."] if bateria else []),
            "limitaciones": [v.replace(" ni batería/recarga sin datos validados", "") for v in LIMITACIONES] if bateria else LIMITACIONES,
            "alcance_kpis": "Pallet completado = producto terminado descargado en almacén. Cada pallet genera una única misión logística de retiro desde la línea hasta el almacén.",
            "kpis": kpis, "por_agv": detalle, "movimientos": lista, "eventos": traza,
        }


def exportar_json(resultados):
    return json.dumps(resultados, ensure_ascii=False, indent=2, allow_nan=False)
