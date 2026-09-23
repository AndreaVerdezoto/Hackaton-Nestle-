"""Regresión del flujo manual, sin conexión a FlexSim."""
import unittest
from unittest.mock import Mock
from app.models.agv import AGV
from app.models.solicitud import SolicitudTraslado, PrioridadSolicitud, EstadoSolicitud
from app.services.gestor_flota import GestorFlota


class PruebaGestor(unittest.TestCase):
    def test_ciclo_manual(self):
        gestor = GestorFlota()
        gestor.flexsim = Mock()
        gestor.flexsim.ejecutar_mision.return_value = "OK|MISION_INICIADA"
        agv = AGV("AGV_01", 80, "TRANSIT_4")
        gestor.registrar_agv(agv)
        solicitud = SolicitudTraslado("TAREA_001", "PALLET_001", "Chocolate", 500,
                                     "ALMACEN", "CHOCOLATE", PrioridadSolicitud.ALTA)
        gestor.registrar_solicitud(solicitud)
        mision = gestor.asignar_solicitud(solicitud)
        self.assertIsNotNone(mision)
        gestor.iniciar_mision(mision.id_mision)
        gestor.flexsim.ejecutar_mision.assert_called_once_with(
            "agv_01", "ControlPoint7", "ControlPoint17", "PALLET_001",
            "pallet_transit4", "entrada_material_chocolate",
        )
        gestor.completar_mision(mision.id_mision)
        self.assertEqual(solicitud.estado, EstadoSolicitud.COMPLETADA)
        self.assertEqual(agv.ubicacion, "ControlPoint17")


if __name__ == "__main__":
    unittest.main()
