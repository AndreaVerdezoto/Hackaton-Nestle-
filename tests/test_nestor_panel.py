from pathlib import Path
import unittest

try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Streamlit no está instalado en este intérprete")
class NestorPanelTests(unittest.TestCase):
    def app(self, codigo):
        return AppTest.from_string(codigo, default_timeout=20).run()

    def boton(self, at, etiqueta):
        return next(b for b in at.button if b.label == etiqueta)

    def abrir_nestor(self, at):
        return self.boton(at, "Néstor").click().run()

    def test_chat_cerrado_inicialmente(self):
        at = self.app("""
from app.ui.nestor_panel import mostrar_nestor_flotante
mostrar_nestor_flotante({"resultado": "simulado"}, escenario_id="escenario_1")
""")

        self.assertFalse(at.exception)
        self.assertTrue(any(b.label == "Néstor" for b in at.button))
        self.assertFalse(any(x.label == "Pregunta para Néstor" for x in at.text_input))

    def test_abrir_y_cerrar_chat(self):
        at = self.app("""
from app.ui.nestor_panel import mostrar_nestor_flotante
mostrar_nestor_flotante({"resultado": "simulado"}, escenario_id="escenario_1")
""")
        at = self.abrir_nestor(at)

        self.assertTrue(any(x.label == "Pregunta para Néstor" for x in at.text_input))

        at = self.boton(at, "Cerrar").click().run()

        self.assertFalse(at.exception)
        self.assertTrue(any(b.label == "Néstor" for b in at.button))
        self.assertFalse(any(x.label == "Pregunta para Néstor" for x in at.text_input))

    def test_interfaz_sin_resultado(self):
        at = self.app("""
from app.ui.nestor_panel import mostrar_nestor_flotante
mostrar_nestor_flotante(None)
""")
        at = self.abrir_nestor(at)

        self.assertFalse(at.exception)
        self.assertTrue(any("Ejecuta primero una simulación para que pueda analizar la operación." in x.value for x in at.info))
        self.assertFalse(any(x.label == "Pregunta para Néstor" for x in at.text_input))

    def test_interfaz_con_resultado_muestra_entrada(self):
        at = self.app("""
from app.ui.nestor_panel import mostrar_nestor_flotante
mostrar_nestor_flotante({"resultado": "simulado"}, escenario_id="escenario_1")
""")
        at = self.abrir_nestor(at)

        self.assertFalse(at.exception)
        self.assertTrue(any(x.label == "Pregunta para Néstor" for x in at.text_input))
        self.assertFalse(any("Ejecuta primero una simulación" in x.value for x in at.info))

    def test_nestor_recibe_preguntas_y_muestra_respuesta_breve(self):
        at = self.app("""
import streamlit as st
from app.ui import nestor_panel as panel

class FakeNestor:
    def __init__(self, resultado):
        self.resultado = resultado
    def responder(self, pregunta):
        st.session_state["ultima_pregunta_nestor"] = pregunta
        return {
            "tipo": "ESTADO_GENERAL",
            "respuesta": "Respuesta breve de Néstor.",
            "metricas_utilizadas": {"utilizacion_flota_pct": 70},
            "problemas_relacionados": [],
            "limitaciones": [],
            "acciones_revision": [],
        }

panel.Nestor = FakeNestor
panel.mostrar_nestor_flotante({"resultado": "simulado"}, escenario_id="escenario_1")
""")
        at = self.abrir_nestor(at)
        next(x for x in at.text_input if x.label == "Pregunta para Néstor").set_value("¿Cómo está operando la flota?")
        at = self.boton(at, "Preguntar").click().run()

        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["ultima_pregunta_nestor"], "¿Cómo está operando la flota?")
        self.assertTrue(any("Respuesta breve de Néstor." in x.value for x in at.markdown))

    def test_pregunta_no_reconocida_no_rompe_interfaz(self):
        at = self.app("""
from app.ui import nestor_panel as panel

class FakeNestor:
    def __init__(self, resultado):
        pass
    def responder(self, pregunta):
        return {
            "tipo": "NO_RECONOCIDA",
            "respuesta": "Néstor analiza el estado operativo y las desviaciones detectadas.",
            "metricas_utilizadas": {},
            "problemas_relacionados": [],
            "limitaciones": ["Intención no reconocida."],
            "acciones_revision": [],
        }

panel.Nestor = FakeNestor
panel.mostrar_nestor_flotante({"resultado": "simulado"}, escenario_id="escenario_1")
""")
        at = self.abrir_nestor(at)
        next(x for x in at.text_input if x.label == "Pregunta para Néstor").set_value("¿Qué se podría mejorar?")
        at = self.boton(at, "Preguntar").click().run()

        self.assertFalse(at.exception)
        self.assertTrue(any("Néstor analiza el estado operativo" in x.value for x in at.markdown))
        self.assertTrue(any("Información no disponible" in x.value for x in at.markdown))

    def test_acciones_revision_aparecen_cuando_corresponde_sin_duplicarse(self):
        at = self.app("""
from app.ui import nestor_panel as panel

class FakeNestor:
    def __init__(self, resultado):
        pass
    def responder(self, pregunta):
        return {
            "tipo": "DIAGNOSTICO",
            "respuesta": "Los datos muestran backlog elevado.",
            "metricas_utilizadas": {"solicitudes_pendientes_backlog": 5},
            "problemas_relacionados": [{"codigo": "BACKLOG_ELEVADO"}],
            "limitaciones": [],
            "acciones_revision": [
                "Revisar las franjas con mayor cola.",
                "Revisar la disponibilidad de AGV.",
                "Esta accion no debe mostrarse.",
            ],
        }

panel.Nestor = FakeNestor
panel.mostrar_nestor_flotante({"resultado": "simulado"}, escenario_id="escenario_1")
""")
        at = self.abrir_nestor(at)
        next(x for x in at.text_input if x.label == "Pregunta para Néstor").set_value("¿Por qué hay solicitudes pendientes?")
        at = self.boton(at, "Preguntar").click().run()

        markdown = "\n".join(x.value for x in at.markdown)
        self.assertFalse(at.exception)
        self.assertIn("Acciones de revisión", markdown)
        self.assertIn("Revisar las franjas con mayor cola.", markdown)
        self.assertIn("Revisar la disponibilidad de AGV.", markdown)
        self.assertNotIn("Esta accion no debe mostrarse.", markdown)
        self.assertNotIn("Acción de revisión:", markdown)

    def test_no_muestra_codigos_internos_en_respuesta_visible(self):
        at = self.app("""
from app.ui import nestor_panel as panel

class FakeNestor:
    def __init__(self, resultado):
        pass
    def responder(self, pregunta):
        return {
            "tipo": "ESTADO_GENERAL",
            "respuesta": "Se detectaron desviaciones operativas.",
            "metricas_utilizadas": {"solicitudes_pendientes_backlog": 5},
            "problemas_relacionados": [{"codigo": "BACKLOG_ELEVADO"}],
            "limitaciones": [],
            "acciones_revision": ["Revisar las franjas con mayor cola."],
        }

panel.Nestor = FakeNestor
panel.mostrar_nestor_flotante({"resultado": "simulado"}, escenario_id="escenario_1")
""")
        at = self.abrir_nestor(at)
        next(x for x in at.text_input if x.label == "Pregunta para Néstor").set_value("¿Hay alguna alerta?")
        at = self.boton(at, "Preguntar").click().run()

        visible = "\n".join(x.value for x in at.markdown)
        self.assertFalse(at.exception)
        self.assertNotIn("BACKLOG_ELEVADO", visible)

    def test_imagen_faltante_no_derrumba_widget(self):
        at = self.app(f"""
from pathlib import Path
from app.ui import nestor_panel as panel
panel.NESTOR_AVATAR = Path({str(Path('/tmp/nestor_avatar_inexistente.png'))!r})
panel.mostrar_nestor_flotante(None)
""")

        self.assertFalse(at.exception)
        self.assertTrue(any("No se encontró la imagen" in x.value for x in at.warning))


if __name__ == "__main__":
    unittest.main()
