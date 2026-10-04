"""Creación compartida de solicitudes de retiro de producto terminado."""

from app.models.pallet import Pallet
from app.models.solicitud import PrioridadSolicitud, SolicitudTraslado
from app.services.gestor_flota import GestorFlota

DESTINO_ALMACEN = "ControlPoint7"


def crear_solicitud_retiro(
    *,
    id_tarea,
    pallet,
    linea,
    prioridad=PrioridadSolicitud.NORMAL,
    id_ciclo=None,
):
    """Crea la solicitud estándar línea -> almacén para un pallet listo.

    Este es el punto de entrada común para el retiro de producto terminado.
    Hoy lo usa la producción simulada; en el futuro un sensor podrá llamar a
    esta misma función cuando determine que un pallet alcanzó su límite.
    """
    if not isinstance(pallet, Pallet):
        raise TypeError("pallet debe ser un objeto Pallet.")
    if linea not in GestorFlota.NODOS_PRODUCTO_TERMINADO:
        raise ValueError(f"Línea de producción no válida: {linea}")

    origen = GestorFlota.NODOS_PRODUCTO_TERMINADO[linea]
    pallet.mover_a(origen)

    return SolicitudTraslado(
        id_tarea_wms=str(id_tarea),
        id_pallet=pallet.id_pallet,
        producto=pallet.producto,
        peso=pallet.peso,
        origen=origen,
        destino=DESTINO_ALMACEN,
        prioridad=prioridad,
        id_ciclo=id_ciclo,
        pallet=pallet,
    )
