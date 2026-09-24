import json
import threading
import unittest
from urllib.request import urlopen

from app.services.conector_wms import enviar_evento_wms, preparar_payload_wms, verificar_wms
from wms_mock import crear_servidor, limpiar_movimientos, movimientos_recibidos


class ConectorWMSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = crear_servidor("127.0.0.1", 0)
        cls.hilo = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.hilo.start()
        puerto = cls.servidor.server_address[1]
        cls.base = f"http://127.0.0.1:{puerto}"

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.hilo.join(timeout=2)

    def setUp(self):
        limpiar_movimientos()

    def evento(self):
        return {
            "escenario_id": "ESC-1",
            "tipo_evento": "MOVIMIENTO_PALLET_COMPLETADO",
            "pallet": "PALLET_034",
            "ciclo": 34,
            "origen": "Cookies 2",
            "origen_nodo": "ControlPoint25",
            "destino": "Almacén",
            "destino_nodo": "ControlPoint7",
            "agv": "AGV_02",
            "estado": "ENTREGADO",
            "movimiento": "M-068",
            "tiempo_simulado_s": 1234.5,
            "hora_turno": "00:20:35",
        }

    def test_payload_tiene_id_y_contrato_generico(self):
        p = preparar_payload_wms(self.evento())
        self.assertEqual(p["evento_id"], "ESC-1:PALLET_034:M-068")
        self.assertEqual(p["destino"], "Almacén")
        self.assertEqual(p["fuente"], "GESTOR_AGV_NESTLE")
        self.assertEqual(p["version_contrato"], 1)

    def test_envio_real_http_y_consulta(self):
        r = enviar_evento_wms(self.evento(), f"{self.base}/api/movimientos")
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], 200)
        self.assertEqual(len(movimientos_recibidos()), 1)
        with urlopen(f"{self.base}/api/movimientos", timeout=1) as response:
            data = json.loads(response.read().decode("utf-8"))
        self.assertEqual(data["movimientos"][0]["pallet"], "PALLET_034")

    def test_receptor_es_idempotente(self):
        endpoint = f"{self.base}/api/movimientos"
        self.assertTrue(enviar_evento_wms(self.evento(), endpoint)["ok"])
        segunda = enviar_evento_wms(self.evento(), endpoint)
        self.assertTrue(segunda["ok"])
        self.assertTrue(segunda["respuesta"]["duplicado"])
        self.assertEqual(len(movimientos_recibidos()), 1)

    def test_salud(self):
        r = verificar_wms(f"{self.base}/api/salud")
        self.assertTrue(r["ok"])
        self.assertEqual(r["respuesta"]["estado"], "activo")


if __name__ == "__main__":
    unittest.main()
