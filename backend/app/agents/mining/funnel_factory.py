"""
Funnel Factory — port of the n8n-peneirador-kw.json node "🏭 FUNNEL FACTORY"
(V7 — OUTPUT UNIFICADO), com a correção do vazamento entre o conjunto
SELECIONADO e o conjunto EXPORTADO.

## O defeito que este arquivo carregava

O port era fiel, inclusive no defeito. `selected` escolhia de 3 a 10 termos por
sub-intenção; `all_keywords_for_campaign` era alimentada de `deduped`; e
`lista_google_ads` / `keywords_array` exportavam `final_campaign`. A tela
mostrava a escolha e a campanha recebia a mineração inteira. Medido em
2026-09-03 contra `origin/volc-os-v2@34dc7b4`, funil BPC/LOAS:

    selecionadas : 5      exportadas : 8

E a ordenação por volume colocava `meu inss login` (480.000) e
`inss telefone 135` (300.000) no topo da própria seleção — navegacional e
suporte empurrando elegibilidade para fora.

## A correção, em uma frase

Elegibilidade primeiro, quantidade depois. `paid_eligibility.decidir_keyword`
decide cada termo pela intenção, pelo risco e pelo ESTADO do dado; só então o
corte por volume se aplica, e só sobre o que já é elegível. Invertida, a ordem
promove exatamente os termos que a elegibilidade recusaria.

`lista_google_ads` passou a sair de `derivar_lista_google_ads(conjunto)` — uma
função só, usada pelo produtor e pelo teste, que é o que impede a divergência
silenciosa de voltar.

## Ausência deixou de ser zero

`kw.get("volume") or 0` e `kw.get("cpc") or 0` sumiram. Um termo sem CPC medido
não é um termo barato, e a tela não escreve mais "Vol: 0, CPC: 0.00" para um
dado que ninguém mediu — escreve `s/ dado`. `stats.avg_cpc` passou a sair só
dos CPCs MEDIDOS, com o estado junto: o funil IPVA publicava `"0.00"` a partir
de dois termos que nunca tiveram CPC nenhum.

A deduplicação entre sub-intenções também saiu. Ela fundia `bpc loas`
(ELEGIBILIDADE) com `BPC LOAS ` (NAVEGACIONAL) numa linha só, rotulada
NAVEGACIONAL, e a intenção de elegibilidade desaparecia sem aparecer em
`keywords_removidas`. Dentro de uma sub-intenção a dedup continua — lá os dois
termos são de fato o mesmo.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.agents.mining.paid_eligibility import (
    CampaignKeywordSet,
    INCLUDE,
    MEDIDO,
    Sinal,
    aplicar_politica_de_selecao,
    decidir_keyword,
    derivar_lista_google_ads,
    media_de_cpc,
    montar_conjunto,
    normalizar_termo,
)

MONTHS_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

# Campos numéricos que viajam do minerador para a decisão. Copiados SÓ quando
# a chave existe — copiar com default é como a ausência virava zero.
CAMPOS_NUMERICOS = ("volume", "cpc", "competition_index", "high_bid", "low_bid")

SEM_DADO = "s/ dado"


def _fmt_int_ptbr(n: int) -> str:
    """toLocaleString('pt-BR') for integers: thousands separated by '.'."""
    return f"{int(n):,}".replace(",", ".")


def _vol_legivel(sinal: Sinal) -> str:
    return _fmt_int_ptbr(sinal.valor) if sinal.tem_numero else SEM_DADO


def _cpc_legivel(sinal: Sinal) -> str:
    return f"{float(sinal.valor):.2f}" if sinal.tem_numero else SEM_DADO


def _volume_bruto(bruto: Dict[str, Any]) -> Optional[float]:
    """O volume comparável, pela MESMA régua que `Sinal` usa.

    Antes esta função devolvia `float(0)` para um `0` cru, enquanto
    `Sinal.de_bruto` classificava o mesmo `0` como `unknown` — "sem número".
    Duas réguas no mesmo payload é como a coerção volta pela porta dos fundos:
    o desempate de dedup e a contagem de volume perdido liam um número que a
    decisão dizia não existir.
    """
    sinal = Sinal.de_bruto(bruto, "volume", fonte="funnel_prospector")
    return sinal.valor if sinal.tem_numero else None


def _fundir(velho: Dict[str, Any], novo: Dict[str, Any]) -> Dict[str, Any]:
    """Funde duas grafias do MESMO termo sem descartar medição.

    A troca em bloco (`result[idx] = kw`) escolhia o vencedor pelo volume e
    jogava fora tudo o que o perdedor tinha medido. Entrada concreta, numa
    sub-intenção só:

        {"keyword": "ipva 2026 consulta", "volume": 30000}              (sem CPC)
        {"keyword": "IPVA 2026 consulta", "volume": 28000, "cpc": 0.40}

    O primeiro vencia por volume, o CPC medido do segundo sumia, e a decisão
    caía de INCLUDE para EXPERIMENT por um dado que a mineração TINHA.

    Agora cada campo é decidido por conta própria: vence o que tem medição, e
    entre dois medidos vence o maior volume — mas só no campo volume.
    """
    fundido = dict(velho)
    v_novo, v_velho = _volume_bruto(novo), _volume_bruto(velho)
    if v_novo is not None and (v_velho is None or v_novo > v_velho):
        fundido["keyword"] = novo.get("keyword", fundido.get("keyword"))
        fundido["volume"] = novo.get("volume")
        if "volume_estado" in novo:
            fundido["volume_estado"] = novo["volume_estado"]
    for campo in CAMPOS_NUMERICOS:
        if campo == "volume":
            continue
        atual = Sinal.de_bruto(fundido, campo, fonte="funnel_prospector")
        candidato = Sinal.de_bruto(novo, campo, fonte="funnel_prospector")
        if candidato.tem_numero and not atual.tem_numero:
            fundido[campo] = novo[campo]
            if f"{campo}_estado" in novo:
                fundido[f"{campo}_estado"] = novo[f"{campo}_estado"]
    if not fundido.get("original") and novo.get("original"):
        fundido["original"] = novo["original"]
    return fundido


def funnel_factory_com_conjuntos(
    ai_output: Dict[str, Any],
    *,
    today: Optional[datetime] = None,
    teto_do_dono: Optional[float] = None,
    marcas_proprias: Sequence[str] = (),
    marcas_de_terceiro: Sequence[str] = (),
    congruencia: str = "nao_avaliada",
) -> Tuple[List[Dict[str, Any]], List[CampaignKeywordSet]]:
    """A fila de produção (JSON-safe) e os conjuntos pagos vivos, na mesma ordem.

    Existem duas saídas porque existem dois consumidores com necessidades
    incompatíveis: o router serializa a fila para o Supabase e para a tela, e
    não pode receber objeto; o domínio e os testes precisam do objeto para
    decidir e para congelar. As duas saem da MESMA construção — o dicionário é
    `conjunto.como_dicionario()` do próprio conjunto devolvido aqui, nunca uma
    segunda montagem que pudesse divergir.
    """
    date = today or datetime.now(timezone.utc)
    current_year = date.year
    current_month = date.month
    previous_year = current_year - 1

    # O ano só é reescrito quando aparece como TOKEN INTEIRO. O `replace`
    # cego do port original transformava `declaracao irpf 2025/2026` em
    # `declaracao irpf 2026/2026` — uma keyword malformada que ia direto para
    # a campanha. Exercício/ano-calendário lado a lado é forma ordinária em
    # keyword de imposto e benefício no Brasil.
    padrao_ano_anterior = re.compile(rf"(?<!\d){previous_year}(?!\d)")
    padrao_ano_atual = re.compile(rf"(?<!\d){current_year}(?!\d)")

    def process_keyword_date(keyword: str) -> Tuple[Optional[str], bool, Optional[str]]:
        processed = keyword or ""
        # Só reescreve se o ano anterior aparece SOZINHO e o ano atual ainda
        # não está no termo. `declaracao irpf 2025/2026` já carrega os dois:
        # reescrever produziria `2026/2026`, que não é o termo de ninguém.
        if padrao_ano_anterior.search(processed) and not padrao_ano_atual.search(processed):
            processed = padrao_ano_anterior.sub(str(current_year), processed)
        if str(current_year) in processed:
            for month_name, month_num in MONTHS_PT.items():
                if month_name in processed.lower() and month_num < current_month:
                    return None, True, f"Mês {month_name} já passou"
        return processed, False, None

    def deduplicate_keywords(keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Dedup DENTRO de uma sub-intenção, sem inventar volume.

        O desempate é por volume MEDIDO: um termo sem medição nunca vence um
        medido, e dois sem medição mantêm o primeiro. O código antigo comparava
        `(kw.get("volume") or 0)`, o que fazia o ausente empatar em 0 com um
        zero real e perder para qualquer coisa — inclusive por motivo errado.
        """
        seen: Dict[str, int] = {}
        result: List[Dict[str, Any]] = []
        for kw in keywords:
            chave = normalizar_termo(kw.get("keyword"))
            if chave not in seen:
                seen[chave] = len(result)
                result.append(dict(kw))
                continue
            idx = seen[chave]
            result[idx] = _fundir(result[idx], kw)
        return result

    funnels = ai_output.get("funis_sugeridos") or []

    batch_info = {
        "total_funnels": len(funnels),
        "processed_at": date.isoformat(),
        "ano_referencia": current_year,
        "priorizacao": ai_output.get("priorizacao") or {},
        "observacoes": ai_output.get("observacoes") or [],
        "alertas_anti_canibalizacao": ai_output.get("alertas_anti_canibalizacao") or [],
    }

    production_queue: List[Dict[str, Any]] = []
    conjuntos: List[CampaignKeywordSet] = []

    for funnel in funnels:
        sub_intencoes = funnel.get("sub_intencoes") or []
        removed_keywords: List[Dict[str, Any]] = []
        processed_intents: List[Dict[str, Any]] = []
        decisoes_do_funil = []
        selecionadas_do_funil = []

        for intent in sub_intencoes:
            tipo = intent.get("tipo")
            processed_kws: List[Dict[str, Any]] = []
            for kw in intent.get("keywords") or []:
                novo, removido, motivo = process_keyword_date(str(kw.get("keyword") or ""))
                if removido:
                    removed_keywords.append(
                        {
                            "original": kw.get("keyword"),
                            "reason": motivo,
                            # O volume perdido também é um Sinal: sem medição,
                            # não há volume perdido — há volume desconhecido.
                            "volume_lost": _volume_bruto(kw),
                        }
                    )
                    continue
                bruto: Dict[str, Any] = {"keyword": novo}
                for campo in CAMPOS_NUMERICOS:
                    if campo in kw:
                        bruto[campo] = kw[campo]
                    # ⚠️ O ESTADO ATRAVESSA A FRONTEIRA JUNTO COM O NÚMERO.
                    #
                    # Copiar só os campos numéricos destruía, aqui, a
                    # proveniência que `gold_extractor` grava na origem — o
                    # mesmo defeito que esta sprint fechou um salto antes,
                    # reaparecendo um salto depois. Reproduzido numa revisão
                    # adversarial: `volume_estado="failed"` sumia e o número
                    # voltava a valer como medido.
                    if f"{campo}_estado" in kw:
                        bruto[f"{campo}_estado"] = kw[f"{campo}_estado"]
                for extra in ("cpc_motivo_de_ausencia", "bloco_de_metricas_presente"):
                    if extra in kw:
                        bruto[extra] = kw[extra]
                if kw.get("keyword") != novo:
                    # A proveniência da reescrita de ano viajava e era lida por
                    # ninguém. Um termo que MUDOU antes de entrar na campanha
                    # precisa dizer de onde veio.
                    bruto["original"] = kw.get("keyword")
                processed_kws.append(bruto)

            deduped = deduplicate_keywords(processed_kws)

            # ELEGIBILIDADE PRIMEIRO. O corte por volume só vê o que já passou.
            decisoes = [
                decidir_keyword(
                    b,
                    subintencao=tipo,
                    teto_do_dono=teto_do_dono,
                    marcas_proprias=marcas_proprias,
                    marcas_de_terceiro=marcas_de_terceiro,
                    # O veredito de congruência vem de FORA — quem avalia
                    # destino é `landing_policy`. Recebê-lo como entrada é o
                    # que evita mutar a decisão depois de tomada só para
                    # limpar um bloqueador, que era como o teste fazia.
                    congruencia=congruencia,
                )
                for b in deduped
            ]
            elegiveis = [d for d in decisoes if d.decisao == INCLUDE]
            escolhidos, _fora = aplicar_politica_de_selecao(elegiveis)

            decisoes_do_funil.extend(decisoes)
            selecionadas_do_funil.extend(escolhidos)

            escolhidos_ids = {id(d) for d in escolhidos}
            retidas = [d for d in decisoes if id(d) not in escolhidos_ids]

            keywords_text = "\n".join(
                f"  - {d.termo} (Vol: {_vol_legivel(d.volume)}, CPC: {_cpc_legivel(d.cpc)})"
                for d in escolhidos
            )
            # As retidas viajam junto e ESCRITAS. Uma keyword que sai do
            # conjunto sem aparecer em lugar nenhum é a mesma opacidade que
            # deixava a campanha receber termo que ninguém escolheu.
            keywords_retidas_text = "\n".join(
                f"  - {d.termo} (Vol: {_vol_legivel(d.volume)}, CPC: {_cpc_legivel(d.cpc)})"
                f" — {d.situacao}: {'; '.join(d.motivos) or 'sem motivo registrado'}"
                for d in retidas
            )

            processed_intents.append(
                {
                    "tipo": tipo,
                    "descricao": intent.get("descricao") or "",
                    "volume_sub": intent.get("volume_sub") or 0,
                    "keywords": [_kw_publica(d) for d in escolhidos],
                    "keywords_text": keywords_text,
                    "keywords_retidas": [_kw_publica(d) for d in retidas],
                    "keywords_retidas_text": keywords_retidas_text,
                }
            )

        processed_intents.sort(key=lambda a: a.get("volume_sub") or 0, reverse=True)

        conjunto = montar_conjunto(
            decisoes_do_funil,
            selecionadas_do_funil,
            teto_do_dono=teto_do_dono,
            evidence_snapshot={
                "tema": funnel.get("keyword_ancora"),
                "processado_em": date.isoformat(),
                "funil": funnel.get("nome_funil"),
            },
        )
        conjuntos.append(conjunto)

        # O CONJUNTO EXPORTADO É O CONJUNTO SELECIONADO. Sem segunda dedup,
        # sem reordenação por volume que reintroduza o que a decisão tirou.
        final_campaign = [_kw_publica(d) for d in conjunto.selected_keywords]

        formatted_subs = "\n\n".join(
            f"📌 {intent['tipo']} ({_fmt_int_ptbr(intent['volume_sub'])} vol)\n"
            + (f'   "{intent["descricao"]}"\n' if intent["descricao"] else "")
            + intent["keywords_text"]
            for intent in processed_intents
        )
        keywords_for_ads = derivar_lista_google_ads(conjunto)
        keywords_for_clickup = "\n".join(
            f"{d.termo} | Vol: {_vol_legivel(d.volume)} | CPC: R${_cpc_legivel(d.cpc)}"
            f" | {d.subintencao} | {d.match_type}"
            for d in conjunto.selected_keywords
        )

        volumes_medidos = [
            d.volume.valor for d in conjunto.selected_keywords if d.volume.estado == MEDIDO
        ]
        total_valid_volume = int(sum(volumes_medidos))
        perdidos = [r["volume_lost"] for r in removed_keywords if r["volume_lost"] is not None]
        total_lost_volume = int(sum(perdidos))
        cpc_medio = media_de_cpc(conjunto.selected_keywords)
        metricas = funnel.get("metricas") or {}

        production_queue.append(
            {
                "_batch_info": batch_info,
                "project_name": funnel.get("nome_funil"),
                "execution_rank": funnel.get("rank"),
                "funnel_context": {
                    "theme": funnel.get("keyword_ancora"),
                    "anchor_volume": funnel.get("volume_ancora") or 0,
                    "metrics": {
                        "total_volume_declarado": metricas.get("volume_agregado"),
                        "valid_volume": total_valid_volume,
                        "valid_keywords_com_volume_medido": len(volumes_medidos),
                        "lost_volume": total_lost_volume,
                        "removed_keywords_sem_volume_medido": len(removed_keywords) - len(perdidos),
                        # Declarado pelo LLM do prospector, não medido. `None` quando ele
                        # não declarou — `0` diria "de graça".
                        "avg_cpc_declarado": metricas.get("cpc_medio"),
                        "total_keywords": metricas.get("qtd_keywords") or 0,
                        "candidatas": len(conjunto.candidates),
                        "valid_keywords": len(conjunto.selected_keywords),
                        "removed_keywords": len(removed_keywords),
                        "retidas_por_elegibilidade": len(conjunto.excluded_keywords),
                        "em_revisao_humana": len(conjunto.human_review_keywords),
                        "sub_intents_count": metricas.get("qtd_sub_intencoes") or len(processed_intents),
                    },
                    "strategic_direction": funnel.get("justificativa"),
                    "tags": ", ".join(funnel.get("tags") or []),
                    "sub_intencoes_raw": processed_intents,
                    "sub_intencoes_text": formatted_subs,
                },
                "keywords_campanha": {
                    "lista_google_ads": keywords_for_ads,
                    "lista_clickup": keywords_for_clickup,
                    "keywords_array": final_campaign,
                    "conjunto_pago": conjunto.como_dicionario(),
                    "stats": {
                        "total_keywords": len(conjunto.selected_keywords),
                        "total_volume": total_valid_volume,
                        "avg_cpc": _cpc_legivel(cpc_medio),
                        "avg_cpc_estado": cpc_medio.estado,
                        "avg_cpc_n": len(
                            [d for d in conjunto.selected_keywords if d.cpc.estado == MEDIDO]
                        ),
                    },
                },
                "keywords_removidas": {
                    "lista": removed_keywords,
                    "total_removidas": len(removed_keywords),
                    "volume_perdido": total_lost_volume,
                },
                "processamento": {
                    "data_processamento": date.isoformat(),
                    "ano_referencia": current_year,
                    "mes_atual": current_month,
                    "regras_aplicadas": [
                        f"Substituição {previous_year} → {current_year}",
                        f"Remoção de meses passados (< mês {current_month})",
                        "Deduplicação por keyword normalizada DENTRO da sub-intenção",
                        "Elegibilidade paga antes do corte por volume",
                        "Conjunto exportado derivado de selected_keywords",
                    ],
                },
            }
        )

    ordem = sorted(range(len(production_queue)), key=lambda i: production_queue[i].get("execution_rank") or 0)
    return [production_queue[i] for i in ordem], [conjuntos[i] for i in ordem]


def _kw_publica(decisao) -> Dict[str, Any]:
    """A forma pública de uma keyword — com o ESTADO do número junto do número.

    `volume: None` e `volume_estado: "absent"` dizem a mesma coisa duas vezes de
    propósito: um leitor antigo que só olha `volume` recebe `None` e falha alto,
    em vez de receber `0` e seguir confiante.
    """
    return {
        "keyword": decisao.termo,
        "original": decisao.original,
        "sub_intencao": decisao.subintencao,
        "match_type": decisao.match_type,
        "volume": decisao.volume.valor,
        "volume_estado": decisao.volume.estado,
        "cpc": decisao.cpc.valor,
        "cpc_estado": decisao.cpc.estado,
        "arquetipos": list(decisao.arquetipos),
        "decisao": decisao.decisao,
        "situacao": decisao.situacao,
        "motivos": list(decisao.motivos),
        "alertas": list(decisao.alertas),
        "bloqueadores": list(decisao.bloqueadores),
    }


def funnel_factory(
    ai_output: Dict[str, Any],
    *,
    today: Optional[datetime] = None,
    teto_do_dono: Optional[float] = None,
    marcas_proprias: Sequence[str] = (),
    marcas_de_terceiro: Sequence[str] = (),
    congruencia: str = "nao_avaliada",
) -> List[Dict[str, Any]]:
    """A fila de produção, JSON-safe — a assinatura que o orquestrador chama."""
    fila, _conjuntos = funnel_factory_com_conjuntos(
        ai_output, today=today, teto_do_dono=teto_do_dono,
        marcas_proprias=marcas_proprias, marcas_de_terceiro=marcas_de_terceiro,
        congruencia=congruencia,
    )
    return fila
