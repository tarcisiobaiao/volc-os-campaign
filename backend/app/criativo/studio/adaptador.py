"""Traduz um lote estratégico aprovado em pedidos de render — sem redecidir nada.

## A regra que este arquivo existe para cumprir

"N conceitos × M formatos são N×M saídas, não N ideias novas."

O `CreativeStrategistAgent` do Aprova é referência de implementação, não cérebro:
rodá-lo aqui daria uma SEGUNDA autoridade estratégica decidindo o mesmo briefing,
e as duas divergiriam em silêncio. A estratégia já foi decidida pelo
`AgenteCriativoMeta` e aprovada por uma pessoa; aqui ela só muda de vocabulário.

## Os três campos que não podem se misturar

    headline_interna / complemento_interno / cta_visual  -> vão DENTRO da arte
    direcao_visual                                        -> instrui a composição
    CopyCompartilhada.texto_principal                     -> vai FORA, no anúncio

Usar `texto_principal` como se fosse a arte é o erro mais fácil aqui, e ele não
aparece em teste de tipo: os dois são `str`. Por isso a função que monta o texto
da arte não RECEBE a copy da campanha — ela não tem como cometer o engano.
"""

from __future__ import annotations

from app.criativo import dominio
from app.criativo.agente.contrato import (
    CopyCompartilhada,
    PecaCriativa,
    SaidaDoAgente,
    contem_metadado_operacional,
)

from .contrato import (
    MAX_RENDERS_POR_PEDIDO,
    Bloqueio,
    BriefingDeImagem,
    Linhagem,
    PedidoDeGeracao,
    PlanoDeGeracao,
)


def texto_na_arte(peca: PecaCriativa) -> str:
    """O que é para aparecer NOS PIXELS. Só os campos internos da peça.

    A assinatura recebe a peça e nada mais de propósito: sem acesso à
    `CopyCompartilhada`, não há como o texto do anúncio vazar para dentro da
    imagem por um `+` distraído.
    """
    partes = [peca.headline_interna, peca.complemento_interno, peca.cta_visual]
    return " · ".join(p.strip() for p in partes if p and p.strip())


def _custo_estimado(total: int) -> float | None:
    """Preço de referência do motor, ou ausência declarada.

    ⚠️ Devolve `None`, nunca `0.0`, quando o motor não publica preço. Zero é um
    preço — e um "custo estimado: US$ 0,00" ao lado de um botão que gasta é a
    frase mais cara que esta tela poderia dizer.
    """
    try:
        from services.creative_engine.motores.gemini_imagem import (  # noqa: PLC0415
            PRECO_REFERENCIA_USD_POR_IMAGEM,
        )
    except Exception:  # noqa: BLE001
        return None
    if not PRECO_REFERENCIA_USD_POR_IMAGEM:
        return None
    return round(total * float(PRECO_REFERENCIA_USD_POR_IMAGEM), 6)


def montar_plano(
    *,
    saida: SaidaDoAgente,
    pedido: PedidoDeGeracao,
    caminhos_aprovados: frozenset[str],
    contexto_do_publico: str,
    objetivo: str,
) -> PlanoDeGeracao:
    """Expande a seleção em N×M briefings, ou explica por que não expande.

    Nada aqui escreve, dispara ou chama provider: o plano é calculado inteiro —
    inclusive o teto e o custo — antes de existir a possibilidade de gastar.
    `bloqueios` não vazio é uma recusa que a tela desenha ANTES do clique.
    """
    bloqueios: list[Bloqueio] = []

    pecas_por_ref: dict[str, PecaCriativa] = {p.ref: p for p in saida.pecas}
    copies_por_ref: dict[str, CopyCompartilhada] = {
        c.ref: c for c in saida.copies_compartilhadas
    }

    # (1) A seleção precisa existir NESTE lote. Uma ref de outra run apontaria
    #     para um conceito que esta pessoa não leu e não aprovou.
    ausentes = [r for r in pedido.selected_creative_refs if r not in pecas_por_ref]
    if ausentes:
        bloqueios.append(
            Bloqueio(
                codigo="CRIATIVO_STUDIO_PECA_FORA_DO_LOTE",
                mensagem=(
                    "A seleção aponta para peças que não estão nesta estratégia: "
                    + ", ".join(sorted(ausentes))
                ),
            )
        )

    # (2) Os formatos precisam ser produzíveis. Oferecer um slot que o motor não
    #     renderiza é prometer um arquivo que nunca chega.
    formatos_invalidos: list[str] = []
    for slot in pedido.format_ids:
        try:
            dominio.formato_de(slot)
        except dominio.SlotDesconhecido:
            formatos_invalidos.append(slot)
    if formatos_invalidos:
        bloqueios.append(
            Bloqueio(
                codigo="CRIATIVO_STUDIO_FORMATO_INDISPONIVEL",
                mensagem=(
                    "O motor não produz estes formatos: " + ", ".join(sorted(formatos_invalidos))
                ),
            )
        )

    # (3) Cada peça selecionada precisa de aprovação humana registrada. O recibo
    #     do agente prova contrato, não decisão de gente — e é a decisão de gente
    #     que autoriza gastar.
    sem_aprovacao = [
        ref
        for ref in pedido.selected_creative_refs
        if ref in pecas_por_ref and f"/pecas/{ref}" not in caminhos_aprovados
    ]
    if sem_aprovacao:
        bloqueios.append(
            Bloqueio(
                codigo="CRIATIVO_STUDIO_PECA_NAO_APROVADA",
                mensagem=(
                    "Estas peças ainda não foram aprovadas por uma pessoa: "
                    + ", ".join(sorted(sem_aprovacao))
                ),
            )
        )

    conceitos = len(pedido.selected_creative_refs)
    formatos = len(pedido.format_ids)
    total = conceitos * formatos

    # (4) O teto é conferido ANTES de qualquer insert ou despacho.
    if total > MAX_RENDERS_POR_PEDIDO:
        bloqueios.append(
            Bloqueio(
                codigo="CRIATIVO_STUDIO_TETO_DE_RENDERS",
                mensagem=(
                    f"{conceitos} conceito(s) × {formatos} formato(s) dão {total} imagens, "
                    f"acima do teto de {MAX_RENDERS_POR_PEDIDO} por pedido."
                ),
            )
        )

    briefings: list[BriefingDeImagem] = []
    if not bloqueios:
        for creative_ref in pedido.selected_creative_refs:
            peca = pecas_por_ref[creative_ref]
            copy = copies_por_ref.get(peca.shared_copy_ref)
            if copy is None:
                bloqueios.append(
                    Bloqueio(
                        codigo="CRIATIVO_STUDIO_COPY_AUSENTE",
                        mensagem=f"{creative_ref} cita uma copy que não está no lote.",
                    )
                )
                continue

            arte = texto_na_arte(peca)
            # (5) Metadado operacional não entra em pixel. O contrato já tem o
            #     detector; usá-lo aqui evita gerar — e pagar por — uma peça com
            #     "APROVADO" ou "G1-C01" carimbado nela.
            if contem_metadado_operacional(peca):
                bloqueios.append(
                    Bloqueio(
                        codigo="CRIATIVO_STUDIO_METADADO_NA_ARTE",
                        mensagem=f"{creative_ref} tem metadado operacional no texto da arte.",
                    )
                )
                continue

            for slot in pedido.format_ids:
                briefings.append(
                    BriefingDeImagem(
                        linhagem=Linhagem(
                            creative_ref=peca.ref,
                            group_ref=peca.group_ref,
                            copy_ref=peca.shared_copy_ref,
                            state_ref=peca.estado_mental_ref,
                            project_ref=saida.project_ref,
                            run_ref=pedido.run_ref,
                            fato_refs=list(peca.fato_refs),
                            rule_refs=list(peca.rule_refs),
                        ),
                        formato_slot=slot,
                        direcao_visual=peca.direcao_visual,
                        texto_na_arte=arte,
                        contexto_do_publico=contexto_do_publico,
                        objetivo=objetivo,
                    )
                )

    return PlanoDeGeracao(
        briefings=briefings if not bloqueios else [],
        conceitos=conceitos,
        formatos=formatos,
        total_de_renders=total,
        custo_estimado_usd=_custo_estimado(total),
        bloqueios=bloqueios,
    )


def pedido_de_job(briefings: list[BriefingDeImagem], *, nome_da_operacao: str) -> dict:
    """O `pedido` que `Executor.criar_job_de_imagem` espera, para UM conceito.

    Todos os briefings desta lista pertencem à MESMA peça: um job carrega os M
    formatos dela. Agrupar assim é o que faz o retry preencher buraco por slot em
    vez de refazer o conceito inteiro — e o que faz uma falha em 9x16 não jogar
    fora o 1x1 que já ficou pronto.
    """
    if not briefings:
        raise ValueError("nenhum briefing para montar o job")
    primeiro = briefings[0]
    if any(b.linhagem.creative_ref != primeiro.linhagem.creative_ref for b in briefings):
        raise ValueError("um job de imagem cobre um único conceito")

    return {
        "projeto_titulo": nome_da_operacao,
        "objetivo": primeiro.objetivo,
        "mensagem": f"{primeiro.direcao_visual}\nTexto na arte: {primeiro.texto_na_arte}",
        "audiencia": primeiro.contexto_do_publico,
        "modo": "full_llm",
        "slots": [b.formato_slot for b in briefings],
        "origem": "assistente_criativo_meta",
        "destinos_pretendidos": ["meta_feed"],
    }
