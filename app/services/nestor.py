"""Néstor: capa consultiva intralogística, sin IA ni integraciones externas."""
from __future__ import annotations

import unicodedata

from app.services.analizador_operativo import AnalizadorOperativo


class Nestor:
    def __init__(self, resultado=None, analizador=None):
        if analizador is None:
            if resultado is None:
                raise ValueError("Indique un resultado de SimuladorFlota o un AnalizadorOperativo.")
            analizador = AnalizadorOperativo(resultado)
        self.analizador = analizador

    def responder(self, pregunta: str) -> dict:
        intencion = self._detectar_intencion(pregunta)
        metricas = self.analizador.obtener_metricas()
        problemas = self.analizador.detectar_problemas()
        no_disponibles = self.analizador.metricas_no_disponibles()
        activos = self._problemas_activos(problemas)

        if intencion == "ESTADO_GENERAL":
            usadas = self._tomar(metricas, (
                "misiones_completadas", "solicitudes_pendientes_backlog",
                "tiempo_promedio_espera_s", "tiempo_promedio_ciclo_s",
                "utilizacion_flota_pct",
            ))
            relacionados = activos
            if relacionados:
                texto = (
                    "Los datos muestran {misiones} misiones completadas, {backlog} solicitudes pendientes, "
                    "{utilizacion} de utilizacion promedio y {espera} de espera media. "
                    "Se detectaron desviaciones operativas en las metricas disponibles."
                ).format(
                    misiones=self._fmt(usadas.get("misiones_completadas")),
                    backlog=self._fmt(usadas.get("solicitudes_pendientes_backlog")),
                    utilizacion=self._pct(usadas.get("utilizacion_flota_pct")),
                    espera=self._seg(usadas.get("tiempo_promedio_espera_s")),
                )
            else:
                texto = (
                    "Los datos no muestran problemas detectados. "
                    "La flota completo {misiones} misiones, con {backlog} solicitudes pendientes y "
                    "{utilizacion} de utilizacion promedio."
                ).format(
                    misiones=self._fmt(usadas.get("misiones_completadas")),
                    backlog=self._fmt(usadas.get("solicitudes_pendientes_backlog")),
                    utilizacion=self._pct(usadas.get("utilizacion_flota_pct")),
                )
            return self._respuesta(intencion, texto, usadas, relacionados, [], relacionados)

        if intencion == "DIAGNOSTICO":
            usadas = self._tomar(metricas, (
                "solicitudes_pendientes_backlog", "backlog_maximo",
                "tiempo_promedio_espera_s", "tiempo_promedio_ciclo_s",
                "utilizacion_flota_pct",
            ))
            relacionados = self._filtrar_problemas(activos, {
                "BACKLOG_ELEVADO", "ESPERA_ELEVADA", "UTILIZACION_ALTA",
            })
            texto = (
                "Los datos muestran {backlog} solicitudes pendientes, espera media de {espera} "
                "y utilizacion promedio de {utilizacion}. "
                "Esto podria estar asociado con presion operativa o acumulacion en ciertos periodos, "
                "pero estos datos no demuestran una causa unica."
            ).format(
                backlog=self._fmt(usadas.get("solicitudes_pendientes_backlog")),
                espera=self._seg(usadas.get("tiempo_promedio_espera_s")),
                utilizacion=self._pct(usadas.get("utilizacion_flota_pct")),
            )
            return self._respuesta(intencion, texto, usadas, relacionados, [], relacionados)

        if intencion == "BATERIA":
            claves = ("bateria_promedio_pct", "bateria_minima_pct", "cantidad_recargas")
            usadas = self._tomar(metricas, claves)
            relacionados = self._filtrar_problemas(activos, {"BATERIA_BAJA"})
            limitaciones = self._limitaciones(no_disponibles, claves)
            if limitaciones:
                texto = (
                    "No hay datos suficientes para evaluar completamente la bateria. "
                    "Las metricas necesarias no estan disponibles en este resultado."
                )
            else:
                texto = (
                    "La bateria promedio fue {promedio}, la minima fue {minima} "
                    "y se registraron {recargas} recargas."
                ).format(
                    promedio=self._pct(usadas.get("bateria_promedio_pct")),
                    minima=self._pct(usadas.get("bateria_minima_pct")),
                    recargas=self._fmt(usadas.get("cantidad_recargas")),
                )
                if relacionados:
                    texto += " Se detecto una condicion de bateria baja en la operacion."
                else:
                    texto += " No se detecto riesgo operativo de bateria."
            return self._respuesta(intencion, texto, usadas, relacionados, limitaciones, relacionados)

        if intencion == "UTILIZACION":
            claves = ("utilizacion_flota_pct", "utilizacion_por_agv_pct")
            usadas = self._tomar(metricas, claves)
            relacionados = self._filtrar_problemas(activos, {"UTILIZACION_ALTA"})
            limitaciones = self._limitaciones(no_disponibles, claves)
            mas_usado = self._agv_mas_usado(usadas.get("utilizacion_por_agv_pct"))
            texto = "La utilizacion promedio de la flota fue {utilizacion}.".format(
                utilizacion=self._pct(usadas.get("utilizacion_flota_pct"))
            )
            if mas_usado:
                texto += " El AGV con mayor utilizacion fue {agv} con {valor}.".format(
                    agv=mas_usado[0], valor=self._pct(mas_usado[1])
                )
            if relacionados:
                texto += " Se detecto poca holgura operativa en la flota."
            return self._respuesta(intencion, texto, usadas, relacionados, limitaciones, relacionados)

        if intencion == "DISTANCIAS":
            claves = (
                "distancia_total_m", "distancia_cargada_m", "distancia_vacia_m",
                "porcentaje_desplazamiento_vacio",
            )
            usadas = self._tomar(metricas, claves)
            relacionados = self._filtrar_problemas(activos, {"DESPLAZAMIENTO_VACIO_ALTO"})
            limitaciones = self._limitaciones(no_disponibles, claves)
            texto = (
                "Los AGV recorrieron {total} en total: {cargada} con carga y {vacia} sin carga. "
                "El desplazamiento vacio representa {pct}."
            ).format(
                total=self._metros(usadas.get("distancia_total_m")),
                cargada=self._metros(usadas.get("distancia_cargada_m")),
                vacia=self._metros(usadas.get("distancia_vacia_m")),
                pct=self._pct(usadas.get("porcentaje_desplazamiento_vacio")),
            )
            if relacionados:
                texto += " La proporcion de recorridos vacios requiere revision."
            return self._respuesta(intencion, texto, usadas, relacionados, limitaciones, relacionados)

        return {
            "tipo": "NO_RECONOCIDA",
            "respuesta": (
                "Néstor analiza el estado operativo y las desviaciones detectadas. "
                "Puedes consultarme sobre estado de la operación, alertas, tiempos de espera, "
                "utilización, batería o recorridos."
            ),
            "metricas_utilizadas": {},
            "problemas_relacionados": [],
            "limitaciones": ["Intencion no reconocida por reglas locales; no se uso IA."],
            "acciones_revision": [],
        }

    def _respuesta(self, tipo, texto, metricas, problemas, limitaciones, problemas_para_acciones):
        acciones_revision = self._acciones_revision(problemas_para_acciones)
        return {
            "tipo": tipo,
            "respuesta": texto,
            "metricas_utilizadas": metricas,
            "problemas_relacionados": problemas,
            "limitaciones": limitaciones,
            "acciones_revision": acciones_revision,
        }

    def _detectar_intencion(self, pregunta):
        texto = self._normalizar(pregunta)
        if not texto:
            return "NO_RECONOCIDA"
        if self._contiene(texto, ("bateria", "recarga", "recargas", "energia")):
            return "BATERIA"
        if self._contiene(texto, ("utilizacion", "utilizacion de los agv", "trabajo mas", "trabajo mas", "ocupacion", "ocupado")):
            return "UTILIZACION"
        if self._contiene(texto, ("recorridos vacios", "recorrido vacio", "sin carga", "distancia", "recorrieron")):
            return "DISTANCIAS"
        if self._contiene(texto, ("por que", "porque", "pendientes", "aumento la espera", "aumento espera", "lentos", "lento")):
            return "DIAGNOSTICO"
        if self._contiene(texto, ("como esta operando", "como esta la operacion", "hay algun problema", "estado general", "operacion", "operando", "alerta", "alertas", "desviacion", "desviaciones")):
            return "ESTADO_GENERAL"
        return "NO_RECONOCIDA"

    @staticmethod
    def _normalizar(valor):
        if not isinstance(valor, str):
            return ""
        texto = unicodedata.normalize("NFD", valor.lower())
        texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
        return " ".join(texto.split())

    @staticmethod
    def _contiene(texto, patrones):
        return any(patron in texto for patron in patrones)

    @staticmethod
    def _problemas_activos(problemas):
        return [p for p in problemas if p.get("codigo") != "SIN_PROBLEMAS"]

    @staticmethod
    def _filtrar_problemas(problemas, codigos):
        return [p for p in problemas if p.get("codigo") in codigos]

    @staticmethod
    def _tomar(metricas, claves):
        return {clave: metricas.get(clave) for clave in claves}

    @staticmethod
    def _limitaciones(no_disponibles, claves):
        return [f"{clave}: {no_disponibles[clave]}" for clave in claves if clave in no_disponibles]

    @staticmethod
    def _agv_mas_usado(utilizacion_por_agv):
        if not isinstance(utilizacion_por_agv, dict) or not utilizacion_por_agv:
            return None
        return max(utilizacion_por_agv.items(), key=lambda item: (item[1], item[0]))

    @staticmethod
    def _fmt(valor):
        if valor is None:
            return "dato no disponible"
        if isinstance(valor, float) and not valor.is_integer():
            return f"{valor:.1f}"
        return str(int(valor)) if isinstance(valor, float) else str(valor)

    def _pct(self, valor):
        return "dato no disponible" if valor is None else f"{float(valor):.1f} %"

    def _seg(self, valor):
        return "dato no disponible" if valor is None else f"{float(valor):.1f} s"

    def _metros(self, valor):
        return "dato no disponible" if valor is None else f"{float(valor):.1f} m"

    @staticmethod
    def _acciones_revision(problemas):
        por_codigo = {
            "BACKLOG_ELEVADO": "Revisar las franjas con mayor cola y el nivel de carga operativa en esos periodos.",
            "ESPERA_ELEVADA": "Revisar la secuencia de llegadas y la disponibilidad de AGV en los picos de espera.",
            "UTILIZACION_ALTA": "Validar si la flota conserva holgura antes de aumentar la demanda del turno.",
            "BATERIA_BAJA": "Revisar el plan de recarga y la disponibilidad de cargadores.",
            "DESPLAZAMIENTO_VACIO_ALTO": "Revisar ubicaciones iniciales y balance de origenes/destinos para reducir reposicionamientos.",
        }
        acciones = []
        for problema in problemas:
            texto = por_codigo.get(problema.get("codigo"))
            if texto and texto not in acciones:
                acciones.append(texto)
            if len(acciones) == 2:
                break
        return acciones
