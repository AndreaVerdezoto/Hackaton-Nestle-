"""Consulta del estado a un instante simulado; no despacha ni modifica misiones."""
import json
import math
from pathlib import Path
from app.models.bateria import MODELO_BATERIA
from app.services.bateria_flota import bateria_en_instante


def cargar_mapa():
    return json.loads((Path(__file__).resolve().parents[2] / "data/red_agv_grafo_actualizado.json").read_text(encoding="utf-8"))


def distancia_en_tiempo(trayecto, segundos, parametros):
    distancia = trayecto["distancia_m"]
    v, a, d = (parametros[k] for k in ("velocidad_maxima_ms", "aceleracion_ms2", "desaceleracion_ms2"))
    pico = min(v, math.sqrt(2 * distancia * a * d / (a + d)))
    acelerando, frenando = pico/a, pico/d
    total = trayecto["tiempo_s"]
    t = max(0, min(segundos, total))
    if t <= acelerando:
        return 0.5*a*t*t
    if t >= total - frenando:
        return max(0, distancia - 0.5*d*(total-t)**2)
    return 0.5*a*acelerando**2 + pico*(t-acelerando)


def posicion(trayecto, segundos, parametros, mapa):
    nodos = {n["id"]: (n["x"], n["y"]) for n in mapa["nodos"]}
    pesos = {}
    for e in mapa["aristas"]:
        pesos[e["origen"], e["destino"]] = e["distancia_m"]
        if e.get("bidireccional"):
            pesos[e["destino"], e["origen"]] = e["distancia_m"]
    ruta = trayecto["ruta"]
    restante = distancia_en_tiempo(trayecto, segundos, parametros) / parametros["factor_escala_metros_por_unidad"]
    for origen, destino in zip(ruta, ruta[1:]):
        largo = pesos[origen, destino]
        if restante <= largo and largo > 0:
            f = restante/largo
            x, y = nodos[origen]; u, v = nodos[destino]
            return (x+(u-x)*f, y+(v-y)*f)
        restante -= largo
    return nodos[ruta[-1]]


def estado_en_instante(resultado, tiempo_s, mapa=None):
    mapa = mapa or cargar_mapa()
    p = resultado["parametros"]
    t = max(0, min(tiempo_s, resultado["kpis"]["tiempo_total_s"]))
    nodos = {n["id"]: (n["x"], n["y"]) for n in mapa["nodos"]}
    flota = []
    movimientos = resultado["movimientos"]
    for agv in resultado["por_agv"]:
        nombre = agv["agv"]
        recargas = resultado.get("recargas", {}).get(nombre, [])
        propios = [m for m in movimientos if m["agv"] == nombre]
        tareas = [(m["inicio_s"], "mision", m) for m in propios if m["inicio_s"] <= t]
        tareas += [(r["inicio_s"], "recarga", r) for r in recargas if r["inicio_s"] <= t]
        item = {"agv": nombre, "estado": "DISPONIBLE", "destino": "—", "origen": "—", "pallet": "—", "pallet_asignado": "—", "mision": "—",
                "posicion": nodos[p["ubicacion_inicial"]], "ruta": []}
        if tareas:
            _, tipo, tarea = max(tareas, key=lambda q: q[0])
            item["posicion"] = nodos[tarea["destino"]]
            if t < tarea["fin_s"]:
                item["destino"] = tarea["destino"]
                if tipo == "recarga":
                    if t < tarea["llegada_s"]:
                        item["estado"] = "VIAJANDO_A_CARGADOR"
                        item["ruta"] = tarea["viaje"]["ruta"]
                        item["posicion"] = posicion(tarea["viaje"], t-tarea["inicio_s"], p, mapa)
                    elif t < tarea["inicio_carga_s"]:
                        item["estado"] = "ESPERANDO_CARGADOR"
                    else:
                        item["estado"] = "CARGANDO_BATERIA"
                else:
                    item["mision"] = f"M-{tarea['numero']:03d}"
                    item["origen"] = tarea["origen"]
                    item["pallet_asignado"] = tarea["id_pallet"]
                    local = t-tarea["inicio_s"]
                    fases = [("VIAJANDO_A_RECOGIDA", tarea["vacio"]["tiempo_s"], "vacio"),
                             ("ESPERANDO_PRODUCTO", tarea["espera_disponibilidad_s"], None),
                             ("CARGANDO_PALLET", tarea["carga_s"], None),
                             ("TRANSPORTANDO", tarea["cargado"]["tiempo_s"], "cargado"),
                             ("DESCARGANDO_PALLET", tarea["descarga_s"], None)]
                    for estado, duracion, viaje in fases:
                        if local < duracion:
                            item["estado"] = estado
                            item["posicion"] = posicion(tarea[viaje], local, p, mapa) if viaje else nodos[tarea["destino"] if estado == "DESCARGANDO_PALLET" else tarea["origen"]]
                            item["ruta"] = tarea[viaje]["ruta"] if viaje else []
                            item["pallet"] = tarea["id_pallet"] if estado in ("CARGANDO_PALLET", "TRANSPORTANDO", "DESCARGANDO_PALLET") else "—"
                            if estado == "VIAJANDO_A_RECOGIDA":
                                item["destino"] = tarea["origen"]
                            break
                        local -= duracion
        nivel = bateria_en_instante(recargas, t)
        item.update(bateria=nivel, uso_restante_s=MODELO_BATERIA.uso_restante_s(nivel),
                    carga_restante_s=MODELO_BATERIA.carga_restante_s(nivel) if item["estado"] == "CARGANDO_BATERIA" else None,
                    bateria_inicial=100, recargas_iniciadas=sum(r["inicio_carga_s"] <= t for r in recargas),
                    tiempo_recarga_s=sum(max(0, min(t, r["fin_s"])-r["inicio_carga_s"]) for r in recargas),
                    misiones_completadas=sum(m["fin_s"] <= t for m in propios))
        item["tiempo_operativo_s"] = t-item["tiempo_recarga_s"]
        item["tiempo_ocupado_s"] = sum(max(0, min(t,m["fin_s"])-m["inicio_s"]) for m in propios)
        no_disponible = sum(max(0, min(t,r["fin_s"])-r["inicio_s"]) for r in recargas)
        item["tiempo_libre_s"] = max(0, t-item["tiempo_ocupado_s"]-no_disponible)
        item["distancia_vacia_m"] = sum(distancia_en_tiempo(m["vacio"],t-m["inicio_s"],p) for m in propios)
        item["distancia_vacia_m"] += sum(distancia_en_tiempo(r["viaje"],t-r["inicio_s"],p) for r in recargas)
        item["distancia_cargada_m"] = sum(distancia_en_tiempo(m["cargado"],t-m["inicio_s"]-m["vacio"]["tiempo_s"]-m["espera_disponibilidad_s"]-m["carga_s"],p) for m in propios)
        item["distancia_total_m"] = item["distancia_vacia_m"]+item["distancia_cargada_m"]
        flota.append(item)
    pendientes = [m for m in movimientos if m["llegada_s"] <= t < m["inicio_s"]]
    activas = [m for m in movimientos if m["inicio_s"] <= t < m["fin_s"]]
    ocupado = sum(max(0, min(t, m["fin_s"])-m["inicio_s"]) for m in movimientos)
    return {"tiempo_s": t, "flota": flota, "pendientes": pendientes, "activas": activas,
            "completados": sum(m["tipo"] == "producto_terminado" and m["fin_s"] <= t for m in movimientos),
            "utilizacion_pct": 100*ocupado/(t*len(flota)) if t else 0}
