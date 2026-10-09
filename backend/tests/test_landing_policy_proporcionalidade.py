"""Portão de destino proporcional: o que o Google exige × o que a casa decidiu.

Revisão de 09/10/2026, sobre a página real https://creditoup.com.br/r/guia-cursos-senac/.
Das 12 "alegações financeiras" que a reprovavam, 6 eram o NOME do site
("O Crédito Up é um guia independente…") e 6 eram valores da regra de renda da
gratuidade ("R$ 3.242 por pessoa"). Nenhuma era preço, taxa ou oferta — o que a
política de preços desonestos cobre. E a página já dizia o que não é ("guia
independente, sem vínculo"; "não faz inscrição"), numa redação que o padrão de
divulgação não reconhecia.

Os testes provam as duas correções E o que NÃO pode afrouxar: oferta financeira
de verdade sem divulgação continua reprovando.
"""
from __future__ import annotations

from app.landing_policy.contrato import (
    FUNDAMENTO_GOOGLE,
    FUNDAMENTO_INTERNO,
    FUNDAMENTO_INTERPRETACAO,
    fundamento,
)
from app.landing_policy.portao import elegibilidade_de_destino_de_campanha
from app.landing_policy.varredura import PaginaObservada, varrer_alegacoes

URL = "https://creditoup.com.br/r/guia-cursos-senac/"
FIN = "ALEGACAO_FINANCEIRA_SEM_DIVULGACAO"


def _pagina(corpo: str, url: str = URL) -> PaginaObservada:
    return PaginaObservada(url=url, html=f"<html><body><main>{corpo}</main></body></html>",
                           status_http=200)


def _codigos(corpo: str, url: str = URL) -> set[str]:
    return {a.codigo for a in varrer_alegacoes(_pagina(corpo, url)).achados}


# ── o que a página real escreve: tem de passar ────────────────────────────

TRECHO_REAL = (
    "<p>Portal editorial independente. O Crédito Up publica guias informativos, "
    "sem vínculo com órgãos públicos.</p>"
    "<p>O limite é de até 2 salários mínimos por pessoa: R$ 3.242 em 2026 "
    "(2 × R$ 1.621). Exemplo: 4 pessoas com R$ 5.000 somados dão R$ 1.250 por pessoa.</p>"
    "<p>O Crédito Up é o Senac? Não. O Crédito Up é um site independente de guias "
    "e não faz inscrição nem recebe documentos.</p>"
)


def teste_pagina_real_da_senac_nao_tem_alegacao_financeira_sem_divulgacao():
    assert FIN not in _codigos(TRECHO_REAL)


def teste_o_nome_do_site_nao_e_alegacao_financeira():
    """Sem valor nenhum e sem divulgação: só o nome do operador não dispara."""
    assert FIN not in _codigos("<p>O Crédito Up é um portal de guias.</p>")


def teste_guia_independente_conta_como_divulgacao():
    corpo = "<p>Guia independente, sem vínculo com o órgão. O benefício é de R$ 1.412.</p>"
    assert FIN not in _codigos(corpo)


# ── o que NÃO pode afrouxar ───────────────────────────────────────────────

def teste_oferta_de_credito_sem_divulgacao_continua_reprovando():
    corpo = "<p>Crédito consignado com juros de 1,5% ao mês. Parcela a partir de R$ 89,90.</p>"
    assert FIN in _codigos(corpo)


def teste_credito_que_nao_e_o_nome_do_site_continua_contando():
    """No domínio creditoup.com.br, 'crédito pessoal' não é o nome do site."""
    corpo = "<p>O Crédito Up indica crédito pessoal com aprovação na hora.</p>"
    assert FIN in _codigos(corpo)


def teste_em_outro_dominio_credito_up_nao_e_marca():
    """A exclusão vale para o operador da página, não para a palavra."""
    assert FIN in _codigos("<p>O Crédito Up libera R$ 500 hoje.</p>",
                           url="https://outro-portal.com.br/x/")


# ── fundamento declarado em cada achado ──────────────────────────────────

def teste_cada_exigencia_que_reprovou_a_senac_tem_fundamento_declarado():
    assert fundamento("IDENTIDADE_OPERADOR_AUSENTE") == FUNDAMENTO_INTERPRETACAO
    assert fundamento("IDENTIDADE_CONTATO_AUSENTE") == FUNDAMENTO_INTERPRETACAO
    assert fundamento("DIVULGACAO_DE_MONETIZACAO_AUSENTE") == FUNDAMENTO_INTERPRETACAO
    assert fundamento("LINK_EXTERNO_NAO_CLASSIFICADO") == FUNDAMENTO_INTERPRETACAO
    assert fundamento("SCRIPT_TERCEIRO_NAO_DECLARADO") == FUNDAMENTO_INTERPRETACAO
    assert fundamento("LINK_EXTERNO_NO_CHROME") == FUNDAMENTO_INTERNO
    assert fundamento("RECIBO_DE_APROVACAO_AUSENTE") == FUNDAMENTO_INTERNO
    assert fundamento(FIN) == FUNDAMENTO_GOOGLE
    assert fundamento("CODIGO_QUE_NAO_EXISTE") == "nao_classificado"


def teste_o_fundamento_viaja_no_achado_serializado():
    av = elegibilidade_de_destino_de_campanha(_pagina("<p>Sem rodapé nenhum.</p>"))
    por_codigo = {a.codigo: a.para_json() for a in av.bloqueios}
    assert por_codigo["IDENTIDADE_OPERADOR_AUSENTE"]["basis"] == FUNDAMENTO_INTERPRETACAO
    # A severidade não mudou: no destino pago, a decisão da espinha v2 continua.
    assert por_codigo["IDENTIDADE_OPERADOR_AUSENTE"]["severity"] == "blocker"


# ── revisão de 09/10/2026: piso de palavras e links para o próprio site ──

def teste_piso_de_palavras_e_declarado_como_regua_da_casa():
    assert fundamento("CONTEUDO_ORIGINAL_INSUFICIENTE") == FUNDAMENTO_INTERPRETACAO
    av = elegibilidade_de_destino_de_campanha(_pagina("<p>Texto curto.</p>"))
    (a,) = [x for x in av.bloqueios if x.codigo == "CONTEUDO_ORIGINAL_INSUFICIENTE"]
    assert "piso INTERNO" in a.mensagem and "sem número" in a.mensagem


def teste_link_para_post_do_proprio_site_nao_e_marca_governamental():
    """Título de post nosso com 'Caixa Tem' não finge levar ao órgão."""
    corpo = ('<p><a href="https://creditoup.com.br/saldo-bloqueado-caixa-tem/">'
             'Saldo bloqueado no Caixa Tem: como resolver</a></p>'
             '<p><a href="/curso-gratuito/">Curso gratuito do governo com certificado</a></p>')
    av = elegibilidade_de_destino_de_campanha(_pagina(corpo))
    assert "MARCA_GOVERNAMENTAL_COM_DESTINO_DIVERGENTE" not in {a.codigo for a in av.bloqueios}


def teste_link_para_terceiro_com_marca_publica_continua_marcado():
    corpo = '<p><a href="https://consulta-beneficio.example.com/">Consulta oficial Caixa</a></p>'
    av = elegibilidade_de_destino_de_campanha(_pagina(corpo))
    assert "MARCA_GOVERNAMENTAL_COM_DESTINO_DIVERGENTE" in {a.codigo for a in av.bloqueios}
