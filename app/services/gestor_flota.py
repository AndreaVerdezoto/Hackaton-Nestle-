from datetime import datetime
from pathlib import Path
import heapq
import json

from app.models.solicitud import PrioridadSolicitud


class GestorFlota:
    """Servicios compartidos de red y prioridad usados por el simulador actual."""

    MAPEO_UBICACIONES = {
        "ALMACEN": "ControlPoint7",
    }

    NODOS_PRODUCTO_TERMINADO = {
        "COOKIE_1": "ControlPoint24",
        "COOKIE_2": "ControlPoint25",
        "COOKIE_3": "ControlPoint26",
        "CHOCOLATE": "ControlPoint18",
        "WAFER": "ControlPoint15",
    }

    def __init__(self):
        self.grafo = {}
        self.ahora = datetime.now
        self.construir_red()

    # ---------------------------------------------------------
    # RED / GRAFO
    # ---------------------------------------------------------

    def construir_red(self):
        ruta = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "red_agv_grafo_actualizado.json"
        )

        if not ruta.exists():
            raise FileNotFoundError("Falta data/red_agv_grafo_actualizado.json")

        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)

        for nodo in datos["nodos"]:
            self.grafo[nodo["id"]] = []

        for arista in datos["aristas"]:
            origen = arista["origen"]
            destino = arista["destino"]
            distancia = float(arista["distancia_m"])

            self.grafo[origen].append((destino, distancia))

            if arista["bidireccional"]:
                self.grafo[destino].append((origen, distancia))

    def resolver_nodo(self, ubicacion):
        if ubicacion in self.grafo:
            return ubicacion

        if ubicacion in self.MAPEO_UBICACIONES:
            return self.MAPEO_UBICACIONES[ubicacion]

        raise ValueError(f"No existe mapeo para {ubicacion}")

    def obtener_ruta(self, origen, destino):
        """Ruta mínima por distancia usando Dijkstra."""
        origen = self.resolver_nodo(origen)
        destino = self.resolver_nodo(destino)

        distancias = {nodo: float("inf") for nodo in self.grafo}
        anteriores = {nodo: None for nodo in self.grafo}
        distancias[origen] = 0
        pendientes = [(0, origen)]

        while pendientes:
            distancia_actual, nodo_actual = heapq.heappop(pendientes)

            if distancia_actual > distancias[nodo_actual]:
                continue

            if nodo_actual == destino:
                break

            for vecino, distancia in self.grafo[nodo_actual]:
                nueva_distancia = distancia_actual + distancia

                if nueva_distancia < distancias[vecino]:
                    distancias[vecino] = nueva_distancia
                    anteriores[vecino] = nodo_actual
                    heapq.heappush(pendientes, (nueva_distancia, vecino))

        if distancias[destino] == float("inf"):
            raise ValueError(f"No existe ruta entre {origen} y {destino}")

        ruta = []
        actual = destino
        while actual is not None:
            ruta.append(actual)
            actual = anteriores[actual]
        ruta.reverse()

        return ruta, distancias[destino]

    # ---------------------------------------------------------
    # PRIORIDAD DE SOLICITUDES
    # ---------------------------------------------------------

    def calcular_score_solicitud(self, solicitud):
        puntos = {
            PrioridadSolicitud.BAJA: 0,
            PrioridadSolicitud.NORMAL: 10,
            PrioridadSolicitud.ALTA: 20,
        }
        minutos = (self.ahora() - solicitud.fecha_creacion).total_seconds() / 60
        return puntos[solicitud.prioridad] + minutos
