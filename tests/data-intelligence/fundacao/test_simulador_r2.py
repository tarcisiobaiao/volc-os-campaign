"""R2-G13 (mutante E3): o observador não lê campanha antes de ela existir."""
from __future__ import annotations

from datetime import datetime

import pytest

from volc_dil.fundacao.simulador import simular


@pytest.mark.parametrize("seed", [1, 20261016])
def test_intradia_nao_le_campanha_antes_do_lancamento(seed):
    s = simular("campanha_nova_aprendendo", seed, n_campanhas=6, n_dias=4)
    lancamento = {c.id: s.mundo.instante_local(0, c.inicio_h) for c in s.mundo.campanhas if c.nova}
    assert lancamento, "o cenário precisa ter campanha nova"
    intradia = [r for r in s.leituras.registros
                if r.fonte == "google_ads" and r.tipo_leitura == "intradia" and r.entidade in lancamento]
    assert intradia, "o cenário precisa produzir leitura intradiária de campanha nova"
    cedo = [r for r in intradia if datetime.fromisoformat(r.observed_at) <= lancamento[r.entidade]]
    assert cedo == []
