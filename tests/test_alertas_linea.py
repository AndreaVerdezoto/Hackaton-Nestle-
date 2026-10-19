"""Alertas temporales: fronteras, trazabilidad, reproducción y configuración."""
from copy import deepcopy
import unittest
import math
from unittest.mock import patch

from app.services.alertas_linea import (
    consultar_alertas, actualizar_registro, historial_visible, nuevas_sin_leer,
    normalizar_registro, TOLERANCIA_ESPERA_S,
)
from app.services.nestor import Nestor
from app.services.simulador_flota import SimuladorFlota
from app.ui.simulacion_2d import avanzar_reloj


def movimiento(numero=1, linea="COOKIE_1", llegada=0, inicio=200):
    return {"numero": numero, "linea": linea, "tipo": "producto_terminado",
            "id_pallet": f"P-{numero}", "llegada_s": llegada, "inicio_s": inicio,
            "fin_s": inicio + 100, "agv": "AGV_ASIGNADO_DESPUES", "espera_s": inicio - llegada}


def resultado(*movimientos):
    return {"movimientos": list(movimientos or (movimiento(),)), "kpis": {"tiempo_total_s": 1000}}


class AlertasLineaTests(unittest.TestCase):
    def test_umbral_es_estricto_y_tiempo_es_el_del_reloj(self):
        r = resultado()
        for t, cantidad in ((-1, 0), (0, 0), (119.9, 0), (120, 0), (120.001, 1)):
            with self.subTest(t=t):
                consulta = consultar_alertas(r, t)
                self.assertEqual(len(consulta["activas"]), cantidad)
                if cantidad:
                    self.assertEqual(consulta["activas"][0]["espera_s"], t)
        # El umbral de 60 s del analizador global no se utiliza aquí.
        self.assertFalse(consultar_alertas(r, 90)["activas"])

    def test_no_anuncia_solicitudes_futuras_ni_asignaciones_futuras(self):
        r = resultado(movimiento(), movimiento(2, llegada=300, inicio=600))
        consulta = consultar_alertas(r, 121)
        self.assertEqual(len(consulta["activas"]), 1)
        activa = consulta["activas"][0]
        for campo in ("agv", "asignada_s", "inicio_s", "fin_s"):
            self.assertNotIn(campo, activa)
        self.assertEqual(consulta["asignaciones"], [])
        r["movimientos"][0]["inicio_s"] = 999
        r["movimientos"][0]["agv"] = "OTRO_AGV_FUTURO"
        r["movimientos"][1]["linea"] = "FUTURA"
        self.assertEqual(consulta, consultar_alertas(r, 121))

    def test_asignada_antes_o_exactamente_en_umbral_no_genera_alerta(self):
        for inicio in (10, 120):
            consulta = consultar_alertas(resultado(movimiento(inicio=inicio)), 300)
            self.assertEqual(consulta["activas"], [])
            self.assertEqual(consulta["resueltas"], [])

    def test_al_asignar_despues_del_umbral_pasa_a_historica_atendida(self):
        r = resultado()
        self.assertEqual(len(consultar_alertas(r, 199)["activas"]), 1)
        consulta = consultar_alertas(r, 200)
        self.assertEqual(consulta["activas"], [])
        self.assertEqual(consulta["resueltas"][0]["espera_s"], 200)
        self.assertEqual(consulta["resueltas"][0]["asignada_s"], 200)
        self.assertEqual(consulta["resueltas"][0]["agv"], "AGV_ASIGNADO_DESPUES")

    def test_agrupa_por_linea_sin_perder_solicitudes(self):
        r = resultado(movimiento(), movimiento(2, llegada=10, inicio=400),
                      movimiento(3, "CHOCOLATE", inicio=300), movimiento(4, "WAFER", inicio=500))
        consulta = consultar_alertas(r, 150)
        grupos = {g["linea"]: g for g in consulta["por_linea"]}
        self.assertEqual(len(grupos), 3)
        self.assertEqual(grupos["COOKIE_1"]["cantidad"], 2)
        self.assertEqual(grupos["COOKIE_1"]["espera_maxima_s"], 150)
        self.assertEqual({m["solicitud"] for m in grupos["COOKIE_1"]["solicitudes"]}, {"1", "2"})
        self.assertEqual(grupos["WAFER"]["nombre"], "Wafer")

    def test_puede_reutilizar_estado_en_instante(self):
        r = resultado()
        estado = {"tiempo_s": 121, "pendientes": r["movimientos"]}
        self.assertEqual(consultar_alertas(r, 121), consultar_alertas(r, 121, estado=estado))

    def test_no_recalcula_ni_modifica_resultados(self):
        r = resultado()
        antes = deepcopy(r)
        with patch.object(SimuladorFlota, "ejecutar", side_effect=AssertionError("No simular")):
            consultar_alertas(r, 150)
            Nestor(r, tiempo_s=150).responder_sugerida("alertas_actuales")
        self.assertEqual(r, antes)

    def test_exportacion_antigua_con_contrato_minimo_es_compatible(self):
        r = resultado()
        r["version_modelo"] = "version_anterior"
        m = r["movimientos"][0]
        m["id_mision"] = m.pop("numero")
        consulta = consultar_alertas(r, 150)
        self.assertEqual(len(consulta["activas"]), 1)
        self.assertEqual(consulta["limitaciones"], [])

    def test_datos_incompletos_no_inventan_lineas_ni_tiempos(self):
        casos = [{}, {"movimientos": None}, resultado({"numero": 1}),
                 resultado(movimiento(inicio=float("nan"))), resultado(movimiento(llegada=-1)),
                 resultado(movimiento(inicio=-2)), resultado(movimiento(linea=None)),
                 resultado(movimiento(), movimiento())]
        for r in casos:
            with self.subTest(r=r):
                consulta = consultar_alertas(r, 150)
                self.assertFalse(consulta["activas"])
                self.assertTrue(consulta["limitaciones"])
                respuesta = Nestor(r, tiempo_s=150).responder_sugerida("alertas_actuales")
                self.assertTrue(respuesta["limitaciones"])
                self.assertFalse(respuesta["acciones_revision"])

    def test_validacion_de_umbral_y_reloj(self):
        for umbral in (-1, float("nan"), float("inf"), True, "120"):
            with self.subTest(umbral=umbral), self.assertRaises(ValueError):
                consultar_alertas(resultado(), 150, umbral)
        for t in (None, float("nan"), float("inf"), True):
            self.assertTrue(consultar_alertas(resultado(), t)["limitaciones"])
        self.assertEqual(consultar_alertas(resultado(), 2000)["tiempo_s"], 1000)


class RegistroAlertasTests(unittest.TestCase):
    def consultar(self, t, registro=None, umbral=120, revision=0, leidas=False):
        return actualizar_registro(registro, "a", consultar_alertas(resultado(), t, umbral),
                                   revision=revision, leidas=leidas)

    def test_pausa_reanudacion_y_no_duplicacion(self):
        r = self.consultar(0)
        r = self.consultar(121, r)
        primero = deepcopy(r["eventos"])
        for _ in range(4):
            r = self.consultar(121, r)
        self.assertEqual(r["eventos"], primero)
        r = self.consultar(140, r)
        self.assertEqual(len(r["eventos"]), 1)
        self.assertEqual(nuevas_sin_leer(r, 140), 1)
        r = self.consultar(140, r, leidas=True)
        self.assertEqual(nuevas_sin_leer(r, 140), 0)

    def test_x50_registra_retraso_atendido_entre_actualizaciones(self):
        reloj = {"tiempo_s": 110., "marca": 0., "ejecutando": True, "velocidad": 50}
        r = self.consultar(reloj["tiempo_s"])
        avanzar_reloj(reloj, 2, 1000)
        self.assertEqual(reloj["tiempo_s"], 210)
        r = self.consultar(reloj["tiempo_s"], r)
        e = historial_visible(r, 210)[0]
        self.assertEqual(e["estado"], "ATENDIDA")
        self.assertEqual(e["asignada_s"], 200)
        self.assertFalse(consultar_alertas(resultado(), 210)["activas"])
        self.assertEqual(nuevas_sin_leer(r, 210), 1)

    def test_reinicio_retroceso_y_reproduccion_no_duplican_avisos(self):
        r = self.consultar(150)
        r = self.consultar(210, r)
        r = self.consultar(0, r, revision=1)
        self.assertEqual(historial_visible(r, 0), [])
        self.assertEqual(nuevas_sin_leer(r, 0), 0)
        r = self.consultar(150, r, revision=1)
        e = historial_visible(r, 150)[0]
        self.assertNotIn("asignada_s", e)
        self.assertNotIn("agv", e)
        self.assertEqual(len(r["eventos"]), 1)
        r = self.consultar(210, r, revision=1)
        self.assertEqual(len(r["eventos"]), 1)
        r = self.consultar(50, r)  # Retroceso sin marcador también se reconoce.
        self.assertFalse(historial_visible(r, 50))

    def test_salto_manual_no_produce_rafaga_de_nuevas_notificaciones(self):
        r = self.consultar(0)
        r = self.consultar(300, r, revision=1)
        self.assertEqual(len(historial_visible(r, 300)), 1)
        self.assertEqual(nuevas_sin_leer(r, 300), 0)

    def test_registros_aislados_por_escenario(self):
        a = self.consultar(150)
        b = actualizar_registro(None, "b", consultar_alertas(resultado(), 150))
        self.assertNotEqual(set(a["eventos"]), set(b["eventos"]))
        with self.assertRaises(ValueError):
            actualizar_registro(a, "b", consultar_alertas(resultado(), 150))

    def test_fin_no_muestra_activas_y_conserva_historicas(self):
        r = self.consultar(0)
        r = self.consultar(1000, r)
        self.assertFalse(consultar_alertas(resultado(), 1000)["activas"])
        self.assertEqual(historial_visible(r, 1000)[0]["estado"], "ATENDIDA")

    def test_subir_umbral_no_reescribe_evento_ni_impide_marcarlo_atendido(self):
        r = self.consultar(121)
        r = self.consultar(150, r, umbral=300)
        self.assertFalse(consultar_alertas(resultado(), 150, 300)["activas"])
        r = self.consultar(210, r, umbral=300)
        e = historial_visible(r, 210)[0]
        self.assertEqual(e["umbral_s"], 120)
        self.assertEqual(e["estado"], "ATENDIDA")
        self.assertEqual(len(r["eventos"]), 1)

    def test_bajar_umbral_reevalua_activas_sin_agregar_atendidas_anteriores(self):
        r = self.consultar(150, umbral=300)
        r = self.consultar(150, r, umbral=120)
        self.assertEqual(len(r["eventos"]), 1)
        r = self.consultar(150, r, umbral=60)
        self.assertEqual(len(r["eventos"]), 1)
        self.assertEqual(next(iter(r["eventos"].values()))["umbral_s"], 120)
        otro = self.consultar(250, umbral=300)
        otro = self.consultar(250, otro, umbral=120)
        otro = self.consultar(300, otro, umbral=120)
        self.assertFalse(otro["eventos"])


class TrazabilidadAlertasTests(unittest.TestCase):
    def registrar(self, r, t, registro=None, **kwargs):
        return actualizar_registro(registro, "a", consultar_alertas(r, t), **kwargs)

    def test_cruce_deteccion_espera_observada_y_final_son_independientes(self):
        r = resultado(movimiento(llegada=10, inicio=212.8))
        registro = self.registrar(r, 135)
        e = next(iter(registro["eventos"].values()))
        self.assertEqual(e["supera_desde_s"], 130)
        self.assertEqual(e["detectada_s"], 135)
        self.assertEqual(e["espera_observada_s"], 125)
        self.assertIsNone(e["espera_final_s"])
        registro = self.registrar(r, 160, registro)
        e = next(iter(registro["eventos"].values()))
        self.assertEqual((e["espera_s"], e["espera_observada_s"]), (150, 125))
        registro = self.registrar(r, 220, registro)
        e = next(iter(registro["eventos"].values()))
        self.assertEqual(e["estado"], "ATENDIDA")
        self.assertAlmostEqual(e["espera_final_s"], 202.8)
        self.assertEqual((e["detectada_s"], e["espera_observada_s"]), (135, 125))

    def test_deteccion_tardia_no_se_backdatea_al_cruce(self):
        r = resultado(movimiento(llegada=10, inicio=212.8))
        registro = self.registrar(r, 0)
        registro = self.registrar(r, 300, registro, revision=1)
        e = next(iter(registro["eventos"].values()))
        self.assertEqual((e["supera_desde_s"], e["detectada_s"]), (130, 300))
        self.assertAlmostEqual(e["espera_observada_s"], 202.8)
        self.assertAlmostEqual(e["espera_final_s"], 202.8)
        self.assertEqual((e["origen"], e["revision_deteccion"]), ("salto", 1))

    def test_dos_solicitudes_conservan_tiempos_propios(self):
        r = resultado(movimiento(35, "WAFER", llegada=0, inicio=202.8),
                      movimiento(40, "WAFER", llegada=10, inicio=280))
        registro = self.registrar(r, 140)
        registro = self.registrar(r, 220, registro)
        eventos = {e["solicitud"]: e for e in registro["eventos"].values()}
        self.assertEqual((eventos["35"]["estado"], eventos["35"]["espera_observada_s"]), ("ATENDIDA", 140))
        self.assertAlmostEqual(eventos["35"]["espera_final_s"], 202.8)
        self.assertEqual((eventos["40"]["estado"], eventos["40"]["espera_s"]), ("ACTIVA", 210))
        self.assertEqual(eventos["40"]["espera_observada_s"], 130)
        self.assertIsNone(eventos["40"]["espera_final_s"])

    def test_retroceso_no_expone_espera_final_ni_asignacion_futura(self):
        r = resultado()
        registro = self.registrar(r, 140)
        registro = self.registrar(r, 250, registro)
        registro = self.registrar(r, 150, registro, revision=1)
        e = historial_visible(registro, 150)[0]
        self.assertEqual((e["estado"], e["espera_s"], e["espera_observada_s"]), ("ACTIVA", 150, 140))
        self.assertIsNone(e["espera_final_s"])
        self.assertNotIn("asignada_s", e)
        self.assertNotIn("agv", e)
        registro = self.registrar(r, 250, registro, revision=1)
        self.assertEqual(next(iter(registro["eventos"].values()))["espera_final_s"], 200)

    def test_migracion_legacy_no_confunde_observada_con_final(self):
        viejo = {"escenario_id": "a", "ultimo_t": 220, "eventos": {
            "a:1:ESPERA_SIN_ASIGNACION": {"solicitud": "1", "linea": "WAFER", "estado": "ACTIVA",
                "llegada_s": 0, "umbral_s": 120, "espera_s": 130, "detectada_s": 130,
                "asignada_s": 200}}}
        antes = deepcopy(viejo)
        nuevo = normalizar_registro(viejo)
        e = next(iter(nuevo["eventos"].values()))
        self.assertEqual((e["espera_observada_s"], e["espera_final_s"], e["espera_s"]), (130, 200, 200))
        self.assertEqual((e["estado"], e["supera_desde_s"]), ("ATENDIDA", 120))
        self.assertEqual(viejo, antes)
        self.assertEqual(nuevo, normalizar_registro(nuevo))
        self.assertEqual(len(self.registrar(resultado(), 250, viejo)["eventos"]), 1)

    def test_registro_sin_deteccion_no_inventa_el_instante(self):
        viejo = {"eventos": {"incompleta": {"solicitud": "1", "llegada_s": 0, "umbral_s": 120}}}
        normalizado = normalizar_registro(viejo, 300)
        e = normalizado["eventos"]["incompleta"]
        self.assertIsNone(e["detectada_s"])
        self.assertIsNone(e["espera_observada_s"])
        self.assertEqual(historial_visible(normalizado, 300), [])

    def test_ruido_float_no_genera_alertas_pero_exceso_real_si(self):
        # Llegada fraccionaria real de una exportación anterior: resta >120 por ~1e-13.
        llegada = 401.86046511627904
        for espera in (120-TOLERANCIA_ESPERA_S/2, 120, math.nextafter(120, math.inf),
                       120+TOLERANCIA_ESPERA_S/2, 120+2*TOLERANCIA_ESPERA_S):
            r = resultado(movimiento(llegada=llegada, inicio=llegada+250))
            q = consultar_alertas(r, llegada+espera)
            self.assertEqual(bool(q["activas"]), espera > 120+TOLERANCIA_ESPERA_S)
            r["movimientos"][0]["inicio_s"] = llegada+espera
            q = consultar_alertas(r, 900)
            self.assertEqual(bool(q["resueltas"]), espera > 120+TOLERANCIA_ESPERA_S)

    def test_espera_final_se_actualiza_aunque_se_haya_subido_el_umbral(self):
        r = self.registrar(resultado(), 125)
        r = actualizar_registro(r, "a", consultar_alertas(resultado(), 150, 300))
        self.assertEqual(next(iter(r["eventos"].values()))["espera_s"], 150)
        r = actualizar_registro(r, "a", consultar_alertas(resultado(), 250, 300))
        e = next(iter(r["eventos"].values()))
        self.assertEqual((e["estado"], e["espera_final_s"], e["umbral_s"]), ("ATENDIDA", 200, 120))


class RespuestasDemorasTests(unittest.TestCase):
    def test_pregunta_del_banco_usa_id_y_umbral_configurado(self):
        with patch.object(Nestor, "_detectar_intencion", side_effect=AssertionError("No palabras clave")):
            respuesta = Nestor(resultado(), tiempo_s=90, umbral_alertas_s=60).responder_sugerida("alertas_actuales")
        self.assertEqual(respuesta["tipo"], "DEMORAS_LINEA")
        self.assertIn("Cookies 1", respuesta["respuesta"])
        self.assertIn("no validado por Nestlé", respuesta["respuesta"])
        self.assertEqual(respuesta["metricas_utilizadas"]["solicitudes_retrasadas"], 1)
        self.assertEqual(respuesta["tiempo_s"], 90)
        self.assertNotIn("AGV_ASIGNADO_DESPUES", respuesta["respuesta"])

    def test_no_hay_demoras_y_texto_libre_conserva_alcance_actual(self):
        respuesta = Nestor(resultado(), tiempo_s=120).responder("¿Qué líneas presentan demoras?")
        self.assertIn("No hay solicitudes", respuesta["respuesta"])
        self.assertEqual(respuesta["alcance"], "actual")
        self.assertFalse(respuesta["acciones_revision"])


if __name__ == "__main__":
    unittest.main()
