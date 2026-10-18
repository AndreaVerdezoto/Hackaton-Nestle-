"""Pruebas Streamlit de la organización visual sin servidor web ni FlexSim."""
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Streamlit no está instalado en este intérprete")
class InterfazTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(Path(__file__).resolve().parents[1] / "interfaz.py"), default_timeout=20)

    def boton(self, at, etiqueta):
        return next(b for b in at.button if b.label == etiqueta)

    def test_configuracion_general_siete_minutos_y_meta_distinta_de_produccion(self):
        at = self.app().run()
        self.assertFalse(at.exception)
        self.assertTrue(any(x.label == "Producción por pallet · todas las líneas (min)"
                            and x.value == 7.0 for x in at.number_input))
        self.boton(at, "Simular escenario").click().run()
        self.assertFalse(at.exception)
        r = at.session_state["escenarios_simulados"][-1]["resultado"]
        self.assertEqual(r["kpis"]["meta_pallets_turno"], 215)
        self.assertEqual(r["kpis"]["pallets_producidos_turno"], 340)
        self.assertGreater(r["kpis"]["cumplimiento_pct"], 100)

    def test_configuracion_avanzada_por_linea(self):
        at = self.app().run()
        next(x for x in at.checkbox if x.label == "Personalizar tiempos de cada línea").set_value(True).run()
        self.assertFalse(at.exception)
        next(x for x in at.number_input if x.label == "WAFER (min/pallet)").set_value(11.0).run()
        self.boton(at, "Simular escenario").click().run()
        self.assertFalse(at.exception)
        r = at.session_state["escenarios_simulados"][-1]["resultado"]
        self.assertEqual(r["parametros"]["tiempos_produccion_lineas_s"]["WAFER"], 660)
        self.assertEqual(r["kpis"]["pallets_producidos_turno"], 315)

    def test_dimensionamiento_crea_escenario_sin_cliente_tcp(self):
        at = self.app().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["modo_principal"], "Dimensionamiento")
        self.assertTrue(any(x.label == "Número de AGV a simular" for x in at.selectbox))

        self.boton(at, "Simular escenario").click().run()

        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state["escenarios_simulados"]), 1)
        escenario = at.session_state["escenarios_simulados"][0]
        self.assertEqual(set(escenario), {"id", "guardado", "resultado"})
        self.assertIn("escenario_activo", at.session_state)
        self.assertTrue(any("Simulación completada" in x.value for x in at.success))

    def test_resultados_muestran_solicitudes_y_flota_con_datos_reales(self):
        at = self.app().run()
        self.boton(at, "Simular escenario").click().run()

        self.assertFalse(at.exception)
        metricas = {m.label: m.value for m in at.metric}
        self.assertIn("Pallets por almacenar", metricas)
        self.assertIn("Solicitudes generadas", metricas)
        self.assertIn("Solicitudes completadas", metricas)
        self.assertIn("Solicitudes pendientes", metricas)
        self.assertIn("Misiones activas al cierre", metricas)
        self.assertIn("Pallets aún en producción", metricas)
        kpis = at.session_state["escenarios_simulados"][-1]["resultado"]["kpis"]
        for etiqueta, clave in (
            ("Pallets por almacenar", "pallets_terminados_pendientes"),
            ("Solicitudes generadas", "solicitudes_generadas_turno"),
            ("Solicitudes completadas", "solicitudes_completadas_turno"),
            ("Solicitudes pendientes", "solicitudes_pendientes_turno"),
            ("Pallets aún en producción", "solicitudes_no_generadas_turno"),
        ):
            # Resultados aparece antes del contador del reloj 2D (inicialmente t=0).
            valor_resultados = next(m.value for m in at.metric if m.label == etiqueta)
            self.assertEqual(valor_resultados, str(kpis[clave]))
        self.assertTrue(any(x.label == "Ver detalle de solicitudes" for x in at.expander))
        self.assertTrue(any(x.label == "Ver análisis técnico" for x in at.expander))

    def test_comparacion_reutiliza_escenarios_existentes(self):
        from app.services.simulador_flota import SimuladorFlota

        ejecutar = SimuladorFlota.ejecutar
        with patch.object(SimuladorFlota, "ejecutar", autospec=True, side_effect=ejecutar) as simular:
            at = self.app().run()
            for cantidad in (2, 3):
                next(x for x in at.selectbox if x.label == "Número de AGV a simular").set_value(cantidad)
                self.boton(at, "Simular escenario").click().run()
                self.assertFalse(at.exception)

            at.run()

            self.assertEqual([c.args[1] for c in simular.call_args_list], [2, 3])
            self.assertEqual(simular.call_count, 2)
            self.assertTrue(any(x.label == "Corridas a comparar" for x in at.multiselect))

    def test_simulacion_2d_no_vuelve_a_ejecutar_simulador(self):
        from app.services.simulador_flota import SimuladorFlota

        ejecutar = SimuladorFlota.ejecutar
        with patch.object(SimuladorFlota, "ejecutar", autospec=True, side_effect=ejecutar) as simular:
            at = self.app().run()
            self.boton(at, "Simular escenario").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(simular.call_count, 1)

            at.run()

            self.assertFalse(at.exception)
            self.assertEqual(simular.call_count, 1)
            self.assertFalse(any(b.label == "Iniciar" for b in at.button))
            self.assertTrue(any(x.label == "Escenario para visualización 2D" for x in at.selectbox))

    def test_ubicacion_invalida_se_muestra_sin_romper_interfaz(self):
        at = self.app().run()
        next(x for x in at.text_input if x.label == "Ubicación inicial común").set_value("NO_EXISTE")
        self.boton(at, "Simular escenario").click().run()

        self.assertFalse(at.exception)
        self.assertTrue(any("conectividad" in e.value for e in at.error))

    def test_archiva_corridas_obsoletas(self):
        at = self.app().run()
        self.boton(at, "Simular escenario").click().run()
        at.session_state["escenarios_simulados"][0]["resultado"]["version_modelo"] = "version_anterior"

        at.run()

        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state["escenarios_simulados"]), 0)
        self.assertEqual(len(at.session_state["escenarios_obsoletos"]), 1)


if __name__ == "__main__":
    unittest.main()
