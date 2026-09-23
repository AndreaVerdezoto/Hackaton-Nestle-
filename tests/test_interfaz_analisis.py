"""Pruebas Streamlit sin servidor web ni FlexSim. Instalar requirements.txt."""
from pathlib import Path
import unittest
from unittest.mock import patch

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, 'Streamlit no está instalado en este intérprete')
class InterfazTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'interfaz.py'), default_timeout=20)

    def boton(self, at, etiqueta):
        return next(b for b in at.button if b.label == etiqueta)

    def test_abrir_y_comparar_sin_cliente_tcp(self):
        with patch('app.services.gestor_flota.FlexSimCliente', side_effect=AssertionError('TCP prohibido')) as cliente:
            at = self.app().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['modo_principal'], 'Análisis de flota')
            self.boton(at, 'Simular escenario').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.session_state['escenarios_simulados']), 1)
            self.assertTrue(at.warning)
            at.run()
            self.assertFalse(at.exception)
        cliente.assert_not_called()

    def test_parametros_reset_presupuesto_y_guardado(self):
        at = self.app().run()
        next(x for x in at.number_input if x.label == 'Carga (s)').set_value(60)
        self.boton(at, 'Simular escenario').click().run()
        self.assertFalse(at.exception)
        original = at.session_state['escenarios_simulados'][0]
        self.assertEqual(original['resultado']['parametros']['tiempo_carga_s'], 60)
        self.assertIsNone(original['economia']['capex'])
        next(x for x in at.number_input if x.label == 'Costo por AGV (USD)').set_value(10000).run()
        self.assertIsNone(original['parametros_economicos']['costo_agv'])
        self.boton(at, 'Guardar análisis de negocio').click().run()
        self.assertEqual(at.session_state['escenarios_simulados'][0]['parametros_economicos']['costo_agv'], 10000)
        next(x for x in at.selectbox if x.label == 'Número de AGV a simular').set_value(3)
        self.boton(at, 'Simular escenario').click().run()
        self.assertFalse(at.exception)
        self.assertEqual([e['resultado']['numero_agv'] for e in at.session_state['escenarios_simulados']], [2, 3])
        self.boton(at, 'Comparar escenarios simulados').click().run()
        self.assertFalse(at.exception)
        tabla = next(d.value for d in at.dataframe if 'CAPEX' in d.value.columns)
        self.assertEqual(list(tabla['AGV']), [2, 3])
        self.boton(at, 'Restablecer valores base').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['ana_tiempo_carga_s'], 30)
        self.assertEqual(len(at.session_state['escenarios_simulados']), 2)
        self.assertEqual(at.session_state['escenarios_simulados'][0]['resultado']['parametros']['tiempo_carga_s'], 60)

    def test_ubicacion_invalida_se_muestra(self):
        at = self.app().run()
        next(x for x in at.text_input if x.label == 'Ubicación inicial común').set_value('NO_EXISTE')
        self.boton(at, 'Simular escenario').click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any('conectividad' in e.value for e in at.error))

    def test_capacidad_suficiente_con_cierre_pendiente(self):
        at = self.app().run()
        next(x for x in at.selectbox if x.label == 'Número de AGV a simular').set_value(3)
        self.boton(at, 'Simular escenario').click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any('Capacidad logística: SUFICIENTE' in x.value for x in at.success))
        self.assertTrue(any('liberado demasiado cerca' in x.value for x in at.info))
        self.assertEqual(next(x for x in at.metric if x.label == 'Pallets que esperaron AGV').value, '0')

    def test_suministro_oculto_en_cero_y_archivo_obsoleto(self):
        at = self.app().run()
        self.assertFalse(any(x.label == 'Movimientos de suministro por turno' for x in at.number_input))
        at.session_state['ana_movimientos_suministro'] = 40
        self.boton(at, 'Simular escenario').click().run()
        self.assertFalse(at.exception)
        r = at.session_state['escenarios_simulados'][0]['resultado']
        self.assertEqual(r['parametros']['pallets_terminados'], 215)
        self.assertEqual(r['parametros']['movimientos_suministro'], 0)
        self.assertEqual(r['kpis']['movimientos_logisticos_totales'], 215)
        self.assertEqual(next(x for x in at.metric if x.label == 'Pallets terminados requeridos').value, '215')
        r['version_modelo'] = 'eventos_discretos_cinematica_v1'
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state['escenarios_simulados']), 0)
        self.assertEqual(len(at.session_state['escenarios_obsoletos']), 1)
        self.assertTrue(any('no son válidas' in x.value for x in at.warning))

    def test_rentabilidad_simple_faltantes_y_costos_avanzados(self):
        at = self.app().run()
        self.boton(at, 'Simular escenario').click().run()
        avanzado = next(x for x in at.expander if x.label == 'Costos avanzados')
        self.assertFalse(avanzado.proto.expanded)
        self.assertEqual(len(avanzado.number_input), 10)
        self.assertTrue(any('Aún no hay información suficiente' in x.value for x in at.info))
        self.assertFalse(any(x.label == 'Inversión inicial' for x in at.metric))
        next(x for x in at.number_input if x.label == 'Costo por AGV (USD)').set_value(12000).run()
        limite = next(x for x in at.metric if x.label == 'Límite inferior del beneficio neto anual necesario')
        self.assertEqual(limite.value, '8,000.00 USD/año')
        self.assertFalse(at.exception)

    def test_rentabilidad_directa_con_ceros_declarados(self):
        at = self.app().run()
        self.boton(at, 'Simular escenario').click().run()
        for etiqueta, valor in [('Costo por AGV (USD)', 10000), ('Instalación / integración (USD)', 1000),
                                ('Ahorro anual estimado (USD/año)', 7000),
                                ('Pallets adicionales por turno (supuesto de producción)', 0)]:
            next(x for x in at.number_input if x.label == etiqueta).set_value(valor)
        next(x for x in at.checkbox if x.label.startswith('Confirmo que los costos')).check().run()
        self.assertFalse(at.exception)
        self.assertEqual(next(x for x in at.metric if x.label == 'Inversión inicial').value, '21,000.00 USD')
        self.assertEqual(next(x for x in at.metric if x.label == 'Payback').value, '3.00 años')
        self.boton(at, 'Guardar análisis de negocio').click().run()
        e = at.session_state['escenarios_simulados'][0]
        self.assertEqual(e['parametros_economicos']['ahorro_anual_estimado'], 7000)
        self.assertEqual(e['economia']['beneficio_neto_anual'], 7000)
        self.assertEqual(e['resultado']['kpis']['completados_turno'], 214)

    def test_solo_ejecuta_flota_elegida_y_comparar_no_simula(self):
        from app.services.simulador_flota import SimuladorFlota
        ejecutar = SimuladorFlota.ejecutar
        with patch.object(SimuladorFlota, 'ejecutar', autospec=True, side_effect=ejecutar) as simular:
            at = self.app().run()
            for n in (2, 3, 4, 5):
                next(x for x in at.selectbox if x.label == 'Número de AGV a simular').set_value(n)
                self.boton(at, 'Simular escenario').click().run()
                self.assertFalse(at.exception)
            self.assertEqual([c.args[1] for c in simular.call_args_list], [2, 3, 4, 5])
            self.boton(at, 'Comparar escenarios simulados').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(simular.call_count, 4)
            self.assertTrue(all(e['resultado']['parametros']['pallets_terminados'] == 215
                                for e in at.session_state['escenarios_simulados']))

    def test_economia_guardada_no_reescribe_otras_corridas(self):
        from dataclasses import asdict
        from app.services.analisis_negocio import ParametrosEconomicos
        at = self.app().run()
        p = {k: 0.0 for k in asdict(ParametrosEconomicos())}
        p.update(costo_agv=10000., payback_objetivo_anios=3., porcentaje_evitable=100.,
                 operacion_manual_anual=10000.)
        at.session_state['economia_guardada'] = p
        self.boton(at, 'Simular escenario').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['escenarios_simulados'][0]['economia']['capex'], 20000)
        next(x for x in at.selectbox if x.label == 'Número de AGV a simular').set_value(3)
        self.boton(at, 'Simular escenario').click().run()
        next(x for x in at.number_input if x.label == 'Costo por AGV (USD)').set_value(20000).run()
        self.boton(at, 'Guardar análisis de negocio').click().run()
        escenarios = at.session_state['escenarios_simulados']
        self.assertEqual([e['economia']['capex'] for e in escenarios], [20000, 60000])
        self.boton(at, 'Comparar escenarios simulados').click().run()
        self.assertTrue(any('difieren' in w.value for w in at.warning))
        self.assertFalse(at.exception)

    def test_demo_manual_conservada_sin_enviar_tcp(self):
        with patch('app.services.flexsim_cliente.FlexSimCliente.enviar_comando', side_effect=AssertionError('TCP prohibido')) as enviar:
            at = self.app().run()
            at.session_state['modo_principal'] = 'Demo FlexSim'
            at.run()
            self.assertFalse(at.exception)
            self.assertTrue(any(b.label == 'Registrar solicitud' for b in at.button))
            at.session_state['modo_principal'] = 'Análisis de flota'
            at.run()
            self.assertFalse(at.exception)
        enviar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
