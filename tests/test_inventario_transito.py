import unittest

from app.services.inventario_transito import eventos_inventario, registros_inventario


class InventarioTransitoTests(unittest.TestCase):
    def setUp(self):
        self.resultado = {
            "movimientos": [
                {
                    "numero": 8,
                    "tipo": "producto_terminado",
                    "id_pallet": "PALLET_004",
                    "id_ciclo": 4,
                    "origen": "ControlPoint24",
                    "destino": "ControlPoint7",
                    "agv": "AGV_02",
                    "llegada_s": 100.0,
                    "inicio_s": 120.0,
                    "fin_s": 200.0,
                },
            ]
        }

    def test_no_aparece_antes_de_generarse_solicitud(self):
        self.assertEqual(registros_inventario(self.resultado, 99.0), [])

    def test_transicion_pendiente_transito_entregado(self):
        pendiente = registros_inventario(self.resultado, 110.0)[0]
        self.assertEqual(pendiente["estado"], "PENDIENTE")
        self.assertEqual(pendiente["destino"], "Almacén")
        self.assertEqual(pendiente["agv"], "—")

        transito = registros_inventario(self.resultado, 150.0)[0]
        self.assertEqual(transito["estado"], "EN TRÁNSITO")
        self.assertEqual(transito["agv"], "AGV_02")

        entregado = registros_inventario(self.resultado, 200.0)[0]
        self.assertEqual(entregado["estado"], "ENTREGADO")
        self.assertEqual(entregado["origen"], "Cookies 1")
        self.assertEqual(entregado["ultima_actualizacion"], "00:03:20")

    def test_evento_se_genera_solo_al_finalizar(self):
        self.assertEqual(eventos_inventario(self.resultado, 199.9), [])
        eventos = eventos_inventario(self.resultado, 200.0)
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["tipo_evento"], "MOVIMIENTO_PALLET_COMPLETADO")
        self.assertEqual(eventos[0]["pallet"], "PALLET_004")
        self.assertEqual(eventos[0]["destino"], "Almacén")
        self.assertEqual(eventos[0]["destino_nodo"], "ControlPoint7")


if __name__ == "__main__":
    unittest.main()
