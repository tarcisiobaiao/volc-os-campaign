from app.entities.prompts import build_entity_discovery_mission


def test_mission_without_niche_keeps_diversification():
    m = build_entity_discovery_mission("Brasil")
    assert "DIVERSIFIQUE" in m or "diversif" in m.lower()


def test_mission_with_niche_focuses_and_injects_guidance():
    niches = [{"slug": "financas", "label": "Finanças", "guidance": "Crédito, empréstimo, investimentos."}]
    m = build_entity_discovery_mission("Brasil", niches=niches)
    assert "Finanças" in m
    assert "Crédito, empréstimo, investimentos." in m
    assert "diversif" not in m.lower()  # a diversificação obrigatória some quando há nicho


def test_mission_seasonality_evergreen_bias():
    m = build_entity_discovery_mission("Brasil", seasonality="evergreen")
    assert "Perene" in m


def test_mission_forces_language():
    m = build_entity_discovery_mission("República Dominicana", forced_language="es-DO")
    assert "es-DO" in m
    assert "detecte" not in m.lower()  # não pede mais para o modelo detectar
