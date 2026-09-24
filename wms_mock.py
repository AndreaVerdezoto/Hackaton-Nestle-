"""WMS de prueba para demostrar integración externa por HTTP.

Arranque multiplataforma:
    python wms_mock.py

Después abrir:
    http://127.0.0.1:8001

No representa el WMS ni SAP reales de Nestlé. Solo demuestra que el gestor
puede enviar automáticamente movimientos a un sistema externo mediante API.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlparse


HOST = "127.0.0.1"
PORT = 8001
_MOVIMIENTOS: list[dict] = []
_LOCK = Lock()


def _json_bytes(data) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def movimientos_recibidos() -> list[dict]:
    with _LOCK:
        return [dict(x) for x in _MOVIMIENTOS]


def limpiar_movimientos() -> None:
    with _LOCK:
        _MOVIMIENTOS.clear()


def _guardar_movimiento(payload: dict) -> tuple[dict, bool]:
    evento_id = str(payload.get("evento_id") or "")
    with _LOCK:
        if evento_id:
            existente = next((x for x in _MOVIMIENTOS if x.get("evento_id") == evento_id), None)
            if existente is not None:
                return dict(existente), False
        guardado = dict(payload)
        guardado["recibido_en"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _MOVIMIENTOS.append(guardado)
        return dict(guardado), True


def _e(valor) -> str:
    return html.escape(str(valor if valor not in (None, "") else "—"))


def _pagina_html() -> bytes:
    registros = movimientos_recibidos()
    ultimo = registros[-1] if registros else None

    if ultimo:
        estado_principal = "Último movimiento recibido correctamente"
        detalle_principal = f"{_e(ultimo.get('pallet'))} · {_e(ultimo.get('origen'))} → {_e(ultimo.get('destino'))}"
        ultimo_pallet = _e(ultimo.get("pallet"))
        ultimo_agv = _e(ultimo.get("agv"))
        ultima_hora = _e(ultimo.get("hora_turno"))
        estado_evento = _e(ultimo.get("estado"))
    else:
        estado_principal = "Esperando movimientos del gestor AGV"
        detalle_principal = "Cuando un pallet sea entregado, aparecerá aquí automáticamente."
        ultimo_pallet = "—"
        ultimo_agv = "—"
        ultima_hora = "—"
        estado_evento = "Esperando"

    filas = []
    for r in reversed(registros[-8:]):
        filas.append(
            "<tr>"
            f"<td><strong>{_e(r.get('pallet'))}</strong></td>"
            f"<td>{_e(r.get('origen'))} → {_e(r.get('destino'))}</td>"
            f"<td>{_e(r.get('agv'))}</td>"
            f"<td><span class='badge'>{_e(r.get('estado'))}</span></td>"
            f"<td>{_e(r.get('hora_turno'))}</td>"
            "</tr>"
        )
    cuerpo = "".join(filas) or '<tr><td colspan="5" class="empty">Aún no se han recibido movimientos.</td></tr>'

    documento = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta http-equiv="refresh" content="2">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WMS de prueba</title>
<style>
*{{box-sizing:border-box}}
:root{{--rojo:#c42336;--rojo-osc:#b31e32;--rojo-suave:#fbeaec;--borde:#dfe4ea;--texto:#202938;--muted:#687588;--blanco:#ffffff}}
body{{margin:0;background:#f5f6f8;color:var(--texto);font-family:Inter,Arial,sans-serif}}
main{{max-width:980px;margin:32px auto;padding:0 20px}}
.top{{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:18px}}
.title{{margin:0;font-size:28px;color:var(--texto)}}
.sub{{margin:4px 0 0;color:var(--muted);font-size:14px}}
.api{{display:inline-flex;align-items:center;gap:7px;background:var(--blanco);color:var(--rojo-osc);border:1px solid var(--borde);border-radius:999px;padding:8px 12px;font-weight:700;font-size:13px;white-space:nowrap}}
.dot{{width:9px;height:9px;border-radius:50%;background:var(--rojo)}}
.statusline{{margin-bottom:18px;padding:14px 16px;border-radius:12px;background:var(--blanco);border:1px solid var(--borde)}}
.statusline strong{{display:block;color:var(--rojo-osc);margin-bottom:4px;font-size:16px}}
.statusline span{{color:var(--muted);font-size:14px}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}}
.stat{{background:var(--blanco);border:1px solid var(--borde);border-radius:12px;padding:15px}}
.stat small{{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}}
.stat strong{{font-size:19px;color:var(--texto)}}
.card{{background:var(--blanco);border:1px solid var(--borde);border-radius:14px;overflow:hidden}}
.cardhead{{padding:15px 18px;border-bottom:1px solid #dfe4ea;font-weight:700;color:var(--rojo-osc);background:#ffffff}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:11px 13px;border-bottom:1px solid #edf1f4;text-align:left;font-size:13px}}
th{{background:#f2f5f8;color:#657285;font-size:11px;text-transform:uppercase}}
tr:last-child td{{border-bottom:0}}
.badge{{display:inline-block;background:var(--rojo-suave);color:var(--rojo-osc);padding:4px 8px;border-radius:999px;font-weight:700;font-size:11px;border:1px solid var(--borde)}}
.empty{{text-align:center;color:#7d8999;padding:26px}}
.note{{margin-top:12px;color:#687588;font-size:12px;text-align:center}}
.details{{margin-top:16px;background:var(--blanco);border:1px solid var(--borde);border-radius:12px;overflow:hidden}}
.details summary{{list-style:none;cursor:pointer;padding:13px 16px;font-weight:700;color:var(--rojo-osc);background:#ffffff}}
.details summary::-webkit-details-marker{{display:none}}
.details summary::after{{content:'▾';float:right;color:var(--rojo)}}
.details[open] summary::after{{content:'▴'}}
.details-body{{padding:14px 16px;border-top:1px solid #dfe4ea;color:#334155;font-size:14px}}
.codechip{{display:inline-block;background:var(--rojo-suave);color:var(--rojo-osc);border:1px solid var(--borde);border-radius:999px;padding:4px 10px;font-weight:700;margin-left:6px}}
@media(max-width:700px){{.top{{align-items:flex-start;flex-direction:column}}.stats{{grid-template-columns:repeat(2,1fr)}}.card{{overflow-x:auto}}table{{min-width:620px}}}}
</style></head><body><main>
<div class="top"><div><h1 class="title">WMS de prueba</h1><p class="sub">Demostración visual de registro automático desde el gestor AGV</p></div><div class="api"><span class="dot"></span> API conectada</div></div>

<section class="statusline"><strong>{estado_principal}</strong><span>{detalle_principal}</span></section>

<section class="stats">
  <div class="stat"><small>Movimientos recibidos</small><strong>{len(registros)}</strong></div>
  <div class="stat"><small>Último pallet</small><strong>{ultimo_pallet}</strong></div>
  <div class="stat"><small>AGV</small><strong>{ultimo_agv}</strong></div>
  <div class="stat"><small>Estado</small><strong>{estado_evento}</strong></div>
</section>

<section class="card"><div class="cardhead">Últimos movimientos registrados en WMS</div>
<table><thead><tr><th>Pallet</th><th>Movimiento</th><th>AGV</th><th>Estado</th><th>Hora</th></tr></thead><tbody>{cuerpo}</tbody></table></section>

<details class="details"><summary>Tipo de archivo y formato</summary><div class="details-body">Los movimientos se envían mediante API como objeto <span class="codechip">JSON</span>.</div></details>

<p class="note">Demo de integración. No representa el WMS ni SAP reales de Nestlé.</p>
</main></body></html>"""
    return documento.encode("utf-8")


class WMSHandler(BaseHTTPRequestHandler):
    server_version = "WMSDemo/1.1"

    def log_message(self, formato, *args):
        # Evita llenar la terminal con las comprobaciones repetidas de salud.
        if self.command == "GET" and urlparse(self.path).path == "/api/salud":
            return
        print(f"[WMS] {self.address_string()} - {formato % args}")

    def _responder(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _responder_json(self, status: int, data):
        self._responder(status, _json_bytes(data), "application/json; charset=utf-8")

    def do_GET(self):
        ruta = urlparse(self.path).path
        if ruta == "/":
            self._responder(200, _pagina_html(), "text/html; charset=utf-8")
            return
        if ruta == "/api/salud":
            self._responder_json(200, {"servicio": "WMS_DEMO", "estado": "activo", "movimientos": len(movimientos_recibidos())})
            return
        if ruta == "/api/movimientos":
            self._responder_json(200, {"movimientos": movimientos_recibidos()})
            return
        self._responder_json(404, {"error": "Ruta no encontrada"})

    def do_POST(self):
        ruta = urlparse(self.path).path
        if ruta != "/api/movimientos":
            self._responder_json(404, {"error": "Ruta no encontrada"})
            return
        try:
            longitud = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(longitud).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            self._responder_json(400, {"ok": False, "error": "JSON inválido"})
            return
        if not isinstance(payload, dict):
            self._responder_json(400, {"ok": False, "error": "El cuerpo debe ser un objeto JSON"})
            return
        requeridos = ("pallet", "origen", "destino", "agv", "estado")
        faltantes = [campo for campo in requeridos if not payload.get(campo)]
        if faltantes:
            self._responder_json(422, {"ok": False, "error": "Faltan campos", "campos": faltantes})
            return
        guardado, nuevo = _guardar_movimiento(payload)
        self._responder_json(200, {
            "ok": True,
            "mensaje": "Movimiento recibido" if nuevo else "Movimiento ya recibido",
            "duplicado": not nuevo,
            "evento_id": guardado.get("evento_id"),
            "pallet": guardado.get("pallet"),
        })


def crear_servidor(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), WMSHandler)


def main():
    servidor = crear_servidor()
    host, port = servidor.server_address[:2]
    print("WMS de prueba activo")
    print(f"Panel:    http://{host}:{port}")
    print(f"Endpoint: http://{host}:{port}/api/movimientos")
    print("Ctrl+C para detener.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nWMS detenido.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
