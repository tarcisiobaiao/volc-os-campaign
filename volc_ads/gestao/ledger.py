"""A tradução de ação/antes/resultado para as linhas do ledger v10_02.

Nada aqui fala com o banco: são dicionários prontos para INSERT/UPDATE, para o
backend gravar pelo caminho que ele já usa. Ficam aqui porque quem sabe o que
é o "antes", o "proposto" e o reverso de uma ação é a própria ação — o backend
só transporta.

  ação + antes          → trafego_proposta  (operacao, alvo_*, valor_atual,
                                             valor_proposto, delta_*, idempotency_key)
  antes do envio        → trafego_aplicacao.valor_anterior
  ResultadoAcao         → trafego_aplicacao.desfecho / erro_* / resposta_bruta
  reverso(antes,criados)→ trafego_atuacao_reversao.valor_restaurado
  cooldown              → nada a fazer: o gatilho `trafego_aplicacao_abre_cooldown`
                          abre a carência por (regra.chave, proposta.alvo_chave)
                          quando a aplicação fecha em 'sucesso'.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from .acoes import Acao, AlterarAlvoDeLance, AlterarOrcamento
from .lote import ResultadoAcao


def alvo_chave(acao: Acao, customer_id: str) -> str:
    """A chave do cooldown. Mesma para toda ação sobre o mesmo alvo — de
    propósito: a carência de "orçamento da campanha X" não deve deixar outra
    regra pausar e despausar X na mesma hora."""
    return f"google_ads:{customer_id}:{acao.alvo_nivel}:{acao.alvo_id}"


def _canonico(v: Any) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def chave_idempotencia(acao: Acao, customer_id: str, antes: dict) -> str:
    """Derivada do CONTEÚDO (alvo + antes + proposto), como na v10_01.

    O "antes" entra na chave: a mesma mudança proposta sobre outro estado é
    outra proposta. Cabe na CHECK `^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$`.
    """
    corpo = _canonico([acao.tipo, alvo_chave(acao, customer_id), antes, acao.valor_proposto()])
    return f"gestao:{acao.tipo}:{hashlib.sha256(corpo.encode()).hexdigest()[:40]}"


def _delta(acao: Acao, antes: dict) -> tuple[float | None, int | None]:
    """(delta_pct, delta_absoluto_micros) quando a ação é numérica.

    Só orçamento e alvo de lance em micros têm delta absoluto; tROAS é razão e
    só tem percentual. Ação sem número (pausa, negativa) não tem delta — e a
    regra que declarar limite de alteração recusará a proposta, que é o certo.
    """
    if isinstance(acao, AlterarOrcamento):
        antes_v, novo = antes.get("verba_diaria_micros"), acao.amount_micros
        absoluto = True
    elif isinstance(acao, AlterarAlvoDeLance):
        antes_v = {"teto_cpc": antes.get("teto_cpc_micros"), "tcpa": antes.get("tcpa_micros"),
                   "troas": antes.get("troas")}[acao.alvo]
        novo, absoluto = acao.valor, acao.alvo != "troas"
    else:
        return None, None
    if antes_v is None:
        return None, None
    pct = round((novo - antes_v) / antes_v * 100, 3) if antes_v else None
    return pct, (int(novo - antes_v) if absoluto else None)


def proposta(acao: Acao, customer_id: str, antes: dict, lido_em: datetime) -> dict:
    """As colunas de `trafego_proposta` que vêm da ação. O backend completa
    `diagnostico_id`, `regra_id`, `volc_campaign_id`, `criada_por`, `expira_em`.

    ⚠️ `volc_campaign_id` é obrigatório quando `alvo_nivel='campanha'` (gatilho
    `trafego_proposta_respeita_regra`) e aponta para `trafego_campanha` — logo,
    campanha que não nasceu pelo VOLC precisa ser importada para lá antes de
    receber proposta de nível campanha.
    """
    pct, absoluto = _delta(acao, antes)
    return {
        "alvo_nivel": acao.alvo_nivel,
        "alvo_id_externo": acao.alvo_id,
        "alvo_chave": alvo_chave(acao, customer_id),
        "operacao": acao.tipo,
        "valor_atual": antes,
        "valor_atual_lido_em": lido_em.isoformat(),
        "valor_proposto": acao.valor_proposto(),
        "delta_pct": pct,
        "delta_absoluto_micros": absoluto,
        "moeda": antes.get("moeda") if absoluto is not None else None,
        "idempotency_key": chave_idempotencia(acao, customer_id, antes),
    }


_DESFECHO_LEDGER = {"ok": "sucesso", "falhou": "erro", "parcial": "erro"}


def desfecho_da_aplicacao(r: ResultadoAcao) -> dict:
    """O UPDATE que fecha a linha `em_voo` de `trafego_aplicacao`.

    `parcial` vira 'erro' (a CHECK não tem outro valor) com os resource names
    criados em `resposta_bruta.criados`: metade aplicada é aplicada, e o
    reverso precisa deles para limpar.
    """
    if r.desfecho not in _DESFECHO_LEDGER:
        raise ValueError(f"desfecho {r.desfecho!r} não é de escrita real")
    linha: dict[str, Any] = {
        "desfecho": _DESFECHO_LEDGER[r.desfecho],
        "resposta_bruta": {"desfecho_gestao": r.desfecho, "criados": list(r.recursos),
                           "faixa_operacoes": list(r.faixa) if r.faixa else None},
    }
    if r.erros:
        primeiro = r.erros[0]
        linha["erro_codigo"] = f"{primeiro.campo_codigo}.{primeiro.valor_codigo}"
        linha["erro_mensagem"] = " | ".join(e.resumo() for e in r.erros)[:4000]
    return linha


def reversao(acao: Acao, valor_anterior: dict, criados: tuple[str, ...] = ()) -> dict:
    """`valor_restaurado` de `trafego_atuacao_reversao` + as ações que o executam.

    Sai de `trafego_aplicacao.valor_anterior` (capturado no envio), nunca do
    "antes" da proposta.
    """
    passos = acao.reverso(valor_anterior, tuple(criados))
    return {
        "valor_restaurado": {
            "reversivel": bool(passos),
            "motivo": "" if passos else (acao.motivo_sem_reverso or "nada a desfazer"),
            "passos": [{"operacao": p.tipo, "valor": p.valor_proposto()} for p in passos],
        },
        "acoes": passos,
    }
