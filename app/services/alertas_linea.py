"""Demoras de retiro: lectura temporal de movimientos, sin simulación ni despacho.

120 s es un parámetro de demostración, no un límite validado por Nestlé.
El registro conserva un evento por escenario/solicitud/tipo, aunque cambie el umbral.
"""
from copy import deepcopy
import math


UMBRAL_DEMO_S = 120.0
# Absoluta, en segundos: no crece con la duración de la corrida.
TOLERANCIA_ESPERA_S = 1e-6
VERSION_REGISTRO = 2
TIPO_ALERTA = "ESPERA_SIN_ASIGNACION"
NOMBRES_LINEAS = {
    "COOKIE_1": "Cookies 1", "COOKIE_2": "Cookies 2", "COOKIE_3": "Cookies 3",
    "CHOCOLATE": "Chocolate", "WAFER": "Wafer",
}


def _numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def _identificador(movimiento):
    valor = movimiento.get("numero", movimiento.get("id_mision"))
    return str(valor) if isinstance(valor, (str, int)) and not isinstance(valor, bool) and str(valor).strip() else None


def supera_umbral(espera_s, umbral_s):
    """Mayor estricto, ignorando diferencias de hasta un microsegundo."""
    return espera_s > umbral_s and not math.isclose(
        espera_s, umbral_s, rel_tol=0, abs_tol=TOLERANCIA_ESPERA_S,
    )


def normalizar_registro(registro, tiempo_s=None):
    """Copia y migra registros antiguos; nunca inventa una detección.

    Conserva los hechos ya observados aunque se retroceda el reloj. ``estado``,
    ``espera_s`` y ``espera_final_s`` se proyectan al instante consultado; la
    primera espera observada y su detección permanecen inmutables.
    """
    if not isinstance(registro, dict):
        return None
    r = deepcopy(registro)
    t = tiempo_s if _numero(tiempo_s) else r.get("ultimo_t")
    r["version_registro"] = VERSION_REGISTRO
    r.setdefault("leidas", [])
    eventos = r.get("eventos")
    r["eventos"] = eventos if isinstance(eventos, dict) else {}
    for clave, evento in list(r["eventos"].items()):
        if not isinstance(evento, dict):
            del r["eventos"][clave]
            continue
        evento.setdefault("id", clave)
        evento.setdefault("nombre", NOMBRES_LINEAS.get(evento.get("linea"), evento.get("linea") or "Línea no disponible"))
        # El registro anterior guardaba aquí la espera de la primera observación.
        evento.setdefault("espera_observada_s", evento.get("espera_s"))
        if not _numero(evento["espera_observada_s"]):
            evento["espera_observada_s"] = None
        # No atribuir la política nueva a alertas generadas por versiones anteriores.
        evento.setdefault("tolerancia_espera_s", None)
        if not _numero(evento.get("detectada_s")):
            evento["detectada_s"] = None
        llegada, umbral = evento.get("llegada_s"), evento.get("umbral_s")
        if not _numero(evento.get("supera_desde_s")):
            evento["supera_desde_s"] = llegada + umbral if _numero(llegada) and _numero(umbral) else None
        asignada = evento.get("asignada_s")
        evento["espera_final_s"] = None
        if _numero(t) and _numero(llegada):
            if _numero(asignada) and llegada <= asignada <= t:
                evento.update(estado="ATENDIDA", espera_final_s=asignada-llegada, espera_s=asignada-llegada)
            else:
                evento.update(estado="ACTIVA", espera_s=max(0, t-llegada))
            if _numero(evento["detectada_s"]) and evento["detectada_s"] > t:
                evento["estado"] = "NO_VISIBLE"
    return r


def _agrupar(solicitudes):
    grupos = {}
    for solicitud in solicitudes:
        linea = solicitud["linea"]
        grupo = grupos.setdefault(linea, {
            "linea": linea, "nombre": NOMBRES_LINEAS.get(linea, linea),
            "cantidad": 0, "espera_maxima_s": 0, "solicitudes": [],
        })
        grupo["cantidad"] += 1
        grupo["espera_maxima_s"] = max(grupo["espera_maxima_s"], solicitud["espera_s"])
        grupo["solicitudes"].append(solicitud)
    return sorted(grupos.values(), key=lambda g: (-g["espera_maxima_s"], g["linea"]))


def consultar_alertas(resultado, tiempo_s, umbral_s=UMBRAL_DEMO_S, *, estado=None):
    """Devuelve activas y atendidas visibles a t; nunca expone la asignación futura.

    Se puede reutilizar la instantánea de estado_en_instante mediante ``estado``.
    Sin ella basta el contrato de movimientos: no se necesita cargar rutas/mapas,
    ni exigir ``producciones`` a una exportación antigua.
    """
    if not _numero(umbral_s) or umbral_s < 0:
        raise ValueError("El umbral debe ser un número finito mayor o igual a cero.")
    salida = {"tiempo_s": None, "umbral_s": float(umbral_s), "activas": [],
              "resueltas": [], "por_linea": [], "asignaciones": [], "limitaciones": []}
    if not _numero(tiempo_s):
        salida["limitaciones"].append("No hay un instante válido del reloj 2D para consultar demoras.")
        return salida
    t = max(0, tiempo_s)
    resultado = resultado if isinstance(resultado, dict) else {}
    kpis = resultado.get("kpis")
    limite = kpis.get("tiempo_total_s") if isinstance(kpis, dict) else None
    if _numero(limite) and limite >= 0:
        t = min(t, limite)
    salida["tiempo_s"] = t
    movimientos = resultado.get("movimientos")
    if not isinstance(movimientos, list):
        salida["limitaciones"].append("El resultado no contiene movimientos para identificar las demoras.")
        return salida
    conteos = {}
    for m in movimientos:
        if (isinstance(m, dict) and m.get("tipo") == "producto_terminado"
                and _numero(m.get("llegada_s")) and m["llegada_s"] <= t):
            identificador = _identificador(m)
            conteos[identificador] = conteos.get(identificador, 0) + 1
    pendientes = None
    if estado is not None and estado.get("tiempo_s") == t:
        pendientes = {_identificador(m) for m in estado["pendientes"]}
    omitidas = 0
    for m in movimientos:
        if not isinstance(m, dict):
            omitidas += 1
            continue
        llegada = m.get("llegada_s")
        # No informar siquiera de defectos de datos correspondientes al futuro.
        if _numero(llegada) and llegada > t:
            continue
        if m.get("tipo") not in (None, "producto_terminado"):
            continue
        identificador = _identificador(m)
        inicio, linea = m.get("inicio_s"), m.get("linea")
        if (m.get("tipo") is None or identificador is None or conteos.get(identificador) != 1
                or not isinstance(linea, str) or not linea.strip()
                or not _numero(llegada) or llegada < 0 or not _numero(inicio) or inicio < llegada):
            omitidas += 1
            continue
        pendiente = llegada <= t < inicio
        if pendientes is not None:
            pendiente = identificador in pendientes
        espera = t - llegada if pendiente else inicio - llegada
        if inicio <= t:
            salida["asignaciones"].append({"solicitud": identificador, "asignada_s": inicio, "agv": m.get("agv")})
        if not supera_umbral(espera, umbral_s):
            continue
        item = {"solicitud": identificador, "id_pallet": m.get("id_pallet"),
                "linea": linea, "nombre": NOMBRES_LINEAS.get(linea, linea),
                "llegada_s": llegada, "espera_s": espera, "umbral_s": float(umbral_s),
                # Frontera matemática: la comparación es >, con tolerancia.
                "supera_desde_s": llegada + umbral_s,
                "estado": "ACTIVA" if pendiente else "ATENDIDA"}
        if pendiente:
            salida["activas"].append(item)
        elif inicio <= t:
            item.update(asignada_s=inicio, agv=m.get("agv"))
            salida["resueltas"].append(item)
    salida["por_linea"] = _agrupar(salida["activas"])
    if omitidas:
        salida["limitaciones"].append(
            f"No se pueden evaluar {omitidas} registros por datos incompletos, incoherentes o identificadores repetidos."
        )
    return salida


def actualizar_registro(registro, escenario_id, consulta, *, revision=0, leidas=False):
    """Registro independiente del chat, aislado por escenario y sin duplicados.

    Cambiar umbral reevalúa activas, sin añadir atendidas anteriores al cambio.
    Un salto incorpora contexto silenciosamente; retroceder oculta eventos futuros.
    Reiniciar conserva los IDs: reproducir la misma solicitud no la vuelve a anunciar.
    """
    if registro and registro.get("escenario_id") not in (None, escenario_id):
        raise ValueError("El registro pertenece a otro escenario.")
    r = normalizar_registro(registro) if registro else {
        "escenario_id": escenario_id, "eventos": {}, "leidas": [],
        "ultimo_t": 0, "revision": revision, "umbral_s": consulta["umbral_s"],
        "desde_config_s": 0,
    }
    r.setdefault("escenario_id", escenario_id)
    r.setdefault("umbral_s", consulta["umbral_s"])
    r.setdefault("ultimo_t", 0)
    r.setdefault("revision", revision)
    r.setdefault("desde_config_s", 0)
    t = consulta["tiempo_s"]
    if t is None:
        return normalizar_registro(r)
    cambio = r["umbral_s"] != consulta["umbral_s"]
    salto = revision != r["revision"] or t < r["ultimo_t"]
    if cambio:
        r["desde_config_s"] = t
    elif salto:
        r["desde_config_s"] = min(t, r["desde_config_s"])
    visibles = []
    for asignacion in consulta["asignaciones"]:
        clave = f"{escenario_id}:{asignacion['solicitud']}:{TIPO_ALERTA}"
        if clave in r["eventos"]:
            r["eventos"][clave].update(asignada_s=asignacion["asignada_s"], agv=asignacion.get("agv"))
    for alerta in consulta["activas"] + consulta["resueltas"]:
        clave = f"{escenario_id}:{alerta['solicitud']}:{TIPO_ALERTA}"
        if alerta["estado"] == "ATENDIDA" and alerta["asignada_s"] <= r["desde_config_s"]:
            continue
        if clave not in r["eventos"]:
            r["eventos"][clave] = {**alerta, "id": clave, "tipo": TIPO_ALERTA,
                                    "detectada_s": t,
                                    "espera_observada_s": alerta["espera_s"],
                                    "tolerancia_espera_s": TOLERANCIA_ESPERA_S,
                                    "revision_deteccion": revision,
                                    "origen": "cambio_umbral" if cambio else "salto" if salto else "reproduccion"}
            if salto:
                r["leidas"].append(clave)
        # La primera observación conserva su umbral, detección y espera observada.
        if alerta["estado"] == "ATENDIDA":
            r["eventos"][clave].update(asignada_s=alerta["asignada_s"], agv=alerta.get("agv"))
    for clave, evento in r["eventos"].items():
        if _numero(evento.get("detectada_s")) and evento["detectada_s"] <= t:
            visibles.append(clave)
    if leidas:
        r["leidas"] = list(set(r["leidas"]) | set(visibles))
    r.update(ultimo_t=t, revision=revision, umbral_s=consulta["umbral_s"])
    return normalizar_registro(r, t)


def historial_visible(registro, tiempo_s):
    """Filtra y reconstruye cada aviso según el reloj, incluso tras un retroceso."""
    if not registro or not _numero(tiempo_s):
        return []
    filas = []
    for evento in normalizar_registro(registro, tiempo_s)["eventos"].values():
        # Un registro antiguo sin detección no permite afirmar que era visible a t.
        if not _numero(evento.get("detectada_s")) or evento["detectada_s"] > tiempo_s:
            continue
        fila = dict(evento)
        asignada = fila.get("asignada_s")
        if _numero(asignada) and asignada <= tiempo_s:
            fila["estado"] = "ATENDIDA"
        else:
            fila["estado"] = "ACTIVA"
            fila.pop("asignada_s", None)
            fila.pop("agv", None)
        filas.append(fila)
    return sorted(filas, key=lambda e: (e["detectada_s"], e["id"]), reverse=True)


def nuevas_sin_leer(registro, tiempo_s):
    leidas = set(registro.get("leidas", [])) if registro else set()
    return sum(e["id"] not in leidas for e in historial_visible(registro, tiempo_s))
