"""Métricas derivadas y flujo de caja simple. No modifica el motor operacional."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from uuid import uuid4


def validar_opcionales(datos):
    for nombre, valor in asdict(datos).items():
        if valor is None or isinstance(valor, bool):
            continue
        if not isinstance(valor, (float, int)) or not math.isfinite(valor) or valor < 0:
            raise ValueError(f"{nombre}: introduzca un número finito no negativo o deje el dato pendiente.")


@dataclass(frozen=True)
class LineaBase:
    movimientos_turno: float | None = None
    tiempo_manual_movimiento_s: float | None = None
    perdida_produccion_turno_s: float | None = None
    pallets_terminados_turno: float | None = None
    espera_logistica_media_s: float | None = None
    comparacion_equivalente: bool = False

    def __post_init__(self):
        validar_opcionales(self)


@dataclass(frozen=True)
class ParametrosEconomicos:
    costo_agv: float | None = None
    integracion: float | None = None
    infraestructura: float | None = None
    cargadores: float | None = None
    otros_iniciales: float | None = None
    mantenimiento_anual_agv: float | None = None
    energia_anual: float | None = None
    otros_opex_anuales: float | None = None
    operacion_manual_anual: float | None = None
    personal_transporte_anual: float | None = None
    otros_actuales_anuales: float | None = None
    porcentaje_evitable: float | None = None
    margen_pallet: float | None = None
    pallets_adicionales_turno: float | None = None
    turnos_dia: float | None = None
    dias_anio: float | None = None
    payback_objetivo_anios: float = 3.0
    ahorro_anual_estimado: float | None = None

    def __post_init__(self):
        validar_opcionales(self)
        if self.payback_objetivo_anios is None or self.payback_objetivo_anios <= 0:
            raise ValueError("El objetivo de payback debe ser mayor que cero.")
        if self.porcentaje_evitable is not None and self.porcentaje_evitable > 100:
            raise ValueError("El porcentaje evitable no puede superar 100%.")


def _suma(*valores):
    return None if any(v is None for v in valores) else math.fsum(valores)


def _producto(*valores):
    # Un cero declarado hace nulo el producto; vacío nunca se convierte en cero.
    if any(v == 0 for v in valores):
        return 0.0
    return None if any(v is None for v in valores) else math.prod(valores)


def _minimo_requerido(necesidad, denominador):
    if necesidad is None:
        return None
    if necesidad <= 0:
        return 0.0
    if denominador is None or denominador <= 0:
        return None
    return necesidad / denominador


def calcular_economia(cantidad_agv, parametros):
    if type(cantidad_agv) is not int or cantidad_agv not in (2, 3, 4, 5):
        raise ValueError("La flota debe ser 2, 3, 4 o 5 AGV.")
    p = parametros
    iniciales = _suma(p.integracion, p.infraestructura, p.cargadores, p.otros_iniciales)
    capex = _suma(_producto(cantidad_agv, p.costo_agv), iniciales)
    opex = _suma(_producto(cantidad_agv, p.mantenimiento_anual_agv), p.energia_anual, p.otros_opex_anuales)
    costos_actuales = _suma(p.operacion_manual_anual, p.personal_transporte_anual, p.otros_actuales_anuales)
    ahorro = _producto(costos_actuales, None if p.porcentaje_evitable is None else p.porcentaje_evitable / 100)
    if p.ahorro_anual_estimado is not None:
        ahorro = p.ahorro_anual_estimado  # Sustituye el desglose; nunca se suma dos veces.
    turnos_anio = _producto(p.turnos_dia, p.dias_anio)
    produccion = _producto(p.pallets_adicionales_turno, p.margen_pallet, turnos_anio)
    neto = _suma(produccion, ahorro, None if opex is None else -opex)
    payback = capex / neto if capex is not None and neto is not None and neto > 0 else None
    roi = 100 * neto / capex if neto is not None and capex is not None and capex > 0 else None
    objetivo = p.payback_objetivo_anios
    necesario = _suma(None if capex is None else capex / objetivo, opex, None if ahorro is None else -ahorro)
    minimo_pallets = _minimo_requerido(necesario, _producto(p.margen_pallet, turnos_anio))
    minimo_margen = _minimo_requerido(necesario, _producto(p.pallets_adicionales_turno, turnos_anio))
    ahorro_minimo = _suma(None if capex is None else capex / objetivo, opex,
                         None if produccion is None else -produccion)
    costo_maximo = None if neto is None or iniciales is None else (neto * objetivo - iniciales) / cantidad_agv
    imposible = costo_maximo is not None and costo_maximo < 0
    resultado = {
        "capex": capex, "beneficio_produccion_anual": produccion, "ahorro_operativo_anual": ahorro,
        "beneficio_neto_anual_minimo": None if capex is None else capex / objetivo,
        "opex_anual": opex, "beneficio_neto_anual": neto,
        "payback_anios": payback, "payback_meses": None if payback is None else payback * 12,
        "roi_anual_pct": roi, "payback_objetivo_anios": objetivo,
        "pallets_minimos_turno": minimo_pallets,
        "pallets_enteros_minimos_turno": math.ceil(minimo_pallets) if minimo_pallets is not None else None,
        "margen_minimo_pallet": minimo_margen,
        "ahorro_anual_minimo": max(0.0, ahorro_minimo) if ahorro_minimo is not None else None,
        "costo_maximo_agv": None if imposible else costo_maximo,
        "objetivo_imposible_incluso_agv_gratis": imposible,
        "estado": ("Pendiente de dato de planta" if neto is None else
                   "No rentable bajo los supuestos actuales." if neto <= 0 else
                   "Beneficio neto positivo bajo los supuestos actuales."),
    }
    if any(isinstance(v, (float, int)) and not math.isfinite(v) for v in resultado.values()):
        raise ValueError("Los datos económicos producen valores no finitos; revise su magnitud.")
    return resultado


def calcular_operacion(resultado):
    """Recorta cada fase conocida al turno; no estima movimientos parciales a ojo."""
    turno = resultado["parametros"]["duracion_turno_s"]
    fases = dict.fromkeys(("viaje_vacio_s", "espera_retorno_s", "carga_s", "viaje_cargado_s", "descarga_s"), 0.0)
    for m in resultado["movimientos"]:
        inicio = m["inicio_s"]
        for nombre, duracion in (("viaje_vacio_s", m["vacio"]["tiempo_s"]),
                                 ("espera_retorno_s", m["espera_disponibilidad_s"]),
                                 ("carga_s", m["carga_s"]), ("viaje_cargado_s", m["cargado"]["tiempo_s"]),
                                 ("descarga_s", m["descarga_s"])):
            fases[nombre] += max(0.0, min(inicio + duracion, turno) - inicio)
            inicio += duracion
    total_disponible = turno * resultado["numero_agv"]
    fases["ocupado_s"] = math.fsum(a["ocupado_turno_s"] for a in resultado["por_agv"])
    fases["libre_s"] = math.fsum(a["libre_turno_s"] for a in resultado["por_agv"])
    fases.update({nombre.replace("_s", "_pct"): 100 * valor / total_disponible for nombre, valor in list(fases.items())})
    k = resultado["kpis"]
    fases["recorrido_vacio_pct"] = 100 * k["distancia_vacia_m"] / k["distancia_total_m"] if k["distancia_total_m"] else 0.0
    fases["pallets_terminados_turno"] = sum(m["tipo"] == "producto_terminado" and m["fin_s"] <= turno
                                             for m in resultado["movimientos"])
    return fases


def comparar_linea_base(resultado, base):
    k = resultado["kpis"]
    comparables = base.comparacion_equivalente
    diferencia = k["completados_turno"] - base.movimientos_turno if comparables and base.movimientos_turno is not None else None
    incremento = 100 * diferencia / base.movimientos_turno if diferencia is not None and base.movimientos_turno > 0 else None
    horas = None
    if comparables and base.movimientos_turno is not None and base.tiempo_manual_movimiento_s is not None:
        completados = [m for m in resultado["movimientos"] if m["fin_s"] <= resultado["parametros"]["duracion_turno_s"]]
        if completados:
            servicio_medio = math.fsum(m["duracion_servicio_s"] for m in completados) / len(completados)
            horas = min(base.movimientos_turno, len(completados)) * (base.tiempo_manual_movimiento_s - servicio_medio) / 3600
    reduccion_espera = base.espera_logistica_media_s - k["espera_media_s"] if comparables and base.espera_logistica_media_s is not None else None
    return {"movimientos_adicionales_atendidos": diferencia, "incremento_logistico_pct": incremento,
            "horas_logisticas_recuperadas": horas, "reduccion_espera_media_s": reduccion_espera,
            "produccion_adicional_calculada": None,
            "horas_produccion_recuperadas": None}


def crear_escenario(resultado, base=None, economia=None):
    """Copia completa: los cambios posteriores de widgets no reescriben corridas."""
    base = base or LineaBase()
    economia = economia or ParametrosEconomicos()
    return deepcopy({
        "id": uuid4().hex, "guardado": datetime.now(timezone.utc).isoformat(),
        "resultado": resultado, "linea_base": asdict(base), "parametros_economicos": asdict(economia),
        "operacion": calcular_operacion(resultado), "impacto": comparar_linea_base(resultado, base),
        "economia": calcular_economia(resultado["numero_agv"], economia),
    })


def son_comparables(escenarios):
    if not escenarios:
        return True
    primero = escenarios[0]
    def firma(e):
        r = e["resultado"]
        return r["parametros"], r["demanda"], r["grafo_sha256"], e["linea_base"], e["parametros_economicos"]
    return all(firma(e) == firma(primero) for e in escenarios[1:])
