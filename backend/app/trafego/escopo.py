"""O escopo da casa — a única árvore de contas em que este sistema opera.

## O defeito que este módulo fecha

Medido em 18/08/2026, resolvendo os 12 ids de `contas.acessiveis()` com
`contas.descobrir()` um a um: a credencial alcança **39 contas anunciáveis
distintas**, sob **9 MCCs**. Três dessas contas são da VOLC. O resto é de
cliente — IESDE, Colégio Positivo, os MCCs pessoais.

Um seletor que oferece as 39 transforma "vincular projeto à conta errada" num
clique, e a consequência não aparece no clique: aparece depois, no `subir`,
dentro da conta de outra empresa. A regra da casa é não alterar nada em conta
de terceiro, e regra que depende de ninguém errar o item de uma lista de 39
não é regra — é esperança.

## Duas camadas, e a segunda foi medida

1. **Nossa, de graça:** `login_customer_id` tem de ser o MCC da casa. Não há
   rede nesta checagem — quem manda outro MCC é recusado antes de a requisição
   sair daqui, e a mensagem diz qual era o escopo.

2. **Do Google, medida em 18/08/2026** (`contas.detalhe()`, GAQL `SELECT`,
   sempre com `login_customer_id=6016739364`):

   | conta pedida | veredito da API |
   |---|---|
   | `8017851692` Crédito Up — filha do MCC da casa | passou |
   | `5838529870` IESDE — outro MCC | `USER_PERMISSION_DENIED` |
   | `8552871761` Colégio Positivo — acesso DIRETO da credencial | `USER_PERMISSION_DENIED` |

   A terceira linha é a que sustenta o desenho: nem uma conta que a credencial
   alcança sozinha entra, porque a chamada viaja sob o manager da casa. Forçar
   o MCC não é um filtro cosmético — é o que faz o próprio Google recusar.

Por isso o portão **não guarda lista de contas permitidas e não tem cache**:
seria uma cópia que envelhece do que o Google já responde de graça.

## O que este módulo NÃO faz

Não protege escrita — isso é `gads/modo.py`, e as duas travas são
independentes de propósito. Este diz ONDE se pode operar; a outra diz SE se
pode escrever. Nenhum dos dois cobre o outro.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

log = logging.getLogger("volc.trafego.escopo")

# O MCC da VOLC. Este número é a fronteira do sistema inteiro.
#
# ⚠️ NÃO leia isto do ambiente. `backend/.env` traz
# `GOOGLE_ADS_LOGIN_CUSTOMER_ID=8696453882`, que é o MCC "Projetos Fla&Fe" —
# 17 contas anunciáveis de terceiro, medido em 18/08/2026. Um portão que lê o
# ambiente apontaria para essa árvore, e um `.env` editado por engano moveria a
# fronteira sem deixar rastro em revisão de código.
MCC_DA_CASA = "6016739364"

# Rótulo para a mensagem de recusa. A verdade sobre o nome vem da API, em
# `mapa()`; aqui ele só existe para o erro não ser dez dígitos secos.
ROTULO_DA_CASA = "VOLC Negócios Digitais"


class ForaDoEscopo(Exception):
    """Conta pedida fora da árvore do MCC da casa. Nada foi enviado à API."""


def so_digitos(valor: Any) -> str:
    """`801-785-1692` é como o Google Ads mostra o id NA TELA DELE.

    Quem copia de lá cola com hífen, e a API responde erro de id inválido — que
    diz o que está errado, mas não que a causa foi o separador.
    """
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def exigir_escopo(customer_id: Any, login_customer_id: Any) -> tuple[str, str]:
    """Recusa qualquer conta fora da árvore da casa. Não faz rede.

    Devolve o par já normalizado — o chamador deve usar o que volta daqui, não o
    que entrou, senão o hífen sobrevive até a API.
    """
    cid, mid = so_digitos(customer_id), so_digitos(login_customer_id)

    if not cid or not mid:
        raise ForaDoEscopo(
            "Faltou o id da conta ou o do MCC. Este sistema opera apenas sob o "
            f"MCC {MCC_DA_CASA} ({ROTULO_DA_CASA})."
        )

    if mid != MCC_DA_CASA:
        raise ForaDoEscopo(
            f"O MCC {mid} está fora do escopo deste sistema, que opera apenas "
            f"sob {MCC_DA_CASA} ({ROTULO_DA_CASA}). A credencial alcança outros "
            f"MCCs — de cliente — e nenhuma operação daqui pode tocá-los."
        )

    if cid == MCC_DA_CASA:
        raise ForaDoEscopo(
            f"{cid} é o próprio MCC, não uma conta de anúncios. Manager "
            f"administra contas; campanha entra nas filhas dele."
        )

    return cid, mid


def mapa() -> Dict[str, Any]:
    """A árvore da casa e o tamanho do que fica de fora. Leitura pura.

    Duas chamadas: `acessiveis()` para saber quanto a credencial alcança e
    `descobrir()` para a árvore que se pode usar. O que fica de fora é contado,
    não expandido — expandir custaria uma chamada por MCC e traria nome de conta
    de cliente para uma tela onde ela não pode ser escolhida.
    """
    from app.trafego import contas as ct

    arvore = ct.descobrir(MCC_DA_CASA)
    acessiveis = [so_digitos(i) for i in ct.acessiveis()]

    # O próprio MCC entra como `nivel: 0` na árvore — é dele que sai o nome.
    proprio = next((c for c in arvore["contas"] if c["customer_id"] == MCC_DA_CASA), None)
    da_casa = {c["customer_id"] for c in arvore["contas"]}

    # ⚠️ Nem todo id acessível está fora: PMUNDO+ e Portal Mundo Mais são
    # alcançados direto pela credencial E pendem do MCC da casa. Subtrair sem
    # interseção contaria os dois como terceiros — medido em 18/08/2026, seriam
    # 11 em vez de 9.
    fora = [i for i in acessiveis if i not in da_casa]

    contas: List[Dict[str, Any]] = arvore["anunciaveis"]
    return {
        "mcc": MCC_DA_CASA,
        "nome": (proprio or {}).get("nome") or ROTULO_DA_CASA,
        "contas": contas,
        "ids_acessiveis": len(acessiveis),
        "ids_fora_do_escopo": len(fora),
        "por_que": (
            f"Este sistema opera apenas sob o MCC {MCC_DA_CASA}. Os outros "
            f"{len(fora)} ids que a credencial alcança, e qualquer conta sob "
            f"eles, são recusados no servidor — não só escondidos na tela."
        ),
    }


def conta_da_casa(customer_id: Any) -> Dict[str, Any]:
    """A conta, se ela for da casa. Levanta `ForaDoEscopo` se não for.

    Custa a leitura da árvore (~1,6 s medido em 18/08/2026), então só vale onde
    a resposta precisa dizer O QUE está errado — o vínculo do projeto. Nos
    caminhos que apenas repassam um id à API, `exigir_escopo()` basta: o Google
    recusa o resto, medido.
    """
    cid, _ = exigir_escopo(customer_id, MCC_DA_CASA)
    for c in mapa()["contas"]:
        if c["customer_id"] == cid:
            return c
    raise ForaDoEscopo(
        f"A conta {cid} não está entre as contas anunciáveis do MCC "
        f"{MCC_DA_CASA}. Escolha uma da lista — ela vem da API, não de cadastro."
    )
