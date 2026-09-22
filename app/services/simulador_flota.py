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
from app.services.gestor_flota import GestorFlota
from app.services.indicadores_capacidad import calcular_capacidad

VERSION_MODELO = "producto_terminado_independiente_v2"

LINEAS = tuple(GestorFlota.NODOS_SUMINISTRO)
SUPUESTOS = [
    "Distribución equilibrada/round-robin: supuesto editable por falta de distribución real por línea. La demanda explícita permite sustituirlo con datos de planta.",
    "Llegadas distribuidas uniformemente durante el turno por falta de histórico de demanda.",
    "Carga, descarga, peso, espera de retorno, escala y posición inicial son supuestos editables.",
    "Producto terminado y suministro son demandas independientes; suministro base 0 por falta de dato de planta, sin relación 1:1.",
    "Cada trayecto operacional comienza y termina a velocidad cero; no se detiene en cada arista del grafo.",
]
LIMITACIONES = [
    "No es simulación física 3D: no modela motores, neumáticos, masa dinámica ni sensores.",
    "No incluye congestión, conflictos entre AGV, tráfico humano, fallas ni batería/recarga sin datos validados.",
    "Las distancias se derivan del grafo del modelo. El factor de escala debe calibrarse con medidas reales de planta antes de una implementación.",
    "El dimensionamiento depende de distancias, tiempos de carga/descarga, demanda y demás parámetros utilizados. Debe recalibrarse con datos reales de planta antes de una implementación.",
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
    movimientos_suministro: int = 0
    duracion_turno_s: float = 28800.0
    velocidad_maxima_ms: float = 2.0
    aceleracion_ms2: float = 1.0
    desaceleracion_ms2: float = 1.0
    tiempo_carga_s: float = 30.0
    tiempo_descarga_s: float = 30.0
    espera_disponibilidad_retorno_s: float = 0.0
    factor_escala_metros_por_unidad: float = 1.0
    ubicacion_inicial: str = "ControlPoint7"
    peso_pallet_kg: float = 500.0

    @property
    def movimientos(self):
        return self.pallets_terminados + self.movimientos_suministro

    def __post_init__(self):
        if type(self.pallets_terminados) is not int or self.pallets_terminados < 1:
            raise ValueError("Pallets terminados debe ser un entero positivo.")
        if type(self.movimientos_suministro) is not int or self.movimientos_suministro < 0:
            raise ValueError("Suministros debe ser un entero no negativo.")
        for nombre in ("duracion_turno_s", "velocidad_maxima_ms", "aceleracion_ms2",
                       "desaceleracion_ms2", "factor_escala_metros_por_unidad", "peso_pallet_kg"):
            _numero(nombre, getattr(self, nombre))
        for nombre in ("tiempo_carga_s", "tiempo_descarga_s", "espera_disponibilidad_retorno_s"):
            _numero(nombre, getattr(self, nombre), cero=True)
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


def generar_demanda(parametros):
    """Dos flujos independientes, uniformes y round-robin; sin retornos implícitos."""
    demanda = []
    for tipo, cantidad in (("producto_terminado", parametros.pallets_terminados),
                           ("suministro", parametros.movimientos_suministro)):
        for i in range(cantidad):
            demanda.append(DemandaMision(len(demanda) + 1, i * parametros.duracion_turno_s / cantidad,
                                          LINEAS[i % len(LINEAS)], tipo))
    return tuple(demanda)


class SimuladorFlota:
    def __init__(self, parametros=None, demanda=None):
        self.parametros = parametros or ParametrosSimulacion()
        self.demanda = tuple(demanda) if demanda is not None else generar_demanda(self.parametros)
        self.red = GestorFlota(habilitar_flexsim=False)
        self._rutas = {}
        p = self.parametros
        if (len(self.demanda) != p.movimientos or
                sum(c.tipo == "producto_terminado" for c in self.demanda) != p.pallets_terminados):
            raise ValueError("La demanda no coincide con la cantidad de movimientos.")
        for i, c in enumerate(self.demanda):
            _numero("llegada", c.llegada_s, cero=True)
            if (c.id_mision != i + 1 or c.linea not in LINEAS or c.llegada_s >= p.duracion_turno_s
                    or c.tipo not in ("producto_terminado", "suministro")
                    or not isinstance(c.prioridad, PrioridadSolicitud)):
                raise ValueError("Demanda inválida: revise misiones, líneas, prioridades y llegadas dentro del turno.")
        # Validación anticipada: jamás sustituir una ruta inexistente por distancia cero.
        self.trayecto(p.ubicacion_inicial, "ALMACEN")
        for c in self.demanda:
            origen, destino = self.extremos(c)
            self.trayecto(p.ubicacion_inicial, origen)
            self.trayecto(origen, destino)

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

    def ejecutar(self, cantidad_agv):
        if type(cantidad_agv) is not int or cantidad_agv not in (2, 3, 4, 5):
            raise ValueError("Seleccione una flota de 2, 3, 4 o 5 AGV.")
        p = self.parametros
        vehiculos = {f"AGV_{i:02d}": {"posicion": p.ubicacion_inicial, "mision": None}
                     for i in range(1, cantidad_agv + 1)}
        eventos, pendientes, movimientos, traza = [], [], {}, []
        solicitudes = {}
        reloj = 0.0
        secuencia = 0
        backlog_maximo = 0
        self.red.ahora = lambda: datetime(2000, 1, 1) + timedelta(seconds=reloj)

        def programar(t, tipo, identificador):
            nonlocal secuencia
            secuencia += 1
            heapq.heappush(eventos, (t, 1 if tipo == "llegada" else 0, secuencia, tipo, identificador))

        def iniciar(c, agv):
            numero = c.id_mision
            origen, destino = self.extremos(c)
            vacio = self.trayecto(vehiculos[agv]["posicion"], origen)
            cargado = self.trayecto(origen, destino)
            espera = p.espera_disponibilidad_retorno_s if c.tipo == "producto_terminado" else 0.0
            duracion = vacio["tiempo_s"] + espera + p.tiempo_carga_s + cargado["tiempo_s"] + p.tiempo_descarga_s
            fin = reloj + duracion
            if not math.isfinite(fin):
                raise ValueError("Los parámetros producen un tiempo no finito.")
            movimientos[numero] = {
                "numero": numero, "id_pallet": f"PALLET_{numero:03d}", "id_mision": c.id_mision,
                "tipo": c.tipo, "linea": c.linea,
                "agv": agv, "origen": origen, "destino": destino,
                "llegada_s": c.llegada_s, "inicio_s": reloj, "fin_s": fin,
                "vacio": vacio, "cargado": cargado, "espera_disponibilidad_s": espera,
                "carga_s": p.tiempo_carga_s, "descarga_s": p.tiempo_descarga_s,
                "duracion_servicio_s": duracion,
            }
            vehiculos[agv]["mision"] = c.id_mision
            traza.append({"tiempo_s": reloj, "evento": "inicio", "movimiento": numero, "agv": agv})
            programar(fin, "fin", numero)

        for c in self.demanda:
            s = SolicitudTraslado(str(c.id_mision), f"PALLET_{c.id_mision:03d}", c.linea,
                                   p.peso_pallet_kg, *self.extremos(c), c.prioridad)
            s.fecha_creacion = datetime(2000, 1, 1) + timedelta(seconds=c.llegada_s)
            solicitudes[c.id_mision] = s
            programar(c.llegada_s, "llegada", c.id_mision)

        while eventos:
            reloj = eventos[0][0]  # Salto lógico directo, sin esperar tiempo real.
            while eventos and eventos[0][0] == reloj:
                _, _, _, tipo, identificador = heapq.heappop(eventos)
                if tipo == "llegada":
                    pendientes.append(identificador)
                    traza.append({"tiempo_s": reloj, "evento": "llegada", "mision": identificador})
                else:
                    m = movimientos[identificador]
                    agv = m["agv"]
                    vehiculos[agv]["posicion"] = m["destino"]
                    traza.append({"tiempo_s": reloj, "evento": "fin", "movimiento": identificador, "agv": agv})
                    vehiculos[agv]["mision"] = None
            pendientes.sort(key=lambda i: (-self.red.calcular_score_solicitud(solicitudes[i]), i))
            while pendientes:
                disponibles = [a for a, v in vehiculos.items() if v["mision"] is None]
                if not disponibles:
                    break
                # Reutiliza el criterio de menor distancia. Sin penalización de batería no validada.
                agv = min(disponibles, key=lambda a: (self.trayecto(vehiculos[a]["posicion"], self.extremos(self.demanda[pendientes[0] - 1])[0])["distancia_m"], a))
                iniciar(self.demanda[pendientes.pop(0) - 1], agv)
            backlog_maximo = max(backlog_maximo, len(pendientes))
            traza.append({"tiempo_s": reloj, "evento": "cola", "pendientes": len(pendientes)})

        if pendientes or len(movimientos) != p.movimientos:
            raise RuntimeError("La simulación terminó con demanda sin procesar.")
        lista = [movimientos[i] for i in sorted(movimientos)]
        for m in lista:
            m["espera_s"] = m["inicio_s"] - m["llegada_s"]
            m["ciclo_movimiento_s"] = m["fin_s"] - m["llegada_s"]
        terminados = [m for m in lista if m["fin_s"] <= p.duracion_turno_s]
        detalle = []
        for agv in vehiculos:
            propios = [m for m in lista if m["agv"] == agv]
            ocupado = min(p.duracion_turno_s, math.fsum(
                max(0.0, min(m["fin_s"], p.duracion_turno_s) - m["inicio_s"]) for m in propios
            ))  # Evita exceder 100% por redondeo de punto flotante.
            vacia = sum(m["vacio"]["distancia_m"] for m in propios)
            cargada = sum(m["cargado"]["distancia_m"] for m in propios)
            detalle.append({
                "agv": agv, "movimientos_totales": len(propios),
                "movimientos_turno": sum(m["fin_s"] <= p.duracion_turno_s for m in propios),
                "pallets_terminados_totales": sum(m["tipo"] == "producto_terminado" for m in propios),
                "pallets_terminados_turno": sum(m["tipo"] == "producto_terminado" and m["fin_s"] <= p.duracion_turno_s for m in propios),
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
        }
        pt = [m for m in lista if m["tipo"] == "producto_terminado"]
        pt_turno = sum(m["fin_s"] <= p.duracion_turno_s for m in pt)
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
            "suministros_requeridos": p.movimientos_suministro,
            "suministros_turno": sum(m["tipo"] == "suministro" for m in terminados),
            "suministros_pendientes": p.movimientos_suministro - sum(m["tipo"] == "suministro" for m in terminados),
            "movimientos_logisticos_totales": p.movimientos,
            "margen_pt_s": max(0, p.duracion_turno_s - fin_pt),
            "exceso_pt_s": max(0, fin_pt - p.duracion_turno_s),
        })
        kpis.update(calcular_capacidad(lista, traza, p.duracion_turno_s, cantidad_agv))
        grafo = Path(__file__).resolve().parents[2] / "data/red_agv_grafo_actualizado.json"
        return {
            "version_modelo": VERSION_MODELO, "modo": "analisis_python",
            "timestamp": datetime.now(timezone.utc).isoformat(), "numero_agv": cantidad_agv,
            "parametros": asdict(p), "demanda": [asdict(c) for c in self.demanda],
            "grafo_sha256": hashlib.sha256(grafo.read_bytes()).hexdigest(),
            "supuestos": SUPUESTOS, "limitaciones": LIMITACIONES,
            "alcance_kpis": "Completados, backlog y utilización al corte; promedios y distancias sobre toda la demanda hasta terminar. Backlog máximo: cola tras despachos instantáneos.",
            "kpis": kpis, "por_agv": detalle, "movimientos": lista, "eventos": traza,
        }


def comparar_flotas(parametros=None, demanda=None):
    simulador = SimuladorFlota(parametros, demanda)
    return [simulador.ejecutar(n) for n in (2, 3, 4, 5)]


def minimo_suficiente(resultados):
    return min((r["numero_agv"] for r in resultados if r["kpis"]["pallets_terminados_pendientes"] == 0), default=None)


def exportar_json(resultados):
    return json.dumps(resultados, ensure_ascii=False, indent=2, allow_nan=False)
