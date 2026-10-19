"""Integración Streamlit: anuncios sin preguntas, configuración y banco permanente."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app.services.nestor import Nestor
from app.services.preguntas_nestor import CATEGORIAS, PREGUNTAS, obtener_pregunta
from app.services.simulador_flota import ParametrosSimulacion, SimuladorFlota
from app.services.alertas_linea import consultar_alertas, historial_visible, nuevas_sin_leer
from app.services.exportacion_nestor import exportar_corrida_nestor


class AlertasPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resultados = [json.loads(json.dumps(SimuladorFlota(ParametrosSimulacion(
            pallets_terminados=8, tiempo_carga_s=200, tiempo_descarga_s=200,
        )).ejecutar(n), default=str)) for n in (2, 3)]
        cls.t = min(m["llegada_s"] for m in cls.resultados[0]["movimientos"]) + 121

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
        self.assertFalse(at.exception)
        return at

    def avanzar(self, at, t):
        at.session_state["reloj_2d"].update(tiempo_s=t, ejecutando=False)
        with patch.object(SimuladorFlota, "ejecutar", side_effect=AssertionError("No recalcular")):
            at.run()
        self.assertFalse(at.exception)
        return at.session_state["nestor_alertas_registros"][at.session_state["escenario_activo"]]

    def test_detecta_sin_preguntas_con_panel_cerrado_y_marca_leidas_al_abrir(self):
        at = self.app()
        r = self.avanzar(at, self.t)
        self.assertGreater(nuevas_sin_leer(r, self.t), 0)
        self.assertTrue(any("nuevas demoras" in e.proto.body for e in at.get("html")))
        self.assertEqual(at.session_state["nestor_historial"], [])
        at.button(key="abrir_nestor").click().run()
        self.assertFalse(at.exception)
        r = at.session_state["nestor_alertas_registros"]["a"]
        self.assertEqual(nuevas_sin_leer(r, self.t), 0)
        self.assertEqual(at.session_state["nestor_historial"], [])
        self.assertTrue(any("Demoras de retiro" in m.value for m in at.markdown))
        self.assertTrue(at.button(key="nestor_consultar_banco"))
        self.assertEqual(len(PREGUNTAS), 11)

    def test_umbral_configurable_persistente_y_consulta_coincide_con_alertas(self):
        at = self.app()
        self.avanzar(at, self.t)
        at.button(key="abrir_nestor").click().run()
        entrada = at.number_input(key="_nestor_umbral_input")
        self.assertEqual(entrada.value, 120)
        self.assertEqual(entrada.proto.default, 120)
        self.assertIn("segundos", entrada.label)
        entrada.set_value(300.0).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["nestor_umbral_alertas_s"], 300)
        self.assertFalse(consultar_alertas(self.resultados[0], self.t, 300)["activas"])
        self.assertTrue(any("Sin demoras de retiro" in x.value for x in at.caption))
        at.selectbox(key="nestor_categoria").select(CATEGORIAS[3]).run()
        at.selectbox(key="nestor_pregunta_banco").select("alertas_actuales").run()
        at.button(key="nestor_consultar_banco").click().run()
        respuesta = at.session_state["nestor_historial"][-1]["respuesta"]
        self.assertEqual(respuesta["metricas_utilizadas"]["umbral_s"], 300)
        self.assertEqual(respuesta["metricas_utilizadas"]["solicitudes_retrasadas"], 0)
        at.button(key="cerrar_nestor").click().run()
        at.button(key="abrir_nestor").click().run()
        self.assertEqual(at.number_input(key="_nestor_umbral_input").value, 300)

    def test_cambio_de_escenario_y_reinicio_aislan_registros(self):
        at = self.app()
        a = deepcopy(self.avanzar(at, self.t))
        at.selectbox(key="escenario_2d").select("b").run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["reloj_2d"]["tiempo_s"], 0)
        self.assertFalse(at.session_state["nestor_alertas_registros"]["b"]["eventos"])
        b = self.avanzar(at, self.t)
        self.assertNotEqual(set(a["eventos"]), set(b["eventos"]))
        at.selectbox(key="escenario_2d").select("a").run()
        self.assertFalse(historial_visible(at.session_state["nestor_alertas_registros"]["a"], 0))
        self.avanzar(at, self.t)
        self.assertEqual(set(at.session_state["nestor_alertas_registros"]["a"]["eventos"]), set(a["eventos"]))
        revision = at.session_state["reloj_2d"]["revision"]
        at.button(key="reset_2d").click().run()
        self.assertGreater(at.session_state["reloj_2d"]["revision"], revision)
        self.assertEqual(at.session_state["reloj_2d"]["tiempo_s"], 0)
        self.assertEqual(at.session_state["nestor_historial"], [])

    def test_cinco_preguntas_con_alertas_no_ocultan_banco_ni_mezclan_historiales(self):
        at = self.app()
        self.avanzar(at, self.t)
        at.button(key="abrir_nestor").click().run()
        eventos = set(at.session_state["nestor_alertas_registros"]["a"]["eventos"])
        for indice, pregunta_id in enumerate(("estado_actual", "agv_mas_utilizado", "bateria_actual",
                                             "alertas_actuales", "resultado_final"), 1):
            p = obtener_pregunta(pregunta_id)
            at.selectbox(key="nestor_categoria").select(p.categoria).run()
            at.selectbox(key="nestor_pregunta_banco").select(pregunta_id).run()
            with patch.object(Nestor, "_detectar_intencion", side_effect=AssertionError("Usar ID")):
                at.button(key="nestor_consultar_banco").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.session_state["nestor_historial"]), indice)
            self.assertEqual(at.selectbox(key="nestor_pregunta_banco").value, pregunta_id)
            self.assertFalse(at.button(key="nestor_consultar_banco").disabled)
            self.assertEqual(set(at.session_state["nestor_alertas_registros"]["a"]["eventos"]), eventos)

    def test_salto_temporal_no_anuncia_retrasos_atendidos_como_pendientes(self):
        at = self.app()
        fin = self.resultados[0]["kpis"]["tiempo_total_s"]
        at.number_input(key="instante_2d").set_value(float(fin)).run()
        revision = at.session_state["reloj_2d"]["revision"]
        at.button(key="buscar_2d").click().run()
        self.assertFalse(at.exception)
        self.assertGreater(at.session_state["reloj_2d"]["revision"], revision)
        r = at.session_state["nestor_alertas_registros"]["a"]
        self.assertEqual(nuevas_sin_leer(r, fin), 0)
        self.assertTrue(historial_visible(r, fin))
        self.assertTrue(all(e["estado"] == "ATENDIDA" for e in historial_visible(r, fin)))

    def test_resultado_parcial_no_rompe_alertas_ni_banco(self):
        at = AppTest.from_string('''
import streamlit as st
from app.ui.nestor_panel import mostrar_nestor_flotante
st.session_state["escenario_2d_activo"] = "parcial"
st.session_state["reloj_2d"] = {"tiempo_s": 150}
mostrar_nestor_flotante({"movimientos": [{"numero": 1}]}, escenario_id="parcial")
''').run()
        at.button(key="abrir_nestor").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("información incompleta" in c.value for c in at.caption))
        at.selectbox(key="nestor_categoria").select(CATEGORIAS[3]).run()
        at.selectbox(key="nestor_pregunta_banco").select("alertas_actuales").run()
        at.button(key="nestor_consultar_banco").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.session_state["nestor_historial"][-1]["respuesta"]["limitaciones"])

    def test_historial_etiquetas_y_descarga_corresponden_al_escenario_actual(self):
        at = self.app()
        self.avanzar(at, self.t)
        capturas = []

        def capturar(*args, **kwargs):
            texto = exportar_corrida_nestor(*args, **kwargs)
            capturas.append(json.loads(texto))
            return texto

        with patch("app.ui.nestor_panel.exportar_corrida_nestor", side_effect=capturar):
            at.button(key="abrir_nestor").click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.get("download_button")), 1)
        self.assertEqual(at.get("download_button")[0].proto.label, "Descargar corrida y alertas (JSON)")
        self.assertEqual(capturas[-1]["escenario"]["id"], "a")
        self.assertEqual(capturas[-1]["simulacion"]["resultado"], self.resultados[0])
        self.assertEqual(capturas[-1]["reproduccion"]["reloj_2d"]["tiempo_s"], self.t)
        self.assertTrue(any("Umbral superado desde" in c.value and "Aviso detectado en" in c.value for c in at.caption))
        self.assertFalse(any("Espera final sin asignación" in c.value for c in at.caption))
        fin = self.resultados[0]["kpis"]["tiempo_total_s"]
        self.avanzar(at, fin)
        self.assertTrue(any("Espera final sin asignación" in c.value for c in at.caption))
        self.assertTrue(any("Espera observada al generar el aviso" in c.value for c in at.caption))
        with patch("app.ui.nestor_panel.exportar_corrida_nestor", side_effect=capturar):
            at.selectbox(key="escenario_2d").select("b").run()
        self.assertFalse(at.exception)
        self.assertEqual(capturas[-1]["escenario"]["id"], "b")
        self.assertEqual(capturas[-1]["simulacion"]["resultado"], self.resultados[1])
        self.assertFalse(capturas[-1]["reproduccion"]["registro_alertas"]["eventos"])
        self.assertTrue(at.button(key="nestor_consultar_banco"))


if __name__ == "__main__":
    unittest.main()
