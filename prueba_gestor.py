from app.models.agv import AGV
from app.models.solicitud import SolicitudTraslado, PrioridadSolicitud
from app.services.gestor_flota import GestorFlota


gestor = GestorFlota()

agv_1 = AGV(
    id_agv="AGV_01",
    bateria=80,
    ubicacion="TRANSIT_4"
)

gestor.registrar_agv(agv_1)

solicitud_1 = SolicitudTraslado(
    id_tarea_wms="TAREA_001",
    id_pallet="PALLET_001",
    producto="Chocolate",
    peso=500,
    origen="ALMACEN",
    destino="LINEA_1",
    prioridad=PrioridadSolicitud.ALTA
)

gestor.registrar_solicitud(solicitud_1)

mision = gestor.asignar_solicitud(
    solicitud_1
)

print("AGV:")
print(agv_1)

print("\nMISIÓN:")
print(mision)

print("\n--- INICIANDO MISIÓN ---")

gestor.iniciar_mision(
    mision.id_mision
)

print(agv_1)
print(mision)


print("\n--- COMPLETANDO MISIÓN ---")

resultado = gestor.completar_mision(
    mision.id_mision
)

print(agv_1)
print(mision)
print(solicitud_1)
