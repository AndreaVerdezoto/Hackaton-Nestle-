from copy import deepcopy
import unittest

from app.services.analizador_operativo import (
    AnalizadorOperativo,
    UmbralesAnalizadorOperativo,
)
from app.services.simulador_flota import ParametrosSimulacion, SimuladorFlota


class AnalizadorOperativoTests(unittest.TestCase):
    def test_metricas_reutilizan_resultado_sin_mutarlo(self):
        resultado = SimuladorFlota().ejecutar(2)
        antes = deepcopy(resultado)

        metricas = AnalizadorOperativo(resultado).obtener_metricas()

        self.assertEqual(resultado, antes)
        self.assertEqual(metricas["misiones_completadas"], resultado["kpis"]["completados_turno"])
        self.assertEqual(metricas["solicitudes_pendientes_backlog"], resultado["kpis"]["solicitudes_pendientes_turno"])
        self.assertEqual(metricas["tiempo_promedio_espera_s"], resultado["kpis"]["espera_media_s"])
        self.assertEqual(metricas["tiempo_promedio_ciclo_s"], resultado["kpis"]["ciclo_medio_s"])
        self.assertEqual(metricas["utilizacion_flota_pct"], resultado["kpis"]["utilizacion_media_pct"])
        self.assertEqual(metricas["distancia_total_m"], resultado["kpis"]["distancia_total_m"])
        self.assertEqual(metricas["distancia_cargada_m"], resultado["kpis"]["distancia_cargada_m"])
        self.assertEqual(metricas["distancia_vacia_m"], resultado["kpis"]["distancia_vacia_m"])
        self.assertAlmostEqual(
            metricas["porcentaje_desplazamiento_vacio"],
            100 * resultado["kpis"]["distancia_vacia_m"] / resultado["kpis"]["distancia_total_m"],
        )
        self.assertEqual(metricas["utilizacion_por_agv_pct"], {
            item["agv"]: item["utilizacion_pct"] for item in resultado["por_agv"]
        })

    def test_metricas_de_bateria_solo_cuando_existen_en_resultado(self):
        sin_bateria = AnalizadorOperativo(SimuladorFlota().ejecutar(2))
        self.assertIsNone(sin_bateria.obtener_metricas()["bateria_promedio_pct"])
        self.assertIn("bateria_promedio_pct", sin_bateria.metricas_no_disponibles())

        resultado = SimuladorFlota(
            ParametrosSimulacion(pallets_terminados=3, duracion_turno_s=600, velocidad_maxima_ms=1)
        ).ejecutar(2, simular_bateria=True, cargadores=("ControlPoint31", "ControlPoint32", "ControlPoint29"))
        metricas = AnalizadorOperativo(resultado).obtener_metricas()

        ultimos = {}
        for movimiento in resultado["movimientos"]:
            agv = movimiento["agv"]
            if agv not in ultimos or movimiento["fin_s"] >= ultimos[agv][0]:
                ultimos[agv] = (movimiento["fin_s"], movimiento["bateria_fin"])
        niveles = [nivel for _, nivel in ultimos.values()]
        self.assertAlmostEqual(metricas["bateria_promedio_pct"], sum(niveles) / len(niveles))
        self.assertEqual(metricas["bateria_minima_pct"], min(niveles))
        self.assertEqual(metricas["cantidad_recargas"], sum(len(v) for v in resultado["recargas"].values()))

    def test_detecta_problemas_con_umbrales_configurables(self):
        resultado = SimuladorFlota(ParametrosSimulacion(tiempo_carga_s=1000, tiempo_descarga_s=1000)).ejecutar(2)
        analizador = AnalizadorOperativo(
            resultado,
            UmbralesAnalizadorOperativo(
                backlog_elevado=0,
                espera_elevada_s=0,
                utilizacion_alta_pct=0,
                desplazamiento_vacio_alto_pct=0,
            ),
        )

        codigos = {p["codigo"] for p in analizador.detectar_problemas()}

        self.assertIn("BACKLOG_ELEVADO", codigos)
        if resultado["kpis"]["espera_media_s"] > 0:
            self.assertIn("ESPERA_ELEVADA", codigos)
        self.assertIn("UTILIZACION_ALTA", codigos)
        self.assertIn("DESPLAZAMIENTO_VACIO_ALTO", codigos)

    def test_sin_problemas_con_umbrales_altos(self):
        resultado = SimuladorFlota().ejecutar(2)
        analizador = AnalizadorOperativo(
            resultado,
            UmbralesAnalizadorOperativo(
                backlog_elevado=999,
                espera_elevada_s=999999,
                utilizacion_alta_pct=101,
                bateria_baja_pct=-1,
                desplazamiento_vacio_alto_pct=101,
            ),
        )

        problemas = analizador.detectar_problemas()

        self.assertEqual(len(problemas), 1)
        self.assertEqual(problemas[0]["codigo"], "SIN_PROBLEMAS")

    def test_fallos_registrados_si_el_resultado_los_incluye(self):
        resultado = SimuladorFlota().ejecutar(2)
        resultado["errores"] = ["sin conectividad en prueba"]

        metricas = AnalizadorOperativo(resultado).obtener_metricas()

        self.assertEqual(metricas["fallos_errores"], ["sin conectividad en prueba"])


if __name__ == "__main__":
    unittest.main()
