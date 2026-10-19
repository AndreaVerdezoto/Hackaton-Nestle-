"""Exportaciones auditables, sin generar simulaciones ni detecciones nuevas."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from app.services.alertas_linea import consultar_alertas, actualizar_registro
from app.services.exportacion_nestor import crear_exportacion, exportar_corrida_nestor
from tests.test_alertas_linea import movimiento, resultado


class ExportacionNestorTests(unittest.TestCase):
    def test_simulacion_completa_y_observaciones_estan_separadas_sin_mutacion(self):
        r = resultado(movimiento(), movimiento(2, "WAFER", llegada=300, inicio=550))
        r.update(version_modelo="modelo_actual", numero_agv=2, parametros={"tiempo_carga_s": 30})
        registro = actualizar_registro(None, "a", consultar_alertas(r, 125))
        originales = deepcopy((r, registro))
        reloj = {"tiempo_s": 150, "revision": 2, "velocidad": 50, "ejecutando": False}
        with patch("app.services.simulador_flota.SimuladorFlota.ejecutar", side_effect=AssertionError("No simular")), \
             patch("app.services.alertas_linea.consultar_alertas", side_effect=AssertionError("No detectar")):
            datos = json.loads(exportar_corrida_nestor(r, "a", registro, reloj=reloj))
        self.assertEqual((r, registro), originales)
        self.assertEqual(datos["escenario"]["id"], "a")
        self.assertEqual(datos["escenario"]["version_modelo"], "modelo_actual")
        self.assertEqual(datos["escenario"]["parametros"], r["parametros"])
        self.assertEqual(datos["simulacion"]["resultado"], r)
        self.assertEqual(datos["reproduccion"]["reloj_2d"], reloj)
        e = datos["reproduccion"]["alertas_visibles_en_reloj"][0]
        self.assertEqual((e["detectada_s"], e["espera_observada_s"], e["espera_s"]), (125, 125, 150))
        self.assertIsNone(e["espera_final_s"])
        self.assertNotIn("asignada_s", e)
        self.assertEqual(len(datos["reproduccion"]["registro_alertas"]["eventos"]), 1)

    def test_corrida_no_observada_no_recibe_detecciones_artificiales(self):
        r = resultado()
        for registro in (None, {"escenario_id": "a", "eventos": {}}):
            datos = crear_exportacion(r, "a", registro, reloj={"tiempo_s": 1000})
            self.assertEqual(datos["reproduccion"]["alertas_visibles_en_reloj"], [])
            archivo = datos["reproduccion"]["registro_alertas"]
            self.assertTrue(archivo is None or not archivo["eventos"])
            self.assertEqual(datos["simulacion"]["resultado"]["movimientos"][0]["espera_s"], 200)

    def test_registro_atendido_conserva_umbral_original_y_observacion(self):
        r = resultado()
        registro = actualizar_registro(None, "a", consultar_alertas(r, 125))
        registro = actualizar_registro(registro, "a", consultar_alertas(r, 250, 300))
        d = crear_exportacion(r, "a", registro, reloj={"tiempo_s": 250}, umbral_s=300)
        e = d["reproduccion"]["alertas_visibles_en_reloj"][0]
        self.assertEqual((e["estado"], e["espera_final_s"], e["espera_observada_s"]), ("ATENDIDA", 200, 125))
        self.assertEqual((e["umbral_s"], d["reproduccion"]["umbral_actual_s"]), (120, 300))

    def test_reinicio_conserva_archivo_observado_y_vista_actual_vacia(self):
        r = resultado()
        registro = actualizar_registro(None, "a", consultar_alertas(r, 250))
        registro = actualizar_registro(registro, "a", consultar_alertas(r, 0), revision=1)
        d = crear_exportacion(r, "a", registro, reloj={"tiempo_s": 0, "revision": 1})
        self.assertFalse(d["reproduccion"]["alertas_visibles_en_reloj"])
        e = next(iter(d["reproduccion"]["registro_alertas"]["eventos"].values()))
        self.assertEqual(e["detectada_s"], 250)
        self.assertEqual(e["estado"], "NO_VISIBLE")
        self.assertIsNone(e["espera_final_s"])

    def test_no_mezcla_registros_de_escenarios(self):
        registro = actualizar_registro(None, "a", consultar_alertas(resultado(), 125))
        with self.assertRaises(ValueError):
            crear_exportacion(resultado(), "b", registro)

    def test_archivo_legacy_sin_meta_deteccion_o_tiempos_no_inventa_datos(self):
        viejo = {"eventos": {"vieja": {"solicitud": "35", "linea": "WAFER", "espera_s": 202.8}}}
        datos = json.loads(exportar_corrida_nestor({"movimientos": []}, registro=viejo))
        self.assertIsNone(datos["escenario"]["id"])
        self.assertIsNone(datos["escenario"]["version_modelo"])
        self.assertIsNone(datos["escenario"]["parametros"])
        e = datos["reproduccion"]["registro_alertas"]["eventos"]["vieja"]
        self.assertIsNone(e["detectada_s"])
        self.assertIsNone(e["supera_desde_s"])
        self.assertIsNone(e["espera_final_s"])
        self.assertEqual(e["espera_observada_s"], 202.8)
        self.assertTrue(datos["limitaciones"])

    def test_exportacion_antigua_real_conserva_todos_los_movimientos(self):
        archivo = Path(__file__).resolve().parents[1] / "resultados_215_pt.json"
        for resultado_guardado in json.loads(archivo.read_text()):
            d = json.loads(exportar_corrida_nestor({"id": "antiguo", "resultado": resultado_guardado}))
            self.assertEqual(d["escenario"]["id"], "antiguo")
            self.assertEqual(d["simulacion"]["resultado"], resultado_guardado)
            self.assertEqual(len(d["simulacion"]["resultado"]["movimientos"]), 215)
            self.assertIsNone(d["reproduccion"]["registro_alertas"])

    def test_precision_original_y_json_estandar_ante_no_finitos(self):
        r = resultado(movimiento(llegada=401.86046511627904, inicio=604.660465116279))
        r["kpis"]["dato_antiguo_invalido"] = float("nan")
        d = json.loads(exportar_corrida_nestor(r, "a"))
        self.assertEqual(d["simulacion"]["resultado"]["movimientos"], r["movimientos"])
        self.assertIsNone(d["simulacion"]["resultado"]["kpis"]["dato_antiguo_invalido"])
        self.assertTrue(any("no finitos" in x for x in d["limitaciones"]))


if __name__ == "__main__":
    unittest.main()
