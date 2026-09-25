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

    def test_dimensionamiento_crea_escenario_sin_cliente_tcp(self):
        with patch("app.services.gestor_flota.FlexSimCliente", side_effect=AssertionError("TCP prohibido")) as cliente:
            at = self.app().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state["modo_principal"], "Dimensionamiento")
            self.assertTrue(any(x.label == "Número de AGV a simular" for x in at.selectbox))

            self.boton(at, "Simular escenario").click().run()

            self.assertFalse(at.exception)
            self.assertEqual(len(at.session_state["escenarios_simulados"]), 1)
            self.assertIn("escenario_activo", at.session_state)
            self.assertTrue(any("Simulación completada" in x.value for x in at.success))
        cliente.assert_not_called()

    def test_resultados_muestran_solicitudes_y_flota_con_datos_reales(self):
        at = self.app().run()
        self.boton(at, "Simular escenario").click().run()

        self.assertFalse(at.exception)
        metricas = {m.label: m.value for m in at.metric}
        self.assertIn("Pallets pendientes", metricas)
        self.assertIn("Solicitudes generadas", metricas)
        self.assertIn("Solicitudes completadas", metricas)
        self.assertIn("Solicitudes pendientes", metricas)
        self.assertIn("Misiones activas al cierre", metricas)
        self.assertIn("Aún no generadas", metricas)
        kpis = at.session_state["escenarios_simulados"][-1]["resultado"]["kpis"]
        for etiqueta, clave in (
            ("Pallets pendientes", "pallets_terminados_pendientes"),
            ("Solicitudes generadas", "solicitudes_generadas_turno"),
            ("Solicitudes completadas", "solicitudes_completadas_turno"),
            ("Solicitudes pendientes", "solicitudes_pendientes_turno"),
            ("Aún no generadas", "solicitudes_no_generadas_turno"),
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

    def test_rentabilidad_mantiene_datos_pendientes_y_guarda_supuestos(self):
        at = self.app().run()
        self.boton(at, "Simular escenario").click().run()

        self.assertFalse(at.exception)
        self.assertTrue(any(m.value == "Pendiente de datos de planta" for m in at.metric))
        self.assertTrue(any(x.label == "Completar datos económicos" for x in at.expander))

        next(x for x in at.number_input if x.label == "Costo por AGV (USD)").set_value(10000)
        self.boton(at, "Guardar análisis de negocio").click().run()

        escenario = at.session_state["escenarios_simulados"][0]
        self.assertEqual(escenario["parametros_economicos"]["costo_agv"], 10000)

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
