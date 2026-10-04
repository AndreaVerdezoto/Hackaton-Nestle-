from app.services.escenarios import crear_escenario


def test_crear_escenario_guarda_copia_independiente():
    resultado = {"numero_agv": 3, "kpis": {"completados_turno": 215}}
    escenario = crear_escenario(resultado)

    assert set(escenario) == {"id", "guardado", "resultado"}
    assert escenario["resultado"] == resultado
    assert escenario["resultado"] is not resultado
    assert escenario["id"]
    assert escenario["guardado"]
