from copy import deepcopy
import unittest

from app.services.simulador_flota import SimuladorFlota, ParametrosSimulacion, comparar_flotas
from app.services.indicadores_capacidad import calcular_capacidad


class CapacidadTests(unittest.TestCase):
    def test_capacidad_se_calcula_con_flujo_completo(self):
        resultados = comparar_flotas()
        self.assertEqual([r['numero_agv'] for r in resultados], [2, 3, 4, 5])
        for r in resultados:
            self.assertIn(r['kpis']['capacidad_logistica'], ('SUFICIENTE', 'SATURADA', 'INSUFICIENTE'))
            self.assertEqual(r['kpis']['movimientos_logisticos_totales'], 430)
            pt = [m for m in r['movimientos'] if m['tipo'] == 'producto_terminado']
            self.assertAlmostEqual(r['kpis']['espera_agv_media_pt_s'],
                                   sum(m['espera_s'] for m in pt) / len(pt))

    def test_servicio_excede_horas_disponibles(self):
        r = SimuladorFlota(ParametrosSimulacion(tiempo_carga_s=1000)).ejecutar(2)
        self.assertEqual(r['kpis']['capacidad_logistica'], 'INSUFICIENTE')
        self.assertGreater(r['kpis']['carga_trabajo_requerida_pct'], 100)

    def test_derivados_no_mutan_misiones_y_separan_servicio(self):
        r = SimuladorFlota().ejecutar(2)
        antes = deepcopy(r)
        k = calcular_capacidad(r['movimientos'], r['eventos'], 28800, 2)
        self.assertEqual(r, antes)
        self.assertAlmostEqual(k['ultimo_pt_llegada_s'] + k['ultimo_pt_espera_agv_s'] + k['ultimo_pt_servicio_s'],
                               r['kpis']['tiempo_producto_terminado_s'])
        pt = [m for m in r['movimientos'] if m['tipo'] == 'producto_terminado']
        esperas_pt = [m['inicio_s'] - m['llegada_s'] for m in pt]
        self.assertAlmostEqual(k['espera_agv_media_pt_s'], sum(esperas_pt) / len(esperas_pt))
        self.assertEqual(k['espera_agv_maxima_pt_s'], max(esperas_pt))
        self.assertEqual(k['pallets_esperaron_agv'], sum(e > 1e-9 for e in esperas_pt))

    def test_suministros_no_se_cuentan_como_pallets_que_esperaron(self):
        r = SimuladorFlota().ejecutar(2)
        pt = [m for m in r['movimientos'] if m['tipo'] == 'producto_terminado']
        self.assertEqual(r['kpis']['pallets_esperaron_agv'], sum(m['espera_s'] > 1e-9 for m in pt))
        self.assertEqual(len([m for m in r['movimientos'] if m['tipo'] == 'suministro']), 215)
