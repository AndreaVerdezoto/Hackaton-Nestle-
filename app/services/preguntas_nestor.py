"""Catálogo local de consultas respaldadas por el analizador operativo."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PreguntaSugerida:
    id: str
    categoria: str
    texto: str
    intencion: str
    alcance: str


CATEGORIAS = (
    "Estado de la operación",
    "Desempeño de AGV",
    "Batería y recorridos",
    "Alertas y retrasos",
)

PREGUNTAS = (
    PreguntaSugerida("estado_actual", CATEGORIAS[0],
                     "¿Cómo está la operación ahora?", "ESTADO_GENERAL", "actual"),
    PreguntaSugerida("resultado_final", CATEGORIAS[0],
                     "¿Cuál es el resultado final de la operación?", "ESTADO_GENERAL", "final"),
    PreguntaSugerida("utilizacion_actual", CATEGORIAS[1],
                     "¿Cómo se está utilizando la flota?", "UTILIZACION", "actual"),
    PreguntaSugerida("agv_mas_utilizado", CATEGORIAS[1],
                     "¿Qué AGV tiene la mayor utilización ahora?", "AGV_MAS_USADO", "actual"),
    PreguntaSugerida("utilizacion_final", CATEGORIAS[1],
                     "¿Cómo fue la utilización al cierre del turno?", "UTILIZACION", "final"),
    PreguntaSugerida("bateria_actual", CATEGORIAS[2],
                     "¿Cómo está la batería y cuántas recargas han comenzado?", "BATERIA", "actual"),
    PreguntaSugerida("distancias_actuales", CATEGORIAS[2],
                     "¿Cuánto han recorrido los AGV con carga y sin carga?", "DISTANCIAS", "actual"),
    PreguntaSugerida("distancias_finales", CATEGORIAS[2],
                     "¿Cuánto recorrieron los AGV en la corrida completa?", "DISTANCIAS", "final"),
    PreguntaSugerida("alertas_actuales", CATEGORIAS[3],
                     "¿Qué líneas presentan demoras?", "DEMORAS_LINEA", "actual"),
    PreguntaSugerida("esperas_actuales", CATEGORIAS[3],
                     "¿Cuántas solicitudes esperan y cuánto tarda una misión?", "DIAGNOSTICO", "actual"),
    PreguntaSugerida("retrasos_finales", CATEGORIAS[3],
                     "¿Qué esperas y pendientes registró la corrida completa?", "DIAGNOSTICO", "final"),
)

PREGUNTAS_POR_ID = {pregunta.id: pregunta for pregunta in PREGUNTAS}
ALTERNATIVAS = ("estado_actual", "utilizacion_actual", "bateria_actual", "esperas_actuales")


def obtener_pregunta(pregunta_id):
    """Un ID desconocido es un error de programación, nunca una consulta ambigua."""
    if pregunta_id not in PREGUNTAS_POR_ID:
        raise ValueError(f"Pregunta sugerida desconocida: {pregunta_id}")
    return PREGUNTAS_POR_ID[pregunta_id]
