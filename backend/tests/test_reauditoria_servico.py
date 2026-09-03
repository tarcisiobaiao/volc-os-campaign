"""A REAUDITORIA AO VIVO — o serviço, as duas rotas e a gravação.

## O que esta suíte mede

O ato que emite o recibo de escopo `live`, que é o único que a barreira 3
aceita. Ele tem duas etapas, e a separação É o assunto: `provar` lê e não
grava; `confirmar` re-lê, re-avalia e só então devolve o recibo.

Toda leitura aqui é INJETADA. Nenhum teste toca rede, WordPress, Supabase
oficial ou disco. O `ler` de mentira também é a sentinela: ele conta as
chamadas, e é por ele que se prova que `provar` fez três leituras — e que o
`confirmar` fez outras três, em vez de confiar no que veio no corpo.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from app.landing_policy import (
    PapelDestino,
    PaginaObservada,
    PontoDePortao,
    avaliar,
    emitir_recibo,
    impressao_canonica,
)
from app.main import app
from app.redator import reauditoria as ra
from app.routers import publicacao as pub

PARAGRAFO = "<p>" + ("palavra " * 60) + "</p>"

#: Uma página limpa o bastante para o ponto de campanha não ter o que reprovar
#: além do que os testes introduzem de propósito.
HTML_LIMPO = (
    "<html><head><title>Rotina de leitura</title></head><body>"
    "<h1>Rotina de leitura</h1>"
    + "".join(f"<h2>Etapa {i}</h2>{PARAGRAFO}" for i in range(1, 12))
    + "<footer><p>Editora Exemplo Ltda - CNPJ 12.345.678/0001-90.</p>"
      "<p>Esta pagina exibe publicidade e nao possui vinculo com nenhum orgao "
      "publico.</p><p>Contato: contato@exemplo.com.br</p>"
      '<p><a href="/sobre/">Sobre</a> - <a href="/contato/">Contato</a> - '
      '<a href="/politica-de-privacidade/">Politica de Privacidade</a></p>'
      "</footer></body></html>"
)

#: O mesmo corpo com um hyperlink externo NO RODAPÉ — região de chrome. É o
#: defeito cujo dono é o TEMA/WordPress, e não o funil.
HTML_COM_LINK_NO_CHROME = HTML_LIMPO.replace(
    '<p><a href="/sobre/">',
    '<p><a href="https://parceiro-externo.com/oferta">Parceiro</a></p>'
    '<p><a href="/sobre/">',
)

#: E um hyperlink externo no CORPO, cujo dono é o FUNIL.
HTML_COM_LINK_NO_CORPO = HTML_LIMPO.replace(
    "<h2>Etapa 1</h2>",
    '<p><a href="https://parceiro-externo.com/oferta">Parceiro</a></p><h2>Etapa 1</h2>',
)

URL = "https://exemplo.com.br/r/rotina/"

#: ⚠️ O INSTANTE É O REAL, e não uma constante fixa — foi medido.
#:
#: Com um epoch cravado no passado, o recibo anterior das fixtures nasce VENCIDO
#: contra o relógio das rotas (que usam `time.time()`), e a suíte inteira passava
#: a medir `RECIBO_DE_APROVACAO_VENCIDO` em vez do que ela diz medir. A janela de
#: frescor do contrato é de 24 h; amarrar as fixtures ao mesmo relógio das rotas
#: é o que mantém as duas camadas dentro dela.
#:
#: Isto NÃO torna a suíte dependente do relógio: nenhuma asserção olha o valor.
#: O que importa é a DISTÂNCIA entre o carimbo e a avaliação, e ela é zero aqui.
AGORA = time.time()


class LeitorFalso:
    """Três leituras públicas de mentira, e o registro de quem pediu o quê.

    ⚠️ Ele é a SENTINELA da contenção: qualquer efeito externo deste módulo teria
    de passar por uma chamada de rede, e a única que existe é esta. Se o serviço
    algum dia escrever em algum lugar, não é por aqui — e os testes de rota
    abaixo fecham o outro lado, contando os `patch` no Supabase de mentira.
    """

    def __init__(self, html: str = HTML_LIMPO, status: int = 200) -> None:
        self.html = html
        self.status = status
        self.chamadas: List[Dict[str, Any]] = []
        self.explode: Exception | None = None

    def __call__(self, url: str, *, user_agent: str, timeout: int) -> Dict[str, Any]:
        self.chamadas.append({"url": url, "user_agent": user_agent, "timeout": timeout})
        if self.explode is not None:
            raise self.explode
        return {
            "status": self.status,
            "html": self.html,
            "hops": [],
            "headers": {"content-type": "text/html; charset=utf-8"},
            "sha256": hashlib.sha256(self.html.encode()).hexdigest(),
            "final_url": url,
        }


def _recibo(html: str, *, escopo: str, epoch: float = AGORA) -> Dict[str, Any]:
    """Um recibo de verdade, emitido pelo emissor de verdade.

    ⚠️ Não é um dict escrito à mão. Um recibo forjado passaria a ser a fonte da
    forma que a suíte acredita ser correta, e ela divergiria do emissor no
    primeiro campo novo — o teste continuaria verde medindo o passado.
    """
    pagina = PaginaObservada(url=URL, html=html, avaliado_em_epoch=epoch)
    avaliacao = avaliar(pagina, PapelDestino.PAID_DESTINATION,
                        PontoDePortao.PRE_PUBLICACAO_WORDPRESS)
    return emitir_recibo(
        avaliacao,
        hash_do_conteudo=hashlib.sha256(html.encode()).hexdigest(),
        impressao_do_conteudo=impressao_canonica(html),
        escopo_da_impressao=escopo,
        carimbo_epoch=epoch,
        janela_de_frescor_s=86400,
        papel_declarado="LP",
    )


@pytest.fixture()
def recibo_live() -> Dict[str, Any]:
    """O recibo `live` de uma reauditoria ANTERIOR desta mesma página.

    ⚠️ Ele é a fixture da maioria dos testes por um motivo MEDIDO, e o motivo
    está pinado em `test_a_primeira_reauditoria_nao_alcanca_elegibilidade`: sem
    um recibo `live` prévio, `live_drift` sai `unavailable`, vira desconhecido e
    reprova. Só a partir do SEGUNDO recibo o laço se sustenta.
    """
    return _recibo(HTML_LIMPO, escopo="live")


# ═══════════════════════════════════════════════════════════════════════════
# A LEITURA: três user-agents, e falha que FECHA
# ═══════════════════════════════════════════════════════════════════════════


def test_provar_le_tres_vezes_com_um_rotulo_de_rastreador(recibo_live):
    """Três leituras, e uma delas rotulada de um jeito que a varredura reconhece.

    Sem o par rastreador/humano, `varrer_redirecionamento` não consegue falar de
    cloaking e sai `unavailable` — que reprova por ausência. Com UMA humana só,
    qualquer diferença de layout por dispositivo viraria acusação de cloaking; é
    o falso positivo medido em `/r/fgts-saque-aniversario/`.
    """
    ler = LeitorFalso()
    ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=recibo_live,
                      agora=AGORA, ler=ler)

    assert len(ler.chamadas) == 3
    agentes = [c["user_agent"] for c in ler.chamadas]
    assert len(set(agentes)) == 3
    assert any("Mobile" in a for a in agentes)
    assert any("AdsBot" in a for a in agentes)

    # ⚠️ O RÓTULO, e não o user-agent, é o que a varredura inspeciona.
    from app.landing_policy.varredura import _ROTULO_DE_RASTREADOR_RE

    rotulos = [r for r, _ in ra.LEITURAS_DA_REAUDITORIA]
    assert sum(1 for r in rotulos if _ROTULO_DE_RASTREADOR_RE.search(r)) == 1


def test_status_diferente_de_200_e_recusa(recibo_live):
    """Um destino que não serve a página não é destino.

    Avaliar o corpo de um 404 diria coisas verdadeiras sobre a página errada.
    """
    ler = LeitorFalso(status=404)
    with pytest.raises(ra.ReauditoriaRecusada) as erro:
        ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=recibo_live,
                          agora=AGORA, ler=ler)
    assert "404" in str(erro.value)


def test_leitura_que_explode_vira_recusa_e_nao_silencio(recibo_live):
    """Falha traduzida em recusa, nunca engolida."""
    ler = LeitorFalso()
    ler.explode = TimeoutError("conexão caiu")
    with pytest.raises(ra.ReauditoriaRecusada) as erro:
        ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=recibo_live,
                          agora=AGORA, ler=ler)
    assert "TimeoutError" in str(erro.value)


def test_url_vazia_e_recusa():
    with pytest.raises(ra.ReauditoriaRecusada):
        ra.provar_destino(url="", papel_do_motor="LP", recibo_anterior=None,
                          agora=AGORA, ler=LeitorFalso())


# ═══════════════════════════════════════════════════════════════════════════
# O PREDICADO, e o que ele NÃO é
# ═══════════════════════════════════════════════════════════════════════════


def test_a_primeira_reauditoria_de_uma_url_consegue_ficar_verde():
    """⚠️ ESTE TESTE AFIRMAVA O CONTRÁRIO, E O CONTRÁRIO ERA O DEFEITO.

    A versão anterior pinava o laço fechado como se fosse o estado correto: com
    `recibo_anterior` de escopo `artifact` (ou nenhum), a página limpa saía com
    ZERO bloqueio e mesmo assim inelegível, porque `live_drift` e
    `approval_receipt` pediam uma aprovação anterior. O único produtor de recibo
    `live` era, portanto, inalcançável por si mesmo — a rodada tinha trocado um
    produtor AUSENTE por um INALCANÇÁVEL, e a parada operacional continuava
    exatamente onde estava.

    A correção não afrouxa nada: a reauditoria passou a avaliar no ponto
    `AUDITORIA_AO_VIVO`, onde as outras OITO verificações continuam exigidas e
    conclusivas, e onde identidade e redirecionamento não podem sair "não se
    aplica". O que deixa de ser cobrado é a única coisa que não pode existir por
    construção: a aprovação anterior a um ato de aprovação.

    E o portão não se autoaprova — quem aprova é a confirmação HUMANA vinculada
    ao mesmo hash, e o portão de CAMPANHA continua exigindo o recibo `live` que
    só este ato produz. A autoridade não sumiu: ela saiu do software e foi para
    a pessoa.
    """
    prova = ra.provar_destino(
        url=URL, papel_do_motor="LP",
        recibo_anterior=_recibo(HTML_LIMPO, escopo="artifact"),
        agora=AGORA, ler=LeitorFalso())

    assert prova.bloqueios == []
    assert prova.desconhecidos == [], prova.desconhecidos
    assert prova.elegivel is True
    assert prova.recibo_candidato["fingerprint_scope"] == "live"
    assert prova.recibo_candidato["gate_point"] == "live_audit"


def test_a_primeira_reauditoria_de_uma_url_SUJA_continua_reprovando():
    """O simétrico obrigatório: o bootstrap não é passe livre.

    Se o ponto novo apenas destravasse tudo, ele seria a porta de saída da
    política em vez do ato que a alimenta.
    """
    prova = ra.provar_destino(
        url=URL, papel_do_motor="LP", recibo_anterior=None,
        agora=AGORA, ler=LeitorFalso(html=HTML_COM_LINK_NO_CORPO))

    assert prova.elegivel is False
    assert "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO" in {b["code"] for b in prova.bloqueios}


def test_com_recibo_live_anterior_a_pagina_limpa_fica_elegivel(recibo_live):
    prova = ra.provar_destino(url=URL, papel_do_motor="LP",
                              recibo_anterior=recibo_live, agora=AGORA,
                              ler=LeitorFalso())
    assert prova.elegivel is True
    assert prova.veredito == "approved"
    assert prova.desconhecidos == []


def test_o_candidato_tem_escopo_live_e_nao_e_gravado(recibo_live):
    """O recibo sai carimbado `live` — e continua sendo só um candidato.

    ⚠️ É a única linha do sistema que carimba `live`, e ela mora atrás de uma
    confirmação humana. Se `provar` gravasse, o recibo passaria a existir como
    efeito colateral de alguém abrir uma tela.
    """
    paginas = [{"page_number": 1, "url_wp": URL, "role": "LP",
                "landing_policy_receipt": recibo_live}]
    antes = [dict(p) for p in paginas]

    prova = ra.provar_destino(url=URL, papel_do_motor="LP",
                              recibo_anterior=recibo_live, agora=AGORA,
                              ler=LeitorFalso())

    assert prova.recibo_candidato["fingerprint_scope"] == "live"
    assert prova.recibo_candidato["paid_destination_ready"] is True
    # A estrutura que a rota gravaria não foi tocada por nada aqui.
    assert paginas == antes


# ═══════════════════════════════════════════════════════════════════════════
# O DONO DE CADA BLOQUEIO
# ═══════════════════════════════════════════════════════════════════════════


def test_link_no_chrome_pertence_ao_tema_e_no_corpo_pertence_ao_funil(recibo_live):
    """Mesmo fato físico, donos diferentes — porque o conserto é em outro lugar.

    Mandar o operador ao repositório errado é como um bloqueio fica seis semanas
    aberto.
    """
    no_chrome = ra.provar_destino(url=URL, papel_do_motor="LP",
                                  recibo_anterior=recibo_live, agora=AGORA,
                                  ler=LeitorFalso(HTML_COM_LINK_NO_CHROME))
    donos = {b["code"]: b["owner"] for b in no_chrome.bloqueios}
    assert donos.get("LINK_EXTERNO_NO_CHROME") == "tema/WordPress"

    no_corpo = ra.provar_destino(url=URL, papel_do_motor="LP",
                                 recibo_anterior=recibo_live, agora=AGORA,
                                 ler=LeitorFalso(HTML_COM_LINK_NO_CORPO))
    donos = {b["code"]: b["owner"] for b in no_corpo.bloqueios}
    assert donos.get("LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO") == "funil"


def test_so_o_chrome_declarado_pelo_site_limpa_o_link_do_chrome(recibo_live):
    """⚠️ Allowlist do cliente não entra nesta função — só configuração de servidor.

    `chrome_declarado_pelo_site` é o ÚNICO parâmetro que a reauditoria repassa
    para essa decisão. Não existe caminho por onde `hosts_declarados` ou
    `adtech_declarada` cheguem aqui, e é assim de propósito: um campo de payload
    não pode ser a chave que abre a política de links.
    """
    ler = LeitorFalso(HTML_COM_LINK_NO_CHROME)
    com_procedencia = ra.provar_destino(
        url=URL, papel_do_motor="LP", recibo_anterior=recibo_live, agora=AGORA,
        chrome_declarado_pelo_site=("parceiro-externo.com",), ler=ler)
    assert not any(b["code"] == "LINK_EXTERNO_NO_CHROME"
                   for b in com_procedencia.bloqueios)


def test_inventario_de_links_nao_carrega_texto_de_ancora(recibo_live):
    """O inventário viaja para a tela e para dentro do hash. Âncora é conteúdo."""
    prova = ra.provar_destino(url=URL, papel_do_motor="LP",
                              recibo_anterior=recibo_live, agora=AGORA,
                              ler=LeitorFalso(HTML_COM_LINK_NO_CORPO))
    assert prova.inventario_de_links
    for item in prova.inventario_de_links:
        assert set(item) == {"host", "regiao", "classe", "em_botao", "oculto"}


# ═══════════════════════════════════════════════════════════════════════════
# O HASH: o que ele cobre, e o que ele NÃO cobre
# ═══════════════════════════════════════════════════════════════════════════


def test_o_hash_nao_inclui_o_relogio(recibo_live):
    """Se o carimbo entrasse no hash, nenhuma confirmação jamais concluiria."""
    a = ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=recibo_live,
                          agora=AGORA, ler=LeitorFalso())
    b = ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=recibo_live,
                          agora=AGORA + 900, ler=LeitorFalso())
    assert a.impressao_da_prova == b.impressao_da_prova
    assert len(a.impressao_da_prova) == 64


def test_o_hash_muda_quando_a_pagina_muda(recibo_live):
    a = ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=recibo_live,
                          agora=AGORA, ler=LeitorFalso())
    b = ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=recibo_live,
                          agora=AGORA, ler=LeitorFalso(HTML_COM_LINK_NO_CORPO))
    assert a.impressao_da_prova != b.impressao_da_prova


def test_o_hash_muda_quando_so_o_inventario_de_links_muda(recibo_live):
    """Um link novo que ainda não vira bloqueio TAMBÉM muda a página.

    Sem o inventário dentro do hash, a página poderia ganhar um link interno
    novo e a confirmação passaria calada sobre uma página diferente da provada.
    """
    com_link_interno = HTML_LIMPO.replace(
        "<h2>Etapa 1</h2>", '<p><a href="/outra/">Outra</a></p><h2>Etapa 1</h2>')
    a = ra.impressao_da_prova(
        canonica=URL, impressao_do_conteudo="f", versao_do_contrato="c",
        versao_das_fontes="v", veredito="approved", bloqueios=[], desconhecidos=[],
        inventario_de_links=[{"host": "a.com"}])
    b = ra.impressao_da_prova(
        canonica=URL, impressao_do_conteudo="f", versao_do_contrato="c",
        versao_das_fontes="v", veredito="approved", bloqueios=[], desconhecidos=[],
        inventario_de_links=[{"host": "a.com"}, {"host": "b.com"}])
    assert a != b
    assert com_link_interno != HTML_LIMPO  # a fixture faz o que diz


def test_a_ordem_dos_links_nao_muda_o_hash():
    """Ordenação existe para o hash: um conflito que sempre acontece ninguém lê."""
    um = [{"host": "b.com", "regiao": "corpo", "classe": "x", "em_botao": False,
           "oculto": False},
          {"host": "a.com", "regiao": "corpo", "classe": "x", "em_botao": False,
           "oculto": False}]
    assert ra.impressao_da_prova(
        canonica=URL, impressao_do_conteudo="f", versao_do_contrato="c",
        versao_das_fontes="v", veredito="approved", bloqueios=[], desconhecidos=[],
        inventario_de_links=sorted(um, key=lambda i: i["host"])
    ) == ra.impressao_da_prova(
        canonica=URL, impressao_do_conteudo="f", versao_do_contrato="c",
        versao_das_fontes="v", veredito="approved", bloqueios=[], desconhecidos=[],
        inventario_de_links=sorted(list(reversed(um)), key=lambda i: i["host"]))


def test_o_diff_diz_que_o_recibo_anterior_era_de_outro_escopo():
    """`artifact` versus `live` é a distinção que travou a barreira 3."""
    prova = ra.provar_destino(
        url=URL, papel_do_motor="LP",
        recibo_anterior=_recibo(HTML_LIMPO, escopo="artifact"),
        agora=AGORA, ler=LeitorFalso())
    diff = prova.diff_com_o_recibo_anterior
    assert diff["tinha_recibo"] is True
    assert diff["escopo_anterior"] == "artifact"
    assert diff["comparavel"] is False
    assert diff["mudou"] is False


# ═══════════════════════════════════════════════════════════════════════════
# A CONFIRMAÇÃO: não confia na prova
# ═══════════════════════════════════════════════════════════════════════════


def test_confirmar_le_de_novo_em_vez_de_aceitar_a_prova(recibo_live):
    """Seis leituras no total: a confirmação refaz a prova, não a acredita."""
    ler = LeitorFalso()
    prova = ra.provar_destino(url=URL, papel_do_motor="LP",
                              recibo_anterior=recibo_live, agora=AGORA, ler=ler)
    assert len(ler.chamadas) == 3

    recibo, nova = ra.confirmar_reauditoria(
        prova_esperada=prova.impressao_da_prova, url=URL, papel_do_motor="LP",
        recibo_anterior=recibo_live, agora=AGORA + 60, ler=ler)

    assert len(ler.chamadas) == 6
    assert recibo["fingerprint_scope"] == "live"
    assert recibo["paid_destination_ready"] is True
    assert nova.impressao_da_prova == prova.impressao_da_prova


def test_pagina_alterada_entre_a_prova_e_a_confirmacao_diverge(recibo_live):
    """O conflito explícito, com os dois hashes e a próxima ação."""
    prova = ra.provar_destino(url=URL, papel_do_motor="LP",
                              recibo_anterior=recibo_live, agora=AGORA,
                              ler=LeitorFalso())
    with pytest.raises(ra.ProvaDivergente) as erro:
        ra.confirmar_reauditoria(
            prova_esperada=prova.impressao_da_prova, url=URL, papel_do_motor="LP",
            recibo_anterior=recibo_live, agora=AGORA + 60,
            ler=LeitorFalso(HTML_COM_LINK_NO_CORPO))
    assert erro.value.esperado == prova.impressao_da_prova
    assert erro.value.observado != prova.impressao_da_prova


def test_confirmar_com_impressao_de_outra_prova_diverge(recibo_live):
    """Confirmar carregando um hash que não é o desta página é conflito."""
    with pytest.raises(ra.ProvaDivergente):
        ra.confirmar_reauditoria(
            prova_esperada="0" * 64, url=URL, papel_do_motor="LP",
            recibo_anterior=recibo_live, agora=AGORA, ler=LeitorFalso())


def test_confirmar_prova_correta_de_pagina_nao_elegivel_recusa(recibo_live):
    """⚠️ A SEGUNDA TRANCA, e por que a ordem das duas importa.

    Uma prova que já saiu reprovada tem hash ESTÁVEL — ela casa na comparação. Se
    a elegibilidade não fosse conferida depois, confirmar uma recusa gravaria um
    recibo de recusa como se fosse aprovação.
    """
    ler = LeitorFalso(HTML_COM_LINK_NO_CORPO)
    prova = ra.provar_destino(url=URL, papel_do_motor="LP",
                              recibo_anterior=recibo_live, agora=AGORA, ler=ler)
    assert prova.elegivel is False

    with pytest.raises(ra.ReauditoriaRecusada):
        ra.confirmar_reauditoria(
            prova_esperada=prova.impressao_da_prova, url=URL, papel_do_motor="LP",
            recibo_anterior=recibo_live, agora=AGORA + 60,
            ler=LeitorFalso(HTML_COM_LINK_NO_CORPO))


# ═══════════════════════════════════════════════════════════════════════════
# A GRAVAÇÃO: casada, idempotente e sem perder histórico
# ═══════════════════════════════════════════════════════════════════════════


def _paginas(recibo_anterior: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    p1 = {"page_number": 1, "url_wp": "https://exemplo.com.br/a/", "role": "PRESELL"}
    p2: Dict[str, Any] = {"page_number": 2, "url_wp": URL, "role": "LP"}
    if recibo_anterior is not None:
        p2["landing_policy_receipt"] = recibo_anterior
    return [p1, p2]


def test_aplicar_casa_pela_url_canonica_ignorando_rastreio(recibo_live):
    novas, mudou = ra.aplicar_recibo(_paginas(), URL + "?gclid=abc&utm_source=g",
                                     recibo_live)
    assert mudou is True
    assert novas[1]["landing_policy_receipt"] == recibo_live
    # A outra página não foi tocada.
    assert "landing_policy_receipt" not in novas[0]


def test_aplicar_e_idempotente(recibo_live):
    """Recibo idêntico ao que já está lá não duplica e não mente dizendo que gravou."""
    novas, _ = ra.aplicar_recibo(_paginas(), URL, recibo_live)
    de_novo, mudou = ra.aplicar_recibo(novas, URL, recibo_live)
    assert mudou is False
    assert de_novo == novas


def test_recibo_que_so_muda_o_carimbo_nao_grava_e_nao_rotaciona(recibo_live):
    """⚠️ A IDEMPOTÊNCIA É SOBRE A AFIRMAÇÃO, e foi medida.

    Dois `confirmar` seguidos NUNCA emitem recibos byte a byte iguais: o
    carimbo é o instante real da leitura. Com igualdade estrita, todo
    duplo-clique gravava, empurrava o recibo da primeira confirmação para
    `..._anterior` e apagava o recibo que de fato precedeu a reauditoria.

    O que fica é o recibo que já estava lá — e o histórico não se move.
    """
    velho = _recibo(HTML_LIMPO, escopo="artifact")
    depois_do_primeiro, _ = ra.aplicar_recibo(_paginas(velho), URL, recibo_live)
    assert depois_do_primeiro[1][ra.CHAVE_DO_RECIBO_ANTERIOR] == velho

    so_o_carimbo = {**recibo_live, "observed_at_epoch": AGORA + 5,
                    "observed_at": "2026-09-03T12:00:00+00:00"}
    depois, mudou = ra.aplicar_recibo(depois_do_primeiro, URL, so_o_carimbo)
    assert mudou is False
    assert depois[1]["landing_policy_receipt"] == recibo_live
    assert depois[1][ra.CHAVE_DO_RECIBO_ANTERIOR] == velho


def test_recibo_que_afirma_outra_coisa_rotaciona_o_historico(recibo_live):
    """Quando a AFIRMAÇÃO muda, o recibo anterior tem de ser preservado."""
    outro = _recibo(HTML_COM_LINK_NO_CORPO, escopo="live")
    assert outro["content_fingerprint"] != recibo_live["content_fingerprint"]
    novas, mudou = ra.aplicar_recibo(_paginas(recibo_live), URL, outro)
    assert mudou is True
    assert novas[1][ra.CHAVE_DO_RECIBO_ANTERIOR] == recibo_live


def test_aplicar_guarda_o_recibo_anterior(recibo_live):
    """Histórico não se perde: a auditoria pergunta contra o que valia ANTES."""
    velho = _recibo(HTML_LIMPO, escopo="artifact")
    novas, mudou = ra.aplicar_recibo(_paginas(velho), URL, recibo_live)
    assert mudou is True
    assert novas[1][ra.CHAVE_DO_RECIBO_ANTERIOR] == velho
    assert novas[1]["landing_policy_receipt"] == recibo_live


def test_aplicar_devolve_lista_nova_sem_mutar_a_original(recibo_live):
    originais = _paginas()
    copia = [dict(p) for p in originais]
    ra.aplicar_recibo(originais, URL, recibo_live)
    assert originais == copia


def test_aplicar_sem_pagina_casada_levanta(recibo_live):
    """⚠️ Silêncio aqui seria indistinguível do retry idempotente.

    Devolver `(lista, False)` faria a rota responder `gravado=false` e o operador
    ler "já estava lá" — quando na verdade o recibo não foi a lugar nenhum.
    """
    with pytest.raises(ra.ReauditoriaRecusada):
        ra.aplicar_recibo(_paginas(), "https://outro-site.com.br/x/", recibo_live)


# ═══════════════════════════════════════════════════════════════════════════
# AS ROTAS
# ═══════════════════════════════════════════════════════════════════════════


class SupaFalso:
    """O Supabase em memória, contando os `patch`.

    ⚠️ A contagem é a prova de contenção do lado da escrita: `/provar` tem de
    terminar com ZERO patches, e um `/confirmar` repetido com UM só.
    """

    enabled = True

    def __init__(self, run: Dict[str, Any]) -> None:
        self.run = run
        self.patches: List[Dict[str, Any]] = []

    async def select(self, tabela: str, params: Dict[str, Any]):
        return [self.run]

    async def patch(self, tabela: str, filtro: Dict[str, Any], valores: Dict[str, Any]):
        self.patches.append(valores)
        self.run = {**self.run, **valores}
        return [self.run]


@pytest.fixture()
def cliente() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def mundo(monkeypatch, recibo_live):
    """Um run terminado, com a página 2 no ar e um recibo `live` anterior."""
    run = {
        "id": 1, "project_id": 3, "opportunity_id": 7, "status": "done",
        "run_id": "rotina-20260903",
        "paginas_publicadas": _paginas(recibo_live),
    }
    supa = SupaFalso(run)
    ler = LeitorFalso()
    monkeypatch.setattr(pub, "_supa", lambda: supa)
    monkeypatch.setattr(ra, "fetch_public_https_chain", ler)

    # ⚠️ O default do parâmetro `ler` é resolvido no import, então trocar o
    # símbolo do módulo não bastaria: a assinatura já guarda a função antiga.
    # Reamarrar as duas funções é o que faz o monkeypatch valer.
    original_provar = ra.provar_destino

    def provar(**kw):
        kw.setdefault("ler", ler)
        return original_provar(**kw)

    original_confirmar = ra.confirmar_reauditoria

    def confirmar(**kw):
        kw.setdefault("ler", ler)
        return original_confirmar(**kw)

    monkeypatch.setattr(ra, "provar_destino", provar)
    monkeypatch.setattr(ra, "confirmar_reauditoria", confirmar)
    return {"supa": supa, "ler": ler, "run": run}


def test_provar_responde_a_prova_e_nao_grava_nada(cliente, mundo):
    r = cliente.post("/api/publicacao/redator/runs/1/reauditar/2/provar")
    assert r.status_code == 200, r.text
    prova = r.json()["prova"]
    assert prova["schema"] == ra.ESQUEMA_DA_PROVA
    assert len(prova["impressao_da_prova"]) == 64
    assert prova["elegivel"] is True
    assert prova["recibo_candidato"]["fingerprint_scope"] == "live"
    assert mundo["supa"].patches == []


def test_confirmar_sem_a_impressao_e_422(cliente, mundo):
    """Confirmar sem o vínculo com a prova nem chega à regra: o corpo não valida."""
    r = cliente.post("/api/publicacao/redator/runs/1/reauditar/2/confirmar", json={})
    assert r.status_code == 422
    assert mundo["supa"].patches == []


def test_confirmar_com_impressao_de_prova_velha_e_409(cliente, mundo):
    r = cliente.post("/api/publicacao/redator/runs/1/reauditar/2/confirmar",
                     json={"impressao_da_prova": "a" * 64})
    assert r.status_code == 409
    detalhe = r.json()["detail"]
    assert detalhe["proxima_acao"] == "provar de novo"
    assert len(detalhe["esperado_12"]) == 12 and len(detalhe["observado_12"]) == 12
    assert mundo["supa"].patches == []


def test_confirmar_grava_so_o_recibo_e_o_retry_nao_duplica(cliente, mundo):
    prova = cliente.post(
        "/api/publicacao/redator/runs/1/reauditar/2/provar").json()["prova"]

    r = cliente.post("/api/publicacao/redator/runs/1/reauditar/2/confirmar",
                     json={"impressao_da_prova": prova["impressao_da_prova"]})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["gravado"] is True
    assert corpo["recibo"]["fingerprint_scope"] == "live"
    assert len(mundo["supa"].patches) == 1
    # ⚠️ SÓ `paginas_publicadas`. Um patch mais largo mexeria em fatos que a
    # reauditoria não observou.
    assert set(mundo["supa"].patches[0]) == {"paginas_publicadas"}
    gravadas = mundo["supa"].patches[0]["paginas_publicadas"]
    assert gravadas[1]["landing_policy_receipt"]["fingerprint_scope"] == "live"
    assert ra.CHAVE_DO_RECIBO_ANTERIOR in gravadas[1]

    # ⚠️ O DUPLO-CLIQUE. Ele não grava e não empurra o histórico para fora: a
    # segunda confirmação emite um recibo que afirma exatamente o mesmo e só
    # difere no carimbo, e isso não é uma gravação.
    de_novo = cliente.post("/api/publicacao/redator/runs/1/reauditar/2/confirmar",
                           json={"impressao_da_prova": prova["impressao_da_prova"]})
    assert de_novo.status_code == 200, de_novo.text
    assert de_novo.json()["gravado"] is False
    assert len(mundo["supa"].patches) == 1


def test_run_em_andamento_recusa_as_duas_etapas(cliente, mundo):
    """⚠️ `worker.resumo_do_estado` reescreve `paginas_publicadas` INTEIRO.

    Um recibo gravado enquanto o motor roda seria apagado pelo próximo resumo,
    em silêncio — e a tela teria dito "gravado".
    """
    mundo["supa"].run = {**mundo["supa"].run, "status": "running"}
    assert cliente.post(
        "/api/publicacao/redator/runs/1/reauditar/2/provar").status_code == 409
    r = cliente.post("/api/publicacao/redator/runs/1/reauditar/2/confirmar",
                     json={"impressao_da_prova": "a" * 64})
    assert r.status_code == 409
    assert mundo["supa"].patches == []


def test_pagina_que_nao_esta_no_ar_recusa(cliente, mundo):
    r = cliente.post("/api/publicacao/redator/runs/1/reauditar/9/provar")
    assert r.status_code == 409
    assert "não está publicada" in r.json()["detail"]


def test_pagina_sem_url_recusa(cliente, mundo):
    mundo["supa"].run = {**mundo["supa"].run, "paginas_publicadas": [
        {"page_number": 2, "url_wp": "", "role": "LP"}]}
    r = cliente.post("/api/publicacao/redator/runs/1/reauditar/2/provar")
    assert r.status_code == 409
    assert "URL" in r.json()["detail"]


def test_run_inexistente_e_404(cliente, monkeypatch):
    class Vazio:
        enabled = True

        async def select(self, tabela, params):
            return []

    monkeypatch.setattr(pub, "_supa", lambda: Vazio())
    assert cliente.post(
        "/api/publicacao/redator/runs/99/reauditar/1/provar").status_code == 404


def test_leitura_que_falha_vira_409_e_nao_500(cliente, mundo):
    """"Não deu para olhar" é recusa do pedido, não defeito deste backend."""
    mundo["ler"].explode = OSError("conexão recusada")
    r = cliente.post("/api/publicacao/redator/runs/1/reauditar/2/provar")
    assert r.status_code == 409
    assert "OSError" in r.json()["detail"]["erro"]
    assert mundo["supa"].patches == []


def test_a_prova_nao_depende_do_recibo_anterior_para_o_hash(recibo_live):
    """⚠️ O recibo anterior NÃO entra no hash da prova, e é de propósito.

    Se entrasse, a própria gravação da confirmação mudaria o hash da página e a
    reauditoria seguinte nasceria divergente de si mesma. O que o hash amarra é
    a PÁGINA e o veredito sobre ela — o recibo anterior aparece no `diff`, que é
    para o operador ler, não para a máquina comparar.
    """
    com = ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=recibo_live,
                            agora=AGORA, ler=LeitorFalso())
    outro = _recibo(HTML_LIMPO, escopo="live", epoch=AGORA - 60)
    com_outro = ra.provar_destino(url=URL, papel_do_motor="LP", recibo_anterior=outro,
                                  agora=AGORA, ler=LeitorFalso())
    assert com.impressao_da_prova == com_outro.impressao_da_prova
