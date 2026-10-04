"""Creación de escenarios simulados reutilizables por la interfaz."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4


def crear_escenario(resultado):
    """Guarda una copia independiente de una corrida del simulador."""
    return deepcopy({
        "id": uuid4().hex,
        "guardado": datetime.now(timezone.utc).isoformat(),
        "resultado": resultado,
    })
