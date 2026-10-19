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
        pregunta_normalizada = self._normalizar(pregunta)
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
                texto = self._texto_estado_con_problemas(usadas, relacionados, pregunta_normalizada)
            else:
                texto = (
                    "La flota completó {misiones} y alcanzó una utilización promedio de {utilizacion}. "
                    "La operación cerró con {pendientes}, sin alertas operativas relevantes."
                ).format(
                    misiones=self._misiones(usadas.get("misiones_completadas")),
                    pendientes=self._solicitudes(usadas.get("solicitudes_pendientes_backlog")),
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
            cantidad_pendiente = usadas.get("solicitudes_pendientes_backlog")
            if cantidad_pendiente == 0:
                texto = (
                    "No quedaron solicitudes pendientes al cierre del turno. "
                    "La flota terminó el escenario con una utilización de {utilizacion} y {espera} de espera media."
                ).format(
                    espera=self._seg(usadas.get("tiempo_promedio_espera_s")),
                    utilizacion=self._pct(usadas.get("utilizacion_flota_pct")),
                )
            else:
                texto = (
                    "La flota terminó el escenario con una utilización de {utilizacion} y {espera} de espera media. "
                    "Esto puede haber contribuido a que quedara {pendientes}, aunque los datos no permiten atribuirlo a una única causa."
                ).format(
                    pendientes=self._solicitudes(cantidad_pendiente),
                    espera=self._seg(usadas.get("tiempo_promedio_espera_s")),
                    utilizacion=self._pct(usadas.get("utilizacion_flota_pct")),
                )
            return self._respuesta(intencion, texto, usadas, relacionados, [], relacionados)

        if intencion == "BATERIA":
            claves = ("bateria_promedio_pct", "bateria_minima_pct", "cantidad_recargas")
            usadas = self._tomar(metricas, claves)
            relacionados = self._filtrar_problemas(activos, {"BATERIA_BAJA"})
            limitaciones = self._limitaciones(no_disponibles, claves)
            bateria_incompleta = any(usadas.get(clave) is None for clave in claves)
            if limitaciones or bateria_incompleta:
                limitaciones = ["No hay suficiente información para determinarlo."]
                texto = "Esta corrida no registró datos de batería ni recargas, así que no puedo determinarlo para este escenario."
            else:
                texto = (
                    "La batería promedio fue de {promedio}, con un mínimo de {minima}. "
                    "Se registraron {recargas} durante el escenario."
                ).format(
                    promedio=self._pct(usadas.get("bateria_promedio_pct")),
                    minima=self._pct(usadas.get("bateria_minima_pct")),
                    recargas=self._recargas(usadas.get("cantidad_recargas")),
                )
                if relacionados:
                    texto += " Se detectó una condición de batería baja que conviene revisar."
                else:
                    texto += " No se detectó riesgo operativo de batería."
            return self._respuesta(intencion, texto, usadas, relacionados, limitaciones, relacionados)

        if intencion == "UTILIZACION":
            claves = ("utilizacion_flota_pct", "utilizacion_por_agv_pct")
            usadas = self._tomar(metricas, claves)
            relacionados = self._filtrar_problemas(activos, {"UTILIZACION_ALTA"})
            limitaciones = self._limitaciones(no_disponibles, claves)
            mas_usado = self._agv_mas_usado(usadas.get("utilizacion_por_agv_pct"))
            if mas_usado and self._es_consulta_agv_mas_usado(pregunta_normalizada):
                texto = "{agv} tuvo la mayor utilización, con {valor}. El promedio de la flota fue de {utilizacion}.".format(
                    agv=mas_usado[0],
                    valor=self._pct(mas_usado[1]),
                    utilizacion=self._pct(usadas.get("utilizacion_flota_pct")),
                )
            else:
                texto = "La utilización promedio fue de {utilizacion}.".format(
                    utilizacion=self._pct(usadas.get("utilizacion_flota_pct"))
                )
                if mas_usado:
                    texto += " {agv} presentó la mayor utilización, con {valor}.".format(
                        agv=mas_usado[0], valor=self._pct(mas_usado[1])
                    )
                if relacionados:
                    texto += " La flota operó con poca capacidad libre durante el escenario."
            return self._respuesta(intencion, texto, usadas, relacionados, limitaciones, [])

        if intencion == "DISTANCIAS":
            claves = (
                "distancia_total_m", "distancia_cargada_m", "distancia_vacia_m",
                "porcentaje_desplazamiento_vacio",
            )
            usadas = self._tomar(metricas, claves)
            relacionados = self._filtrar_problemas(activos, {"DESPLAZAMIENTO_VACIO_ALTO"})
            limitaciones = self._limitaciones(no_disponibles, claves)
            texto = (
                "Sí. Los AGVs recorrieron {total} en total y {vacia} fueron sin carga. "
                "Esto representa un {pct} del recorrido total."
            ).format(
                total=self._metros(usadas.get("distancia_total_m")),
                vacia=self._metros(usadas.get("distancia_vacia_m")),
                pct=self._pct(usadas.get("porcentaje_desplazamiento_vacio")),
            )
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
            "limitaciones": ["Intención no reconocida por reglas locales; no se usó IA."],
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
        if self._contiene(texto, ("recorridos vacios", "recorrido vacio", "sin carga", "distancia", "recorrieron", "tuvimos recorridos vacios")):
            return "DISTANCIAS"
        if self._contiene(texto, (
            "por que", "porque", "pendientes", "pendiente",
            "por que quedo una solicitud pendiente",
            "por que quedaron solicitudes pendientes",
            "por que hubo espera", "hubo espera",
            "aumento la espera", "aumento espera",
            "por que estamos lentos", "estamos lentos", "lentos", "lento",
        )):
            return "DIAGNOSTICO"
        if self._contiene(texto, (
            "como esta la flota", "estado de la flota", "como va la flota",
            "como estamos operando", "como esta operando",
            "como va la operacion", "como esta la operacion", "estado de la operacion",
            "como estan los agv", "como estan los agvs",
            "hay algun problema", "estado general", "operacion", "operando",
            "alerta", "alertas", "desviacion", "desviaciones",
        )):
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
        nombres = {
            "bateria_promedio_pct": "No se registró batería promedio en esta simulación.",
            "bateria_minima_pct": "No se registró batería mínima en esta simulación.",
            "cantidad_recargas": "No se registraron recargas en esta simulación.",
            "utilizacion_por_agv_pct": "No se registró el detalle de utilización por AGV.",
            "distancia_total_m": "No se registró la distancia total recorrida.",
            "distancia_cargada_m": "No se registró la distancia recorrida con carga.",
            "distancia_vacia_m": "No se registró la distancia recorrida sin carga.",
            "porcentaje_desplazamiento_vacio": "No se registró el porcentaje de recorridos vacíos.",
        }
        return [nombres.get(clave, "No se registró una métrica necesaria.") for clave in claves if clave in no_disponibles]

    def _texto_estado_con_problemas(self, metricas, problemas, pregunta):
        pendientes = self._solicitudes(metricas.get("solicitudes_pendientes_backlog"))
        utilizacion = self._pct(metricas.get("utilizacion_flota_pct"))
        misiones = self._misiones(metricas.get("misiones_completadas"))
        condiciones = self._condiciones_detectadas(problemas)

        if self._es_consulta_alerta(pregunta):
            texto = self._texto_alertas(condiciones)
            if self._hay_codigo(problemas, "BACKLOG_ELEVADO"):
                texto += " Además, quedó {pendientes} al finalizar el escenario.".format(pendientes=pendientes)
            elif self._hay_codigo(problemas, "UTILIZACION_ALTA"):
                texto += " La utilización promedio fue de {utilizacion}.".format(utilizacion=utilizacion)
            if condiciones:
                return texto
            return texto

        texto = (
            "La flota completó {misiones} y alcanzó una utilización promedio de {utilizacion}. "
            "Quedó {pendientes}"
        ).format(misiones=misiones, utilizacion=utilizacion, pendientes=pendientes)
        if self._hay_codigo(problemas, "UTILIZACION_ALTA"):
            texto += ", por lo que la operación trabajó con poca capacidad libre."
        elif condiciones:
            texto += ". Se observa una condición que conviene revisar."
        else:
            texto += "."
        return texto

    def _condiciones_detectadas(self, problemas):
        condiciones = []
        if self._hay_codigo(problemas, "UTILIZACION_ALTA"):
            condiciones.append("la utilización de la flota fue alta")
        if self._hay_codigo(problemas, "DESPLAZAMIENTO_VACIO_ALTO"):
            condiciones.append("el porcentaje de recorridos sin carga fue elevado")
        if self._hay_codigo(problemas, "ESPERA_ELEVADA"):
            condiciones.append("la espera media fue elevada")
        if self._hay_codigo(problemas, "BATERIA_BAJA"):
            condiciones.append("se detectó una condición de batería baja")
        if self._hay_codigo(problemas, "BACKLOG_ELEVADO") and not condiciones:
            condiciones.append("quedaron solicitudes pendientes al cierre")
        return condiciones

    def _texto_alertas(self, condiciones):
        if not condiciones:
            return "No se observan alertas operativas relevantes."
        if len(condiciones) == 1:
            return "Se observa un punto que requiere atención: {condicion}.".format(condicion=condiciones[0])
        return "Se observan {cantidad} puntos que requieren atención: {condiciones}.".format(
            cantidad=len(condiciones),
            condiciones=self._unir_lista(condiciones),
        )

    @staticmethod
    def _unir_lista(valores):
        if len(valores) <= 1:
            return "".join(valores)
        return ", ".join(valores[:-1]) + " y " + valores[-1]

    @staticmethod
    def _hay_codigo(problemas, codigo):
        return any(problema.get("codigo") == codigo for problema in problemas)

    @staticmethod
    def _es_consulta_alerta(pregunta):
        return any(patron in pregunta for patron in ("problema", "alerta", "desviacion"))

    @staticmethod
    def _es_consulta_agv_mas_usado(pregunta):
        return any(patron in pregunta for patron in ("cual agv", "trabajo mas", "mayor utilizacion", "mas utilizado"))

    @staticmethod
    def _agv_mas_usado(utilizacion_por_agv):
        if not isinstance(utilizacion_por_agv, dict) or not utilizacion_por_agv:
            return None
        return max(utilizacion_por_agv.items(), key=lambda item: (item[1], item[0]))

    def _misiones(self, valor):
        if valor is None:
            return "dato no disponible"
        cantidad = self._entero(valor)
        return f"{cantidad} movimiento logístico" if cantidad == 1 else f"{cantidad} movimientos logísticos"

    def _solicitudes(self, valor):
        if valor is None:
            return "dato no disponible"
        cantidad = self._entero(valor)
        return f"{cantidad} solicitud pendiente" if cantidad == 1 else f"{cantidad} solicitudes pendientes"

    def _recargas(self, valor):
        if valor is None:
            return "dato no disponible"
        cantidad = self._entero(valor)
        return f"{cantidad} recarga" if cantidad == 1 else f"{cantidad} recargas"

    @staticmethod
    def _entero(valor):
        return int(valor) if isinstance(valor, float) and valor.is_integer() else valor

    def _pct(self, valor):
        return "dato no disponible" if valor is None else f"{float(valor):.1f} %"

    def _seg(self, valor):
        return "dato no disponible" if valor is None else f"{float(valor):.1f} s"

    def _metros(self, valor):
        if valor is None:
            return "dato no disponible"
        distancia = float(valor)
        if distancia > 1000:
            return f"{distancia / 1000:.1f} km"
        return f"{distancia:.1f} m"

    @staticmethod
    def _acciones_revision(problemas):
        por_codigo = {
            "BACKLOG_ELEVADO": "Revisar las franjas con mayor cola y el nivel de carga operativa en esos periodos.",
            "ESPERA_ELEVADA": "Revisar la secuencia de llegadas y la disponibilidad de AGV en los picos de espera.",
            "UTILIZACION_ALTA": "Validar si la flota conserva holgura antes de aumentar la demanda del turno.",
            "BATERIA_BAJA": "Revisar el plan de recarga y la disponibilidad de cargadores.",
            "DESPLAZAMIENTO_VACIO_ALTO": "Conviene revisar los desplazamientos vacíos de los AGV hacia los puntos de recogida.",
        }
        acciones = []
        for problema in problemas:
            texto = por_codigo.get(problema.get("codigo"))
            if texto and texto not in acciones:
                acciones.append(texto)
            if len(acciones) == 2:
                break
        return acciones
