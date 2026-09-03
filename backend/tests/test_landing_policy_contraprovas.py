"""CONTRAPROVAS VERMELHAS A–X — escritas para o portão FALHAR, e só depois passar.

## O que é uma contraprova vermelha aqui

Cada teste abaixo monta uma página que um humano razoável olharia e diria "isso
não pode receber clique comprado", e exige que o portão diga o mesmo — pelo
CÓDIGO certo, não por acidente de outro achado. Quatro delas (J, N, P-limpa, X2)
são o simétrico: cenários legítimos que um portão apressado reprovaria, e que
precisam passar. Portão que só sabe reprovar é desligado pela operação na
primeira semana, e aí não protege nada.

## Sobre a rotulagem A–X

O briefing desta missão enumera contraprovas A–X literalmente. As
provas abaixo mantêm tanto a cobertura por requisito quanto a nomenclatura explícita do incidente — identidade, classes de link,
formulário e dado sensível, alegação financeira e divulgação, serviço
governamental, originalidade/ponte/congruência, e redirecionamento/cloaking/
deriva. A correspondência requisito → letra do brief está em `GATES.md`.

Todas rodam sobre HTML sintético: nenhuma toca a rede, nenhuma lê conta do
Google, nenhuma escreve em site nenhum.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from app.landing_policy import (
    PaginaObservada,
    PapelDestino,
    PontoDePortao,
    avaliar,
    elegibilidade_de_destino_de_campanha,
)

CNPJ = "42.724.548/0001-24"

#: O rodapé que uma página CORRETA tem. Ele entra em quase toda contraprova para
#: que o único defeito da página seja o que aquela letra injeta — senão a prova
#: passaria por causa de um achado vizinho e não provaria nada sobre a regra.
RODAPE = """
<p>Os conteúdos aqui publicados são de caráter informativo e não possuem vínculo,
parceria ou qualquer ligação com órgãos públicos ou entidades governamentais.</p>
<p>O site é financiado por blocos de anúncios em parceria com o Google Adsense.</p>
<p>Projeto da Volc Negocios Digitais 42.724.548/0001-24.</p>
<a href="/sobre">Sobre</a> <a href="/contato">Contato</a>
<a href="/politica-de-privacidade">Política de Privacidade</a>
"""

CORPO = " ".join(
    ["O texto explica as regras vigentes e onde o leitor confere cada informação."] * 110
)

SHA = "a" * 64


def montar(miolo: str = "", *, rodape: str = RODAPE, corpo: str = CORPO, **kwargs):
    padrao = {
        "url": "https://exemplo.com.br/r/pagina/",
        "status_http": 200,
        "saltos_redirecionamento": [],
        "variantes_sha256": {"user": SHA, "googlebot": SHA},
        "sha256_observado": SHA,
        "sha256_aprovado": SHA,
        "cnpj_esperado": CNPJ,
    }
    padrao.update(kwargs)
    html = f"<html><body><h1>Guia</h1><p>{corpo}</p>{miolo}{rodape}</body></html>"
    return PaginaObservada(html=html, **padrao)


def bloqueios(pagina) -> set[str]:
    return {a.codigo for a in elegibilidade_de_destino_de_campanha(pagina).bloqueios}


def tudo(pagina) -> set[str]:
    av = elegibilidade_de_destino_de_campanha(pagina)
    return {a.codigo for a in av.bloqueios + av.riscos + av.observacoes}


# ── identidade ─────────────────────────────────────────────────────────────


def test_cp_a_destino_pago_sem_identidade_de_operador():
    assert "IDENTIDADE_OPERADOR_AUSENTE" in bloqueios(montar(rodape=""))


def test_cp_b_cnpj_da_pagina_diverge_do_cnpj_do_operador():
    trocado = RODAPE.replace(CNPJ, "11.222.333/0001-44")
    assert "IDENTIDADE_CNPJ_DIVERGENTE" in bloqueios(montar(rodape=trocado))


def test_cp_c_credencial_inventada_nao_passa():
    miolo = "<p>Somos licenciados pelo Banco Central para intermediar o benefício.</p>"
    assert "IDENTIDADE_CREDENCIAL_NAO_COMPROVADA" in bloqueios(montar(miolo))


def test_cp_d_marca_de_terceiro_apresentada_como_parceira_sem_lastro():
    miolo = "<p>Basta autorizar um banco parceiro, como o Banco Bmg ou o Santander.</p>"
    achados = bloqueios(montar(miolo))
    assert "MARCA_TERCEIRA_SEM_LASTRO" in achados


# ── governo e afiliação ────────────────────────────────────────────────────


def test_cp_e_orgao_publico_citado_sem_aviso_de_nao_vinculo():
    sem_aviso = RODAPE.replace(
        "não possuem vínculo,\nparceria ou qualquer ligação com órgãos públicos ou entidades governamentais.",
        "trazem informação.",
    )
    pagina = montar(
        "<p>A Caixa Econômica Federal administra o FGTS e o benefício.</p>", rodape=sem_aviso
    )
    achados = bloqueios(pagina)
    assert "AVISO_NAO_OFICIAL_AUSENTE" in achados
    assert "AFILIACAO_GOVERNAMENTAL_IMPLICITA" in achados


def test_cp_f_link_de_governo_com_ancora_de_valor():
    miolo = '<p>A multa é de <a href="https://www.caixa.gov.br/"><strong>40 %</strong></a>.</p>'
    assert "LINK_GOVERNO_COM_ANCORA_DE_VALOR" in bloqueios(montar(miolo))


def test_cp_g_botao_principal_apontando_para_site_de_governo():
    miolo = (
        '<div class="wp-block-button">'
        '<a class="wp-block-button__link" href="https://www.gov.br/">Acessar o benefício</a>'
        "</div>"
    )
    assert "AFILIACAO_GOVERNAMENTAL_IMPLICITA" in bloqueios(montar(miolo))


def test_cp_h_oferta_de_documento_de_governo_restrito():
    miolo = "<p>Veja como emitir a sua carteira de identidade nacional pelo nosso passo a passo.</p>"
    assert "SERVICO_GOVERNAMENTAL_RESTRITO" in bloqueios(montar(miolo))


# ── classes de link ────────────────────────────────────────────────────────


def test_cp_i_host_externo_sem_lastro_nao_e_classificado():
    miolo = '<p>Veja <a href="https://credito-liberado-rapido.example/x">o simulador oficial</a>.</p>'
    assert "LINK_EXTERNO_NAO_CLASSIFICADO" in bloqueios(montar(miolo))


def test_cp_j_host_declarado_pela_evidencia_passa():
    """A autorização vem da EVIDÊNCIA daquela página, não de allowlist estática.

    O simétrico da contraprova I: com lastro declarado, o mesmo link passa. Sem
    esta, a regra I seria só "todo link externo reprova", que trava a operação.
    """
    miolo = '<p>Veja a <a href="https://meutudo.com.br/fgts">tabela publicada</a>.</p>'
    pagina = montar(miolo, hosts_declarados=("meutudo.com.br",))
    assert "LINK_EXTERNO_NAO_CLASSIFICADO" not in bloqueios(pagina)


def test_cp_k_botao_para_terceiro_nao_autorizado():
    miolo = (
        '<div class="wp-block-button">'
        '<a class="wp-block-button__link" href="https://parceiro-nao-declarado.example/lp">'
        "Simular agora</a></div>"
    )
    achados = bloqueios(montar(miolo))
    assert "BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO" in achados
    assert "LINK_EXTERNO_NAO_CLASSIFICADO" in achados


# ── formulário e dado sensível ─────────────────────────────────────────────


def test_cp_l_campo_de_senha_e_a_assinatura_de_phishing():
    miolo = '<form action="/entrar"><input type="password" name="senha"></form>'
    achados = bloqueios(montar(miolo))
    assert "CAMPO_CREDENCIAL_OBSERVADO" in achados
    assert "FORMULARIO_DADO_SENSIVEL" in achados


def test_cp_m_coleta_de_cpf_no_destino_pago():
    miolo = '<form action="/consulta"><input type="text" name="cpf" placeholder="Seu CPF"></form>'
    assert "FORMULARIO_DADO_SENSIVEL" in bloqueios(montar(miolo))


def test_cp_n_busca_do_wordpress_nao_e_coleta_de_dado():
    """O simétrico de L/M: sem esta exceção todo WordPress vira 'formulário de coleta'."""
    miolo = (
        '<form role="search" method="get" action="https://exemplo.com.br">'
        '<input type="text" name="s" placeholder="Buscar no site"></form>'
    )
    assert "FORMULARIO_DADO_SENSIVEL" not in tudo(montar(miolo))


# ── alegações e divulgações ────────────────────────────────────────────────


def test_cp_o_promessa_de_resultado_improvavel():
    miolo = (
        "<p>Saque-Aniversário FGTS liberado pelo governo: a liberação do dinheiro "
        "costuma ocorrer em poucos minutos, sem consulta ao SPC.</p>"
    )
    assert "ALEGACAO_DE_RESULTADO_IMPROVAVEL" in bloqueios(montar(miolo))


def test_cp_p_alegacao_financeira_sem_divulgacao_reprova_e_com_divulgacao_passa():
    numeros = "<p>A alíquota vai de 5% a 50% e a parcela fixa chega a R$ 2.900,00.</p>"
    sem = RODAPE.replace("de caráter informativo e ", "")
    assert "ALEGACAO_FINANCEIRA_SEM_DIVULGACAO" in bloqueios(montar(numeros, rodape=sem))
    com = sem + (
        "<p>Valores meramente ilustrativos, sujeitos às regras vigentes; consulte o canal oficial.</p>"
    )
    assert "ALEGACAO_FINANCEIRA_SEM_DIVULGACAO" not in bloqueios(montar(numeros, rodape=com))


def test_cp_q_valor_monetario_malformado_vira_risco_nao_silencio():
    av = elegibilidade_de_destino_de_campanha(
        montar("<p>A parcela fixa chega a 2900.00 R$ por ano.</p>")
    )
    assert "VALOR_MONETARIO_MALFORMADO" in {a.codigo for a in av.riscos}


# ── conteúdo, ponte e congruência ──────────────────────────────────────────


def test_cp_r_conteudo_original_insuficiente():
    assert "CONTEUDO_ORIGINAL_INSUFICIENTE" in bloqueios(montar(corpo="Texto muito curto."))


def test_cp_s_pagina_ponte_e_mais_botao_do_que_texto():
    botoes = "".join(
        f'<div class="wp-block-button"><a class="wp-block-button__link" '
        f'href="/rec/destino-{i}/">Ver o destino {i}</a></div>'
        for i in range(12)
    )
    pagina = montar(botoes, corpo=" ".join(["palavra"] * 300))
    assert "PAGINA_PONTE" in bloqueios(pagina)


def test_cp_t_destino_incongruente_com_a_promessa_do_anuncio():
    pagina = montar(promessa_do_anuncio="maquininha de cartão com menor taxa para MEI")
    assert "DESTINO_INCONGRUENTE_COM_ANUNCIO" in bloqueios(pagina)


# ── redirecionamento, cloaking e deriva ────────────────────────────────────


def test_cp_u_redirecionamento_para_fora_do_dominio():
    pagina = montar(
        saltos_redirecionamento=[
            {"from": "https://exemplo.com.br/r/pagina/", "status": 302,
             "to": "https://outro-dominio.example/oferta"}
        ]
    )
    achados = bloqueios(pagina)
    assert "REDIRECIONAMENTO_CROSS_DOMAIN" in achados


def test_cp_v_html_diferente_para_rastreador_e_para_usuario():
    pagina = montar(variantes_sha256={"user": "a" * 64, "googlebot": "b" * 64})
    assert "DIVERGENCIA_RASTREADOR_USUARIO" in bloqueios(pagina)


def test_cp_v_desktop_diferente_de_mobile_nao_e_cloaking():
    """O simétrico de V, e a acusação mais cara de errar.

    Medido na preservação real: desktop e mobile de `/r/fgts-saque-aniversario/`
    diferem em 27 bytes (um token rotativo de push), enquanto o Googlebot devolve
    HTML byte a byte igual ao do desktop. Chamar isso de cloaking num pacote de
    apelação seria uma admissão falsa — o oposto do que a evidência diz.
    """
    pagina = montar(
        variantes_sha256={
            "common_desktop": "a" * 64,
            "common_mobile": "b" * 64,
            "googlebot": "a" * 64,
        }
    )
    assert "DIVERGENCIA_RASTREADOR_USUARIO" not in tudo(pagina)


def test_cp_v_sem_variante_de_rastreador_o_cloaking_e_desconhecido_e_nao_limpo():
    av = elegibilidade_de_destino_de_campanha(
        montar(variantes_sha256={"common_desktop": "a" * 64, "common_mobile": "b" * 64})
    )
    assert "DIVERGENCIA_RASTREADOR_USUARIO" not in {a.codigo for a in av.bloqueios}
    assert any(d["verificacao"] == "redirect_and_cloaking" for d in av.desconhecidos)
    assert av.paid_destination_ready is False


def test_cp_w_deriva_do_que_foi_aprovado():
    pagina = montar(sha256_observado="c" * 64, sha256_aprovado="d" * 64)
    assert "DERIVA_AO_VIVO" in bloqueios(pagina)


def test_cp_x_conteudo_misto_reprova_e_namespace_svg_nao_conta():
    misto = '<img src="http://cdn-inseguro.example/banner.png">'
    assert "CONTEUDO_MISTO" in bloqueios(montar(misto))
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
    assert "CONTEUDO_MISTO" not in tudo(montar(svg))


# ── a fronteira do papel, atravessando as contraprovas ─────────────────────


@pytest.mark.parametrize(
    "miolo,codigo",
    [
        ('<form><input type="password" name="senha"></form>', "CAMPO_CREDENCIAL_OBSERVADO"),
        ('<p>A multa é <a href="https://www.gov.br/"><strong>40 %</strong></a>.</p>',
         "LINK_GOVERNO_COM_ANCORA_DE_VALOR"),
    ],
)
def test_o_mesmo_defeito_e_registrado_no_artigo_organico_sem_reprovar(miolo, codigo):
    """O achado não some no papel frouxo — ele muda de peso.

    Perder o achado seria pior que reprovar: a operação deixaria de saber que o
    defeito existe naquela página, e ele viajaria intacto para o dia em que
    aquela URL virasse destino de campanha.
    """
    pagina = montar(miolo)
    organico = avaliar(pagina, PapelDestino.ORGANIC_ARTICLE, PontoDePortao.ARTEFATO_DE_GERACAO)
    registrados = {a.codigo for a in organico.bloqueios + organico.riscos + organico.observacoes}
    assert codigo in registrados
    assert codigo not in {a.codigo for a in organico.bloqueios}
    assert codigo in bloqueios(pagina)


# ── checklist literal A–X do briefing ───────────────────────────────────────
# Estes testes mantêm a nomenclatura do incidente. Alguns cenários também são
# cobertos acima por requisito técnico; aqui a prova é que a lista EXATA do brief
# continua endereçada e não vira um mapeamento inventado pelo executor.


def test_brief_a_link_caixa_gov_rotulado_como_cta_oficial():
    miolo = '<div class="wp-block-button"><a href="https://www.caixa.gov.br/">Acessar CTA oficial da Caixa</a></div>'
    assert "AFILIACAO_GOVERNAMENTAL_IMPLICITA" in bloqueios(montar(miolo))


def test_brief_b_link_visivel_caixa_apontando_para_outro_dominio():
    miolo = '<p><a href="https://captura.example/login-caixa">Caixa</a></p>'
    achados = bloqueios(montar(miolo))
    assert "LINK_EXTERNO_NAO_CLASSIFICADO" in achados
    assert "MARCA_GOVERNAMENTAL_COM_DESTINO_DIVERGENTE" in achados


def test_brief_c_cta_passando_por_redirect_desconhecido():
    pagina = montar(
        '<div class="wp-block-button"><a href="/go/oferta">Simular agora</a></div>',
        saltos_redirecionamento=[{"from":"https://exemplo.com.br/r/pagina/","status":302,"to":"https://tracker.example/out"}],
    )
    assert "REDIRECIONAMENTO_CROSS_DOMAIN" in bloqueios(pagina)


def test_brief_d_identidade_do_operador_ausente():
    assert "IDENTIDADE_OPERADOR_AUSENTE" in bloqueios(montar(rodape=""))


def test_brief_e_pagina_sugerindo_ser_oficial_sem_comprovacao():
    miolo = "<p>Portal oficial para ativar o benefício do governo federal e consultar FGTS.</p>"
    assert "AFILIACAO_GOVERNAMENTAL_IMPLICITA" in bloqueios(montar(miolo, rodape=RODAPE.replace('não possuem vínculo,\nparceria ou qualquer ligação com órgãos públicos ou entidades governamentais.','publica guias.')))


def test_brief_f_logo_nome_governamental_usado_como_identidade_propria():
    miolo = '<header><img src="/logo-caixa.png" alt="Caixa"><h1>Caixa FGTS</h1></header>'
    achados = bloqueios(montar(miolo, rodape=RODAPE.replace('não possuem vínculo,\nparceria ou qualquer ligação com órgãos públicos ou entidades governamentais.','publica guias.')))
    assert "AFILIACAO_GOVERNAMENTAL_IMPLICITA" in achados


def test_brief_g_formulario_pedindo_senha_govbr_ou_caixa():
    miolo = '<form><input type="password" name="senha_gov_br" placeholder="Senha gov.br"></form>'
    assert "CAMPO_CREDENCIAL_OBSERVADO" in bloqueios(montar(miolo))


def test_brief_h_formulario_pedindo_otp():
    miolo = '<form><input name="token" placeholder="Código de autenticação OTP"></form>'
    # O contrato trata OTP/token como credencial sensível via texto do campo.
    achados = tudo(montar(miolo))
    assert "FORMULARIO_DADO_SENSIVEL" in achados or "CAMPO_CREDENCIAL_OBSERVADO" in achados


def test_brief_i_cpf_sem_disclosure_finalidade():
    miolo = '<form><input name="cpf" placeholder="CPF"></form>'
    assert "FORMULARIO_DADO_SENSIVEL" in bloqueios(montar(miolo))


def test_brief_j_lp_financeira_sem_disclosures_aplicaveis():
    sem = RODAPE.replace("de caráter informativo e ", "")
    assert "ALEGACAO_FINANCEIRA_SEM_DIVULGACAO" in bloqueios(montar("<p>Empréstimo com taxa de juros baixa.</p>", rodape=sem))


def test_brief_k_promessa_de_aprovacao_ou_resultado_garantido():
    assert "ALEGACAO_DE_RESULTADO_IMPROVAVEL" in bloqueios(montar("<p>Aprovação garantida em poucos minutos.</p>"))


def test_brief_l_bridge_page_com_pouco_conteudo_original():
    botoes = "".join(
        f'<div class="wp-block-button"><a class="wp-block-button__link" href="/rec/{i}">Continuar</a></div>'
        for i in range(8)
    )
    achados = bloqueios(montar(botoes, corpo=" ".join(["curto"] * 100)))
    assert "CONTEUDO_ORIGINAL_INSUFICIENTE" in achados
    assert "PAGINA_PONTE" in achados


def test_brief_m_pagina_gerada_diferente_para_googlebot():
    assert "DIVERGENCIA_RASTREADOR_USUARIO" in bloqueios(montar(variantes_sha256={"user":"a"*64,"googlebot":"b"*64}))


def test_brief_n_javascript_redirecionando_apos_carregamento():
    pagina = montar('<script>window.location="https://fora.example"</script>')
    assert "SCRIPT_REDIRECIONA_CLIENT_SIDE" in tudo(pagina)


def test_brief_o_dominio_externo_desconhecido():
    assert "LINK_EXTERNO_NAO_CLASSIFICADO" in bloqueios(montar('<a href="https://desconhecido.example/x">Saiba mais</a>'))


def test_brief_p_external_source_link_editorial_corretamente_rotulado():
    miolo = '<p>Fonte oficial de referência: <a href="https://www.caixa.gov.br/beneficios-trabalhador/fgts">site da Caixa</a>.</p>'
    assert "LINK_GOVERNO_COM_ANCORA_DE_VALOR" not in bloqueios(montar(miolo))


def test_brief_q_link_interno_correto():
    assert "LINK_EXTERNO_NAO_CLASSIFICADO" not in tudo(montar('<a href="/sobre">Sobre</a>'))


def test_brief_r_editorial_permite_referencia_que_paid_restringe():
    miolo = '<p>A multa é de <a href="https://www.caixa.gov.br/"><strong>40 %</strong></a>.</p>'
    pago = avaliar(montar(miolo), PapelDestino.PAID_DESTINATION, PontoDePortao.ELEGIBILIDADE_DESTINO_CAMPANHA)
    editorial = avaliar(montar(miolo), PapelDestino.EDITORIAL_SOLUTION, PontoDePortao.ARTEFATO_DE_GERACAO)
    assert "LINK_GOVERNO_COM_ANCORA_DE_VALOR" in {a.codigo for a in pago.bloqueios}
    assert "LINK_GOVERNO_COM_ANCORA_DE_VALOR" not in {a.codigo for a in editorial.bloqueios}


def test_brief_s_rota_r_publicada_sem_receipt_de_politica():
    av = elegibilidade_de_destino_de_campanha(montar(sha256_aprovado=None))
    assert av.paid_destination_ready is False
    assert any(d["verificacao"] == "live_drift" for d in av.desconhecidos)


def test_brief_t_campanha_usando_lp_cujo_hash_mudou_apos_aprovacao():
    assert "DERIVA_AO_VIVO" in bloqueios(montar(sha256_aprovado="b"*64, sha256_observado="a"*64))


def test_brief_u_pagina_comprometida_ou_script_externo_nao_allowlisted():
    assert "SCRIPT_TERCEIRO_NAO_DECLARADO" in bloqueios(montar('<script src="https://cdn-estranho.example/x.js"></script>'))


def test_brief_v_erro_do_scanner_tratado_como_bloqueio(monkeypatch):
    from app.landing_policy import portao
    def quebra(_pagina):
        raise RuntimeError("scanner caiu")
    monkeypatch.setitem(portao.VARREDURAS, "identity", quebra)
    av = elegibilidade_de_destino_de_campanha(montar())
    assert av.paid_destination_ready is False
    assert any(d["status"] == "failed" for d in av.desconhecidos)


def test_brief_w_unknown_nao_vira_pronto_no_frontend_ou_api():
    av = elegibilidade_de_destino_de_campanha(montar(saltos_redirecionamento=None, variantes_sha256={}))
    assert av.paid_destination_ready is False
    assert av.desconhecidos


def test_brief_x_appeal_package_nao_afirma_causa_sem_evidencia():
    texto = (Path(__file__).resolve().parents[2] / "docs" / "closure" / "hermes-redator-google-ads-policy-incident-v1" / "APPEAL-DRAFT.md")
    if not texto.exists():
        pytest.skip("closure package not present in isolated test run")
    corpo = texto.read_text(encoding="utf-8")
    proibidos = ["causa confirmada", "confirmed cause", "a causa foi phishing"]
    assert all(p not in corpo.lower() for p in proibidos)
    assert "não enviado" in corpo.lower() or "not submitted" in corpo.lower()
