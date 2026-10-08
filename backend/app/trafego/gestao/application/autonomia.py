"""O PONTO ÚNICO em que a autonomia de aplicar sem humano entraria. Hoje: vazio.

## Por que isto é uma constante vazia, e não um `if` com flag de ambiente

A v10_02 não tem vocabulário para "a máquina aplica sozinha": a CHECK
`trafego_regra_nivel_conhecido` só aceita T0 e T1, `trafego_aplicacao.aprovacao_id`
é NOT NULL com FK, e o gatilho `trafego_aplicacao_exige_aprovacao` recusa
qualquer aprovação cuja decisão não seja `aprovada`. Uma flag de ambiente aqui
seria uma porta pintada na parede: o banco recusaria do mesmo jeito, e a recusa
apareceria como 409 do gatilho depois de a chamada ao Google já ter sido
considerada — o pior lugar para descobrir.

A decisão é do dono (ADR-11). Quando ela vier, entram JUNTAS:

  1. a migration `supabase/migrations/v17_02_autonomia_gestao.PROPOSTA.sql`
     (T2 no vocabulário + `trafego_aprovacao.decisor_tipo` + o gatilho que só
     aceita decisor `regra` quando a regra é T2 e a operação está na lista de
     operações autônomas da própria regra);
  2. o nível em `NIVEIS_QUE_APLICAM_SEM_HUMANO` abaixo;
  3. o ramo de `casos_de_uso.Gestao.aplicar` que hoje levanta
     `ExigeAprovacaoHumana`, e que passaria a gravar a aprovação com
     `decisor_tipo='regra'` e `decidida_por='regra:<chave>@<versao>'`.

Um sem os outros não faz nada — e é de propósito: nenhum dos três, sozinho,
consegue fazer a máquina aplicar sem humano.
"""
from __future__ import annotations

from typing import Any, FrozenSet, Mapping

#: ⚠️ VAZIO. T2 não existe na v10_02. Ver o docstring do módulo antes de mexer.
NIVEIS_QUE_APLICAM_SEM_HUMANO: FrozenSet[str] = frozenset()


def aplica_sem_humano(regra: Mapping[str, Any], operacao: str) -> bool:
    """Esta regra pode aplicar ESTA operação sem aprovação humana?

    Hoje sempre `False`. Mesmo com o nível na constante, a regra precisa listar
    a operação em `acao.operacoes_autonomas` — autonomia é por operação, não
    por regra inteira: pausar e dobrar orçamento são riscos diferentes. É a
    mesma condição que o gatilho proposto na v17_02 confere no banco.
    """
    nivel = str(regra.get("nivel_autonomia") or "")
    if nivel not in NIVEIS_QUE_APLICAM_SEM_HUMANO:
        return False
    acao = regra.get("acao") or {}
    return operacao in (acao.get("operacoes_autonomas") or ())
