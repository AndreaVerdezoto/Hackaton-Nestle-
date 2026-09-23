import ast
from collections import Counter
from dataclasses import replace
import inspect
import json
import math
import unittest
from unittest.mock import patch

from app.services.gestor_flota import GestorFlota
from app.services import simulador_flota as modulo
from app.services.simulador_flota import (
    ParametrosSimulacion, DemandaMision, SimuladorFlota, comparar_flotas,
    generar_demanda, tiempo_desplazamiento, minimo_suficiente, exportar_json,
)
from app.models.solicitud import PrioridadSolicitud


class CinematicaTests(unittest.TestCase):
    def test_trapezoidal(self):
        self.assertEqual(tiempo_desplazamiento(10, 2, 1, 1), 7)
        self.assertEqual(tiempo_desplazamiento(4, 2, 1, 1), 4)

    def test_triangular(self):
        self.assertAlmostEqual(tiempo_desplazamiento(2, 2, 1, 1), 2 * math.sqrt(2))
        pico = math.sqrt(2 * 1 * 2 * 3 / 5)
        self.assertAlmostEqual(tiempo_desplazamiento(1, 4, 2, 3), pico / 2 + pico / 3)

    def test_cero(self):
        self.assertEqual(tiempo_desplazamiento(0, 2, 1, 1), 0)

    def test_invalidos(self):
        for argumentos in ((-1, 2, 1, 1), (1, 0, 1, 1), (1, 2, 0, 1), (1, 2, 1, -1),
                           (float('nan'), 2, 1, 1), (1, float('inf'), 1, 1)):
            with self.subTest(argumentos=argumentos), self.assertRaises(ValueError):
                tiempo_desplazamiento(*argumentos)


class SimuladorTests(unittest.TestCase):
    def test_no_cliente_socket_ni_sleep(self):
        with patch('app.services.gestor_flota.FlexSimCliente', side_effect=AssertionError('TCP prohibido')) as cliente, \
                patch('socket.socket', side_effect=AssertionError('socket prohibido')), \
                patch('time.sleep', side_effect=AssertionError('sleep prohibido')):
            resultados = comparar_flotas()
        cliente.assert_not_called()
        self.assertEqual(len(resultados), 4)
        arbol = ast.parse(inspect.getsource(modulo))
        self.assertFalse(any(isinstance(n, ast.Attribute) and n.attr in ('sleep', 'monotonic', 'obtener_estado') for n in ast.walk(arbol)))

    def test_demanda_215_producto_terminado_round_robin_uniforme(self):
        demanda = generar_demanda(ParametrosSimulacion())
        self.assertEqual(len(demanda), 215)
        self.assertTrue(all(c.tipo == 'producto_terminado' for c in demanda))
        self.assertEqual(Counter(c.linea for c in demanda), dict.fromkeys(modulo.LINEAS, 43))
        self.assertEqual([c.llegada_s for c in demanda], [i * 28800 / 215 for i in range(215)])
        r = SimuladorFlota().ejecutar(3)
        self.assertEqual(len(r['movimientos']), 215)
        for m in r['movimientos']:
            self.assertEqual(m['destino'], 'ControlPoint7')
            self.assertEqual(m['origen'], GestorFlota.NODOS_PRODUCTO_TERMINADO[m['linea']])
            self.assertEqual(m['cargado']['ruta'][-1], 'ControlPoint7')
            self.assertGreater(m['vacio']['distancia_m'], 0)
        self.assertEqual([m['id_pallet'] for m in r['movimientos']], [f'PALLET_{i:03d}' for i in range(1,216)])

    def test_suministros_independientes_y_cumplimiento(self):
        r = SimuladorFlota(ParametrosSimulacion(movimientos_suministro=40)).ejecutar(2)
        self.assertEqual(Counter(m['tipo'] for m in r['movimientos']), {'producto_terminado':215, 'suministro':40})
        self.assertEqual(r['kpis']['movimientos_logisticos_totales'], 255)
        pt = [m for m in r['movimientos'] if m['tipo'] == 'producto_terminado']
        completados = sum(m['fin_s'] <= 28800 for m in pt)
        self.assertEqual(r['kpis']['pallets_terminados_turno'], completados)
        self.assertEqual(r['kpis']['pallets_terminados_pendientes'], 215 - completados)
        self.assertEqual(r['kpis']['cumplimiento_pct'], 100 * completados/215)
        self.assertEqual(r['kpis']['tiempo_producto_terminado_s'], max(m['fin_s'] for m in pt))
        self.assertEqual(r['kpis']['cumple'], completados == 215)

    def test_comparacion_justa_y_reproducible(self):
        resultados = comparar_flotas()
        self.assertEqual([r['numero_agv'] for r in resultados], [2, 3, 4, 5])
        for r in resultados:
            self.assertEqual(r['parametros'], resultados[0]['parametros'])
            self.assertEqual(r['demanda'], resultados[0]['demanda'])
            repetido = SimuladorFlota().ejecutar(r['numero_agv'])
            self.assertEqual(r['kpis'], repetido['kpis'])
            self.assertEqual(r['movimientos'], repetido['movimientos'])
            for a in r['por_agv']:
                propios = [m for m in r['movimientos'] if m['agv'] == a['agv']]
                for anterior, siguiente in zip(propios, propios[1:]):
                    self.assertLessEqual(anterior['fin_s'], siguiente['inicio_s'])
                self.assertLessEqual(a['utilizacion_pct'], 100)
                self.assertGreaterEqual(a['libre_turno_s'], 0)

    def test_suministro_pendiente_no_cambia_cumplimiento_producto(self):
        p = ParametrosSimulacion(pallets_terminados=1, movimientos_suministro=1)
        demanda = (DemandaMision(1, 0, modulo.LINEAS[0]),
                   DemandaMision(2, 28799, modulo.LINEAS[0], 'suministro'))
        r = SimuladorFlota(p, demanda).ejecutar(2)
        self.assertEqual(r['kpis']['suministros_pendientes'], 1)
        self.assertEqual(r['kpis']['pallets_terminados_pendientes'], 0)
        self.assertTrue(r['kpis']['cumple'])
        self.assertEqual(minimo_suficiente([r]), 2)

    def test_suministro_invalido_y_demandas_sin_relacion(self):
        for valor in (-1, 1.2, True):
            with self.assertRaises(ValueError):
                ParametrosSimulacion(movimientos_suministro=valor)
        p = ParametrosSimulacion(movimientos_suministro=40)
        base = generar_demanda(ParametrosSimulacion())
        extra = generar_demanda(p)
        self.assertEqual(base, extra[:215])
        r = SimuladorFlota(p).ejecutar(3)
        for agv in r['por_agv']:
            misiones = sorted((m for m in r['movimientos'] if m['agv'] == agv['agv']), key=lambda m: m['inicio_s'])
            for anterior, siguiente in zip(misiones, misiones[1:]):
                self.assertLessEqual(anterior['fin_s'], siguiente['inicio_s'])
                self.assertEqual(siguiente['vacio']['ruta'][0], anterior['destino'])

    def test_kpis_desde_eventos_y_distancias(self):
        r = SimuladorFlota(ParametrosSimulacion(tiempo_carga_s=200, tiempo_descarga_s=200)).ejecutar(2)
        k = r['kpis']
        m = r['movimientos']
        self.assertGreater(k['exceso_tiempo_s'], 0)
        self.assertEqual(k['tiempo_total_s'], max(x['fin_s'] for x in m))
        self.assertEqual(k['completados_turno'], sum(x['fin_s'] <= 28800 for x in m))
        self.assertEqual(k['completados_turno'] + k['backlog_corte'], 215)
        self.assertGreaterEqual(k['backlog_corte'], 0)
        self.assertEqual(k['backlog_maximo'], max(e['pendientes'] for e in r['eventos'] if e['evento'] == 'cola'))
        self.assertEqual(k['throughput_mov_h'], k['completados_turno'] / 8)
        self.assertAlmostEqual(k['espera_media_s'], sum(x['inicio_s'] - x['llegada_s'] for x in m) / 215)
        self.assertAlmostEqual(k['ciclo_medio_s'], sum(x['fin_s'] - x['llegada_s'] for x in m) / 215)
        self.assertAlmostEqual(k['distancia_total_m'], k['distancia_vacia_m'] + k['distancia_cargada_m'])
        for a in r['por_agv']:
            propios = [x for x in m if x['agv'] == a['agv']]
            ocupado = sum(max(0, min(x['fin_s'], 28800) - x['inicio_s']) for x in propios)
            self.assertAlmostEqual(a['ocupado_turno_s'], ocupado)
            self.assertAlmostEqual(a['libre_turno_s'] + ocupado, 28800)
            self.assertAlmostEqual(a['distancia_total_m'], sum(x['vacio']['distancia_m'] + x['cargado']['distancia_m'] for x in propios))
        self.assertEqual(Counter(e['evento'] for e in r['eventos'])['fin'], 215)

    def test_dijkstra_conserva_sentidos_y_distancia(self):
        red = GestorFlota(habilitar_flexsim=False)
        red.grafo = {'A': [('B', 3), ('C', 10)], 'B': [('C', 2)], 'C': []}
        self.assertEqual(red.obtener_ruta('A', 'C'), (['A', 'B', 'C'], 5))
        with self.assertRaises(ValueError):
            red.obtener_ruta('C', 'A')

    def test_falta_conectividad_error_claro(self):
        with patch.object(GestorFlota, 'obtener_ruta', side_effect=ValueError('sin ruta')):
            with self.assertRaisesRegex(ValueError, 'falta conectividad'):
                SimuladorFlota()
        with self.assertRaisesRegex(ValueError, 'falta conectividad'):
            SimuladorFlota(ParametrosSimulacion(ubicacion_inicial='INEXISTENTE'))

    def test_parametros_invalidos(self):
        for campo, valor in (('pallets_terminados', 0), ('pallets_terminados', 1.2), ('duracion_turno_s', -2),
                             ('velocidad_maxima_ms', 0), ('aceleracion_ms2', 0), ('desaceleracion_ms2', 0),
                             ('tiempo_carga_s', -1), ('tiempo_descarga_s', float('nan')),
                             ('espera_disponibilidad_retorno_s', -2), ('peso_pallet_kg', 801),
                             ('factor_escala_metros_por_unidad', 0)):
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                ParametrosSimulacion(**{campo: valor})
        with self.assertRaises(ValueError):
            SimuladorFlota().ejecutar(1)

    def test_escala_y_posicion_inicial(self):
        p = ParametrosSimulacion(ubicacion_inicial='ControlPoint11')
        a = SimuladorFlota(p).ejecutar(2)
        b = SimuladorFlota(replace(p, factor_escala_metros_por_unidad=2)).ejecutar(2)
        self.assertGreater(a['movimientos'][0]['vacio']['distancia_m'], 0)
        self.assertAlmostEqual(b['movimientos'][0]['vacio']['distancia_m'], 2 * a['movimientos'][0]['vacio']['distancia_m'])
        self.assertGreater(b['movimientos'][0]['duracion_servicio_s'], a['movimientos'][0]['duracion_servicio_s'])

    def test_espera_retorno_y_reserva(self):
        r = SimuladorFlota(ParametrosSimulacion(pallets_terminados=6, espera_disponibilidad_retorno_s=60)).ejecutar(3)
        for m in r['movimientos']:
            self.assertEqual(m['espera_disponibilidad_s'], 60 if m['tipo'] == 'producto_terminado' else 0)
            self.assertAlmostEqual(m['duracion_servicio_s'], m['vacio']['tiempo_s'] + m['carga_s'] +
                                   m['cargado']['tiempo_s'] + m['descarga_s'] + m['espera_disponibilidad_s'])
        for a in r['por_agv']:
            self.assertEqual(a['posicion_final'], 'ControlPoint7')

    def test_demanda_historica_y_prioridad(self):
        p = ParametrosSimulacion(pallets_terminados=3)
        demanda = tuple(DemandaMision(i + 1, 0, modulo.LINEAS[i], "producto_terminado",
                                    PrioridadSolicitud.ALTA if i == 2 else PrioridadSolicitud.NORMAL) for i in range(3))
        r = SimuladorFlota(p, demanda).ejecutar(2)
        inicios = [e['movimiento'] for e in r['eventos'] if e['evento'] == 'inicio']
        self.assertEqual(inicios[:2], [3, 1])
        self.assertGreater(r['kpis']['backlog_maximo'], 0)
        with self.assertRaises(ValueError):
            SimuladorFlota(p, demanda[:1])

    def test_peso_no_inventa_cinematica(self):
        a = SimuladorFlota(ParametrosSimulacion(peso_pallet_kg=100)).ejecutar(2)
        b = SimuladorFlota(ParametrosSimulacion(peso_pallet_kg=800)).ejecutar(2)
        self.assertEqual(a['kpis'], b['kpis'])

    def test_ejemplo_analitico_y_corte_inclusivo(self):
        p = ParametrosSimulacion(pallets_terminados=1, duracion_turno_s=22, tiempo_carga_s=3, tiempo_descarga_s=5)
        s = SimuladorFlota(p)
        s.red.grafo = {'ControlPoint7': [('ControlPoint24', 10)], 'ControlPoint24': [('ControlPoint7', 10)]}
        s._rutas.clear()
        r = s.ejecutar(2)
        self.assertEqual(r['movimientos'][0]['fin_s'], 22)
        self.assertEqual(r['kpis']['pallets_terminados_turno'], 1)
        self.assertEqual(r['kpis']['pallets_terminados_pendientes'], 0)
        self.assertTrue(r['kpis']['cumple'])
        self.assertEqual(r['por_agv'][0]['utilizacion_pct'], 100)
        self.assertEqual(r['kpis']['distancia_total_m'], 20)

    def test_fin_producto_separado_de_ultimo_suministro(self):
        p = ParametrosSimulacion(pallets_terminados=1, movimientos_suministro=1, espera_disponibilidad_retorno_s=30000)
        r = SimuladorFlota(p).ejecutar(2)
        self.assertGreater(r['kpis']['tiempo_total_s'], r['kpis']['hora_fin_movimiento_ultimo_id_s'])
        self.assertEqual(r['kpis']['margen_tiempo_s'], 0)
        self.assertEqual(r['kpis']['pallets_terminados_pendientes'], 1)
        self.assertEqual(r['kpis']['suministros_pendientes'], 0)

    def test_json_y_minimo_sin_resultados_fijos(self):
        resultados = comparar_flotas()
        self.assertEqual(json.loads(exportar_json(resultados)), resultados)
        esperado = min((r['numero_agv'] for r in resultados if r['kpis']['backlog_corte'] == 0), default=None)
        self.assertEqual(minimo_suficiente(resultados), esperado)
        lentos = comparar_flotas(ParametrosSimulacion(tiempo_carga_s=1000, tiempo_descarga_s=1000))
        self.assertIsNone(minimo_suficiente(lentos))
        self.assertNotEqual(lentos[0]['kpis'], resultados[0]['kpis'])


if __name__ == '__main__':
    unittest.main()
