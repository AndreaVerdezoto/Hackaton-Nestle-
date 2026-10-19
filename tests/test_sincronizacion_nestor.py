"""Regresiones del contrato temporal entre reproducción 2D y consultas del chat."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app.models.bateria import CARGADORES
from app.services.analizador_operativo import AnalizadorOperativo
from app.services.estado_visual import estado_en_instante
from app.services.nestor import Nestor, formatear_duracion
from app.services.simulador_flota import ParametrosSimulacion, SimuladorFlota
from app.ui.simulacion_2d import avanzar_reloj


class SincronizacionTemporalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resultado = SimuladorFlota().ejecutar(2)
        cls.ordenadas = sorted(cls.resultado["movimientos"], key=lambda m: m["fin_s"])
        # 59 entregas concluidas, con el resto de la corrida precalculado.
        cls.t = (cls.ordenadas[58]["fin_s"] + cls.ordenadas[59]["fin_s"]) / 2

    def test_59_pallets_y_mision_activa_no_son_resultados_finales(self):
        r = deepcopy(self.resultado)
        r["kpis"]["completados_turno"] = 339
        antes = deepcopy(r)
        with patch.object(SimuladorFlota, "ejecutar", side_effect=AssertionError("No recalcular")):
            respuesta = Nestor(r, tiempo_s=self.t).responder("¿Cómo está la flota?")
        m = respuesta["metricas_utilizadas"]
        self.assertEqual(m["pallets_completados"], 59)
        self.assertEqual(m["misiones_completadas"], 59)
        self.assertEqual(m["misiones_activas"], len(estado_en_instante(r, self.t)["activas"]))
        self.assertGreater(m["misiones_activas"], 0)
        self.assertNotIn("339", respuesta["respuesta"])
        self.assertNotIn("cerró", respuesta["respuesta"])
        self.assertEqual(respuesta["tiempo_s"], self.t)
        self.assertEqual(respuesta["alcance"], "actual")
        self.assertEqual(r, antes)

    def test_pallets_y_movimientos_se_cuentan_por_separado(self):
        r = deepcopy(self.resultado)
        next(m for m in r["movimientos"] if m["fin_s"] <= self.t)["tipo"] = "abastecimiento"
        respuesta = Nestor(r, tiempo_s=self.t).responder("¿Cuántos pallets se completaron?")
        self.assertEqual(respuesta["metricas_utilizadas"]["pallets_completados"], 58)
        self.assertEqual(respuesta["metricas_utilizadas"]["misiones_completadas"], 59)
        self.assertIn("58 pallets", respuesta["respuesta"])
        self.assertIn("59 movimientos logísticos", respuesta["respuesta"])

    def test_fronteras_de_mision_y_limites_del_reloj(self):
        m = self.ordenadas[0]
        for t, completadas in ((-1, 0), (m["inicio_s"], 0), (m["fin_s"] - .001, 0),
                               (m["fin_s"], sum(x["fin_s"] == m["fin_s"] for x in self.ordenadas)),
                               (1e9, len(self.ordenadas))):
            with self.subTest(t=t):
                respuesta = Nestor(self.resultado, tiempo_s=t).responder("Estado actual")
                self.assertEqual(respuesta["metricas_utilizadas"]["misiones_completadas"], completadas)
                self.assertGreaterEqual(respuesta["tiempo_s"], 0)
                self.assertLessEqual(respuesta["tiempo_s"], self.resultado["kpis"]["tiempo_total_s"])

    def test_reproducir_pausar_reanudar_reiniciar_y_finalizar(self):
        limite = self.resultado["kpis"]["tiempo_total_s"]
        reloj = dict(tiempo_s=0., marca=0., ejecutando=True, velocidad=10)
        avanzar_reloj(reloj, self.t / 10, limite)
        def consultar():
            return Nestor(self.resultado, tiempo_s=reloj["tiempo_s"]).responder("Estado actual")
        en_marcha = consultar()
        reloj["ejecutando"] = False
        avanzar_reloj(reloj, limite, limite)
        self.assertEqual(consultar(), en_marcha)
        reloj["ejecutando"] = True
        avanzar_reloj(reloj, limite + 10, limite)
        self.assertGreater(consultar()["tiempo_s"], en_marcha["tiempo_s"])
        avanzar_reloj(reloj, limite * 100, limite)
        self.assertFalse(reloj["ejecutando"])
        fin = consultar()
        self.assertEqual(fin["alcance"], "actual")
        self.assertEqual(fin["metricas_utilizadas"]["misiones_activas"], 0)
        self.assertEqual(fin["metricas_utilizadas"]["misiones_completadas"], len(self.ordenadas))
        reloj.update(tiempo_s=0., ejecutando=False)
        self.assertEqual(consultar()["metricas_utilizadas"]["pallets_completados"], 0)

    def test_cada_consulta_actual_ignora_metricas_y_eventos_futuros(self):
        r = deepcopy(self.resultado)
        preguntas = ("Estado actual", "¿Por qué hay pendientes?", "¿Cómo está la batería?",
                     "¿Cuál AGV trabajó más?", "¿Qué distancia recorrieron?")
        originales = [Nestor(r, tiempo_s=self.t).responder(p) for p in preguntas]
        r["kpis"].update({k: 999999 for k in r["kpis"] if k != "tiempo_total_s"})
        for a in r["por_agv"]:
            a["utilizacion_pct"] = 999999
        for m in r["movimientos"]:
            if m["inicio_s"] > self.t:
                m["inicio_s"] += 1000
                m["fin_s"] += 1000
                m["espera_s"] = 999999
                m["ciclo_movimiento_s"] = 999999
        r["errores"] = ["Error final sin instante"]
        with patch.object(SimuladorFlota, "ejecutar", side_effect=AssertionError("No recalcular")):
            self.assertEqual(originales, [Nestor(r, tiempo_s=self.t).responder(p) for p in preguntas])

    def test_acumulados_coinciden_con_visualizacion_y_muestra_observada(self):
        e = estado_en_instante(self.resultado, self.t)
        a = AnalizadorOperativo(self.resultado, tiempo_s=self.t)
        m = a.obtener_metricas()
        self.assertEqual(m["utilizacion_flota_pct"], e["utilizacion_pct"])
        self.assertEqual(m["solicitudes_pendientes_backlog"], len(e["pendientes"]))
        self.assertAlmostEqual(m["distancia_total_m"], sum(x["distancia_total_m"] for x in e["flota"]))
        completadas = [x for x in self.ordenadas if x["fin_s"] <= self.t]
        self.assertAlmostEqual(m["tiempo_promedio_ciclo_s"],
                               sum(x["ciclo_movimiento_s"] for x in completadas) / len(completadas))
        for agv in e["flota"]:
            self.assertAlmostEqual(m["utilizacion_por_agv_pct"][agv["agv"]],
                                   100 * agv["tiempo_ocupado_s"] / self.t)

    def test_sin_muestra_y_sin_bateria_no_inventa_metricas(self):
        n = Nestor(self.resultado, tiempo_s=0)
        diagnostico = n.responder("¿Cuál es la espera y el ciclo actual?")
        self.assertIsNone(diagnostico["metricas_utilizadas"]["tiempo_promedio_espera_s"])
        self.assertIsNone(diagnostico["metricas_utilizadas"]["tiempo_promedio_ciclo_s"])
        self.assertTrue(diagnostico["limitaciones"])
        self.assertTrue(n.responder("Batería actual")["limitaciones"])
        self.assertTrue(n.responder("Backlog máximo actual")["limitaciones"])

    def test_resultados_finales_son_explicitos_aunque_el_reloj_este_en_cero(self):
        preguntas = ("Resultados finales", "Utilización al final", "Batería de toda la corrida",
                     "Distancia de la simulación completa", "Pendientes al cierre del turno")
        n = Nestor(self.resultado, tiempo_s=0)
        with patch.object(SimuladorFlota, "ejecutar", side_effect=AssertionError("No recalcular")):
            respuestas = [n.responder(p) for p in preguntas]
        for respuesta in respuestas:
            self.assertEqual(respuesta["alcance"], "final")
            self.assertIsNone(respuesta["tiempo_s"])
            self.assertIn("corrida completa", respuesta["respuesta"])
        self.assertEqual(respuestas[0]["metricas_utilizadas"]["misiones_completadas"],
                         self.resultado["kpis"]["completados_turno"])
        self.assertEqual(n.responder("Estado actual")["metricas_utilizadas"]["misiones_completadas"], 0)

    def test_recargas_y_bateria_se_cortan_en_el_instante(self):
        r = SimuladorFlota(ParametrosSimulacion(tiempo_carga_s=100, tiempo_descarga_s=100)).ejecutar(
            2, simular_bateria=True, cargadores=CARGADORES)
        recarga = min((c for cs in r["recargas"].values() for c in cs), key=lambda c: c["inicio_carga_s"])
        for t in (0, recarga["inicio_carga_s"] - .001, recarga["inicio_carga_s"],
                  (recarga["inicio_carga_s"] + recarga["fin_s"]) / 2, recarga["fin_s"]):
            with self.subTest(t=t):
                e = estado_en_instante(r, t)
                m = Nestor(r, tiempo_s=t).responder("Batería actual")["metricas_utilizadas"]
                self.assertAlmostEqual(m["bateria_promedio_pct"], sum(a["bateria"] for a in e["flota"]) / 2)
                self.assertEqual(m["bateria_minima_pct"], min(a["bateria"] for a in e["flota"]))
                self.assertEqual(m["cantidad_recargas"],
                                 sum(c["inicio_carga_s"] <= t for cs in r["recargas"].values() for c in cs))


class SincronizacionChatTests(unittest.TestCase):
    def app(self):
        r = SimuladorFlota(ParametrosSimulacion(pallets_terminados=8)).ejecutar(2)
        r = json.loads(json.dumps(r, default=str))
        # Restaurar el servicio real: otras pruebas del chat inyectan un doble.
        codigo = f'''
import streamlit as st
from app.services.nestor import Nestor
from app.ui import nestor_panel as panel
panel.Nestor = Nestor
st.session_state.setdefault("escenarios_simulados", [
    {{"id": "a", "resultado": {r!r}}}, {{"id": "b", "resultado": {r!r}}}])
st.selectbox("Escenario simulado", ["a", "b"], key="escenario_activo")
from app.ui.simulacion_2d import mostrar_2d
mostrar_2d()
panel.mostrar_nestor_flotante()
'''
        return AppTest.from_string(codigo, default_timeout=20).run(), r

    def preguntar(self, at, pregunta="¿Cómo está la flota?"):
        next(x for x in at.text_input if x.label == "Pregunta para Néstor").set_value(pregunta)
        at.button(key="FormSubmitter:formulario_nestor_flotante-Preguntar").click().run()
        self.assertFalse(at.exception)
        return at.session_state["nestor_historial"][-1]

    def test_chat_lee_reloj_al_enviar_y_conserva_el_instante_historico(self):
        at, r = self.app()
        at.button(key="abrir_nestor").click().run()
        t = sorted(m["fin_s"] for m in r["movimientos"])[2]
        at.session_state["reloj_2d"].update(tiempo_s=t, ejecutando=False)
        with patch.object(SimuladorFlota, "ejecutar", side_effect=AssertionError("No recalcular")):
            entrada = self.preguntar(at)
            self.assertEqual(entrada["tiempo_s"], t)
            self.assertEqual(entrada["respuesta"]["metricas_utilizadas"]["pallets_completados"],
                             sum(m["fin_s"] <= t for m in r["movimientos"]))
            at.button(key="reset_2d").click().run()
            nueva = self.preguntar(at)
        self.assertEqual(nueva["tiempo_s"], 0)
        self.assertEqual(nueva["respuesta"]["metricas_utilizadas"]["pallets_completados"], 0)
        self.assertEqual(at.session_state["nestor_historial"][0], entrada)
        self.assertIn(formatear_duracion(t), entrada["respuesta"]["respuesta"])

    def test_cambio_de_escenario_desde_ambos_selectores(self):
        at, r = self.app()
        at.button(key="abrir_nestor").click().run()
        at.session_state["reloj_2d"].update(tiempo_s=r["kpis"]["tiempo_total_s"], ejecutando=False)
        self.preguntar(at)
        at.selectbox(key="escenario_activo").select("b").run()
        self.assertFalse(at.exception)
        self.assertEqual(at.selectbox(key="escenario_2d").value, "b")
        self.assertEqual(at.session_state["escenario_2d_activo"], "b")
        self.assertEqual(at.session_state["reloj_2d"]["tiempo_s"], 0)
        entrada = self.preguntar(at)
        self.assertEqual(entrada["escenario_id"], "b")
        self.assertEqual(entrada["respuesta"]["metricas_utilizadas"]["pallets_completados"], 0)
        at.session_state["reloj_2d"].update(tiempo_s=100, ejecutando=True)
        at.selectbox(key="escenario_2d").select("a").run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["escenario_activo"], "a")
        self.assertEqual(at.session_state["reloj_2d"]["tiempo_s"], 0)
        self.assertFalse(at.session_state["reloj_2d"]["ejecutando"])
        # El historial visible sigue aislado por escenario.
        from app.ui.nestor_panel import _historial_visible
        self.assertEqual(len(_historial_visible(at.session_state["nestor_historial"], "a")), 1)

    def test_reloj_ajeno_o_ausente_no_se_aplica_al_escenario(self):
        from app.ui import nestor_panel as panel
        for state in ({}, {"escenario_2d_activo": "a", "reloj_2d": {"tiempo_s": 500}}):
            with patch.object(panel.st, "session_state", state):
                self.assertEqual(panel._tiempo_desde_session_state("b"), 0)


if __name__ == "__main__":
    unittest.main()
