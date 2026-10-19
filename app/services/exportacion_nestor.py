"""Exportación de una corrida y sus observaciones; nunca simula ni detecta avisos."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math

from app.services.alertas_linea import (
    UMBRAL_DEMO_S, TOLERANCIA_ESPERA_S, historial_visible, normalizar_registro,
)


def crear_exportacion(resultado, escenario_id=None, registro=None, *, reloj=None,
                      umbral_s=UMBRAL_DEMO_S):
    """Acepta resultados antiguos o el envoltorio {id, resultado} de escenarios.

    La simulación completa puede contener hechos futuros respecto al cursor 2D.
    El registro contiene solo avisos efectivamente observados, incluidos los
    conservados de una reproducción anterior al reinicio. La vista temporal se
    entrega por separado. Los datos ausentes se mantienen como null.
    """
    if isinstance(resultado, dict) and isinstance(resultado.get("resultado"), dict):
        escenario_id = escenario_id if escenario_id is not None else resultado.get("id")
        resultado = resultado["resultado"]
    resultado = deepcopy(resultado) if isinstance(resultado, dict) else {}
    reloj = deepcopy(reloj) if isinstance(reloj, dict) else {}
    tiempo = reloj.get("tiempo_s")
    if not isinstance(tiempo, (int, float)) or isinstance(tiempo, bool) or not math.isfinite(tiempo):
        tiempo = None
    if registro and registro.get("escenario_id") not in (None, escenario_id):
        raise ValueError("Las alertas no pertenecen al escenario exportado.")
    registro = normalizar_registro(registro, tiempo)
    limitaciones = []
    if escenario_id is None:
        limitaciones.append("El archivo antiguo no incluye identificador de escenario.")
    if not resultado.get("version_modelo"):
        limitaciones.append("La versión del modelo no está disponible.")
    if not isinstance(resultado.get("movimientos"), list):
        limitaciones.append("No se dispone de la lista completa de movimientos.")
    if tiempo is None:
        limitaciones.append("No hay un instante válido del reloj 2D; no se genera una vista temporal.")
    if registro is None:
        limitaciones.append("No se proporcionó un registro de alertas de reproducción; no se reconstruyen detecciones.")
    elif any(e.get("detectada_s") is None for e in registro["eventos"].values()):
        limitaciones.append("Hay alertas antiguas sin instante de detección: se conservan, pero se excluyen de la vista temporal.")
    return {
        "version_exportacion": 1,
        "exportado_en_utc": datetime.now(timezone.utc).isoformat(),
        "escenario": {
            "id": escenario_id,
            "version_modelo": resultado.get("version_modelo"),
            "numero_agv": resultado.get("numero_agv"),
            "parametros": deepcopy(resultado.get("parametros")),
            "timestamp_simulacion": resultado.get("timestamp"),
            "grafo_sha256": resultado.get("grafo_sha256"),
        },
        "simulacion": {
            "origen": "Resultado completo precalculado por el simulador, independiente del reloj 2D.",
            "resultado": resultado,
        },
        "reproduccion": {
            "origen": "Avisos detectados por la interfaz; no son eventos generados por el simulador.",
            "reloj_2d": {**reloj, "tiempo_s": tiempo},
            "umbral_actual_s": umbral_s,
            "tolerancia_espera_s": TOLERANCIA_ESPERA_S,
            "registro_alertas": registro,
            "alertas_visibles_en_reloj": historial_visible(registro, tiempo),
        },
        "convenciones": {
            "unidad_temporal": "segundos simulados desde el inicio de la corrida",
            "supera_desde_s": "Frontera matemática llegada_s + umbral_s del aviso; se exige espera mayor, con tolerancia absoluta.",
            "detectada_s": "Instante del reloj 2D de la primera detección efectiva; null si se desconoce. No es hora de pared.",
            "espera_observada_s": "Espera sin asignación observada al detectar el aviso; no cambia después.",
            "espera_final_s": "asignada_s - llegada_s cuando la misión ya comenzó en el instante consultado; null mientras está pendiente o falta información.",
            "espera_s": "Alias compatible: espera parcial al reloj consultado o final si ya comenzó la misión.",
            "tolerancia_espera_s": "Política de comparación actual y, en cada aviso nuevo, la usada al detectarlo. En avisos antiguos puede ser null por falta de trazabilidad.",
            "registro_alertas": "Conserva observaciones previas incluso tras reiniciar o retroceder. Puede contener asignaciones ya observadas posteriores al cursor actual; usar alertas_visibles_en_reloj para la vista a ese instante.",
        },
        "limitaciones": limitaciones,
    }


def exportar_corrida_nestor(*args, **kwargs):
    """JSON estándar sin redondear tiempos; números no finitos antiguos => null."""
    datos = crear_exportacion(*args, **kwargs)
    no_finitos = []

    def limpiar(valor):
        if isinstance(valor, float) and not math.isfinite(valor):
            no_finitos.append(True)
            return None
        if isinstance(valor, dict):
            return {k: limpiar(v) for k, v in valor.items()}
        if isinstance(valor, (list, tuple)):
            return [limpiar(v) for v in valor]
        return valor

    datos = limpiar(datos)
    if no_finitos:
        datos["limitaciones"].append("Valores numéricos no finitos del archivo de origen se exportaron como null.")
    return json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False)
