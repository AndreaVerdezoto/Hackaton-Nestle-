"""Interpretación de eventos ya calculados; no interviene en el despacho."""
import math


def calcular_capacidad(movimientos, eventos, turno_s, cantidad_agv):
    tolerancia = 1e-9  # Exclusivamente para ruido numérico en la clasificación.
    pt = [m for m in movimientos if m["tipo"] == "producto_terminado"]
    esperas = [m["inicio_s"] - m["llegada_s"] for m in pt]
    trabajo = math.fsum(m["duracion_servicio_s"] for m in movimientos)
    disponible = turno_s * cantidad_agv
    hay_espera = any(m["inicio_s"] - m["llegada_s"] > tolerancia for m in movimientos)
    # Criterio explícito para esta corrida, no prueba de estabilidad a largo plazo.
    estado = ("INSUFICIENTE" if trabajo > disponible + tolerancia else
              "SATURADA" if hay_espera else "SUFICIENTE")
    pendientes = [m for m in pt if m["fin_s"] > turno_s]
    ultimo = max(pt, key=lambda m: m["fin_s"])
    return {
        "capacidad_logistica": estado,
        "espera_agv_media_pt_s": math.fsum(esperas) / len(pt),
        "espera_agv_maxima_pt_s": max(esperas),
        "pallets_esperaron_agv": sum(e > tolerancia for e in esperas),
        "backlog_maximo_agv": max((e["pendientes"] for e in eventos if e["evento"] == "cola"), default=0),
        "carga_trabajo_requerida_pct": 100 * trabajo / disponible,
        "pt_sin_asignar_corte": sum(m["inicio_s"] > turno_s for m in pendientes),
        "pt_en_servicio_corte": sum(m["inicio_s"] <= turno_s for m in pendientes),
        "pt_tardios_sin_espera_agv": sum(m["inicio_s"] - m["llegada_s"] <= tolerancia for m in pendientes),
        "ultimo_pt_llegada_s": ultimo["llegada_s"],
        "ultimo_pt_espera_agv_s": ultimo["inicio_s"] - ultimo["llegada_s"],
        "ultimo_pt_servicio_s": ultimo["duracion_servicio_s"],
    }
