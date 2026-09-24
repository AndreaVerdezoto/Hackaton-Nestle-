"""Trazabilidad digital de pallets para una futura integración WMS/SAP.

Este módulo no modifica la simulación ni despacha AGV. Traduce los movimientos
ya calculados por ``SimuladorFlota`` a estados de inventario en tránsito y a
eventos digitales exportables.
"""
from __future__ import annotations


LINEA_POR_NODO = {
    "ControlPoint24": "Cookies 1",
    "ControlPoint25": "Cookies 2",
    "ControlPoint26": "Cookies 3",
    "ControlPoint18": "Chocolate",
    "ControlPoint15": "Wafer",
}


def _hora_turno(segundos: float) -> str:
    """Formatea segundos desde el inicio del turno como HH:MM:SS."""
    total = max(0, int(round(float(segundos))))
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segundos:02d}"


def _movimientos_producto_terminado(resultado):
    return [m for m in resultado.get("movimientos", []) if m.get("tipo") == "producto_terminado"]


def registros_inventario(resultado, tiempo_s):
    """Devuelve el inventario digital visible hasta ``tiempo_s``.

    La solicitud aparece cuando producción genera el retiro. Desde ahí el
    pallet queda PENDIENTE; al iniciar la misión pasa a EN TRÁNSITO y al
    finalizar la descarga en almacén queda ENTREGADO.
    """
    if not resultado:
        return []
    t = max(0.0, float(tiempo_s))
    registros = []
    for m in _movimientos_producto_terminado(resultado):
        if m["llegada_s"] > t:
            continue
        if t < m["inicio_s"]:
            estado = "PENDIENTE"
            actualizacion_s = m["llegada_s"]
            agv = "—"
        elif t < m["fin_s"]:
            estado = "EN TRÁNSITO"
            actualizacion_s = m["inicio_s"]
            agv = m["agv"]
        else:
            estado = "ENTREGADO"
            actualizacion_s = m["fin_s"]
            agv = m["agv"]
        registros.append({
            "id_pallet": m["id_pallet"],
            "id_ciclo": m.get("id_ciclo"),
            "origen": LINEA_POR_NODO.get(m["origen"], m["origen"]),
            "destino": "Almacén",
            "estado": estado,
            "agv": agv,
            "ultima_actualizacion_s": actualizacion_s,
            "ultima_actualizacion": _hora_turno(actualizacion_s),
            "movimiento": m["numero"],
        })
    return sorted(registros, key=lambda r: (r["ultima_actualizacion_s"], r["movimiento"]), reverse=True)


def eventos_inventario(resultado, tiempo_s=None):
    """Genera los eventos de movimiento terminados, listos para una interfaz.

    El payload es deliberadamente genérico: demuestra qué información podría
    sincronizarse con WMS/SAP sin afirmar una integración real con Nestlé.
    """
    if not resultado:
        return []
    limite = float("inf") if tiempo_s is None else max(0.0, float(tiempo_s))
    eventos = []
    for m in _movimientos_producto_terminado(resultado):
        if m["fin_s"] > limite:
            continue
        eventos.append({
            "tipo_evento": "MOVIMIENTO_PALLET_COMPLETADO",
            "pallet": m["id_pallet"],
            "ciclo": m.get("id_ciclo"),
            "origen": LINEA_POR_NODO.get(m["origen"], m["origen"]),
            "origen_nodo": m["origen"],
            "destino": "Almacén",
            "destino_nodo": m["destino"],
            "agv": m["agv"],
            "estado": "ENTREGADO",
            "movimiento": f"M-{m['numero']:03d}",
            "tiempo_simulado_s": m["fin_s"],
            "hora_turno": _hora_turno(m["fin_s"]),
        })
    return sorted(eventos, key=lambda e: (e["tiempo_simulado_s"], e["movimiento"]))
