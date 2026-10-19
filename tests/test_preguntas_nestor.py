"""Banco explícito, plantillas y navegación del chat con el reloj de reproducción."""
from copy import deepcopy
from dataclasses import replace
import json
import time
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app.services.analizador_operativo import AnalizadorOperativo
from app.services.estado_visual import estado_en_instante
from app.services.nestor import Nestor, formatear_duracion
from app.services.preguntas_nestor import (
    ALTERNATIVAS, CATEGORIAS, PREGUNTAS, PREGUNTAS_POR_ID, obtener_pregunta,
)
from app.services.simulador_flota import ParametrosSimulacion, SimuladorFlota


class BancoNestorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = SimuladorFlota(ParametrosSimulacion(pallets_terminados=8)).ejecutar(2)
        cls.t = sorted(m["fin_s"] for m in cls.r["movimientos"])[2]

    def test_todas_las_preguntas_se_resuelven_sin_reconocer_palabras_ni_simular(self):
        antes = deepcopy(self.r)
        self.assertEqual(len({p.id for p in PREGUNTAS}), len(PREGUNTAS))
        self.assertEqual({p.categoria for p in PREGUNTAS}, set(CATEGORIAS))
        with patch.object(Nestor, "_detectar_intencion", side_effect=AssertionError("No reconocer texto")), \
             patch.object(Nestor, "_es_consulta_final", side_effect=AssertionError("Alcance explícito")), \
             patch.object(SimuladorFlota, "ejecutar", side_effect=AssertionError("No recalcular")):
            for pregunta in PREGUNTAS:
                with self.subTest(id=pregunta.id):
                    respuesta = Nestor(self.r, tiempo_s=self.t).responder_sugerida(pregunta.id)
                    self.assertEqual(respuesta["tipo"], pregunta.intencion)
                    self.assertEqual(respuesta["alcance"], pregunta.alcance)
                    self.assertEqual(respuesta["pregunta_id"], pregunta.id)
                    self.assertTrue(respuesta["metricas_utilizadas"])
                    if pregunta.alcance == "actual":
                        self.assertEqual(respuesta["tiempo_s"], self.t)
                    else:
                        self.assertIsNone(respuesta["tiempo_s"])
                        self.assertIn("corrida completa", respuesta["respuesta"])
        self.assertEqual(self.r, antes)

    def test_cambiar_redaccion_no_cambia_intencion_ni_alcance(self):
        for pregunta_id in ("agv_mas_utilizado", "resultado_final", "alertas_actuales"):
            n = Nestor(self.r, tiempo_s=self.t)
            original = n.responder_sugerida(pregunta_id)
            pregunta = replace(obtener_pregunta(pregunta_id), texto="Alerta de batería máxima al final")
            with patch.dict(PREGUNTAS_POR_ID, {pregunta_id: pregunta}):
                self.assertEqual(n.responder_sugerida(pregunta_id), original)

    def test_id_desconocido_no_se_interpreta_como_texto_libre(self):
        with self.assertRaisesRegex(ValueError, "desconocida"):
            Nestor(self.r).responder_sugerida("no_existe")

    def test_consulta_no_reconocida_ofrece_alternativas_validas(self):
        respuesta = Nestor(self.r).responder("¿Qué tiempo hará mañana?")
        self.assertEqual(respuesta["tipo"], "NO_RECONOCIDA")
        self.assertEqual(respuesta["metricas_utilizadas"], {})
        self.assertEqual(respuesta["acciones_revision"], [])
        self.assertEqual(respuesta["preguntas_alternativas"], list(ALTERNATIVAS))
        for pregunta_id in respuesta["preguntas_alternativas"]:
            self.assertEqual(obtener_pregunta(pregunta_id).alcance, "actual")

    def test_bateria_no_disponible_no_se_sustituye_por_metricas_finales(self):
        respuesta = Nestor(self.r, tiempo_s=self.t).responder_sugerida("bateria_actual")
        self.assertTrue(respuesta["limitaciones"])
        self.assertTrue(all(v is None for v in respuesta["metricas_utilizadas"].values()))
        self.assertEqual(respuesta["acciones_revision"], [])
        self.assertNotIn("No se detectó riesgo", respuesta["respuesta"])

    def test_bateria_parcial_conserva_niveles_conocidos_y_explica_recargas_faltantes(self):
        r = deepcopy(self.r)
        for m in r["movimientos"]:
            m["bateria_fin"] = 76.0
        respuesta = Nestor(r).responder("¿Cómo fue la batería de la corrida completa?")
        self.assertIn("76.0 %", respuesta["respuesta"])
        self.assertNotIn("no registró datos de batería", respuesta["respuesta"])
        self.assertIsNone(respuesta["metricas_utilizadas"]["cantidad_recargas"])
        self.assertTrue(any("recargas" in l for l in respuesta["limitaciones"]))

    def test_sin_misiones_no_inventa_un_agv_mas_utilizado_ni_recomendaciones(self):
        respuesta = Nestor(self.r, tiempo_s=0).responder_sugerida("agv_mas_utilizado")
        self.assertIn("Todavía no se ha acumulado tiempo", respuesta["respuesta"])
        self.assertNotIn("tiene la mayor", respuesta["respuesta"])
        self.assertEqual(respuesta["acciones_revision"], [])
        alertas = Nestor(self.r, tiempo_s=0).responder_sugerida("alertas_actuales")
        self.assertEqual(alertas["acciones_revision"], [])
        self.assertEqual(alertas["metricas_utilizadas"]["solicitudes_retrasadas"], 0)

    def test_comparacion_de_agv_informa_empates(self):
        t = min(m["inicio_s"] for m in self.r["movimientos"]) + .1
        respuesta = Nestor(self.r, tiempo_s=t).responder_sugerida("agv_mas_utilizado")
        self.assertIn("comparten la mayor utilización", respuesta["respuesta"])
        self.assertIn("AGV_01", respuesta["respuesta"])
        self.assertIn("AGV_02", respuesta["respuesta"])

    def test_alertas_explican_indicadores_y_solo_proponen_revisiones_con_evidencia(self):
        t = min(m["inicio_s"] for m in self.r["movimientos"]) + 121
        respuesta = Nestor(self.r, tiempo_s=t).responder_sugerida("alertas_actuales")
        self.assertGreater(respuesta["metricas_utilizadas"]["solicitudes_retrasadas"], 0)
        self.assertIn("demoras de retiro sin asignación", respuesta["respuesta"])
        self.assertIn("no validado por Nestlé", respuesta["respuesta"])
        self.assertTrue(respuesta["acciones_revision"])
        self.assertLessEqual(len(respuesta["acciones_revision"]), 2)
        self.assertNotIn("BACKLOG_ELEVADO", respuesta["respuesta"])

    def test_metrica_final_faltante_se_declara_sin_inventar_un_valor(self):
        r = deepcopy(self.r)
        r["kpis"].pop("espera_media_s")
        respuesta = Nestor(r).responder_sugerida("retrasos_finales")
        self.assertIsNone(respuesta["metricas_utilizadas"]["tiempo_promedio_espera_s"])
        self.assertTrue(any("espera media" in l for l in respuesta["limitaciones"]))
        self.assertNotIn("contribuido", respuesta["respuesta"])

    def test_inyectar_analizador_final_no_filtra_resultados_en_pregunta_actual(self):
        respuesta = Nestor(analizador=AnalizadorOperativo(self.r), tiempo_s=self.t).responder_sugerida("estado_actual")
        self.assertEqual(respuesta["alcance"], "actual")
        self.assertEqual(respuesta["tiempo_s"], self.t)
        self.assertEqual(respuesta["metricas_utilizadas"]["pallets_completados"],
                         estado_en_instante(self.r, self.t)["completados"])

    def test_formato_de_duraciones_y_respuestas_largas(self):
        for segundos, texto in ((None, "dato no disponible"), (0, "0.0 s"), (12.2, "12.2 s"),
                                (59.9, "59.9 s"), (60, "1 min"), (80, "1 min 20 s"),
                                (3600, "1 h"), (5400, "1 h 30 min"), (3661, "1 h 1 min 1 s")):
            with self.subTest(segundos=segundos):
                self.assertEqual(formatear_duracion(segundos), texto)
        r = deepcopy(self.r)
        r["kpis"].update(espera_media_s=5400, ciclo_medio_s=3661)
        respuesta = Nestor(r).responder_sugerida("retrasos_finales")
        self.assertIn("1 h 30 min", respuesta["respuesta"])
        self.assertEqual(respuesta["metricas_utilizadas"]["tiempo_promedio_espera_s"], 5400)


class BancoChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resultados = [json.loads(json.dumps(
            SimuladorFlota(ParametrosSimulacion(pallets_terminados=8)).ejecutar(n), default=str))
            for n in (2, 3)]

    def app(self):
        codigo = f'''
import streamlit as st
from app.services.nestor import Nestor
from app.ui import nestor_panel as panel
panel.Nestor = Nestor
st.session_state.setdefault("escenarios_simulados", [
    {{"id": "a", "resultado": {self.resultados[0]!r}}},
    {{"id": "b", "resultado": {self.resultados[1]!r}}}])
st.selectbox("Escenario simulado", ["a", "b"], key="escenario_activo")
from app.ui.simulacion_2d import mostrar_2d
mostrar_2d()
panel.mostrar_nestor_flotante()
'''
        at = AppTest.from_string(codigo, default_timeout=20).run()
        at.button(key="abrir_nestor").click().run()
        self.assertFalse(at.exception)
        return at

    def consultar(self, at, pregunta_id):
        pregunta = obtener_pregunta(pregunta_id)
        if at.selectbox(key="nestor_categoria").value != pregunta.categoria:
            at.selectbox(key="nestor_categoria").select(pregunta.categoria).run()
        at.selectbox(key="nestor_pregunta_banco").select(pregunta_id).run()
        at.button(key="nestor_consultar_banco").click().run()
        self.assertFalse(at.exception)

    def test_cinco_preguntas_consecutivas_sin_ocultar_ni_reiniciar_el_banco(self):
        at = self.app()
        ids = ("estado_actual", "agv_mas_utilizado", "bateria_actual", "alertas_actuales", "resultado_final")
        anteriores = []
        with patch.object(Nestor, "_detectar_intencion", side_effect=AssertionError("Usar identificadores")):
            for indice, pregunta_id in enumerate(ids, 1):
                with self.subTest(pregunta_id=pregunta_id):
                    self.consultar(at, pregunta_id)
                    historial = at.session_state["nestor_historial"]
                    self.assertEqual(len(historial), indice)
                    self.assertEqual(historial[:-1], anteriores)
                    self.assertEqual(historial[-1]["pregunta_id"], pregunta_id)
                    self.assertEqual(at.selectbox(key="nestor_categoria").value,
                                     obtener_pregunta(pregunta_id).categoria)
                    self.assertEqual(at.selectbox(key="nestor_pregunta_banco").value, pregunta_id)
                    self.assertFalse(at.button(key="nestor_consultar_banco").disabled)
                    self.assertTrue(any(historial[-1]["respuesta"]["respuesta"] in m.value for m in at.markdown))
                    anteriores = deepcopy(historial)
        self.assertEqual(len({obtener_pregunta(p).categoria for p in ids}), 4)

    def test_las_once_preguntas_siguen_accesibles_al_cambiar_categoria(self):
        at = self.app()
        self.consultar(at, "estado_actual")
        antes = deepcopy(at.session_state["nestor_historial"])
        disponibles = []
        for categoria in CATEGORIAS:
            at.selectbox(key="nestor_categoria").select(categoria).run()
            self.assertFalse(at.exception)
            esperadas = [p.texto for p in PREGUNTAS if p.categoria == categoria]
            self.assertEqual(at.selectbox(key="nestor_pregunta_banco").options, esperadas)
            self.assertEqual(at.session_state["nestor_historial"], antes)
            disponibles.extend(esperadas)
        self.assertEqual(len(disponibles), 11)

    def test_banco_permanece_despues_de_responder_y_texto_libre_sigue_disponible(self):
        at = self.app()
        self.assertEqual(at.selectbox(key="nestor_categoria").options, list(CATEGORIAS))
        with patch.object(Nestor, "_detectar_intencion", side_effect=AssertionError("ID explícito")):
            self.consultar(at, "estado_actual")
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state["nestor_historial"]), 1)
        self.assertTrue(at.button(key="nestor_consultar_banco"))
        self.assertEqual(at.selectbox(key="nestor_pregunta_banco").value, "estado_actual")
        self.assertTrue(at.text_input(key="nestor_pregunta"))
        at.selectbox(key="nestor_categoria").select(CATEGORIAS[1]).run()
        self.consultar(at, "agv_mas_utilizado")
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state["nestor_historial"]), 2)
        self.assertEqual(at.session_state["nestor_historial"][-1]["pregunta_id"], "agv_mas_utilizado")

    def test_pregunta_manual_no_reconocida_ofrece_boton_para_continuar(self):
        at = self.app()
        at.text_input(key="nestor_pregunta").set_value("¿Qué tiempo hará mañana?")
        next(b for b in at.button if b.label == "Preguntar").click().run()
        self.assertEqual(at.session_state["nestor_historial"][-1]["respuesta"]["tipo"], "NO_RECONOCIDA")
        for pregunta_id in ALTERNATIVAS:
            self.assertTrue(at.button(key=f"nestor_alternativa_{pregunta_id}"))
        at.button(key="nestor_alternativa_estado_actual").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["nestor_historial"][-1]["pregunta_id"], "estado_actual")
        self.assertFalse(any(b.key.startswith("nestor_alternativa_") for b in at.button if b.key))

    def test_sugerencia_durante_reproduccion_usa_el_reloj_y_no_recalcula(self):
        at = self.app()
        r = self.resultados[0]
        t = sorted(m["fin_s"] for m in r["movimientos"])[2]
        at.session_state["reloj_2d"].update(tiempo_s=t, marca=time.monotonic(), ejecutando=True)
        instantes_consultados = []
        responder_original = Nestor.responder_sugerida
        def consultar(nestor, pregunta_id):
            from app.ui import nestor_panel as panel
            instantes_consultados.append(panel.st.session_state["reloj_2d"]["tiempo_s"])
            return responder_original(nestor, pregunta_id)
        with patch.object(SimuladorFlota, "ejecutar", side_effect=AssertionError("No recalcular")), \
             patch.object(Nestor, "responder_sugerida", autospec=True, side_effect=consultar):
            self.consultar(at, "estado_actual")
        self.assertFalse(at.exception)
        entrada = at.session_state["nestor_historial"][-1]
        reloj = at.session_state["reloj_2d"]
        self.assertTrue(reloj["ejecutando"])
        self.assertEqual(instantes_consultados, [entrada["tiempo_s"]])
        # El rerun que dibuja la respuesta puede avanzar el reloj después de la consulta.
        self.assertLessEqual(entrada["tiempo_s"], reloj["tiempo_s"])
        self.assertGreaterEqual(entrada["tiempo_s"], t)
        self.assertEqual(entrada["respuesta"]["metricas_utilizadas"]["pallets_completados"],
                         estado_en_instante(r, entrada["tiempo_s"])["completados"])

    def test_cambio_de_escenario_conserva_banco_y_aisla_historial_y_reloj(self):
        at = self.app()
        at.session_state["reloj_2d"].update(tiempo_s=self.resultados[0]["kpis"]["tiempo_total_s"], ejecutando=False)
        self.consultar(at, "estado_actual")
        primera = deepcopy(at.session_state["nestor_historial"][0])
        at.selectbox(key="escenario_activo").select("b").run()
        self.consultar(at, "estado_actual")
        self.assertFalse(at.exception)
        segunda = at.session_state["nestor_historial"][-1]
        self.assertEqual(segunda["escenario_id"], "b")
        self.assertEqual(segunda["tiempo_s"], 0)
        self.assertEqual(segunda["respuesta"]["metricas_utilizadas"]["pallets_completados"], 0)
        self.assertEqual(at.session_state["nestor_historial"][0], primera)
        at.selectbox(key="escenario_2d").select("a").run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["reloj_2d"]["tiempo_s"], 0)
        self.assertEqual(at.session_state["nestor_historial"][0], primera)
        from app.ui.nestor_panel import _historial_visible
        self.assertEqual(len(_historial_visible(at.session_state["nestor_historial"], "a")), 1)

    def test_botones_actual_y_final_no_cambian_el_reloj(self):
        at = self.app()
        self.consultar(at, "resultado_final")
        self.assertFalse(at.exception)
        final = at.session_state["nestor_historial"][-1]["respuesta"]
        self.assertEqual(final["alcance"], "final")
        self.assertEqual(final["metricas_utilizadas"]["misiones_completadas"],
                         self.resultados[0]["kpis"]["completados_turno"])
        self.assertEqual(at.session_state["reloj_2d"]["tiempo_s"], 0)
        self.consultar(at, "estado_actual")
        actual = at.session_state["nestor_historial"][-1]["respuesta"]
        self.assertEqual(actual["alcance"], "actual")
        self.assertEqual(actual["metricas_utilizadas"]["misiones_completadas"], 0)


if __name__ == "__main__":
    unittest.main()
