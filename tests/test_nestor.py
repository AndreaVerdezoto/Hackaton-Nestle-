from copy import deepcopy
import unittest

from app.services.nestor import Nestor


class AnalizadorFalso:
    def __init__(self, metricas, problemas=None, no_disponibles=None):
        self.metricas = metricas
        self.problemas = problemas or [{
            "codigo": "SIN_PROBLEMAS",
            "severidad": "INFO",
            "descripcion": "Sin problemas",
            "metricas": {},
        }]
        self.no_disponibles = no_disponibles or {}

    def obtener_metricas(self):
        return deepcopy(self.metricas)

    def detectar_problemas(self):
        return deepcopy(self.problemas)

    def metricas_no_disponibles(self):
        return deepcopy(self.no_disponibles)


def problema(codigo, severidad="MEDIA", metricas=None):
    return {
        "codigo": codigo,
        "severidad": severidad,
        "descripcion": codigo,
        "metricas": metricas or {},
    }


def metricas_base(**extra):
    datos = {
        "misiones_completadas": 214,
        "solicitudes_pendientes_backlog": 1,
        "backlog_maximo": 3,
        "tiempo_promedio_espera_s": 12.0,
        "tiempo_promedio_ciclo_s": 180.0,
        "utilizacion_flota_pct": 72.0,
        "utilizacion_por_agv_pct": {"AGV_01": 80.0, "AGV_02": 64.0},
        "distancia_total_m": 1000.0,
        "distancia_cargada_m": 620.0,
        "distancia_vacia_m": 380.0,
        "porcentaje_desplazamiento_vacio": 38.0,
        "bateria_promedio_pct": None,
        "bateria_minima_pct": None,
        "cantidad_recargas": None,
        "fallos_errores": None,
    }
    datos.update(extra)
    return datos


class NestorTests(unittest.TestCase):
    def test_estado_general(self):
        don = Nestor(analizador=AnalizadorFalso(metricas_base()))

        respuesta = don.responder("Como esta operando la flota?")

        self.assertEqual(respuesta["tipo"], "ESTADO_GENERAL")
        self.assertIn("misiones_completadas", respuesta["metricas_utilizadas"])
        self.assertEqual(respuesta["problemas_relacionados"], [])
        self.assertIn("acciones_revision", respuesta)
        self.assertNotIn("recomendaciones", respuesta)
        self.assertIn("no muestran problemas", respuesta["respuesta"])

    def test_diagnostico_con_varios_problemas_no_inventa_causalidad(self):
        problemas = [
            problema("BACKLOG_ELEVADO", "ALTA"),
            problema("ESPERA_ELEVADA"),
            problema("UTILIZACION_ALTA"),
        ]
        don = Nestor(analizador=AnalizadorFalso(
            metricas_base(
                solicitudes_pendientes_backlog=5,
                tiempo_promedio_espera_s=80.0,
                utilizacion_flota_pct=89.0,
            ),
            problemas,
        ))

        respuesta = don.responder("Por que hay solicitudes pendientes?")

        self.assertEqual(respuesta["tipo"], "DIAGNOSTICO")
        self.assertEqual({p["codigo"] for p in respuesta["problemas_relacionados"]},
                         {"BACKLOG_ELEVADO", "ESPERA_ELEVADA", "UTILIZACION_ALTA"})
        self.assertLessEqual(len(respuesta["acciones_revision"]), 2)
        self.assertIn("no demuestran una causa unica", respuesta["respuesta"])
        self.assert_no_afirma_causalidad(respuesta)

    def test_operacion_sin_problemas(self):
        don = Nestor(analizador=AnalizadorFalso(metricas_base(
            solicitudes_pendientes_backlog=0,
            tiempo_promedio_espera_s=0.0,
            utilizacion_flota_pct=55.0,
        )))

        respuesta = don.responder("Hay algun problema?")

        self.assertEqual(respuesta["tipo"], "ESTADO_GENERAL")
        self.assertEqual(respuesta["problemas_relacionados"], [])
        self.assertEqual(respuesta["acciones_revision"], [])
        self.assertNotIn("Acción de revisión:", respuesta["respuesta"])

    def test_bateria_disponible(self):
        don = Nestor(analizador=AnalizadorFalso(metricas_base(
            bateria_promedio_pct=76.0,
            bateria_minima_pct=32.0,
            cantidad_recargas=3,
        )))

        respuesta = don.responder("Como esta la bateria?")

        self.assertEqual(respuesta["tipo"], "BATERIA")
        self.assertEqual(respuesta["metricas_utilizadas"]["cantidad_recargas"], 3)
        self.assertEqual(respuesta["limitaciones"], [])
        self.assertIn("76.0 %", respuesta["respuesta"])
        self.assert_no_afirma_causalidad(respuesta)

    def test_bateria_no_disponible(self):
        don = Nestor(analizador=AnalizadorFalso(
            metricas_base(),
            no_disponibles={
                "bateria_promedio_pct": "No se simulo bateria.",
                "bateria_minima_pct": "No se simulo bateria.",
                "cantidad_recargas": "No se simulo bateria.",
            },
        ))

        respuesta = don.responder("Cuantas recargas hubo?")

        self.assertEqual(respuesta["tipo"], "BATERIA")
        self.assertEqual(respuesta["metricas_utilizadas"]["cantidad_recargas"], None)
        self.assertEqual(len(respuesta["limitaciones"]), 3)
        self.assertIn("No hay datos suficientes", respuesta["respuesta"])

    def test_pregunta_no_reconocida(self):
        don = Nestor(analizador=AnalizadorFalso(metricas_base()))

        respuesta = don.responder("Cual es el clima de hoy?")

        self.assertEqual(respuesta["tipo"], "NO_RECONOCIDA")
        self.assertEqual(respuesta["metricas_utilizadas"], {})
        self.assertTrue(respuesta["limitaciones"])
        self.assertIn("Néstor analiza el estado operativo", respuesta["respuesta"])
        self.assertNotIn("mejoras", respuesta["respuesta"].lower())

    def test_ausencia_de_metrica_necesaria(self):
        don = Nestor(analizador=AnalizadorFalso(
            metricas_base(utilizacion_por_agv_pct=None),
            no_disponibles={"utilizacion_por_agv_pct": "El resultado no contiene detalle por AGV."},
        ))

        respuesta = don.responder("Cual AGV trabajo mas?")

        self.assertEqual(respuesta["tipo"], "UTILIZACION")
        self.assertIsNone(respuesta["metricas_utilizadas"]["utilizacion_por_agv_pct"])
        self.assertEqual(len(respuesta["limitaciones"]), 1)
        self.assertIn("detalle por AGV", respuesta["limitaciones"][0])

    def test_utilizacion_conserva_respuesta(self):
        don = Nestor(analizador=AnalizadorFalso(metricas_base()))

        respuesta = don.responder("Como esta la utilizacion de los AGVs?")

        self.assertEqual(respuesta["tipo"], "UTILIZACION")
        self.assertEqual(respuesta["metricas_utilizadas"]["utilizacion_flota_pct"], 72.0)
        self.assertIn("AGV_01", respuesta["respuesta"])
        self.assert_no_afirma_causalidad(respuesta)

    def test_distancias_conserva_respuesta(self):
        don = Nestor(analizador=AnalizadorFalso(metricas_base()))

        respuesta = don.responder("Tenemos muchos recorridos vacios?")

        self.assertEqual(respuesta["tipo"], "DISTANCIAS")
        self.assertEqual(respuesta["metricas_utilizadas"]["distancia_vacia_m"], 380.0)
        self.assertIn("sin carga", respuesta["respuesta"])
        self.assert_no_afirma_causalidad(respuesta)

    def test_pregunta_mejora_ya_no_produce_intencion_mejora(self):
        don = Nestor(analizador=AnalizadorFalso(metricas_base()))

        respuesta = don.responder("Que se podria mejorar?")

        self.assertEqual(respuesta["tipo"], "NO_RECONOCIDA")
        self.assertIn("estado de la operación", respuesta["respuesta"])
        self.assertNotIn("MEJORA", respuesta["tipo"])

    def test_acciones_revision_solo_con_problemas_detectados(self):
        sin_problemas = Nestor(analizador=AnalizadorFalso(metricas_base()))
        con_problemas = Nestor(analizador=AnalizadorFalso(
            metricas_base(solicitudes_pendientes_backlog=5),
            [problema("BACKLOG_ELEVADO", "ALTA")],
        ))

        respuesta_sin = sin_problemas.responder("Como esta la operacion?")
        respuesta_con = con_problemas.responder("Como esta la operacion?")

        self.assertEqual(respuesta_sin["acciones_revision"], [])
        self.assertNotIn("Acción de revisión:", respuesta_sin["respuesta"])
        self.assertTrue(respuesta_con["acciones_revision"])
        self.assertLessEqual(len(respuesta_con["acciones_revision"]), 2)
        self.assertNotIn("Acción de revisión:", respuesta_con["respuesta"])

    def test_ninguna_respuesta_afirma_causalidad(self):
        problemas = [
            problema("BACKLOG_ELEVADO"),
            problema("ESPERA_ELEVADA"),
            problema("UTILIZACION_ALTA"),
            problema("BATERIA_BAJA"),
            problema("DESPLAZAMIENTO_VACIO_ALTO"),
        ]
        don = Nestor(analizador=AnalizadorFalso(
            metricas_base(
                solicitudes_pendientes_backlog=5,
                tiempo_promedio_espera_s=80.0,
                utilizacion_flota_pct=89.0,
                bateria_promedio_pct=40.0,
                bateria_minima_pct=18.0,
                cantidad_recargas=2,
                porcentaje_desplazamiento_vacio=60.0,
            ),
            problemas,
        ))
        preguntas = (
            "Como esta operando la flota?",
            "Por que hay solicitudes pendientes?",
            "Como esta la bateria?",
            "Como esta la utilizacion?",
            "Tenemos muchos recorridos vacios?",
            "Que se podria mejorar?",
        )

        for pregunta in preguntas:
            with self.subTest(pregunta=pregunta):
                self.assert_no_afirma_causalidad(don.responder(pregunta))

    def test_respuesta_visible_no_expone_codigos_internos_ni_acciones_duplicadas(self):
        problemas = [
            problema("BACKLOG_ELEVADO"),
            problema("UTILIZACION_ALTA"),
            problema("DESPLAZAMIENTO_VACIO_ALTO"),
        ]
        don = Nestor(analizador=AnalizadorFalso(metricas_base(), problemas))

        respuesta = don.responder("Como esta operando la flota?")

        self.assertTrue(respuesta["acciones_revision"])
        self.assertLessEqual(len(respuesta["acciones_revision"]), 2)
        self.assertNotIn("BACKLOG_ELEVADO", respuesta["respuesta"])
        self.assertNotIn("UTILIZACION_ALTA", respuesta["respuesta"])
        self.assertNotIn("DESPLAZAMIENTO_VACIO_ALTO", respuesta["respuesta"])
        self.assertNotIn("reglas configuradas", respuesta["respuesta"])
        self.assertNotIn("Acción de revisión:", respuesta["respuesta"])

    def assert_no_afirma_causalidad(self, respuesta):
        texto = respuesta["respuesta"].lower()
        prohibidas = ("causo", "causó", "causa las", "causa los", "provoco", "provocó")
        for palabra in prohibidas:
            self.assertNotIn(palabra, texto)


if __name__ == "__main__":
    unittest.main()
