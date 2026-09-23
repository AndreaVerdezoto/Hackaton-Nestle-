from copy import deepcopy
import unittest

from app.services.simulador_flota import SimuladorFlota, ParametrosSimulacion, comparar_flotas
from app.services.indicadores_capacidad import calcular_capacidad


class CapacidadTests(unittest.TestCase):
    def test_dos_generan_cola_tres_la_eliminan_sin_cambiar_cierre(self):
        resultados = comparar_flotas()
        self.assertEqual([r['kpis']['capacidad_logistica'] for r in resultados],
                         ['SATURADA', 'SUFICIENTE', 'SUFICIENTE', 'SUFICIENTE'])
        self.assertGreater(resultados[0]['kpis']['espera_agv_media_pt_s'], 0)
        for r in resultados[1:]:
            self.assertEqual(r['kpis']['espera_agv_media_pt_s'], 0)
            self.assertEqual(r['kpis']['backlog_maximo_agv'], 0)
            self.assertEqual(r['kpis']['pallets_terminados_pendientes'], 1)
            self.assertEqual(r['kpis']['pt_tardios_sin_espera_agv'], 1)
            self.assertEqual(r['kpis']['pt_en_servicio_corte'], 1)
            self.assertEqual(r['kpis']['pt_sin_asignar_corte'], 0)

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
        esperas = [m['inicio_s']-m['llegada_s'] for m in r['movimientos']]
        self.assertAlmostEqual(k['espera_agv_media_pt_s'], sum(esperas)/215)
        self.assertEqual(k['espera_agv_maxima_pt_s'], max(esperas))
        self.assertEqual(k['pallets_esperaron_agv'], sum(e > 1e-9 for e in esperas))

    def test_suministros_no_se_cuentan_como_pallets_que_esperaron(self):
        r = SimuladorFlota(ParametrosSimulacion(movimientos_suministro=40)).ejecutar(2)
        pt = [m for m in r['movimientos'] if m['tipo'] == 'producto_terminado']
        self.assertEqual(r['kpis']['pallets_esperaron_agv'], sum(m['espera_s'] > 1e-9 for m in pt))
