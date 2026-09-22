from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.models.solicitud import SolicitudTraslado, PrioridadSolicitud
from app.services.flexsim_cliente import FlexSimCliente
from app.services.gestor_flota import GestorFlota
from app.services.escenario_turno import EscenarioTurno, generar_eventos, preparar_flota, LINEAS


class Reloj:
    valor = 0.0

    def __call__(self):
        return self.valor


class EscenarioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reloj = Reloj()
        self.gestor = GestorFlota()
        self.gestor.flexsim = Mock()
        self.gestor.flexsim.obtener_estado.return_value = "OK|LIBRE"
        self.gestor.flexsim.crear_pallet.return_value = "OK|PALLET_CREADO"
        self.gestor.flexsim.ejecutar_mision.return_value = "OK|MISION_INICIADA"
        preparar_flota(self.gestor, 3)

    def corrida(self, **kwargs):
        corrida = EscenarioTurno(self.gestor, reloj=self.reloj, directorio=self.tmp.name, **kwargs)
        corrida.iniciar()
        return corrida

    def test_generacion_exacta_determinista(self):
        eventos = generar_eventos()
        self.assertEqual(eventos, generar_eventos())
        self.assertEqual(len(eventos), 215)
        self.assertEqual(Counter(e.tipo for e in eventos), {"suministro": 108, "producto_terminado": 107})
        self.assertEqual([e.id_pallet for e in eventos], [f"PALLET_{i:03d}" for i in range(1, 216)])
        self.assertTrue(all(0 <= e.tiempo_programado < 28800 for e in eventos))
        self.assertEqual(Counter(e.linea for e in eventos),
                         dict(zip(LINEAS, (44, 44, 43, 42, 42))))
        for ida, retorno in zip(eventos[0:214:2], eventos[1:214:2]):
            self.assertEqual(ida.linea, retorno.linea)
            self.assertEqual(ida.id_ciclo, retorno.id_ciclo)
            self.assertEqual(retorno.depende_de, ida.numero_movimiento)
            self.assertEqual(retorno.estado, "ESPERANDO_IDA")
        for tipo in ("suministro", "producto_terminado"):
            conteos = Counter(e.linea for e in eventos if e.tipo == tipo)
            self.assertLessEqual(max(conteos.values()) - min(conteos.values()), 1)

    def test_flota_activa_2_a_5_y_sin_inventar_posiciones(self):
        for n in (2, 3, 4, 5):
            with self.subTest(n=n):
                gestor = GestorFlota()
                preparar_flota(gestor, 5, {"AGV_04": "TRANSIT_4", "AGV_05": "TRANSIT_4"})
                gestor.configurar_flota_activa(n)
                self.assertEqual(gestor.agvs_activos, {f"AGV_{i:02d}" for i in range(1, n + 1)})
                for i in range(8):
                    gestor.registrar_solicitud(SolicitudTraslado(str(i), str(i), "Cookies", 500, "ALMACEN", "COOKIE_1"))
                misiones = gestor.procesar_solicitudes_pendientes()
                self.assertEqual(len(misiones), n)
                self.assertTrue(all(m.agv.id_agv in gestor.agvs_activos for m in misiones))
                self.assertEqual(len(gestor.obtener_solicitudes_pendientes_ordenadas()), 8 - n)
        with self.assertRaises(ValueError):
            preparar_flota(GestorFlota(), 4)
        with self.assertRaises(ValueError):
            self.gestor.configurar_flota_activa(1)

    def test_crear_pallet_valida_respuesta(self):
        cliente = FlexSimCliente()
        with patch.object(cliente, "enviar_comando", return_value="OK|PALLET_CREADO") as enviar:
            cliente.crear_pallet("PALLET_001", "spawn_almacen")
            enviar.assert_called_once_with("CREAR_PALLET|PALLET_001|spawn_almacen")
        for respuesta in ("OK", "OK|LIBRE", "ERROR|PALLET_YA_EXISTE", ""):
            with patch.object(cliente, "enviar_comando", return_value=respuesta):
                with self.assertRaises(RuntimeError):
                    cliente.crear_pallet("P", "spawn_almacen")
        with self.assertRaises(ValueError):
            cliente.crear_pallet("P|otra", "spawn_almacen")

    def test_mapeos_ambos_tipos_y_no_duplicacion_en_rerun(self):
        corrida = self.corrida(cantidad=2, duracion=100)
        corrida.actualizar()
        self.gestor.flexsim.obtener_estado.return_value = "OK|OCUPADO"
        corrida.actualizar()
        self.assertEqual(self.gestor.flexsim.crear_pallet.call_count, 1)
        self.reloj.valor = 50
        corrida.actualizar()
        self.assertEqual(self.gestor.flexsim.crear_pallet.call_count, 1)
        self.gestor.flexsim.obtener_estado.return_value = "OK|LIBRE"
        corrida.actualizar()
        comandos = [c.args for c in self.gestor.flexsim.ejecutar_mision.call_args_list]
        self.assertEqual(comandos[0][1:], ("ControlPoint7", "ControlPoint23", "PALLET_001", "spawn_almacen", "entrada_material_cookie_1"))
        self.assertEqual(comandos[1][1:], ("ControlPoint24", "ControlPoint7", "PALLET_002", "spawn_cookie_1", "pallet_transit4"))
        self.assertEqual(comandos[0][0], comandos[1][0])
        self.assertEqual(corrida.eventos[1].hora_habilitacion, 50)

    def test_cola_y_prioridad_al_liberar(self):
        corrida = self.corrida(cantidad=12, duracion=60)
        self.reloj.valor = 50
        corrida.actualizar()
        self.assertEqual(corrida.indicadores()["Backlog"], 3)
        self.gestor.flexsim.obtener_estado.return_value = "OK|OCUPADO"
        corrida.actualizar()
        self.assertEqual(self.gestor.flexsim.ejecutar_mision.call_count, 3)
        pendientes = self.gestor.obtener_solicitudes_pendientes_ordenadas()
        pendientes[-1].prioridad = PrioridadSolicitud.ALTA
        self.gestor.flexsim.obtener_estado.side_effect = ["OK|LIBRE", "OK|OCUPADO", "OK|OCUPADO"]
        self.reloj.valor = 51
        corrida.actualizar()
        # LIBRE de la ida obliga al retorno, aunque haya otra ida de prioridad ALTA.
        self.assertEqual(self.gestor.flexsim.ejecutar_mision.call_args.args[3], "PALLET_002")
        self.assertEqual(corrida.indicadores()["Backlog"], 3)
        self.gestor.flexsim.obtener_estado.side_effect = ["OK|OCUPADO", "OK|OCUPADO", "OK|LIBRE"]
        self.reloj.valor = 52
        corrida.actualizar()
        self.assertEqual(self.gestor.flexsim.ejecutar_mision.call_args.args[3], pendientes[-1].id_pallet)
        self.assertEqual(corrida.indicadores()["Backlog"], 2)

    def test_kpis_aceleracion_corte_y_persistencia(self):
        corrida = self.corrida(cantidad=2, duracion=100, factor=10)
        corrida.actualizar()
        self.reloj.valor = 2
        corrida.actualizar()
        self.assertEqual(corrida.eventos[0].hora_finalizacion, 20)
        self.gestor.flexsim.obtener_estado.return_value = "OK|OCUPADO"
        self.reloj.valor = 5
        corrida.actualizar()
        self.gestor.flexsim.obtener_estado.return_value = "OK|OCUPADO"
        self.reloj.valor = 10
        corrida.actualizar()
        resultado = json.loads(Path(corrida.ruta_resultado).read_text(encoding="utf-8"))
        self.assertEqual(resultado["numero_agv"], 3)
        self.assertEqual(resultado["kpis"]["movimientos_completados"], 1)
        self.assertEqual(resultado["kpis"]["movimientos_pendientes_al_corte"], 1)
        self.assertEqual(resultado["kpis"]["ciclo_promedio_s"], 20)
        self.assertEqual(resultado["kpis"]["espera_promedio_s"], 0)
        self.assertAlmostEqual(sum(a["tiempo_ocupado_s"] for a in resultado["kpis"]["por_agv"].values()), 100)
        for a in resultado["kpis"]["por_agv"].values():
            self.assertAlmostEqual(a["tiempo_libre_s"] + a["tiempo_ocupado_s"], 100)
        self.assertGreater(resultado["kpis"]["distancia_total_estimada_m"], 0)
        self.gestor.flexsim.obtener_estado.return_value = "OK|LIBRE"
        self.reloj.valor = 20
        corrida.actualizar()
        self.assertEqual(corrida.resultado, resultado)
        self.assertEqual(corrida.tiempo_logico, 100)
        self.assertEqual(corrida.indicadores()["Completados"], 1)

    def test_respuesta_tardia_no_cuenta_como_completada(self):
        corrida = self.corrida(cantidad=2, duracion=10)
        corrida.actualizar()
        def tarde(_):
            self.reloj.valor = 11
            return "OK|LIBRE"
        self.gestor.flexsim.obtener_estado.side_effect = tarde
        self.reloj.valor = 9
        corrida.actualizar()
        self.assertEqual(corrida.resultado["kpis"]["movimientos_completados"], 0)
        self.assertEqual(self.gestor.flexsim.crear_pallet.call_count, 1)
        self.assertIsNone(corrida.eventos[1].hora_creacion)

    def test_detener_no_envia_mas_trabajo(self):
        corrida = self.corrida(cantidad=6, duracion=60)
        self.reloj.valor = 50
        corrida.actualizar()
        corrida.detener()
        corrida.actualizar()
        self.assertEqual(corrida.estado, "DETENIDO")
        self.assertEqual(self.gestor.flexsim.ejecutar_mision.call_count, 3)

    def test_timeout_creacion_no_reintenta(self):
        corrida = self.corrida()
        self.gestor.flexsim.crear_pallet.side_effect = TimeoutError("respuesta perdida")
        corrida.actualizar()
        corrida.actualizar()
        self.assertEqual(corrida.estado, "ERROR")
        self.assertEqual(self.gestor.flexsim.crear_pallet.call_count, 1)
        self.assertEqual(corrida.eventos[0].estado, "CREACION_ENVIADA")
        self.gestor.flexsim.ejecutar_mision.assert_not_called()

    def test_timeout_mision_no_libera_agv_ni_reintenta(self):
        corrida = self.corrida()
        self.gestor.flexsim.ejecutar_mision.side_effect = TimeoutError("respuesta perdida")
        corrida.actualizar()
        corrida.actualizar()
        self.assertEqual(corrida.estado, "ERROR")
        self.assertEqual(self.gestor.flexsim.ejecutar_mision.call_count, 1)
        self.assertIsNotNone(self.gestor.misiones[0].agv.mision_actual)

    def test_estado_invalido_detiene(self):
        corrida = self.corrida()
        corrida.actualizar()
        self.gestor.flexsim.obtener_estado.return_value = "ERROR|AGV_NO_EXISTE"
        corrida.actualizar()
        self.assertEqual(corrida.estado, "ERROR")
        self.assertEqual(corrida.indicadores()["Completados"], 0)

    def test_disponibilidad_fisica_antes_de_iniciar(self):
        corrida = EscenarioTurno(self.gestor, reloj=self.reloj, directorio=self.tmp.name)
        self.gestor.flexsim.obtener_estado.return_value = "OK|OCUPADO"
        with self.assertRaises(RuntimeError):
            corrida.iniciar()
        self.gestor.flexsim.crear_pallet.assert_not_called()

    def test_peso_maximo_y_validacion_configuracion(self):
        with self.assertRaises(ValueError):
            SolicitudTraslado("T", "P", "Cookies", 801, "ALMACEN", "COOKIE_1")
        for factor in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                EscenarioTurno(self.gestor, factor=factor)

    def test_215_eventos_solo_con_doble_tcp(self):
        corrida = self.corrida()
        for evento in corrida.eventos:
            self.reloj.valor = evento.tiempo_programado
            corrida.actualizar()
        self.reloj.valor = 28799
        corrida.actualizar()
        self.reloj.valor = 28800
        corrida.actualizar()
        self.assertEqual(self.gestor.flexsim.crear_pallet.call_count, 215)
        self.assertEqual(corrida.indicadores()["Lanzados"], 215)
        self.assertEqual(corrida.estado, "FINALIZADO")
        self.assertEqual(corrida.indicadores()["Completados"], 215)
        for ida, retorno in zip(corrida.eventos[0:214:2], corrida.eventos[1:214:2]):
            self.assertEqual(ida.agv, retorno.agv)
            self.assertGreaterEqual(retorno.hora_creacion, ida.hora_finalizacion)
        self.assertGreaterEqual(corrida.eventos[-1].hora_creacion,
                                max(e.hora_finalizacion for e in corrida.retornos.values()))

    def test_prueba_pequena_secuencia_exacta(self):
        eventos = generar_eventos(6, 600)
        self.assertEqual([(e.tipo, e.linea) for e in eventos], [
            ("suministro", "COOKIE_1"), ("producto_terminado", "COOKIE_1"),
            ("suministro", "COOKIE_2"), ("producto_terminado", "COOKIE_2"),
            ("suministro", "COOKIE_3"), ("producto_terminado", "COOKIE_3"),
        ])

    def test_reserva_durante_creacion_retorno_y_concurrencia(self):
        corrida = self.corrida(cantidad=6, duracion=60)
        self.reloj.valor = 40
        corrida.actualizar()
        self.assertEqual(len(self.gestor.reservas_ciclo), 3)
        self.assertEqual({m.solicitud.id_pallet for m in self.gestor.misiones},
                         {"PALLET_001", "PALLET_003", "PALLET_005"})
        agv = self.gestor.misiones[0].agv
        # Durante CREAR_PALLET, la misión anterior ya terminó pero la reserva sigue.
        def crear(pallet, estacion):
            self.assertEqual((pallet, estacion), ("PALLET_002", "spawn_cookie_1"))
            self.assertIn(agv.id_agv, self.gestor.reservas_ciclo)
            self.assertFalse(agv.esta_disponible())
            ajena = SolicitudTraslado("ajena", "P", "Cookies", 500, "ALMACEN", "COOKIE_1")
            self.assertIsNone(self.gestor.asignar_solicitud(ajena))
            with self.assertRaises(ValueError):
                self.gestor.configurar_flota_activa(2)
            return "OK|PALLET_CREADO"
        self.gestor.flexsim.crear_pallet.side_effect = crear
        self.gestor.flexsim.obtener_estado.side_effect = ["OK|LIBRE", "OK|OCUPADO", "OK|OCUPADO"]
        corrida.actualizar()
        self.assertIs(self.gestor.misiones[-1].agv, agv)
        self.gestor.flexsim.obtener_estado.side_effect = ["OK|OCUPADO", "OK|OCUPADO", "OK|LIBRE"]
        corrida.actualizar()
        self.assertNotIn(agv.id_agv, self.gestor.reservas_ciclo)
        self.assertTrue(agv.esta_disponible())

    def test_timeout_creando_retorno_conserva_reserva(self):
        corrida = self.corrida(cantidad=2, duracion=100)
        corrida.actualizar()
        agv = self.gestor.misiones[0].agv
        self.gestor.flexsim.crear_pallet.side_effect = TimeoutError("retorno ambiguo")
        self.reloj.valor = 10
        corrida.actualizar()
        corrida.actualizar()
        self.assertEqual(corrida.estado, "ERROR")
        self.assertEqual(self.gestor.flexsim.crear_pallet.call_count, 2)
        self.assertIn(agv.id_agv, self.gestor.reservas_ciclo)
        self.assertEqual(corrida.indicadores()["AGV ocupados"], 1)

    def test_suministro_final_espera_todos_los_retornos(self):
        corrida = self.corrida(cantidad=5, duracion=100)
        self.reloj.valor = 80
        corrida.actualizar()
        self.assertIsNone(corrida.eventos[-1].hora_creacion)
        corrida.actualizar()  # Finaliza ambas idas, inicia sus retornos.
        self.assertIsNone(corrida.eventos[-1].hora_creacion)
        corrida.actualizar()  # Finaliza ambos retornos y habilita suministro final.
        self.assertIsNotNone(corrida.eventos[-1].hora_creacion)

    def test_ocupacion_incluye_transicion_entre_piernas(self):
        corrida = self.corrida(cantidad=2, duracion=100)
        corrida.actualizar()
        def crear(*_):
            self.reloj.valor = 15
            return "OK|PALLET_CREADO"
        self.gestor.flexsim.crear_pallet.side_effect = crear
        self.reloj.valor = 10
        corrida.actualizar()
        self.reloj.valor = 25
        corrida.actualizar()
        kpis = corrida.kpis()
        self.assertEqual(kpis["movimientos_completados"], 2)
        self.assertEqual(kpis["ciclo_promedio_s"], 10)
        self.assertEqual(sum(a["tiempo_ocupado_s"] for a in kpis["por_agv"].values()), 25)

    def test_bateria_debe_alcanzar_para_ciclo_completo(self):
        corrida = self.corrida(cantidad=2, duracion=100)
        for agv in self.gestor.agvs:
            agv.bateria = 21  # Puede cubrir una ida corta, pero no todo el ciclo COOKIE_1.
        corrida.actualizar()
        solicitud = self.gestor.solicitudes[0]
        self.assertGreater(solicitud.distancia_retorno, 0)
        self.assertTrue(self.gestor.agvs[0].puede_completar_mision(
            self.gestor.calcular_distancia_mision(self.gestor.agvs[0], solicitud)))
        self.gestor.flexsim.ejecutar_mision.assert_not_called()

    def test_ciclos_con_flotas_2_3_4_5(self):
        for cantidad_agv in (2, 3, 4, 5):
            with self.subTest(agvs=cantidad_agv):
                gestor = GestorFlota()
                gestor.flexsim = Mock()
                gestor.flexsim.obtener_estado.return_value = "OK|LIBRE"
                gestor.flexsim.ejecutar_mision.return_value = "OK|MISION_INICIADA"
                preparar_flota(gestor, 5, {"AGV_04": "TRANSIT_4", "AGV_05": "TRANSIT_4"})
                gestor.configurar_flota_activa(cantidad_agv)
                reloj = Reloj()
                corrida = EscenarioTurno(gestor, cantidad=10, duracion=100,
                                         reloj=reloj, directorio=self.tmp.name)
                corrida.iniciar()
                reloj.valor = 80
                corrida.actualizar()
                self.assertEqual(len(gestor.reservas_ciclo), cantidad_agv)
                for _ in range(6):
                    corrida.actualizar()
                self.assertEqual(corrida.indicadores()["Completados"], 10)
                self.assertFalse(gestor.reservas_ciclo)
                for ida, retorno in zip(corrida.eventos[::2], corrida.eventos[1::2]):
                    self.assertEqual(ida.agv, retorno.agv)
                    self.assertIn(ida.agv, gestor.agvs_activos)

    def test_mapeo_manual_producto_terminado_preservado(self):
        solicitud = SolicitudTraslado("T", "P", "Cookies", 500, "COOKIE_1", "ALMACEN")
        mision = self.gestor.asignar_solicitud(solicitud)
        self.gestor.iniciar_mision(mision.id_mision)
        self.assertEqual(self.gestor.flexsim.ejecutar_mision.call_args.args[-2:], ("fin_linea_cookie_1", "pallet_transit4"))

    def test_salto_hasta_corte_no_lanza_fuera_del_turno(self):
        corrida = self.corrida()
        self.reloj.valor = 40000
        corrida.actualizar()
        self.gestor.flexsim.crear_pallet.assert_not_called()
        self.assertEqual(corrida.resultado["kpis"]["no_lanzados"], 215)
        self.assertEqual(corrida.tiempo_logico, 28800)

    def test_creacion_lenta_no_envia_mision_fuera_del_turno(self):
        corrida = self.corrida(cantidad=2, duracion=10)
        def crear(*_):
            self.reloj.valor = 11
            return "OK|PALLET_CREADO"
        self.gestor.flexsim.crear_pallet.side_effect = crear
        corrida.actualizar()
        self.gestor.flexsim.ejecutar_mision.assert_not_called()
        self.assertEqual(self.gestor.flexsim.crear_pallet.call_count, 1)
        self.assertEqual(corrida.estado, "FINALIZADO")

    def test_error_guardado_conserva_resultado_y_permite_reintento(self):
        corrida = self.corrida()
        with patch.object(Path, "write_text", side_effect=OSError("sin espacio")):
            corrida.detener()
        self.assertIsNotNone(corrida.resultado)
        self.assertEqual(corrida.error_guardado, "sin espacio")
        corrida.guardar_resultado()
        self.assertIsNone(corrida.error_guardado)
        self.assertTrue(Path(corrida.ruta_resultado).exists())


if __name__ == "__main__":
    unittest.main()
