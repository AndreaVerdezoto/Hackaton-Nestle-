import unittest
from unittest.mock import patch
from copy import deepcopy
from pathlib import Path

from app.models.bateria import MODELO_BATERIA, CARGADORES
from app.services.bateria_flota import bateria_en_instante
from app.services.simulador_flota import SimuladorFlota, ParametrosSimulacion
from app.services.estado_visual import estado_en_instante, cargar_mapa, posicion
from app.ui.simulacion_2d import horas_minutos, avanzar_reloj
from streamlit.testing.v1 import AppTest


class BateriaTests(unittest.TestCase):
    def test_ejemplos_restantes(self):
        self.assertAlmostEqual(MODELO_BATERIA.uso_restante_s(72), 14976)
        self.assertEqual(horas_minutos(MODELO_BATERIA.uso_restante_s(72)), '4 h 10 min')
        self.assertEqual(horas_minutos(MODELO_BATERIA.carga_restante_s(45)), '1 h 39 min')
        self.assertEqual(MODELO_BATERIA.uso_restante_s(20), 0)

    def test_tiempo_y_limites(self):
        self.assertEqual(MODELO_BATERIA.nivel(100, 1800), 93.75)
        self.assertEqual(MODELO_BATERIA.nivel(20, 8640, cargando=True), 100)
        self.assertEqual(MODELO_BATERIA.nivel(10, 100000), 0)
        self.assertEqual(MODELO_BATERIA.nivel(90, 100000, cargando=True), 100)
        self.assertFalse(MODELO_BATERIA.admite_mision(25, 2304))
        self.assertTrue(MODELO_BATERIA.admite_mision(25, 1440))

    def test_pausa_y_velocidad_solo_reloj(self):
        reloj = {'tiempo_s':0.,'marca':0.,'ejecutando':True,'velocidad':10}
        avanzar_reloj(reloj, 180, 28800)
        self.assertEqual(reloj['tiempo_s'], 1800)
        reloj['ejecutando'] = False
        avanzar_reloj(reloj, 2000, 28800)
        self.assertEqual(reloj['tiempo_s'], 1800)
        self.assertEqual(bateria_en_instante([], reloj['tiempo_s']), 93.75)


class SimulacionBateriaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch('app.services.gestor_flota.FlexSimCliente', side_effect=AssertionError('TCP prohibido')):
            cls.r = SimuladorFlota(ParametrosSimulacion(velocidad_maxima_ms=1)).ejecutar(3,simular_bateria=True,cargadores=CARGADORES)

    def test_misiones_reserva_cargadores_y_no_cambio_peso(self):
        r = self.r
        self.assertEqual(len(r['movimientos']), 215)
        self.assertTrue(all(m['bateria_fin'] >= 20-1e-8 for m in r['movimientos']))
        self.assertEqual(r['cargadores_no_utilizables'], ['ControlPoint30'])
        self.assertTrue(all(len(rs) >= 1 for rs in r['recargas'].values()))
        pesado = SimuladorFlota(ParametrosSimulacion(velocidad_maxima_ms=1,peso_pallet_kg=800)).ejecutar(3,simular_bateria=True,cargadores=CARGADORES)
        self.assertEqual(r['recargas'], pesado['recargas'])
        self.assertEqual(r['movimientos'], pesado['movimientos'])

    def test_recarga_no_asigna_y_regresa_a_cien(self):
        for agv, recargas in self.r['recargas'].items():
            for carga in recargas:
                self.assertAlmostEqual(bateria_en_instante(recargas,carga['fin_s']),100)
                for m in self.r['movimientos']:
                    if m['agv'] == agv:
                        self.assertTrue(m['fin_s'] <= carga['inicio_s'] or m['inicio_s'] >= carga['fin_s'])
                t=(carga['inicio_carga_s']+carga['fin_s'])/2
                a=next(x for x in estado_en_instante(self.r,t)['flota'] if x['agv']==agv)
                self.assertEqual(a['estado'],'CARGANDO_BATERIA')
                self.assertAlmostEqual(a['carga_restante_s'],carga['fin_s']-t)

    def test_libre_consume_y_consulta_no_muta(self):
        antes=deepcopy(self.r)
        estado=estado_en_instante(self.r,60)
        self.assertTrue(any(a['estado']=='DISPONIBLE' for a in estado['flota']))
        self.assertTrue(all(abs(a['bateria']-(100-100*60/28800))<1e-9 for a in estado['flota']))
        self.assertEqual(antes,self.r)

    def test_interpolacion_continua(self):
        m=self.r['movimientos'][0]; viaje=m['vacio']; p=self.r['parametros']; mapa=cargar_mapa()
        principio=posicion(viaje,0,p,mapa)
        mitad=posicion(viaje,viaje['tiempo_s']/2,p,mapa)
        fin=posicion(viaje,viaje['tiempo_s'],p,mapa)
        self.assertNotEqual(principio,mitad)
        self.assertNotEqual(mitad,fin)
        cerca=posicion(viaje,viaje['tiempo_s']/2+0.001,p,mapa)
        self.assertLess(abs(cerca[0]-mitad[0])+abs(cerca[1]-mitad[1]),0.01)

    def test_cargadores_sin_conectividad_error(self):
        with self.assertRaisesRegex(ValueError,'cargadores existentes'):
            SimuladorFlota().ejecutar(2,simular_bateria=True,cargadores=['ControlPoint30'])


class Interfaz2DTests(unittest.TestCase):
    def test_2d_reutiliza_escenario_existente_sin_simular(self):
        resultado = {
            'numero_agv': 1,
            'parametros': {
                'ubicacion_inicial': 'ControlPoint7',
                'velocidad_maxima_ms': 1,
                'aceleracion_ms2': 1,
                'desaceleracion_ms2': 1,
                'factor_escala_metros_por_unidad': 1,
            },
            'kpis': {'tiempo_total_s': 600},
            'movimientos': [],
            'por_agv': [{
                'agv': 'AGV_01',
                'movimientos_turno': 0,
                'movimientos_totales': 0,
                'pallets_terminados_turno': 0,
                'pallets_terminados_totales': 0,
                'ocupado_turno_s': 0,
                'libre_turno_s': 600,
                'utilizacion_pct': 0,
                'distancia_vacia_m': 0,
                'distancia_cargada_m': 0,
                'distancia_total_m': 0,
                'posicion_final': 'ControlPoint7',
            }],
            'demanda': [],
            'eventos': [],
        }
        codigo = f"""
import streamlit as st
st.session_state['escenarios_simulados'] = [{{'id': 'escenario_1', 'resultado': {resultado!r}}}]
st.session_state['escenario_activo'] = 'escenario_1'
from app.ui.simulacion_2d import mostrar_2d
mostrar_2d()
"""
        with patch.object(SimuladorFlota, 'ejecutar', side_effect=AssertionError('No debe simular')):
            at = AppTest.from_string(codigo, default_timeout=20).run()
            self.assertFalse(at.exception)
            self.assertFalse(any(b.label == 'Iniciar' for b in at.button))
            self.assertTrue(any(x.label == 'Escenario para visualización 2D' for x in at.selectbox))
            next(b for b in at.button if b.label == 'Reanudar').click().run()
            self.assertTrue(at.session_state['reloj_2d']['ejecutando'])
            next(b for b in at.button if b.label == 'Reiniciar reloj').click().run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state['reloj_2d']['tiempo_s'], 0)
