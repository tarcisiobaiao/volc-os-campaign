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

from typing import Any

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


def preco_de_referencia(motor: Any) -> float | None:
    """O preço por imagem que ESTE motor publica, ou `None`.

    ⚠️ Antes esta função importava a constante do motor Gemini, sem olhar para o
    motor que ia rodar. Com um provider novo instalado, o plano continuava
    mostrando US$ 0,039 por imagem — o preço de um motor que não seria chamado.
    Um número de preço ao lado de um botão que gasta precisa ser o preço DAQUELE
    ato; um número herdado de outro provider é pior que nenhum, porque parece
    conferido.

    O `gpt-image-2` é o caso que expõe a diferença: ele é cobrado por TOKEN e a
    OpenAI não publica dólar por imagem por `size`/`quality`. O motor declara
    `preco_referencia_usd_por_imagem = None`, e `None` sobe até a tela como
    "estimativa indisponível".
    """
    preco = getattr(motor, "preco_referencia_usd_por_imagem", None)
    if preco is None:
        return None
    try:
        return float(preco)
    except (TypeError, ValueError):
        return None


def _custo_estimado(total: int, motor: Any) -> float | None:
    """A estimativa do lote, ou ausência declarada.

    Devolve `None`, nunca `0.0`, quando o motor não publica preço. Zero é um
    preço — e um "custo estimado: US$ 0,00" ao lado de um botão que gasta é a
    frase mais cara que esta tela poderia dizer.
    """
    preco = preco_de_referencia(motor)
    if not preco:
        return None
    return round(total * preco, 6)


def montar_plano(
    *,
    saida: SaidaDoAgente,
    pedido: PedidoDeGeracao,
    caminhos_aprovados: frozenset[str],
    contexto_do_publico: str,
    objetivo: str,
    motor: Any = None,
    anexo: dict[str, Any] | None = None,
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

    # (3b) A fotografia precisa existir E ser desta operação. A ref é opaca, mas
    #      ref opaca não é autorização: quem a resolve confere o dono, e este
    #      bloqueio existe para o caso em que ela some entre a tela e o clique
    #      (o operador removeu o anexo noutra aba).
    if pedido.modo_de_composicao != "sem_foto" and anexo is None:
        bloqueios.append(
            Bloqueio(
                codigo="CRIATIVO_STUDIO_ANEXO_INDISPONIVEL",
                mensagem=(
                    "A fotografia escolhida não está mais disponível nesta operação. "
                    "Envie a imagem de novo ou produza sem fotografia."
                ),
            )
        )

    # (3c) O motor precisa saber receber a foto. Um motor que ignorasse o anexo
    #      entregaria uma peça diferente da pedida e cobraria por ela.
    if pedido.modo_de_composicao == "reinterpretado" and motor is not None:
        if not getattr(motor, "aceita_referencia", True):
            bloqueios.append(
                Bloqueio(
                    codigo="CRIATIVO_STUDIO_MOTOR_SEM_REFERENCIA",
                    mensagem=(
                        "O motor configurado neste servidor não recebe fotografia "
                        "como referência."
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
        custo_estimado_usd=_custo_estimado(total, motor),
        bloqueios=bloqueios,
        modo_de_composicao=pedido.modo_de_composicao,
        anexo_sha256=(anexo or {}).get("content_sha256"),
    )


def pedido_de_job(
    briefings: list[BriefingDeImagem],
    *,
    nome_da_operacao: str,
    modo_de_composicao: str = "sem_foto",
    anexo: dict[str, Any] | None = None,
    plano_sha256: str | None = None,
    teto_custo_usd: float | None = None,
) -> dict:
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
        # `photo_preserved` e `full_llm` são modos DIFERENTES no vocabulário que
        # a v11_04 já fechou por CHECK, e a diferença é exatamente a promessa
        # que a peça faz: um preserva os pixels da fotografia, o outro não.
        # Gravar `full_llm` numa peça composta apagaria essa distinção no banco.
        "modo": "photo_preserved" if modo_de_composicao == "hibrido" else "full_llm",
        "slots": [b.formato_slot for b in briefings],
        # Origem e o dominio chamador, conforme criativo_projeto_origem_valida
        # (v11_01), nao o nome da ferramenta. A identificacao do Assistente
        # permanece na ponte project/run/creative -> job, sem ampliar o enum SQL.
        "origem": "trafego",
        "destinos_pretendidos": ["meta_feed"],
        # ⚠️ `creative_ref` e `run_ref` entram no pedido, e não é decoração: eles
        # participam da CHAVE DE IDEMPOTÊNCIA. Sem eles, duas peças que o modelo
        # devolveu com a mesma direção visual e o mesmo texto colapsavam num job
        # só, e a resposta mentia o total — o operador autorizava 4 renders e
        # recebia 2, sem nenhuma recusa.
        "creative_ref": primeiro.linhagem.creative_ref,
        "run_ref": primeiro.linhagem.run_ref,
        "modo_de_composicao": modo_de_composicao,
        "anexo_ref": (anexo or {}).get("anexo_ref"),
        "anexo_sha256": (anexo or {}).get("content_sha256"),
        "anexo_storage_chave": (anexo or {}).get("storage_chave"),
        "anexo_mime": (anexo or {}).get("mime"),
        # A trilha da autorizacao acompanha o pedido ate o job: sem ela, "quem
        # autorizou este gasto e sobre qual plano?" nao tem resposta em SQL.
        "plano_sha256": plano_sha256,
        "teto_custo_usd": teto_custo_usd,
    }
