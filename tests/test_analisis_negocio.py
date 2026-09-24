"""Cifras sintéticas de prueba; no representan costos ni producción de Nestlé."""
from copy import deepcopy
from dataclasses import replace
import unittest

from app.services.analisis_negocio import (
    LineaBase, ParametrosEconomicos, calcular_economia, calcular_operacion,
    comparar_linea_base, crear_escenario, son_comparables,
)
from app.services.simulador_flota import ParametrosSimulacion, SimuladorFlota


def datos():
    return ParametrosEconomicos(costo_agv=10000, integracion=1000, infraestructura=2000,
        cargadores=1000, otros_iniciales=0, mantenimiento_anual_agv=500, energia_anual=500,
        otros_opex_anuales=500, operacion_manual_anual=10000, personal_transporte_anual=20000,
        otros_actuales_anuales=0, porcentaje_evitable=50, margen_pallet=10,
        pallets_adicionales_turno=2, turnos_dia=2, dias_anio=250, payback_objetivo_anios=3)


class EconomiaTests(unittest.TestCase):
    def test_ahorro_directo_sustituye_desglose_incluso_cero(self):
        for ahorro in (0, 4000):
            e = calcular_economia(2, replace(datos(), ahorro_anual_estimado=ahorro))
            self.assertEqual(e['ahorro_operativo_anual'], ahorro)
            self.assertEqual(e['beneficio_neto_anual'], 10000 + ahorro - 2000)

    def test_beneficio_minimo_sin_datos_de_beneficios(self):
        e = calcular_economia(2, ParametrosEconomicos(costo_agv=10000, integracion=1000,
            infraestructura=0, cargadores=0, otros_iniciales=0))
        self.assertEqual(e['beneficio_neto_anual_minimo'], 7000)
        self.assertIsNone(e['beneficio_neto_anual'])
        self.assertIsNone(e['roi_anual_pct'])
        self.assertIsNone(e['payback_anios'])

    def test_capex_opex_beneficios_roi_payback(self):
        e = calcular_economia(2, datos())
        self.assertEqual(e['capex'], 24000)
        self.assertEqual(e['opex_anual'], 2000)
        self.assertEqual(e['beneficio_produccion_anual'], 10000)
        self.assertEqual(e['ahorro_operativo_anual'], 15000)
        self.assertEqual(e['beneficio_neto_anual'], 23000)
        self.assertAlmostEqual(e['payback_anios'], 24000/23000)
        self.assertAlmostEqual(e['payback_meses'], 12*24000/23000)
        self.assertAlmostEqual(e['roi_anual_pct'], 100*23000/24000)

    def test_equilibrio_verificado_sustituyendo_cada_umbral(self):
        p = replace(datos(), porcentaje_evitable=0)
        e = calcular_economia(2, p)
        self.assertEqual(e['pallets_minimos_turno'], 2)
        self.assertEqual(e['margen_minimo_pallet'], 10)
        self.assertEqual(e['ahorro_anual_minimo'], 0)
        self.assertEqual(e['costo_maximo_agv'], 10000)
        self.assertEqual(e['payback_anios'], 3)
        self.assertEqual(calcular_economia(2, replace(p, pallets_adicionales_turno=e['pallets_minimos_turno']))['payback_anios'], 3)

    def test_neto_negativo_y_cero(self):
        for margen, esperado in ((0, -2000), (2, 0)):
            with self.subTest(margen=margen):
                e = calcular_economia(2, replace(datos(), porcentaje_evitable=0, margen_pallet=margen))
                self.assertEqual(e['beneficio_neto_anual'], esperado)
                self.assertEqual(e['estado'], 'No rentable bajo los supuestos actuales.')
                self.assertIsNone(e['payback_anios'])
                self.assertLessEqual(e['roi_anual_pct'], 0)

    def test_faltantes_no_se_convierten_en_cero(self):
        e = calcular_economia(2, ParametrosEconomicos())
        for campo in ('capex', 'beneficio_neto_anual', 'opex_anual', 'payback_anios', 'roi_anual_pct', 'pallets_minimos_turno'):
            self.assertIsNone(e[campo])

    def test_denominadores_cero(self):
        p = replace(datos(), margen_pallet=0, pallets_adicionales_turno=0, porcentaje_evitable=0)
        e = calcular_economia(2, p)
        self.assertIsNone(e['pallets_minimos_turno'])
        self.assertIsNone(e['margen_minimo_pallet'])
        self.assertTrue(e['objetivo_imposible_incluso_agv_gratis'])
        e = calcular_economia(2, replace(p, porcentaje_evitable=100))
        self.assertEqual(e['pallets_minimos_turno'], 0)
        self.assertEqual(e['margen_minimo_pallet'], 0)

    def test_capex_cero(self):
        p = replace(datos(), costo_agv=0, integracion=0, infraestructura=0, cargadores=0)
        e = calcular_economia(2, p)
        self.assertIsNone(e['roi_anual_pct'])
        self.assertEqual(e['payback_anios'], 0)

    def test_cero_produccion_explicito_no_exige_margen(self):
        e = calcular_economia(2, replace(datos(), pallets_adicionales_turno=0, margen_pallet=None))
        self.assertEqual(e['beneficio_produccion_anual'], 0)

    def test_entradas_invalidas(self):
        for valor in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                replace(datos(), costo_agv=valor)
        with self.assertRaises(ValueError):
            replace(datos(), payback_objetivo_anios=0)
        with self.assertRaises(ValueError):
            replace(datos(), porcentaje_evitable=101)


class OperacionTests(unittest.TestCase):
    def test_fases_recortadas_cuadran_con_ocupacion(self):
        for turno in (100., 28800.):
            r = SimuladorFlota(ParametrosSimulacion(duracion_turno_s=turno, espera_disponibilidad_retorno_s=30)).ejecutar(2)
            o = calcular_operacion(r)
            self.assertAlmostEqual(sum(o[c] for c in ('viaje_vacio_s', 'viaje_cargado_s', 'espera_retorno_s', 'carga_s', 'descarga_s')), o['ocupado_s'])
            self.assertAlmostEqual(o['ocupado_s'] + o['libre_s'], turno*2)
            self.assertAlmostEqual(o['ocupado_pct'] + o['libre_pct'], 100)

    def test_flujo_completo_distingue_movimientos_y_pallets(self):
        r = SimuladorFlota().ejecutar(2)
        operacion = calcular_operacion(r)
        self.assertEqual(operacion['pallets_terminados_turno'], r['kpis']['pallets_terminados_turno'])
        self.assertEqual(r['kpis']['movimientos_logisticos_totales'], 430)
        i = comparar_linea_base(r, LineaBase(movimientos_turno=200, comparacion_equivalente=True))
        self.assertEqual(i['movimientos_adicionales_atendidos'], r['kpis']['completados_turno'] - 200)
        self.assertIsNone(i['produccion_adicional_calculada'])

    def test_linea_base_faltante_cero_no_equivalente(self):
        r = SimuladorFlota().ejecutar(2)
        self.assertIsNone(comparar_linea_base(r, LineaBase(movimientos_turno=200))['movimientos_adicionales_atendidos'])
        self.assertIsNone(comparar_linea_base(r, LineaBase(movimientos_turno=0, comparacion_equivalente=True))['incremento_logistico_pct'])

    def test_guardado_independiente_y_comparaciones_2345(self):
        resultados = [SimuladorFlota().ejecutar(n) for n in (2, 3, 4, 5)]
        escenarios = [crear_escenario(r, economia=datos()) for r in resultados]
        antes = deepcopy(escenarios)
        self.assertTrue(son_comparables(escenarios))
        self.assertEqual(escenarios, antes)
        resultados[0]['parametros']['pallets_terminados'] = 99
        self.assertEqual(escenarios[0]['resultado']['parametros']['pallets_terminados'], 215)
        escenarios[1]['parametros_economicos']['costo_agv'] = 1
        self.assertFalse(son_comparables(escenarios))
        self.assertEqual(escenarios[0], antes[0])


if __name__ == '__main__':
    unittest.main()
