"""Conector HTTP mínimo para integrar el gestor con un WMS externo.

El gestor trabaja con su propio evento interno. Este módulo es la única capa que
conoce el endpoint externo. Para una integración real con Nestlé se reemplaza
``preparar_payload_wms`` y/o ``WMS_ENDPOINT`` según el contrato que entregue el
WMS, sin tocar Dijkstra, la simulación ni la lógica de flota.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


WMS_ENDPOINT = os.getenv("WMS_ENDPOINT", "http://127.0.0.1:8001/api/movimientos")
WMS_SALUD_ENDPOINT = os.getenv("WMS_SALUD_ENDPOINT", "http://127.0.0.1:8001/api/salud")


def preparar_payload_wms(evento: dict) -> dict:
    """Traduce el evento interno al contrato genérico usado por la demo WMS.

    Este contrato NO pretende ser el formato privado de Nestlé. Es el punto de
    adaptación que se sustituiría cuando Nestlé entregue su especificación.
    """
    movimiento = str(evento.get("movimiento", ""))
    pallet = str(evento.get("pallet", ""))
    escenario_id = str(evento.get("escenario_id", ""))
    partes_id = [x for x in (escenario_id, pallet, movimiento) if x]
    return {
        "evento_id": ":".join(partes_id),
        "escenario_id": escenario_id or None,
        "tipo_evento": evento.get("tipo_evento", "MOVIMIENTO_PALLET_COMPLETADO"),
        "pallet": pallet,
        "ciclo": evento.get("ciclo"),
        "origen": evento.get("origen"),
        "origen_nodo": evento.get("origen_nodo"),
        "destino": evento.get("destino"),
        "destino_nodo": evento.get("destino_nodo"),
        "agv": evento.get("agv"),
        "estado": evento.get("estado"),
        "movimiento": movimiento,
        "tiempo_simulado_s": evento.get("tiempo_simulado_s"),
        "hora_turno": evento.get("hora_turno"),
        "fuente": "GESTOR_AGV_NESTLE",
        "version_contrato": 1,
    }


def _respuesta_json(respuesta):
    cuerpo = respuesta.read().decode("utf-8", errors="replace")
    if not cuerpo:
        return None
    try:
        return json.loads(cuerpo)
    except json.JSONDecodeError:
        return cuerpo


def enviar_evento_wms(evento: dict, endpoint: str | None = None, timeout_s: float = 0.75) -> dict:
    """Envía un evento por HTTP POST sin propagar fallos de red al simulador."""
    url = endpoint or WMS_ENDPOINT
    payload = preparar_payload_wms(evento)
    solicitud = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(solicitud, timeout=timeout_s) as respuesta:
            status = int(getattr(respuesta, "status", respuesta.getcode()))
            return {
                "ok": 200 <= status < 300,
                "status": status,
                "endpoint": url,
                "respuesta": _respuesta_json(respuesta),
                "payload": payload,
            }
    except HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "endpoint": url,
            "error": str(exc),
            "payload": payload,
        }
    except (URLError, OSError, TimeoutError) as exc:
        return {
            "ok": False,
            "status": None,
            "endpoint": url,
            "error": str(getattr(exc, "reason", exc)),
            "payload": payload,
        }


def verificar_wms(endpoint: str | None = None, timeout_s: float = 0.4) -> dict:
    """Comprueba si el receptor WMS de demo está disponible."""
    url = endpoint or WMS_SALUD_ENDPOINT
    solicitud = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(solicitud, timeout=timeout_s) as respuesta:
            status = int(getattr(respuesta, "status", respuesta.getcode()))
            return {
                "ok": 200 <= status < 300,
                "status": status,
                "endpoint": url,
                "respuesta": _respuesta_json(respuesta),
            }
    except HTTPError as exc:
        return {"ok": False, "status": exc.code, "endpoint": url, "error": str(exc)}
    except (URLError, OSError, TimeoutError) as exc:
        return {
            "ok": False,
            "status": None,
            "endpoint": url,
            "error": str(getattr(exc, "reason", exc)),
        }
