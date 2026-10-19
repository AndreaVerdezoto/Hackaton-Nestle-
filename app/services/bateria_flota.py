"""Planificación simple de recargas sobre el reloj del simulador existente."""
from app.models.agv import EstadoAGV
from app.models.bateria import MODELO_BATERIA


def bateria_en_instante(recargas, tiempo_s):
    nivel, anterior = 100.0, 0.0
    for r in recargas:
        inicio, fin = r["inicio_carga_s"], r["fin_s"]
        if tiempo_s <= inicio:
            break
        nivel = MODELO_BATERIA.nivel(nivel, inicio - anterior)
        nivel = MODELO_BATERIA.nivel(nivel, min(tiempo_s, fin) - inicio, cargando=True)
        anterior = min(tiempo_s, fin)
        if tiempo_s < fin:
            return nivel
    return MODELO_BATERIA.nivel(nivel, tiempo_s - anterior)


class BateriaFlota:
    def __init__(self, vehiculos, cargadores, trayecto, programar):
        if not cargadores:
            raise ValueError("Indique los nodos de cargadores existentes; no se inventan ubicaciones.")
        self.vehiculos, self.trayecto, self.programar = vehiculos, trayecto, programar
        self.libres = dict.fromkeys(cargadores, 0.0)
        self.recargas = {agv: [] for agv in vehiculos}
        self.modelo = MODELO_BATERIA
        for agv in vehiculos:
            self.programar(self.modelo.uso_restante_s(100), "reserva_bateria", agv)

    def nivel(self, agv, t):
        return bateria_en_instante(self.recargas[agv], t)

    def recargar(self, agv, t):
        opciones = []
        for nodo, libre in self.libres.items():
            try:
                viaje = self.trayecto(self.vehiculos[agv].ubicacion, nodo)
            except ValueError:
                continue
            llegada = t + viaje["tiempo_s"]
            inicio = max(llegada, libre)
            nivel = self.nivel(agv, t) - self.modelo.consumo(inicio - t)
            if nivel >= -1e-9:
                opciones.append((viaje["distancia_m"], nodo, viaje, llegada, inicio, max(0, nivel)))
        if not opciones:
            raise ValueError(f"{agv}: no puede alcanzar/esperar un cargador con la batería disponible.")
        _, nodo, viaje, llegada, inicio, nivel = min(opciones, key=lambda x: (x[0], x[1]))
        fin = inicio + self.modelo.carga_restante_s(nivel)
        self.recargas[agv].append({"agv": agv, "origen": self.vehiculos[agv].ubicacion,
            "destino": nodo, "inicio_s": t, "llegada_s": llegada, "inicio_carga_s": inicio,
            "fin_s": fin, "viaje": viaje, "bateria_inicio": self.nivel(agv, t), "bateria_conexion": nivel})
        self.libres[nodo] = fin
        self.vehiculos[agv].estado = EstadoAGV.CARGANDO
        self.vehiculos[agv].mision_actual = "RECARGA"
        self.programar(fin, "fin_recarga", agv)

    def evento(self, tipo, agv, t, seguir):
        if tipo == "reserva_bateria":
            if (seguir and self.vehiculos[agv].esta_disponible()
                    and self.modelo.necesita_recarga(self.nivel(agv, t))):
                self.recargar(agv, t)
            return True
        if tipo == "fin_recarga":
            self.vehiculos[agv].ubicacion = self.recargas[agv][-1]["destino"]
            self.vehiculos[agv].estado = EstadoAGV.DISPONIBLE
            self.vehiculos[agv].mision_actual = None
            if seguir:
                self.programar(t + self.modelo.uso_restante_s(100), "reserva_bateria", agv)
            return True
        return False
