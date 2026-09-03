"""CONTRAPROVAS DA ESPINHA v2 — o que a v1 detectava e deixava passar.

## O que estas provas são, e por que são um arquivo separado

`test_landing_policy_contraprovas.py` trava as contraprovas A–X do incidente
original. Elas continuam válidas e não foram reescritas. Este arquivo trava o
DELTA da espinha v2: as regras que nasceram porque, rodando o portão v1 sobre a
evidência preservada, ele saiu com menos bloqueios do que a evidência sustenta.

A medida que originou o arquivo, sobre os MESMOS bytes de
`docs/closure/hermes-redator-google-ads-policy-incident-v1/evidence-public/`:

    /r/antecipacao-saque-aniversario-fgts/   v1: 8 bloqueios → v2: 11
    /r/fgts-saque-aniversario/               v1: 3 bloqueios → v2:  6
    /r/maquininha-de-cartao-menor-taxa/      v1: 2 bloqueios → v2:  5
    /r/nova-carteira-identidade-nacional/    v1: 3 bloqueios → v2:  6

Treze bloqueios a mais, nenhum a menos. Cada um deles tem um teste aqui.

## A regra de escrita

Toda prova abaixo é HERMÉTICA: nenhuma abre socket, nenhuma lê conta do Google,
nenhuma escreve em site nenhum. E cada uma exige o CÓDIGO certo, não um veredito
vermelho qualquer — um teste que só confere `ready is False` passaria por
acidente de outro achado e não provaria nada sobre a regra que diz testar.
"""
from __future__ import annotations

import pytest

from app.landing_policy import (
    JANELA_DE_FRESCOR_PADRAO_S,
    POLICY_CONTRACT_VERSION,
    PaginaObservada,
    PapelDestino,
    PapelRelaxadoPeloCliente,
    PlanoDaPagina,
    PontoDePortao,
    anexar_recibo,
    avaliar,
    avaliar_plano,
    documento_do_plano,
    elegibilidade_de_destino_de_campanha,
    emitir_recibo,
    impressao_canonica,
    papel_do_servidor,
    recibo_da_url,
    url_canonica,
    versao_da_fonte,
)

CNPJ = "42.724.548/0001-24"
#: Congelado: frescor é aritmética, e uma referência que muda a cada execução
#: torna a prova de vencimento não reprodutível.
AGORA = 1_767_225_600.0  # 2026-01-01T00:00:00Z
SHA = "a" * 64

RODAPE = """
<p>Os conteúdos aqui publicados são de caráter informativo e não possuem vínculo,
parceria ou qualquer ligação com órgãos públicos ou entidades governamentais.</p>
<p>O site é financiado por blocos de anúncios em parceria com o Google Adsense.</p>
<p>Valores meramente ilustrativos, sujeitos às regras vigentes; consulte o canal oficial.</p>
<p>Projeto da Volc Negocios Digitais 42.724.548/0001-24.</p>
<a href="/sobre">Sobre</a> <a href="/contato">Contato</a>
<a href="/politica-de-privacidade">Política de Privacidade</a>
"""

CORPO = " ".join(
    ["O texto explica as regras vigentes e onde o leitor confere cada informação."] * 110
)


def montar(miolo: str = "", *, rodape: str = RODAPE, h1: str = "Guia", **kwargs) -> PaginaObservada:
    padrao = {
        "url": "https://exemplo.com.br/r/pagina/",
        "status_http": 200,
        "saltos_redirecionamento": [],
        "variantes_sha256": {"user": SHA, "googlebot": SHA},
        "sha256_observado": SHA,
        "sha256_aprovado": SHA,
        "cnpj_esperado": CNPJ,
        "avaliado_em_epoch": AGORA,
        "recibo_de_aprovacao": recibo_valido(),
    }
    padrao.update(kwargs)
    html = (
        f"<html><head><title>{h1}</title></head><body><h1>{h1}</h1>"
        f"<p>{CORPO}</p>{miolo}{rodape}</body></html>"
    )
    return PaginaObservada(html=html, **padrao)


def recibo_valido(**kwargs) -> dict:
    base = {
        "policy_contract_version": POLICY_CONTRACT_VERSION,
        "policy_source_version": versao_da_fonte(),
        "observed_at_epoch": AGORA - 60,
        "content_sha256": SHA,
        "paid_destination_ready": True,
    }
    base.update(kwargs)
    return base


def pago(pagina: PaginaObservada) -> set[str]:
    return {a.codigo for a in elegibilidade_de_destino_de_campanha(pagina).bloqueios}


def editorial(pagina: PaginaObservada) -> tuple[set[str], set[str]]:
    """(tudo que foi REGISTRADO, o que BLOQUEOU) no papel frouxo."""
    av = avaliar(pagina, PapelDestino.EDITORIAL_SOLUTION, PontoDePortao.ARTEFATO_DE_GERACAO)
    return (
        {a.codigo for a in av.bloqueios + av.riscos + av.observacoes},
        {a.codigo for a in av.bloqueios},
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1–5 · A POLÍTICA DE LINKS DO VOLC — mais restritiva que a do Google
# ═══════════════════════════════════════════════════════════════════════════

LINK_PAGO = "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO"


@pytest.mark.parametrize(
    "miolo,rotulo",
    [
        ('<p>Veja as <a href="https://www.caixa.gov.br/fgts">regras do FGTS na Caixa</a>.</p>',
         "governo, âncora descritiva, fora de botão"),
        ('<p>Veja a <a href="https://meutudo.com.br/fgts">tabela publicada</a>.</p>',
         "fonte de pesquisa declarada"),
        ('<p>Ir para <a href="//outro-dominio.example/x">o outro site</a>.</p>',
         "protocol-relative"),
    ],
)
def test_cp01_destino_pago_recusa_todo_hyperlink_externo_clicavel(miolo, rotulo):
    """⚠️ REGRA INTERNA DO VOLC, MAIS RESTRITIVA QUE A DO GOOGLE.

    O Google não proíbe hyperlink externo em página de destino; ele proíbe
    sugerir vínculo e proíbe a página-ponte. Banir TODOS os três casos acima é
    decisão da casa.

    Os três passavam no contrato v1, e cada um por um motivo diferente:
    `caixa.gov.br` é host de GOVERNO — classificado; `meutudo.com.br` foi
    DECLARADO pela pesquisa — classificado; e o protocol-relative resolve para
    um host que, sem lastro, cai em `terceiro_desconhecido` (esse a v1 pegava,
    mas só por não ter classificação, não por ser externo).

    A regra v1 barrava a AUSÊNCIA de classificação. A v2 barra a presença do
    link. É outra pergunta, e é a que o incidente pedia.
    """
    hosts = ("meutudo.com.br",) if "meutudo" in miolo else ()
    assert LINK_PAGO in pago(montar(miolo, hosts_declarados=hosts)), rotulo


def test_cp02_a_mesma_regra_nao_se_aplica_a_pagina_editorial():
    """O achado não some no papel frouxo — ele muda de peso.

    Perder o achado seria pior que reprovar: a operação deixaria de saber que o
    link existe naquela página, e ele viajaria intacto até o dia em que a URL
    virasse destino de campanha.
    """
    miolo = '<p>Veja as <a href="https://www.caixa.gov.br/fgts">regras do FGTS na Caixa</a>.</p>'
    registrados, bloqueados = editorial(montar(miolo))
    assert LINK_PAGO in registrados
    assert LINK_PAGO not in bloqueados


def test_cp03_referencia_oficial_com_lastro_e_aceita_em_editorial_solution():
    """O simétrico da 2: o portão precisa saber APROVAR conteúdo editorial.

    Um portão que só sabe reprovar é desligado pela operação na primeira semana,
    e aí não protege nada.
    """
    miolo = (
        '<p>Fonte oficial de referência: '
        '<a href="https://www.caixa.gov.br/beneficios-trabalhador/fgts">'
        "site da Caixa Econômica Federal</a>.</p>"
    )
    av = avaliar(
        montar(miolo, hosts_declarados=("caixa.gov.br",)),
        PapelDestino.EDITORIAL_SOLUTION,
        PontoDePortao.ARTEFATO_DE_GERACAO,
    )
    assert av.bloqueios == [], [a.codigo for a in av.bloqueios]


def test_cp04_link_externo_desconhecido_bloqueia_por_dois_motivos():
    """Sem lastro ele é `terceiro_desconhecido` E é externo. Os dois valem."""
    achados = pago(montar('<p>Veja <a href="https://desconhecido.example/x">o simulador</a>.</p>'))
    assert "LINK_EXTERNO_NAO_CLASSIFICADO" in achados
    assert LINK_PAGO in achados


@pytest.mark.parametrize(
    "href,rotulo",
    [
        ("/sobre", "relativo"),
        ("https://exemplo.com.br/outra-pagina/", "mesmo domínio canônico"),
        ("#secao", "âncora interna"),
        ("mailto:contato@exemplo.com.br", "contato direto permitido"),
        ("tel:+551140028922", "telefone permitido"),
    ],
)
def test_cp05_link_interno_e_caminho_de_contato_passam(href, rotulo):
    """A regra incide sobre NAVEGAÇÃO PARA FORA, não sobre link.

    Se ela pegasse âncora interna, link relativo ou caminho de contato, ela
    tornaria impossível a própria exigência de identidade — que pede contato e
    política de privacidade acessíveis.
    """
    assert LINK_PAGO not in pago(montar(f'<p><a href="{href}">ir</a></p>')), rotulo


def test_cp05b_recurso_tecnico_nao_e_link_editorial_de_saida():
    """Imagem, fonte e script não são navegação clicável do leitor.

    Confundi-los com outbound link editorial afogaria o achado que importa numa
    lista de assets — e a operação aprenderia a ignorar a lista.
    """
    miolo = (
        '<img src="https://cdn.exemplo-externo.example/a.png">'
        '<script src="https://cdn.exemplo-externo.example/a.js"></script>'
    )
    assert LINK_PAGO not in pago(montar(miolo))


# ═══════════════════════════════════════════════════════════════════════════
# 6–12 · COPY, IDENTIDADE E ALEGAÇÕES
# ═══════════════════════════════════════════════════════════════════════════


def test_cp06_ausencia_de_link_externo_nao_salva_copy_com_falsa_afiliacao():
    """Zero link externo, e a página continua reprovando.

    A regra de links não é a defesa; ela é UMA das defesas. Uma página que diz
    ser o canal oficial não fica correta por não linkar ninguém.
    """
    pagina = montar(h1="Saque-Aniversário FGTS Liberado pelo Governo")
    achados = pago(pagina)
    assert LINK_PAGO not in achados, "esta página não tem link externo nenhum"
    assert "TITULO_SUGERE_ORIGEM_OFICIAL" in achados


def test_cp07_identidade_e_disclosure_ausentes_bloqueiam_separadamente():
    """⚠️ MUDANÇA DE CONTRATO: eram um `OU`, e a divulgação nunca bloqueava.

    A v1 aprovava identidade por `CNPJ **ou** (sobre **e** contato)` — uma
    página SEM CNPJ nenhum passava por conter as palavras "Sobre" e "Contato".
    E `DIVULGACAO_DE_MONETIZACAO_AUSENTE` vivia em `_RISCO_SEMPRE`: era
    detectada e não reprovava em papel nenhum.

    São três perguntas diferentes: QUEM responde (registro), COMO se chega até
    ele (contato/privacidade), e SE a página diz que é monetizada.
    """
    so_rotulos = '<a href="/sobre">Sobre</a> <a href="/contato">Contato</a>'
    achados = pago(montar(rodape=so_rotulos))
    assert "IDENTIDADE_OPERADOR_AUSENTE" in achados
    assert "IDENTIDADE_CONTATO_AUSENTE" in achados
    assert "DIVULGACAO_DE_MONETIZACAO_AUSENTE" in achados


def test_cp07b_texto_escondido_nao_satisfaz_identidade_nem_disclosure():
    """Um `display:none` com CNPJ e avisos satisfazia tudo de uma vez.

    O revisor lê o HTML; o visitante lê a tela. Aceitar o bloco escondido como
    prova é uma forma vizinha do cloaking que este módulo existe para proibir.
    """
    achados = pago(montar(rodape=f'<div style="display:none">{RODAPE}</div>'))
    assert "IDENTIDADE_OPERADOR_AUSENTE" in achados
    assert "DIVULGACAO_DE_MONETIZACAO_AUSENTE" in achados


def test_cp08_evidencia_ausente_nao_vira_verde(monkeypatch):
    """Varredura que EXPLODE reprova, mesmo onde ela não é exigida.

    ⚠️ Antes da v2, `failed` só virava desconhecido quando o nome estava em
    `EXIGENCIAS_POR_PONTO[ponto]`. No portão de pré-publicação quatro
    verificações não são exigidas — elas podiam quebrar inteiras e a publicação
    seguia autorizada. "Não é exigível aqui" é decisão do contrato; "quebrou" é
    defeito do software, e software quebrado nunca é evidência de página limpa.
    """
    from app.landing_policy import varredura as v

    def explode(_pagina):
        raise RuntimeError("varredura quebrada")

    monkeypatch.setitem(v.VARREDURAS, "destination_security_signals", explode)
    av = avaliar(montar(), PapelDestino.PAID_DESTINATION, PontoDePortao.PRE_PUBLICACAO_WORDPRESS)
    assert av.paid_destination_ready is False
    assert "destination_security_signals" in {d["verificacao"] for d in av.desconhecidos}


def test_cp09_h1_perigoso_e_capturado_no_plano_antes_de_existir_corpo():
    """A alegação entrou pelo PLANO, e o portão v1 olhava só o CORPO.

    `calm_utility` bania "liberado pelo governo" no corpo escrito; o H1 do plano
    histórico é literalmente "Saque-Aniversário FGTS Liberado pelo Governo". O
    portão olhava depois do ponto em que o defeito nasceu.
    """
    av, papel = avaliar_plano(
        PlanoDaPagina(
            rota="/r/fgts/",
            titulo="Saque-aniversário do FGTS",
            h1="Saque-Aniversário FGTS Liberado pelo Governo",
            corpo=CORPO,
            papel_do_motor="LP",
        ),
        base_do_site="https://exemplo.com.br",
    )
    assert papel is PapelDestino.PAID_DESTINATION
    assert "TITULO_SUGERE_ORIGEM_OFICIAL" in {a.codigo for a in av.bloqueios}


def test_cp09b_o_title_tambem_e_manchete_mesmo_com_h1_calmo():
    """O `<title>` é o que o leitor vê na aba e no resultado de busca."""
    pagina = PaginaObservada(
        url="https://exemplo.com.br/r/x/",
        html=(
            "<html><head><title>Portal oficial do FGTS</title></head><body>"
            f"<h1>Como funciona o saque</h1><p>{CORPO}</p>{RODAPE}</body></html>"
        ),
        cnpj_esperado=CNPJ,
    )
    av = avaliar(pagina, PapelDestino.PAID_DESTINATION, PontoDePortao.ARTEFATO_DE_GERACAO)
    assert "TITULO_SUGERE_ORIGEM_OFICIAL" in {a.codigo for a in av.bloqueios}


def test_cp10_alegacao_financeira_sem_divulgacao_nao_passa_em_silencio():
    numeros = "<p>A alíquota vai de 5% a 50% e a parcela chega a R$ 2.900,00.</p>"
    sem_divulgacao = RODAPE.replace(
        "<p>Valores meramente ilustrativos, sujeitos às regras vigentes; consulte o canal oficial.</p>",
        "",
    ).replace("de caráter informativo e ", "")
    assert "ALEGACAO_FINANCEIRA_SEM_DIVULGACAO" in pago(montar(numeros, rodape=sem_divulgacao))


def test_cp11_moeda_brasileira_malformada_bloqueia_no_pago_e_registra_no_organico():
    """⚠️ MUDANÇA DE CONTRATO: era risco em toda parte, e nunca reprovava nada.

    O que ele vê é `2900.00 R$` — vazamento de máquina apresentado ao leitor
    como cifra oficial, e no destino do incidente ele estava DENTRO de um link
    para o banco público.
    """
    miolo = "<p>A parcela fixa chega a 2900.00 R$ por ano.</p>"
    assert "VALOR_MONETARIO_MALFORMADO" in pago(montar(miolo))
    registrados, bloqueados = editorial(montar(miolo))
    assert "VALOR_MONETARIO_MALFORMADO" in registrados
    assert "VALOR_MONETARIO_MALFORMADO" not in bloqueados


def test_cp12_cta_externo_e_cta_incongruente_bloqueiam():
    """As duas metades da contraprova 12, cada uma pelo seu código."""
    externo = (
        '<div class="wp-block-button">'
        '<a class="wp-block-button__link" href="https://parceiro.example/lp">Simular agora</a></div>'
    )
    achados = pago(montar(externo))
    assert LINK_PAGO in achados
    assert "BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO" in achados

    incongruente = '<p><a href="https://exemplo.com.br/r/maquininha-de-cartao/">consultar o saldo do FGTS</a></p>'
    assert "ANCORA_INCONGRUENTE_COM_DESTINO" in pago(montar(incongruente))


# ═══════════════════════════════════════════════════════════════════════════
# 15–19 · RECIBO, DERIVA E FRESCOR
# ═══════════════════════════════════════════════════════════════════════════


def test_cp15_alteracao_apos_a_aprovacao_invalida_a_elegibilidade():
    """A deriva compara a IMPRESSÃO CANÔNICA, não o byte."""
    html_aprovado = f"<html><body><h1>Guia</h1><p>{CORPO}</p>{RODAPE}</body></html>"
    html_no_ar = html_aprovado.replace("O texto explica as regras", "O GOVERNO LIBEROU as regras")
    pagina = PaginaObservada(
        url="https://exemplo.com.br/r/x/",
        html=html_no_ar,
        status_http=200,
        saltos_redirecionamento=[],
        variantes_sha256={"user": SHA, "googlebot": SHA},
        sha256_observado=SHA,
        impressao_aprovada=impressao_canonica(html_aprovado),
        cnpj_esperado=CNPJ,
        recibo_de_aprovacao=recibo_valido(),
        avaliado_em_epoch=AGORA,
    )
    assert "DERIVA_AO_VIVO" in {a.codigo for a in elegibilidade_de_destino_de_campanha(pagina).bloqueios}


def test_cp15b_ruido_de_rotacao_nao_e_deriva():
    """Desktop e mobile da MESMA leitura diferiram em 27 bytes, no incidente.

    Um token rotativo de push. Reprovar por deriva a cada rotação faria a
    operação desligar o portão — e portão desligado não protege nada. Este é o
    simétrico obrigatório da prova acima.
    """
    html = f'<html><body><h1>Guia</h1><p>{CORPO}</p><span data-time="1756891234">x</span>{RODAPE}</body></html>'
    girado = html.replace("1756891234", "1756899999")
    pagina = PaginaObservada(
        url="https://exemplo.com.br/r/x/",
        html=girado,
        status_http=200,
        saltos_redirecionamento=[],
        variantes_sha256={"user": SHA, "googlebot": SHA},
        sha256_observado=SHA,
        impressao_aprovada=impressao_canonica(html),
        cnpj_esperado=CNPJ,
        recibo_de_aprovacao=recibo_valido(),
        avaliado_em_epoch=AGORA,
    )
    av = elegibilidade_de_destino_de_campanha(pagina)
    assert "DERIVA_AO_VIVO" not in {a.codigo for a in av.bloqueios}
    assert av.paid_destination_ready is True


def test_cp16_recibo_de_versao_antiga_nao_e_reaproveitado_em_silencio():
    antigo = recibo_valido(policy_contract_version="paid_destination_policy_spine.v1")
    assert "RECIBO_DE_POLITICA_DESATUALIZADO" in pago(montar(recibo_de_aprovacao=antigo))
    outra_matriz = recibo_valido(policy_source_version="0" * 16)
    assert "RECIBO_DE_POLITICA_DESATUALIZADO" in pago(montar(recibo_de_aprovacao=outra_matriz))


def test_cp16b_recibo_vencido_e_recibo_ausente_sao_defeitos_diferentes():
    vencido = recibo_valido(observed_at_epoch=AGORA - JANELA_DE_FRESCOR_PADRAO_S - 1)
    assert "RECIBO_DE_APROVACAO_VENCIDO" in pago(montar(recibo_de_aprovacao=vencido))
    assert "RECIBO_DE_APROVACAO_AUSENTE" in pago(montar(recibo_de_aprovacao=None))


def test_cp17_leitura_ao_vivo_indisponivel_falha_fechada():
    """⚠️ O FALSO VERDE QUE A REVISÃO ADVERSARIAL MEDIU.

    Com evidência de redirecionamento COMPLETA e nenhuma leitura ao vivo, o
    portão de campanha devolvia `paid_destination_ready=True` — sem comparar
    hash aprovado e sem conferir recibo. `not_applicable` está em
    `STATUS_CONCLUSIVOS`, e as duas verificações o devolviam quando não havia
    HTML observado. O verde saía de duas ausências.

    Uma página que está no ar SEMPRE tem hash observável. "Não se aplica" ali é
    impossível de boa-fé.
    """
    pagina = PaginaObservada(
        url="https://exemplo.com.br/r/x/",
        html=f"<html><body><h1>Guia</h1><p>{CORPO}</p>{RODAPE}</body></html>",
        status_http=200,
        saltos_redirecionamento=[],
        variantes_sha256={"user": SHA, "googlebot": SHA},
        cnpj_esperado=CNPJ,
        avaliado_em_epoch=AGORA,
    )
    av = elegibilidade_de_destino_de_campanha(pagina)
    assert av.paid_destination_ready is False
    desconhecidos = {d["verificacao"] for d in av.desconhecidos}
    assert "live_drift" in desconhecidos
    assert "approval_receipt" in desconhecidos


def test_cp18_redirect_cross_domain_bloqueia():
    saltos = [{"status": 302, "to": "https://outro-dominio.example/r/x/"}]
    assert "REDIRECIONAMENTO_CROSS_DOMAIN" in pago(montar(saltos_redirecionamento=saltos))


def test_cp19_cadeia_excessiva_bloqueia_e_um_salto_de_rotina_nao():
    longa = [
        {"status": 301, "to": "https://exemplo.com.br/a"},
        {"status": 301, "to": "https://exemplo.com.br/b"},
        {"status": 301, "to": "https://exemplo.com.br/c"},
    ]
    assert "CADEIA_DE_REDIRECIONAMENTO_EXCESSIVA" in pago(montar(saltos_redirecionamento=longa))
    curta = [{"status": 301, "to": "https://exemplo.com.br/r/pagina/"}]
    assert "CADEIA_DE_REDIRECIONAMENTO_EXCESSIVA" not in pago(montar(saltos_redirecionamento=curta))


# ═══════════════════════════════════════════════════════════════════════════
# 20–21 · CLOAKING × RESPONSIVIDADE
# ═══════════════════════════════════════════════════════════════════════════


def test_cp20_conteudo_diferente_por_user_agent_e_sinalizado():
    variantes = {"user": SHA, "googlebot": "b" * 64}
    assert "DIVERGENCIA_RASTREADOR_USUARIO" in pago(montar(variantes_sha256=variantes))


def test_cp21_diferenca_apenas_de_dispositivo_nao_e_falso_positivo():
    """A primeira versão desta regra acusou o destino real, e a evidência dizia o contrário.

    Desktop e mobile diferiam em 27 bytes; o Googlebot devolveu HTML BYTE A BYTE
    igual ao do desktop. Acusar cloaking ali seria, num pacote de apelação, uma
    admissão falsa.
    """
    variantes = {"user_desktop": SHA, "user_mobile": "c" * 64, "googlebot": SHA}
    assert "DIVERGENCIA_RASTREADOR_USUARIO" not in pago(montar(variantes_sha256=variantes))


# ═══════════════════════════════════════════════════════════════════════════
# 24 · A AUTORIDADE DO PAPEL
# ═══════════════════════════════════════════════════════════════════════════


def test_cp24_cliente_nao_consegue_enviar_papel_menos_rigoroso():
    with pytest.raises(PapelRelaxadoPeloCliente):
        papel_do_servidor(e_destino_de_campanha=True, papel_pedido_pelo_cliente="organic_article")


def test_cp24b_o_cliente_pode_subir_o_rigor_e_papel_inventado_e_ignorado():
    assert (
        papel_do_servidor(papel_do_motor="SOLUTION", papel_pedido_pelo_cliente="paid_destination")
        is PapelDestino.PAID_DESTINATION
    )
    assert (
        papel_do_servidor(e_destino_de_campanha=True, papel_pedido_pelo_cliente="qualquer_coisa")
        is PapelDestino.PAID_DESTINATION
    )


def test_cp24c_formulario_no_artefato_sobe_o_papel_sem_ninguem_declarar():
    """`conversion_page` é apurada do ARTEFATO, não declarada."""
    av, papel = avaliar_plano(
        PlanoDaPagina(
            rota="/r/x/",
            h1="Guia",
            corpo=CORPO,
            papel_do_motor="SOLUTION",
            campos_de_formulario=({"tipo": "text", "nome": "cpf"},),
        )
    )
    assert papel is PapelDestino.CONVERSION_PAGE


def test_cp24d_o_papel_estrito_consegue_ficar_verde():
    """Se `conversion_page` nunca ficasse verde, a operação BAIXARIA o papel para publicar.

    Uma régua que ninguém consegue atingir é uma régua que se contorna — e o
    contorno aqui trocaria o regime mais duro pelo menos duro.
    """
    av = avaliar(montar(), PapelDestino.CONVERSION_PAGE, PontoDePortao.ELEGIBILIDADE_DESTINO_CAMPANHA)
    assert av.paid_destination_ready is True


# ═══════════════════════════════════════════════════════════════════════════
# 27–30 · FORMATOS, FONTES, PONTE E O VERDE POSSÍVEL
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "corpo,formato,rotulo",
    [
        ('A multa é de <a href="https://www.caixa.gov.br/"><strong>40 %</strong></a>.', "html", "HTML"),
        ("A multa é de [40%](https://www.caixa.gov.br/).", "markdown", "Markdown"),
        ("Veja https://www.caixa.gov.br/fgts para detalhes.", "markdown", "URL nua"),
        ("Veja <https://www.caixa.gov.br/fgts>.", "markdown", "autolink"),
    ],
)
def test_cp27_o_scanner_trata_html_markdown_e_url_nua(corpo, formato, rotulo):
    """O redator devolve MARKDOWN.

    Um scanner que só enxergasse `<a href>` daria verde para
    `[40%](https://www.caixa.gov.br/)` — o defeito do incidente escrito na
    sintaxe em que ele nasce. E URL nua vira link clicável na maioria dos temas
    de WordPress: tratá-la como texto seria acreditar numa renderização que não
    é a que o leitor vê.
    """
    av, _ = avaliar_plano(
        PlanoDaPagina(
            rota="/r/x/", h1="Guia", corpo=CORPO + " " + corpo, formato=formato, papel_do_motor="LP"
        ),
        base_do_site="https://exemplo.com.br",
    )
    assert LINK_PAGO in {a.codigo for a in av.bloqueios}, rotulo


def test_cp27b_campo_estruturado_entra_na_varredura_como_o_corpo():
    """H1, CTA, alegação, valor e formulário são avaliados, não só o `content`.

    O portão v1 recebia SÓ o corpo — título, H1, CTA, campo de formulário e
    identidade chegavam como campos estruturados, e um portão que recebe só o
    corpo não tem como reprovar o que não está no corpo.
    """
    plano = PlanoDaPagina(
        rota="/r/x/",
        h1="Guia",
        corpo=CORPO,
        papel_do_motor="LP",
        valores_monetarios=("2900.00 R$",),
        ctas=({"texto": "Simular agora", "destino": "https://parceiro.example/lp"},),
    )
    av, _ = avaliar_plano(plano, base_do_site="https://exemplo.com.br")
    achados = {a.codigo for a in av.bloqueios}
    assert "VALOR_MONETARIO_MALFORMADO" in achados
    assert LINK_PAGO in achados


def test_cp28_fonte_registrada_nao_vira_hyperlink_automaticamente():
    """A fonte fica no dossiê. Ela não é renderizada como âncora.

    `fontes_de_pesquisa` alimenta a evidência e dá lastro a link que o plano
    tenha feito — ela nunca gera um `<a href>` sozinha.
    """
    plano = PlanoDaPagina(
        rota="/r/x/",
        h1="Guia",
        corpo=CORPO,
        papel_do_motor="LP",
        identidade={
            "razao_social": "Volc Negocios Digitais",
            "cnpj": CNPJ,
            "sobre": "/sobre",
            "contato": "/contato",
            "privacidade": "/politica-de-privacidade",
        },
        disclosures=(
            "Conteúdo de caráter informativo, sem vínculo com órgãos públicos.",
            "O site é financiado por blocos de anúncios em parceria com o Google Adsense.",
        ),
        fontes_de_pesquisa=("https://www.caixa.gov.br/fgts",),
    )
    documento = documento_do_plano(plano)
    assert "caixa.gov.br" not in documento
    av, _ = avaliar_plano(plano, base_do_site="https://exemplo.com.br")
    assert LINK_PAGO not in {a.codigo for a in av.bloqueios}


def test_cp29_pagina_ponte_sem_valor_original_e_recusada():
    """Mais botão que texto: a assinatura da página cujo propósito é o repasse.

    ⚠️ O corpo longo do resto do arquivo é omitido DE PROPÓSITO aqui. Uma página
    com 1.200 palavras e doze botões não é ponte — é uma página com muitos CTAs.
    O que a regra descreve é a página que não entrega nada por si.
    """
    ponte = "".join(
        f'<div class="wp-block-button"><a class="wp-block-button__link" href="/ir-{i}">Continuar</a></div>'
        for i in range(12)
    )
    pagina = PaginaObservada(
        url="https://exemplo.com.br/r/pagina/",
        html=f"<html><body><h1>Continue</h1><p>Clique para seguir.</p>{ponte}{RODAPE}</body></html>",
        cnpj_esperado=CNPJ,
    )
    achados = {
        a.codigo
        for a in avaliar(
            pagina, PapelDestino.PAID_DESTINATION, PontoDePortao.ARTEFATO_DE_GERACAO
        ).bloqueios
    }
    assert "PAGINA_PONTE" in achados or "CONTEUDO_ORIGINAL_INSUFICIENTE" in achados


def test_cp29b_pagina_longa_com_muitos_ctas_nao_e_ponte():
    """O simétrico: doze botões numa página de 1.200 palavras é design, não ponte.

    Sem esta prova a regra viraria "toda página com CTA reprova", e a operação
    aprenderia a ignorá-la.
    """
    ponte = "".join(
        f'<div class="wp-block-button"><a class="wp-block-button__link" href="/ir-{i}">Continuar</a></div>'
        for i in range(12)
    )
    achados = pago(montar(ponte, h1="Guia completo"))
    assert "PAGINA_PONTE" not in achados


def test_cp30_pagina_util_coerente_e_interna_alcanca_verde():
    """Sem esta prova, todo o resto é um portão que só sabe dizer não."""
    av = elegibilidade_de_destino_de_campanha(montar('<p><a href="/sobre">Quem somos</a></p>'))
    assert av.bloqueios == [], [a.codigo for a in av.bloqueios]
    assert av.desconhecidos == [], av.desconhecidos
    assert av.paid_destination_ready is True


# ═══════════════════════════════════════════════════════════════════════════
# O RECIBO, DE PONTA A PONTA
# ═══════════════════════════════════════════════════════════════════════════


def test_o_recibo_emitido_e_lido_de_volta_pelo_proprio_portao():
    """⚠️ PRODUTOR E CONSUMIDOR PODEM DIVERGIR EM SILÊNCIO.

    `varrer_recibo` lê `policy_contract_version` e `observed_at_epoch`; se
    `emitir_recibo` não os escrevesse, todo recibo real seria classificado como
    desatualizado — um vermelho permanente que nenhuma página conseguiria
    limpar, e que só aparece quando os dois lados se encontram.

    Esta prova é o encontro.
    """
    html = f"<html><body><h1>Guia</h1><p>{CORPO}</p>{RODAPE}</body></html>"
    pre = avaliar(
        PaginaObservada(url="https://exemplo.com.br/r/x/", html=html, cnpj_esperado=CNPJ),
        PapelDestino.PAID_DESTINATION,
        PontoDePortao.PRE_PUBLICACAO_WORDPRESS,
    )
    recibo = emitir_recibo(
        pre,
        hash_do_conteudo=SHA,
        impressao_do_conteudo=impressao_canonica(html),
        carimbo_epoch=AGORA - 60,
        janela_de_frescor_s=JANELA_DE_FRESCOR_PADRAO_S,
        papel_declarado="LP",
    )
    assert recibo["paid_destination_ready"] is True
    assert recibo["policy_contract_version"] == POLICY_CONTRACT_VERSION
    assert recibo["readiness"]["google_approval"] == "unknown"
    assert recibo["evidence_completeness"]["ratio"].endswith("/10")

    no_ar = PaginaObservada(
        url="https://exemplo.com.br/r/x/",
        html=html,
        status_http=200,
        saltos_redirecionamento=[],
        variantes_sha256={"user": SHA, "googlebot": SHA},
        sha256_observado=SHA,
        impressao_aprovada=recibo["content_fingerprint"],
        cnpj_esperado=CNPJ,
        recibo_de_aprovacao=recibo,
        avaliado_em_epoch=AGORA,
    )
    campanha = elegibilidade_de_destino_de_campanha(no_ar)
    assert campanha.paid_destination_ready is True, campanha.motivos


def test_o_recibo_e_resolvido_pela_url_canonica_com_gclid():
    """Um destino do Google chega com `gclid` grudado.

    Um recibo só encontrável com a query exata é um recibo que nunca é
    encontrado — e não encontrar reprova, então a campanha morreria sempre.
    """
    publicadas = [
        anexar_recibo(
            {"url_wp": "https://exemplo.com.br/r/x/", "role": "LP"},
            recibo_valido(),
        )
    ]
    assert recibo_da_url(publicadas, "https://exemplo.com.br/r/x/?gclid=Cj0KC") is not None
    assert recibo_da_url(publicadas, "https://exemplo.com.br/r/outra/") is None
    assert url_canonica("https://Exemplo.com.BR/r/x/?a=1#topo") == "https://exemplo.com.br/r/x"


def test_o_recibo_nao_afirma_aprovacao_do_google():
    """A afirmação mais importante do artefato é a que ele SE RECUSA a fazer."""
    av = avaliar(montar(), PapelDestino.PAID_DESTINATION, PontoDePortao.ARTEFATO_DE_GERACAO)
    recibo = emitir_recibo(av, hash_do_conteudo=SHA)
    assert recibo["readiness"]["google_approval"] == "unknown"
    assert "não lê a decisão do revisor" in recibo["readiness"]["google_approval_note"]
    assert recibo["external_mutation"] == {
        "google_ads_mutate": False,
        "wordpress_write": False,
        "appeal_submitted": False,
        "deploy": False,
    }
