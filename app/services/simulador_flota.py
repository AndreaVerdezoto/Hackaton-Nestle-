"""Análisis offline: eventos discretos, sin cliente TCP ni reloj de pared."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import heapq
import json
import math
from pathlib import Path

from app.models.solicitud import SolicitudTraslado, PrioridadSolicitud
from app.models.bateria import VELOCIDAD_REFERENCIA_MS
from app.services.gestor_flota import GestorFlota
from app.services.indicadores_capacidad import calcular_capacidad

VERSION_MODELO = "flujo_encadenado_suministro_produccion_v3"

LINEAS = tuple(GestorFlota.NODOS_SUMINISTRO)
SUPUESTOS = [
    "Flujo encadenado 1:1: cada pallet terminado requiere primero un suministro de material a su línea y luego un retiro de producto terminado al almacén.",
    "Distribución equilibrada/round-robin entre las cinco líneas por falta de distribución real por línea.",
    "Las necesidades de material se distribuyen uniformemente durante el turno por falta de histórico de demanda.",
    "El tiempo de producción por pallet se deriva del escenario base si no se especifica: duración del turno × número de líneas / pallets requeridos.",
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
    pallets_terminados: int = 215
    # Compatibilidad de serialización. En el flujo encadenado siempre es 1:1 con pallets_terminados.
    movimientos_suministro: int | None = None
    duracion_turno_s: float = 28800.0
    velocidad_maxima_ms: float = VELOCIDAD_REFERENCIA_MS
    aceleracion_ms2: float = 1.0
    desaceleracion_ms2: float = 1.0
    tiempo_carga_s: float = 30.0
    tiempo_descarga_s: float = 30.0
    # Se conserva para leer corridas antiguas, pero el flujo nuevo no espera producto: la solicitud
    # de retiro nace únicamente cuando producción termina.
    espera_disponibilidad_retorno_s: float = 0.0
    # Si es None, se deriva del objetivo 215/turno repartido en cinco líneas.
    tiempo_produccion_s: float | None = None
    factor_escala_metros_por_unidad: float = 1.0
    ubicacion_inicial: str = "ControlPoint7"
    peso_pallet_kg: float = 500.0

    @property
    def suministros_requeridos(self):
        return self.pallets_terminados

    @property
    def movimientos(self):
        # Un suministro + un retiro de producto terminado por cada pallet.
        return 2 * self.pallets_terminados

    @property
    def tiempo_produccion_efectivo_s(self):
        if self.tiempo_produccion_s is not None:
            return self.tiempo_produccion_s
        pallets_linea_max = math.ceil(self.pallets_terminados / len(LINEAS))
        return self.duracion_turno_s / pallets_linea_max

    def __post_init__(self):
        if type(self.pallets_terminados) is not int or self.pallets_terminados < 1:
            raise ValueError("Pallets terminados debe ser un entero positivo.")
        if self.movimientos_suministro is not None and (type(self.movimientos_suministro) is not int or self.movimientos_suministro < 0):
            raise ValueError("Suministros debe ser un entero no negativo.")
        if self.movimientos_suministro not in (None, 0, self.pallets_terminados):
            raise ValueError("En el flujo encadenado debe existir un suministro por cada pallet terminado.")
        object.__setattr__(self, "movimientos_suministro", self.pallets_terminados)
        for nombre in ("duracion_turno_s", "velocidad_maxima_ms", "aceleracion_ms2",
                       "desaceleracion_ms2", "factor_escala_metros_por_unidad", "peso_pallet_kg"):
            _numero(nombre, getattr(self, nombre))
        for nombre in ("tiempo_carga_s", "tiempo_descarga_s", "espera_disponibilidad_retorno_s"):
            _numero(nombre, getattr(self, nombre), cero=True)
        if self.tiempo_produccion_s is not None:
            _numero("tiempo_produccion_s", self.tiempo_produccion_s)
        if self.peso_pallet_kg > SolicitudTraslado.PESO_MAXIMO_PALLET:
            raise ValueError("El peso máximo del pallet es 800 kg.")
        if not isinstance(self.ubicacion_inicial, str) or not self.ubicacion_inicial:
            raise ValueError("Indique una ubicación inicial del grafo.")


@dataclass(frozen=True)
class DemandaMision:
    id_mision: int
    llegada_s: float
    linea: str
    tipo: str = "suministro"
    prioridad: PrioridadSolicitud = PrioridadSolicitud.NORMAL
    id_pallet: str | None = None
    id_ciclo: int | None = None


def generar_demanda(parametros):
    """Necesidades de material uniformes y round-robin; el retorno nace al terminar producción."""
    cantidad = parametros.pallets_terminados
    return tuple(
        DemandaMision(
            i + 1,
            i * parametros.duracion_turno_s / cantidad,
            LINEAS[i % len(LINEAS)],
            "suministro",
            PrioridadSolicitud.NORMAL,
            f"PALLET_{i+1:03d}",
            i + 1,
        )
        for i in range(cantidad)
    )


class SimuladorFlota:
    def __init__(self, parametros=None, demanda=None):
        self.parametros = parametros or ParametrosSimulacion()
        self.demanda = tuple(demanda) if demanda is not None else generar_demanda(self.parametros)
        self.red = GestorFlota(habilitar_flexsim=False)
        self._rutas = {}
        p = self.parametros
        if len(self.demanda) != p.pallets_terminados:
            raise ValueError("La demanda debe contener una necesidad de suministro por cada pallet requerido.")
        for i, c in enumerate(self.demanda):
            _numero("llegada", c.llegada_s, cero=True)
            if (c.id_mision != i + 1 or c.linea not in LINEAS or c.llegada_s >= p.duracion_turno_s
                    or c.tipo != "suministro" or not isinstance(c.prioridad, PrioridadSolicitud)):
                raise ValueError("Demanda inválida: el flujo base inicia con suministros dentro del turno.")
        # Validación anticipada: jamás sustituir una ruta inexistente por distancia cero.
        self.trayecto(p.ubicacion_inicial, "ALMACEN")
        for c in self.demanda:
            origen, destino = self.extremos(c)
            self.trayecto(p.ubicacion_inicial, origen)
            self.trayecto(origen, destino)
        for linea in LINEAS:
            origen_pt = self.red.NODOS_PRODUCTO_TERMINADO[linea]
            self.trayecto(p.ubicacion_inicial, origen_pt)
            self.trayecto(origen_pt, "ControlPoint7")

    def extremos(self, mision):
        if mision.tipo == "producto_terminado":
            return self.red.NODOS_PRODUCTO_TERMINADO[mision.linea], "ControlPoint7"
        return "ControlPoint7", self.red.NODOS_SUMINISTRO[mision.linea]

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
        vehiculos = {f"AGV_{i:02d}": {"posicion": p.ubicacion_inicial, "mision": None}
                     for i in range(1, cantidad_agv + 1)}
        eventos, pendientes, movimientos, traza = [], [], {}, []
        solicitudes = {}
        trabajos = {}
        producciones = []
        produccion_por_ciclo = {}
        linea_disponible_s = dict.fromkeys(LINEAS, 0.0)
        reloj = 0.0
        secuencia = 0
        backlog_maximo = 0
        siguiente_movimiento = p.pallets_terminados + 1
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
            solicitudes[c.id_mision] = SolicitudTraslado(
                str(c.id_mision), id_pallet, c.linea, p.peso_pallet_kg,
                origen, destino, c.prioridad, id_ciclo=c.id_ciclo,
            )
            solicitudes[c.id_mision].fecha_creacion = datetime(2000, 1, 1) + timedelta(seconds=c.llegada_s)
            trabajos[c.id_mision] = c
            if programar_llegada:
                programar(c.llegada_s, "llegada", c.id_mision)

        for c in self.demanda:
            preparar_trabajo(c)

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
            return (self.trayecto(vehiculos[agv]["posicion"], origen)["tiempo_s"] +
                    self.trayecto(origen, destino)["tiempo_s"] +
                    p.tiempo_carga_s + p.tiempo_descarga_s)

        def iniciar(c, agv):
            numero = c.id_mision
            origen, destino = self.extremos(c)
            vacio = self.trayecto(vehiculos[agv]["posicion"], origen)
            cargado = self.trayecto(origen, destino)
            duracion = vacio["tiempo_s"] + p.tiempo_carga_s + cargado["tiempo_s"] + p.tiempo_descarga_s
            fin = reloj + duracion
            if not math.isfinite(fin):
                raise ValueError("Los parámetros producen un tiempo no finito.")
            id_ciclo = c.id_ciclo or c.id_mision
            id_pallet = c.id_pallet or f"PALLET_{id_ciclo:03d}"
            movimientos[numero] = {
                "numero": numero, "id_pallet": id_pallet, "id_mision": c.id_mision,
                "id_ciclo": id_ciclo, "tipo": c.tipo, "linea": c.linea,
                "agv": agv, "origen": origen, "destino": destino,
                "llegada_s": c.llegada_s, "inicio_s": reloj, "fin_s": fin,
                "vacio": vacio, "cargado": cargado, "espera_disponibilidad_s": 0.0,
                "carga_s": p.tiempo_carga_s, "descarga_s": p.tiempo_descarga_s,
                "duracion_servicio_s": duracion,
            }
            if bateria:
                movimientos[numero]["bateria_inicio"] = bateria.nivel(agv, reloj)
                movimientos[numero]["bateria_fin"] = bateria.nivel(agv, fin)
            vehiculos[agv]["mision"] = c.id_mision
            traza.append({"tiempo_s": reloj, "evento": "inicio", "movimiento": numero,
                          "tipo": c.tipo, "pallet": id_pallet, "agv": agv})
            programar(fin, "fin", numero)

        def programar_produccion(movimiento_suministro):
            ciclo = movimiento_suministro["id_ciclo"]
            linea = movimiento_suministro["linea"]
            inicio = max(reloj, linea_disponible_s[linea])
            fin = inicio + p.tiempo_produccion_efectivo_s
            linea_disponible_s[linea] = fin
            produccion = {
                "id_ciclo": ciclo,
                "id_pallet": movimiento_suministro["id_pallet"],
                "linea": linea,
                "inicio_s": inicio,
                "fin_s": fin,
                "duracion_s": p.tiempo_produccion_efectivo_s,
                "movimiento_suministro": movimiento_suministro["numero"],
                "movimiento_producto_terminado": None,
            }
            producciones.append(produccion)
            produccion_por_ciclo[ciclo] = produccion
            traza.append({"tiempo_s": reloj, "evento": "produccion_programada", "ciclo": ciclo,
                          "pallet": produccion["id_pallet"], "linea": linea,
                          "inicio_produccion_s": inicio, "fin_produccion_s": fin})
            programar(inicio, "inicio_produccion", ciclo)
            programar(fin, "fin_produccion", ciclo)

        def crear_retiro_producto(ciclo):
            nonlocal siguiente_movimiento
            produccion = produccion_por_ciclo[ciclo]
            numero = siguiente_movimiento
            siguiente_movimiento += 1
            trabajo = DemandaMision(
                numero, reloj, produccion["linea"], "producto_terminado",
                PrioridadSolicitud.NORMAL, produccion["id_pallet"], ciclo,
            )
            preparar_trabajo(trabajo, programar_llegada=False)
            produccion["movimiento_producto_terminado"] = numero
            pendientes.append(numero)
            traza.append({"tiempo_s": reloj, "evento": "llegada_producto_terminado",
                          "mision": numero, "ciclo": ciclo, "pallet": produccion["id_pallet"],
                          "linea": produccion["linea"]})

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
                    crear_retiro_producto(identificador)
                elif tipo == "fin":
                    finalizados += 1
                    m = movimientos[identificador]
                    agv = m["agv"]
                    vehiculos[agv]["posicion"] = m["destino"]
                    traza.append({"tiempo_s": reloj, "evento": "fin", "movimiento": identificador,
                                  "tipo": m["tipo"], "pallet": m["id_pallet"], "agv": agv})
                    vehiculos[agv]["mision"] = None
                    if m["tipo"] == "suministro":
                        programar_produccion(m)

            if bateria and finalizados < p.movimientos:
                for agv, v in vehiculos.items():
                    if v["mision"] is None and bateria.nivel(agv, reloj) <= bateria.modelo.reserva_pct + 1e-8:
                        bateria.recargar(agv, reloj)

            pendientes.sort(key=lambda i: (-self.red.calcular_score_solicitud(solicitudes[i]), i))
            while pendientes:
                disponibles = [a for a, v in vehiculos.items() if v["mision"] is None]
                c = trabajos[pendientes[0]]
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
                    self.trayecto(vehiculos[a]["posicion"], origen)["distancia_m"], a
                ))
                pendientes.pop(0)
                iniciar(c, agv)
            backlog_maximo = max(backlog_maximo, len(pendientes))
            traza.append({"tiempo_s": reloj, "evento": "cola", "pendientes": len(pendientes)})

        if pendientes or len(movimientos) != p.movimientos or finalizados != p.movimientos:
            raise RuntimeError("La simulación terminó con demanda sin procesar.")

        lista = sorted(movimientos.values(), key=lambda m: (m["inicio_s"], m["numero"]))
        for m in lista:
            m["espera_s"] = m["inicio_s"] - m["llegada_s"]
            m["ciclo_movimiento_s"] = m["fin_s"] - m["llegada_s"]
        terminados = [m for m in lista if m["fin_s"] <= p.duracion_turno_s]

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
                "pallets_terminados_totales": sum(m["tipo"] == "producto_terminado" for m in propios),
                "pallets_terminados_turno": sum(m["tipo"] == "producto_terminado" and m["fin_s"] <= p.duracion_turno_s for m in propios),
                "suministros_totales": sum(m["tipo"] == "suministro" for m in propios),
                "suministros_turno": sum(m["tipo"] == "suministro" and m["fin_s"] <= p.duracion_turno_s for m in propios),
                "ocupado_turno_s": ocupado, "libre_turno_s": p.duracion_turno_s - ocupado,
                "utilizacion_pct": 100 * ocupado / p.duracion_turno_s,
                "distancia_vacia_m": vacia, "distancia_cargada_m": cargada, "distancia_total_m": vacia + cargada,
                "posicion_final": vehiculos[agv]["posicion"],
            })

        total = max(m["fin_s"] for m in lista)
        kpis = {
            "completados_turno": len(terminados), "backlog_corte": p.movimientos - len(terminados),
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

        pt = [m for m in lista if m["tipo"] == "producto_terminado"]
        suministros = [m for m in lista if m["tipo"] == "suministro"]
        pt_turno = sum(m["fin_s"] <= p.duracion_turno_s for m in pt)
        suministros_turno = sum(m["fin_s"] <= p.duracion_turno_s for m in suministros)
        fin_pt = max(m["fin_s"] for m in pt)
        kpis.update({
            "pallets_terminados_requeridos": p.pallets_terminados,
            "pallets_terminados_turno": pt_turno,
            "pallets_terminados_pendientes": p.pallets_terminados - pt_turno,
            "cumplimiento_pct": 100 * pt_turno / p.pallets_terminados,
            "cumple": pt_turno == p.pallets_terminados,
            "tiempo_producto_terminado_s": fin_pt,
            "throughput_pt_h": pt_turno / (p.duracion_turno_s / 3600),
            "capacidad_disponible_pct": 100 - kpis["utilizacion_media_pct"],
            "suministros_requeridos": p.suministros_requeridos,
            "suministros_turno": suministros_turno,
            "suministros_pendientes": p.suministros_requeridos - suministros_turno,
            "movimientos_logisticos_totales": p.movimientos,
            "margen_pt_s": max(0, p.duracion_turno_s - fin_pt),
            "exceso_pt_s": max(0, fin_pt - p.duracion_turno_s),
        })
        kpis.update(calcular_capacidad(lista, traza, p.duracion_turno_s, cantidad_agv))
        grafo = Path(__file__).resolve().parents[2] / "data/red_agv_grafo_actualizado.json"
        parametros_salida = asdict(p)
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
            "supuestos": SUPUESTOS + (["Batería lineal temporal: autonomía 8 h, carga completa 3 h, reserva operativa 20%; batería inicial 100%. Una plaza por cargador."] if bateria else []),
            "limitaciones": [v.replace(" ni batería/recarga sin datos validados", "") for v in LIMITACIONES] if bateria else LIMITACIONES,
            "alcance_kpis": "Pallet completado = producto terminado descargado en almacén. Suministro y retiro se contabilizan como movimientos logísticos separados.",
            "kpis": kpis, "por_agv": detalle, "movimientos": lista, "eventos": traza,
        }


def comparar_flotas(parametros=None, demanda=None):
    simulador = SimuladorFlota(parametros, demanda)
    return [simulador.ejecutar(n) for n in (2, 3, 4, 5)]


def minimo_suficiente(resultados):
    return min((r["numero_agv"] for r in resultados if r["kpis"]["pallets_terminados_pendientes"] == 0), default=None)


def exportar_json(resultados):
    return json.dumps(resultados, ensure_ascii=False, indent=2, allow_nan=False)
