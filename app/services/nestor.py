"""Néstor: capa consultiva intralogística, sin IA ni integraciones externas."""
from __future__ import annotations

import unicodedata
import math

from app.services.analizador_operativo import AnalizadorOperativo
from app.services.preguntas_nestor import ALTERNATIVAS, obtener_pregunta
from app.services.alertas_linea import UMBRAL_DEMO_S, consultar_alertas


def formatear_duracion(segundos):
    """Mantiene décimas en tiempos cortos y expresa duraciones largas en h/min/s."""
    if segundos is None or not math.isfinite(segundos):
        return "dato no disponible"
    segundos = round(max(0, segundos), 1)
    if segundos < 60:
        return f"{segundos:.1f} s"
    horas, resto = divmod(segundos, 3600)
    minutos, resto = divmod(resto, 60)
    partes = []
    if horas:
        partes.append(f"{int(horas)} h")
    if minutos:
        partes.append(f"{int(minutos)} min")
    if round(resto, 1):
        partes.append(f"{resto:.1f}".rstrip("0").rstrip(".") + " s")
    return " ".join(partes)


class Nestor:
    """Usa el reloj recibido (inicio por defecto) y admite preguntas finales explícitas."""

    def __init__(self, resultado=None, analizador=None, *, tiempo_s=0, umbral_alertas_s=UMBRAL_DEMO_S):
        if analizador is None and resultado is None:
            raise ValueError("Indique un resultado de SimuladorFlota o un AnalizadorOperativo.")
        self._analizador = analizador
        self.resultado = resultado if resultado is not None else getattr(analizador, "resultado", None)
        self.tiempo_s = tiempo_s
        self.umbral_alertas_s = umbral_alertas_s

    @property
    def analizador(self):
        # Las demoras solo necesitan movimientos; una exportación parcial no requiere mapa/rutas.
        if self._analizador is None:
            self._analizador = AnalizadorOperativo(self.resultado, tiempo_s=self.tiempo_s)
        return self._analizador

    def responder(self, pregunta: str) -> dict:
        return self._responder(pregunta, self._detectar_intencion(pregunta),
                               "final" if self._es_consulta_final(pregunta) else None)

    def responder_sugerida(self, pregunta_id: str) -> dict:
        pregunta = obtener_pregunta(pregunta_id)
        # El texto del botón es presentación; ninguna regla de texto decide esta consulta.
        respuesta = self._responder("", pregunta.intencion, pregunta.alcance)
        respuesta["pregunta_id"] = pregunta.id
        return respuesta

    def _responder(self, pregunta, intencion, alcance):
        if intencion == "DEMORAS_LINEA":
            return self._respuesta_demoras(alcance)
        estado = getattr(self.analizador, "estado", None)
        if alcance == "actual" and estado is None and self.resultado is not None and self.tiempo_s is not None:
            # Permite usar el catálogo con un analizador final inyectado sin filtrar sus KPI.
            consulta = Nestor(self.resultado, tiempo_s=self.tiempo_s)
            return consulta._responder(pregunta, intencion, alcance)
        if alcance == "actual" and estado is None:
            respuesta = self._respuesta(intencion, "El estado actual del reloj 2D no está disponible.",
                                       {}, [], ["No se dispone de una consulta temporal para este resultado."], [])
            respuesta.update(alcance="actual", tiempo_s=None)
            return respuesta
        if alcance == "final" and self.resultado is not None:
            analizador = AnalizadorOperativo(self.resultado, getattr(self.analizador, "umbrales", None))
            respuesta = Nestor(analizador=analizador)._responder_final(pregunta, intencion)
            estado = None
        elif estado is not None:
            respuesta = self._responder_actual(pregunta, intencion)
        else:
            respuesta = self._responder_final(pregunta, intencion)
        respuesta["alcance"] = "actual" if estado is not None else "final"
        respuesta["tiempo_s"] = estado["tiempo_s"] if estado is not None else None
        etiqueta = (
            f"Estado actual · reloj 2D: {formatear_duracion(estado['tiempo_s'])}. " if estado is not None
            else "Resultado final · análisis de la corrida completa. "
        )
        respuesta["respuesta"] = etiqueta + respuesta["respuesta"]
        return respuesta

    def _respuesta_demoras(self, alcance):
        consulta = consultar_alertas(self.resultado, self.tiempo_s, self.umbral_alertas_s,
                                    estado=getattr(self._analizador, "estado", None))
        grupos = consulta["por_linea"]
        if grupos:
            texto = "Presentan demoras de retiro sin asignación: " + "; ".join(
                f"{g['nombre']}: {g['cantidad']} {'solicitud' if g['cantidad'] == 1 else 'solicitudes'} "
                f"sin asignación, espera máxima {self._seg(g['espera_maxima_s'])}"
                for g in grupos
            ) + "."
        elif consulta["limitaciones"]:
            texto = "No se detectan demoras entre los registros evaluables; faltan datos para evaluar toda la operación."
        else:
            texto = "No hay solicitudes sin asignación que superen el umbral configurado en este instante."
        texto += f" El umbral es {self._seg(self.umbral_alertas_s)}, un parámetro de demostración no validado por Nestlé."
        if alcance == "final":
            texto += " Esta consulta por línea corresponde al reloj 2D actual."
        t = consulta["tiempo_s"]
        respuesta = self._respuesta(
            "DEMORAS_LINEA", f"Estado actual · reloj 2D: {self._seg(t)}. " + texto,
            {"umbral_s": self.umbral_alertas_s, "solicitudes_retrasadas": len(consulta["activas"]),
             "por_linea": grupos}, [], consulta["limitaciones"], [],
        )
        respuesta.update(alcance="actual", tiempo_s=t)
        if grupos:
            respuesta["acciones_revision"] = ["Revisar las solicitudes sin asignar de estas líneas y el estado actual de los AGV."]
        return respuesta

    def _responder_actual(self, pregunta, intencion):
        metricas = self.analizador.obtener_metricas()
        problemas = self._problemas_activos(self.analizador.detectar_problemas())
        no_disponibles = self.analizador.metricas_no_disponibles()
        if intencion == "ALERTAS":
            return self._respuesta_alertas(metricas, problemas, no_disponibles, actual=True)
        if intencion == "ESTADO_GENERAL" and self._es_consulta_alerta(self._normalizar(pregunta)):
            respuesta = self._respuesta_alertas(metricas, problemas, no_disponibles, actual=True)
            respuesta["tipo"] = intencion
            return respuesta
        claves_por_intencion = {
            "ESTADO_GENERAL": ("pallets_completados", "misiones_completadas", "misiones_activas",
                               "solicitudes_pendientes_backlog", "utilizacion_flota_pct"),
            "DIAGNOSTICO": ("solicitudes_pendientes_backlog", "tiempo_promedio_espera_s",
                            "tiempo_promedio_ciclo_s", "utilizacion_flota_pct"),
            "BATERIA": ("bateria_promedio_pct", "bateria_minima_pct", "cantidad_recargas"),
            "UTILIZACION": ("utilizacion_flota_pct", "utilizacion_por_agv_pct"),
            "AGV_MAS_USADO": ("utilizacion_flota_pct", "utilizacion_por_agv_pct"),
            "DISTANCIAS": ("distancia_total_m", "distancia_cargada_m", "distancia_vacia_m",
                           "porcentaje_desplazamiento_vacio"),
        }
        if intencion not in claves_por_intencion:
            respuesta = self._responder_final(pregunta, intencion)
            respuesta["metricas_utilizadas"] = {}
            return respuesta
        claves = claves_por_intencion[intencion]
        if intencion == "DIAGNOSTICO" and "maxim" in self._normalizar(pregunta):
            claves += ("backlog_maximo",)
        usadas = self._tomar(metricas, claves)
        limitaciones = [no_disponibles[c] for c in claves if c in no_disponibles]
        codigos = {
            "DIAGNOSTICO": {"BACKLOG_ELEVADO", "ESPERA_ELEVADA", "UTILIZACION_ALTA"},
            "BATERIA": {"BATERIA_BAJA"},
            "UTILIZACION": {"UTILIZACION_ALTA"},
            "AGV_MAS_USADO": {"UTILIZACION_ALTA"},
            "DISTANCIAS": {"DESPLAZAMIENTO_VACIO_ALTO"},
        }
        relacionados = (problemas if intencion == "ESTADO_GENERAL"
                        else self._filtrar_problemas(problemas, codigos[intencion]))
        if intencion == "ESTADO_GENERAL":
            texto = (
                f"Hasta ahora se han entregado {self._pallets(metricas['pallets_completados'])} de producto terminado "
                f"y se han completado {self._misiones(metricas['misiones_completadas'])} en total. "
                f"Hay {self._activas(metricas['misiones_activas'])} y "
                f"{self._solicitudes(metricas['solicitudes_pendientes_backlog'])}; "
                f"la utilización acumulada en misiones es {self._pct(metricas['utilizacion_flota_pct'])}."
            )
        elif intencion == "DIAGNOSTICO":
            texto = (
                f"En este instante hay {self._solicitudes(metricas['solicitudes_pendientes_backlog'])}. "
                f"La espera media de las misiones ya iniciadas es {self._seg(metricas['tiempo_promedio_espera_s'])} "
                f"y el ciclo medio de las ya completadas es {self._seg(metricas['tiempo_promedio_ciclo_s'])}; "
                f"la utilización acumulada es {self._pct(metricas['utilizacion_flota_pct'])}. "
                "Estos datos no permiten atribuir la situación a una única causa."
            )
        elif intencion == "BATERIA":
            texto = self._texto_bateria(usadas, actual=True)
        elif intencion in ("UTILIZACION", "AGV_MAS_USADO"):
            texto = f"La utilización acumulada en misiones hasta este instante es {self._pct(metricas['utilizacion_flota_pct'])}."
            texto += " " + self._texto_agv_actual(metricas["utilizacion_por_agv_pct"])
        else:
            texto = (
                f"Hasta este instante los AGV han recorrido {self._metros(metricas['distancia_total_m'])}: "
                f"{self._metros(metricas['distancia_cargada_m'])} con carga y "
                f"{self._metros(metricas['distancia_vacia_m'])} sin carga. "
                f"La proporción sin carga es {self._pct(metricas['porcentaje_desplazamiento_vacio'])}."
            )
        return self._respuesta(intencion, texto, usadas, relacionados, limitaciones,
                               [] if intencion in ("UTILIZACION", "AGV_MAS_USADO") else relacionados)

    def _responder_final(self, pregunta: str, intencion) -> dict:
        pregunta_normalizada = self._normalizar(pregunta)
        metricas = self.analizador.obtener_metricas()
        problemas = self.analizador.detectar_problemas()
        no_disponibles = self.analizador.metricas_no_disponibles()
        activos = self._problemas_activos(problemas)
        if intencion == "ALERTAS":
            return self._respuesta_alertas(metricas, activos, no_disponibles, actual=False)

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
                    "La flota completó {misiones} al corte del turno y alcanzó una utilización promedio de {utilizacion}. "
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
                    "Al cierre había {pendientes}; los datos no permiten atribuirlo a una única causa."
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
            if all(usadas.get(clave) is None for clave in claves):
                limitaciones = ["No hay suficiente información para determinarlo."]
                texto = "Esta corrida no registró datos de batería ni recargas, así que no puedo determinarlo para este escenario."
            else:
                texto = self._texto_bateria(usadas, actual=False)
                limitaciones = self._limitaciones(
                    {c: "" for c in claves if usadas.get(c) is None}, claves)
                if relacionados:
                    texto += " Se detectó una condición de batería baja que conviene revisar."
                elif not bateria_incompleta:
                    texto += " Los niveles registrados no cruzan el umbral de batería baja."
            return self._respuesta(intencion, texto, usadas, relacionados, limitaciones, relacionados)

        if intencion in ("UTILIZACION", "AGV_MAS_USADO"):
            claves = ("utilizacion_flota_pct", "utilizacion_por_agv_pct")
            usadas = self._tomar(metricas, claves)
            relacionados = self._filtrar_problemas(activos, {"UTILIZACION_ALTA"})
            limitaciones = self._limitaciones(no_disponibles, claves)
            mas_usado = self._agv_mas_usado(usadas.get("utilizacion_por_agv_pct"))
            if mas_usado and (intencion == "AGV_MAS_USADO" or self._es_consulta_agv_mas_usado(pregunta_normalizada)):
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
                "Los AGV recorrieron {total} en total y {vacia} fueron sin carga. "
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
                "No identifiqué tu consulta; elige una pregunta del banco sobre estado de la operación, "
                "utilización, batería o esperas."
            ),
            "metricas_utilizadas": {},
            "problemas_relacionados": [],
            "limitaciones": ["Intención no reconocida por reglas locales; no se usó IA."],
            "acciones_revision": [],
            "preguntas_alternativas": list(ALTERNATIVAS),
        }

    def _texto_bateria(self, metricas, *, actual):
        if all(v is None for v in metricas.values()):
            return "Los datos de batería y recargas no están disponibles en el instante consultado."
        partes = []
        promedio, minima = metricas.get("bateria_promedio_pct"), metricas.get("bateria_minima_pct")
        if promedio is not None:
            momento = "actual" if actual else "al último movimiento registrado de cada AGV"
            partes.append(f"La batería promedio {momento} es {self._pct(promedio)}")
        if minima is not None:
            partes.append(f"el nivel más bajo entre los AGV es {self._pct(minima)}")
        texto = "; ".join(partes)
        if texto:
            texto = texto[0].upper() + texto[1:] + ". "
        recargas = metricas.get("cantidad_recargas")
        if recargas is not None:
            texto += (f"Hasta ahora se han iniciado {self._recargas(recargas)}." if actual
                      else f"Se registraron {self._recargas(recargas)} durante la corrida.")
        return texto.strip()

    def _texto_agv_actual(self, utilizacion):
        if not utilizacion:
            return "No hay detalle disponible para comparar los AGV."
        mayor = max(utilizacion.values())
        if mayor == 0:
            return "Todavía no se ha acumulado tiempo en misiones para comparar los AGV."
        nombres = sorted(agv for agv, valor in utilizacion.items() if valor == mayor)
        if len(nombres) == 1:
            return f"{nombres[0]} tiene la mayor utilización acumulada, con {self._pct(mayor)}."
        return f"{self._unir_lista(nombres)} comparten la mayor utilización acumulada, con {self._pct(mayor)} cada uno."

    def _respuesta_alertas(self, metricas, problemas, no_disponibles, *, actual):
        claves = ("solicitudes_pendientes_backlog", "tiempo_promedio_espera_s", "utilizacion_flota_pct",
                  "bateria_minima_pct", "porcentaje_desplazamiento_vacio")
        usadas = self._tomar(metricas, claves)
        condiciones = {
            "BACKLOG_ELEVADO": f"las solicitudes en espera ({self._solicitudes(usadas['solicitudes_pendientes_backlog'])})",
            "ESPERA_ELEVADA": f"la espera media ({self._seg(usadas['tiempo_promedio_espera_s'])})",
            "UTILIZACION_ALTA": f"la utilización de la flota ({self._pct(usadas['utilizacion_flota_pct'])})",
            "BATERIA_BAJA": f"la batería mínima entre los AGV ({self._pct(usadas['bateria_minima_pct'])})",
            "DESPLAZAMIENTO_VACIO_ALTO": f"el recorrido sin carga ({self._pct(usadas['porcentaje_desplazamiento_vacio'])})",
        }
        observadas = [condiciones[p['codigo']] for p in problemas if p.get('codigo') in condiciones]
        momento = "hasta este instante" if actual else "en los resultados de la corrida completa"
        texto = (f"Los indicadores {momento} señalan que conviene revisar {self._unir_lista(observadas)}. "
                 "Estos valores activan los umbrales configurados; no identifican por sí solos la causa."
                 if observadas else f"No se detectan desviaciones en los indicadores disponibles {momento}.")
        limitaciones = self._limitaciones(
            {c: no_disponibles.get(c, "") for c in claves if usadas[c] is None}, claves)
        return self._respuesta("ALERTAS", texto, usadas, problemas, limitaciones, problemas)

    def _respuesta(self, tipo, texto, metricas, problemas, limitaciones, problemas_para_acciones):
        acciones_revision = self._acciones_revision(problemas_para_acciones)
        if not limitaciones:
            limitaciones = self._limitaciones({c: "" for c, v in metricas.items() if v is None}, metricas)
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
        if "linea" in texto and self._contiene(texto, ("demora", "retras", "espera")):
            return "DEMORAS_LINEA"
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
            "espera", "ciclo", "backlog",
        )):
            return "DIAGNOSTICO"
        if self._contiene(texto, (
            "como esta la flota", "estado de la flota", "como va la flota",
            "como estamos operando", "como esta operando",
            "como va la operacion", "como esta la operacion", "estado de la operacion",
            "como estan los agv", "como estan los agvs",
            "hay algun problema", "estado general", "operacion", "operando",
            "alerta", "alertas", "desviacion", "desviaciones",
            "pallet", "movimiento", "mision", "estado actual",
        )):
            return "ESTADO_GENERAL"
        if self._es_consulta_final(pregunta):
            return "ESTADO_GENERAL"
        return "NO_RECONOCIDA"

    def _es_consulta_final(self, pregunta):
        return self._contiene(self._normalizar(pregunta), (
            "resultado final", "resultados finales", "resumen final", "balance final",
            "indicadores finales", "corrida completa", "simulacion completa",
            "toda la corrida", "toda la simulacion", "al final", "cierre del turno",
            "termino la simulacion", "termino el escenario", "termino la operacion",
            "finalizo la simulacion", "finalizo la operacion", "al cierre",
            "resultado global", "resultados globales",
        ))

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
            "tiempo_promedio_espera_s": "La espera media aún no está disponible para esta consulta.",
            "tiempo_promedio_ciclo_s": "El ciclo medio aún no está disponible para esta consulta.",
            "solicitudes_pendientes_backlog": "No se dispone del número de solicitudes pendientes.",
            "utilizacion_flota_pct": "No se dispone de la utilización de la flota.",
            "backlog_maximo": "No se dispone del máximo de solicitudes pendientes para esta consulta.",
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
            "La flota completó {misiones} al corte del turno y alcanzó una utilización promedio de {utilizacion}. "
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

    @staticmethod
    def _pallets(valor):
        return f"{valor} pallet" if valor == 1 else f"{valor} pallets"

    @staticmethod
    def _activas(valor):
        return "1 misión activa" if valor == 1 else f"{valor} misiones activas"

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
        return formatear_duracion(valor)

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
