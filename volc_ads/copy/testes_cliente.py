"""Banco de provas do `render.py` e do `cliente.py`. Sem rede e sem chave.

## O que cada bloco tem de provar

  RENDER    todo placeholder do `PROMPT.md` recebe valor, e o valor vem da FONTE
            (`limites.yaml`, `policy/spec.json`) — não de literal escrito à mão.
            E o portão reprova: template pedindo chave sem valor, ou valor
            calculado para chave que o template não pede mais.

  CLIENTE   `ClienteLLM` é intercambiável com `ClienteMock` — não "parecido":
            os NOVE casos de `provar_cascata.py` rodam com ele e produzem o
            MESMO payload, o mesmo veredito e o mesmo número de gerações.

  FALHAS    queda de tubo não vira "o modelo escreveu bobagem", e JSON torto do
            modelo é recuperado pelo `json_defensivo` em vez de virar refazer.

Nada aqui abre socket: o `Transporte` é a costura, e todas as provas injetam um
transporte que devolve texto de memória. É a mesma propriedade que permitiu
provar a cascata inteira antes de existir chave.

Uso:
    backend/.venv/bin/python -m volc_ads.copy.testes_cliente
"""

from __future__ import annotations

import inspect
import json

from .ciclo import Cliente, gerar
from .cliente import ClienteLLM, FalhaDeTransporte, Resposta, SISTEMAS
from .contrato import Pedido
from .mock import SISTEMA_ASSET, SISTEMA_COMPLETO, ClienteMock, JuizMock, copy_valida
from .provar_cascata import CASOS, FATOS, PEDIDO
from .render import (
    Encomenda,
    ErroDeRender,
    Fato,
    PlaceholderDesconhecido,
    PlaceholderFaltando,
    RX_PLACEHOLDER,
    amostra_do_corpus,
    carregar_limites,
    corpo,
    headers_snippet,
    montar,
    valores,
)

# Tokens e preços FICTÍCIOS, e é o que se quer: com preço inventado a conta de
# custo é conferível na mão (1000×1 + 2000×2 por milhão = US$ 0,005 por chamada).
# Nenhum deles vaza para fora deste arquivo — o código de produção recusa preço
# não configurado justamente para não fabricar número.
TOKENS_ENTRADA = 1000
TOKENS_SAIDA = 2000
PRECO_ENTRADA_MI = 1.0
PRECO_SAIDA_MI = 2.0
CUSTO_POR_CHAMADA = 0.005


def encomenda_exemplo(**troca) -> Encomenda:
    """O brief do FGTS reduzido ao que o prompt precisa. Fatos reais do brief."""
    base = dict(
        nicho="Saque-Aniversário FGTS",
        url="https://creditoup.com.br/r/antecipacao-saque-aniversario-fgts/",
        keywords=("saque aniversario fgts", "regras do saque aniversario",
                  "quem tem direito ao saque aniversario"),
        fatos=(
            Fato("F1", "prazo", "Quem adere e desiste cumpre carência antes de "
                 "voltar ao saque-rescisão", "Lei 8.036/90, art. 20-D"),
            Fato("F2", "numero", "A alíquota do saque anual varia de 5% a 50% "
                 "conforme a faixa de saldo", "Anexo I da Lei 8.036/90"),
            Fato("F3", "data", "A adesão vale a partir do mês do aniversário do "
                 "trabalhador", "Resolução CCFGTS 1.130/2025"),
        ),
        nao_fatos=("A página não afirma valor a receber nem prazo de liberação.",),
        pais="BR",
        ano=2026,
        tema_regulado="financeiro",
    )
    base.update(troca)
    return Encomenda(**base)


# ── transportes de mentira ──────────────────────────────────────────────────


class TransporteFixo:
    """Devolve sempre o mesmo texto. Conta as chamadas."""

    def __init__(self, texto: str):
        self.texto = texto
        self.chamadas: list[tuple[str, str]] = []

    def __call__(self, sistema: str, usuario: str) -> Resposta:
        self.chamadas.append((sistema, usuario))
        return Resposta(self.texto, TOKENS_ENTRADA, TOKENS_SAIDA, "modelo-de-prova")


class TransporteDoMock:
    """Encaixa o roteiro do `ClienteMock` num `Transporte`.

    É o que torna a comparação honesta: o `ClienteLLM` recebe exatamente as
    mesmas respostas, na mesma ordem, que o mock daria à cascata.
    """

    def __init__(self, mock: ClienteMock):
        self.mock = mock

    def __call__(self, sistema: str, usuario: str) -> Resposta:
        return Resposta(self.mock.gerar(sistema, usuario),
                        TOKENS_ENTRADA, TOKENS_SAIDA, "modelo-de-prova")


class TransporteQuebrado:
    """Encena o tubo caindo — timeout, DNS, 429, o que for."""

    def __call__(self, sistema: str, usuario: str) -> Resposta:
        raise FalhaDeTransporte("ReadTimeout: encenado")


def cliente_de_prova(transporte, **troca) -> ClienteLLM:
    args = dict(transporte=transporte, provedor="prova", modelo="modelo-de-prova",
                preco_entrada_mi=PRECO_ENTRADA_MI, preco_saida_mi=PRECO_SAIDA_MI)
    args.update(troca)
    return ClienteLLM(**args)


# ── RENDER ──────────────────────────────────────────────────────────────────


def prova_render_preenche_tudo() -> str:
    """Nenhum `{placeholder}` sobrevive, e o texto do modelo não os menciona."""
    enc = encomenda_exemplo()
    prompt = montar(enc)
    resto = RX_PLACEHOLDER.findall(prompt)
    assert not resto, f"sobrou placeholder: {sorted(set(resto))}"

    pedidos = set(RX_PLACEHOLDER.findall(corpo()))
    tabela = valores(enc)
    assert pedidos == set(tabela), (
        f"template pede {sorted(pedidos - set(tabela))}, "
        f"render calcula a mais {sorted(set(tabela) - pedidos)}"
    )
    assert all(v.strip() for v in tabela.values()), (
        "valor vazio: placeholder que renderiza silêncio é o modelo inventando "
        f"({[k for k, v in tabela.items() if not v.strip()]})"
    )
    return f"{len(pedidos)} placeholders, {len(prompt)} caracteres no prompt"


def prova_render_usa_a_fonte() -> str:
    """Os limites vêm de `limites.yaml` e do `spec.json`, não de literal."""
    enc = encomenda_exemplo()
    prompt = montar(enc)
    lim = carregar_limites()

    for termo in lim["politica"]["proibidos"]:
        assert termo in prompt, f"termo travado {termo!r} não chegou à seção 8"
    for header in lim["snippet_headers_pt"]:
        assert header in prompt, f"header {header!r} do limites.yaml não chegou à seção 7"
    assert "14848295" in prompt, "número de política do spec.json não chegou à seção 8"
    # A sigla do FATO tem de entrar na união da seção 8 — sem isso, o modelo
    # escreveria 'Conselho Curador do FGTS' por extenso num título de 30 chars.
    assert "CCFGTS" in prompt, "sigla vinda do campo `fonte` de um fato ficou de fora"
    return (f"{len(lim['politica']['proibidos'])} termos travados · "
            f"{len(lim['snippet_headers_pt'])} headers · siglas do fato incluídas")


def prova_render_erra_quando_falta_valor() -> str:
    """Template pedindo chave nova: ERRO, não `{chave}` literal no prompt."""
    template = carregar_template_com("{nicho_secreto}")
    try:
        montar(encomenda_exemplo(), template=template)
    except PlaceholderFaltando as exc:
        assert "nicho_secreto" in str(exc)
        return f"PlaceholderFaltando: {str(exc)[:60]}…"
    raise AssertionError("montar aceitou template com placeholder sem valor")


def prova_render_erra_quando_sobra_valor() -> str:
    """Template que perdeu uma chave: ERRO, para o dado não sumir em silêncio."""
    template = carregar_template_com("").replace("{siglas_permitidas}", "as de sempre")
    try:
        montar(encomenda_exemplo(), template=template)
    except PlaceholderDesconhecido as exc:
        assert "siglas_permitidas" in str(exc)
        return f"PlaceholderDesconhecido: {str(exc)[:60]}…"
    raise AssertionError("montar aceitou valor órfão")


def carregar_template_com(extra: str) -> str:
    """O template real mais um trecho — sem tocar no arquivo de verdade."""
    from .render import carregar_template

    bruto = carregar_template()
    return bruto.replace("\n---\n", f"\n---\n{extra}\n", 1)


def prova_render_recusa_entrada_torta() -> str:
    """Três entradas que produziriam prompt plausível e errado."""
    casos = []

    try:
        encomenda_exemplo(fatos=(Fato("F9", "valor", "x", "y"),))
    except ErroDeRender as exc:
        casos.append(("tipo de fato inexistente", str(exc)))

    try:
        encomenda_exemplo(match_type="BROAD", max_dki=1)
    except ErroDeRender as exc:
        casos.append(("DKI em ad group BROAD", str(exc)))

    # ⚠️ AQUI ERA `es`, E O ESPANHOL PASSOU A FUNCIONAR EM 18/08/2026.
    #
    # Enquanto `snippet_headers_es` não existia, copy em espanhol era
    # impossível — a operação atende MX, CO, CL, PE e AR. O buraco foi tapado
    # com a INTERSEÇÃO de `es-419` e `es` (ver `limites.yaml`), então usar o
    # espanhol como exemplo de idioma-sem-headers deixou de provar coisa
    # alguma. Um idioma que não existe prova a mesma regra e não expira.
    try:
        headers_snippet("tlh")
    except ErroDeRender as exc:
        casos.append(("idioma sem headers no limites.yaml", str(exc)))

    # E o espanhol PRECISA continuar funcionando: cinco dos sete países.
    assert len(headers_snippet("es")) >= 5, "espanhol perdeu os headers"

    try:
        encomenda_exemplo(n_headlines=16)
    except ErroDeRender as exc:
        casos.append(("16 títulos (a API aceita 15)", str(exc)))

    assert len(casos) == 4, f"alguma entrada torta passou: {[c[0] for c in casos]}"
    return " · ".join(nome for nome, _ in casos)


def prova_render_casa_com_o_contrato() -> str:
    """O `Pedido` que julga a saída nasce da MESMA encomenda que pediu."""
    enc = encomenda_exemplo()
    pedido = enc.pedido()
    prompt = montar(enc)

    assert isinstance(pedido, Pedido)
    assert pedido.n_headlines == enc.n_headlines
    assert pedido.fatos == tuple(f.id for f in enc.fatos)
    assert pedido.headers_snippet == headers_snippet(enc.idioma)
    assert pedido.max_dki == enc.max_dki
    # O prompt tem de PEDIR o mesmo número que o contrato vai CONFERIR.
    assert f"{enc.n_headlines} títulos" in prompt
    assert f'"headlines": [{enc.n_headlines} strings]' in prompt
    return (f"{pedido.n_headlines} títulos · fatos {pedido.fatos} · "
            f"max_dki {pedido.max_dki}")


def prova_amostra_do_corpus() -> str:
    """A amostra é filtrada por idioma e é reproduzível."""
    pt, origem_pt = amostra_do_corpus("pt", 8)
    es, _ = amostra_do_corpus("es", 8)
    de, origem_de = amostra_do_corpus("de", 8)

    assert len(pt) == 8 and len(es) == 8
    assert not set(pt) & set(es), "o mesmo título saiu como pt e como es"
    assert amostra_do_corpus("pt", 8)[0] == pt, "a amostra mudou entre duas chamadas"
    assert de == () and "marcador" in origem_de, "idioma sem marcador devia sair vazio"
    assert "não" in origem_pt.lower(), "a origem precisa declarar o que NÃO se sabe"
    return f"pt {len(pt)} · es {len(es)} · sem sobreposição · de vazio e declarado"


# ── CLIENTE ─────────────────────────────────────────────────────────────────


def prova_cliente_satisfaz_o_protocolo() -> str:
    """Mesma assinatura do `Protocol`, e a mesma que o mock cumpre."""
    esperada = inspect.signature(Cliente.gerar)
    for classe in (ClienteLLM, ClienteMock):
        obtida = inspect.signature(classe.gerar)
        assert list(obtida.parameters) == list(esperada.parameters), (
            f"{classe.__name__}.gerar tem parâmetros {list(obtida.parameters)}")
        assert obtida.return_annotation == esperada.return_annotation

    cliente: Cliente = cliente_de_prova(TransporteFixo('{"ok": 1}'))
    assert isinstance(cliente.gerar(SISTEMA_COMPLETO, "oi"), str)
    return f"gerar{esperada} em ClienteLLM e ClienteMock"


def prova_cascata_roda_igual_com_os_dois() -> str:
    """Os NOVE casos de `provar_cascata`, com mock e com `ClienteLLM`.

    Mesmo payload, mesmo veredito, mesmas gerações. É a prova de que trocar o
    cliente não muda um caminho de decisão da cascata.
    """
    divergencias = []
    for fabrica in CASOS:
        mock, juiz_m, nome = fabrica()
        r_mock = gerar(cliente=mock, juiz=juiz_m, pedido=PEDIDO,
                       prompt_usuario="<prompt>", fatos_texto=FATOS)

        mock2, juiz_l, _ = fabrica()
        llm = cliente_de_prova(TransporteDoMock(mock2))
        r_llm = gerar(cliente=llm, juiz=juiz_l, pedido=PEDIDO,
                      prompt_usuario="<prompt>", fatos_texto=FATOS)

        igual = (
            r_mock.ok == r_llm.ok
            and r_mock.geracoes_conjunto == r_llm.geracoes_conjunto
            and r_mock.geracoes_asset == r_llm.geracoes_asset
            and len(r_mock.pendentes) == len(r_llm.pendentes)
            and json.dumps(r_mock.dados, sort_keys=True, ensure_ascii=False)
            == json.dumps(r_llm.dados, sort_keys=True, ensure_ascii=False)
        )
        if not igual:
            divergencias.append(nome)
        # A telemetria tem de contar as chamadas que a cascata de fato fez.
        assert len(llm.telemetria) == mock2.n_chamadas, (
            f"{nome}: {len(llm.telemetria)} linhas de telemetria para "
            f"{mock2.n_chamadas} chamadas")

    assert not divergencias, f"cascata divergiu em: {divergencias}"
    return f"{len(CASOS)} casos, payload idêntico nos dois clientes"


def prova_json_torto_e_recuperado() -> str:
    """Um `]` a mais — o defeito real que descartou 19k tokens do Gemini.

    O `json_defensivo` conserta, a cascata ACEITA, e a telemetria registra
    `parseou=True`: para a tela, foi uma chamada boa, não uma falha.
    """
    torto = json.dumps(copy_valida(), ensure_ascii=False)[:-1] + "]}"
    llm = cliente_de_prova(TransporteFixo(torto))
    r = gerar(cliente=llm, juiz=JuizMock(), pedido=PEDIDO,
              prompt_usuario="<prompt>", fatos_texto=FATOS)

    assert r.ok, f"a cascata não aceitou o JSON reparado: {r.pendentes}"
    assert r.geracoes_conjunto == 1, "reparo não pode custar uma segunda geração"
    assert llm.telemetria[0].parseou, "telemetria marcou ilegível o que foi reparado"
    return "1 geração · parseou=True · veredito ACEITO"


def prova_conteudo_ilegivel_nao_levanta() -> str:
    """Prosa em vez de JSON volta como TEXTO. Quem julga é a cascata.

    Se `gerar()` levantasse aqui, o `bruto = cliente.gerar(...)` da rodada 1
    — que não está dentro de `try` — derrubaria a cascata inteira em vez de
    exercer o caminho "JSON ilegível → refaz uma vez → desiste".
    """
    llm = cliente_de_prova(TransporteFixo("Claro! Aqui estão os títulos:"))
    texto = llm.gerar(SISTEMA_COMPLETO, "<prompt>")
    assert texto.startswith("Claro!"), "o cliente não devolveu o texto cru"
    assert llm.telemetria[0].parseou is False
    assert llm.telemetria[0].ok, "resposta ilegível não é falha de chamada"

    r = gerar(cliente=cliente_de_prova(TransporteFixo("nada de JSON aqui")),
              juiz=JuizMock(), pedido=PEDIDO, prompt_usuario="<p>", fatos_texto=FATOS)
    assert not r.ok
    assert r.geracoes_conjunto == 2, "devia refazer UMA vez e parar"
    assert any("ilegível" in linha for linha in r.estado.diario)
    return "texto cru devolvido · parseou=False · cascata refez 1× e parou"


def prova_falha_de_transporte_e_distinguivel() -> str:
    """Queda de tubo sobe como `FalhaDeTransporte`, e NÃO como `ValueError`.

    O tipo importa: `ciclo._regenerar` captura `ValueError` para dizer
    "substituto ilegível". Uma queda de rede casando ali viraria acusação contra
    o modelo e queimaria uma das 2 regenerações do teto daquele asset.
    """
    llm = cliente_de_prova(TransporteQuebrado())
    try:
        llm.gerar(SISTEMA_ASSET, "<prompt>")
    except FalhaDeTransporte as exc:
        assert not isinstance(exc, ValueError), (
            "FalhaDeTransporte não pode ser ValueError — ver ciclo._regenerar")
        assert llm.telemetria[0].erro, "a chamada falhada precisa entrar na telemetria"
        assert llm.telemetria[0].latencia_s >= 0
        assert not llm.telemetria[0].ok
        return f"{type(exc).__name__} · não é ValueError · telemetria registrou"
    raise AssertionError("transporte quebrado não levantou")


def prova_telemetria_mede_e_nao_inventa() -> str:
    """Com preço configurado, custo é conta. Sem preço, custo é `None` — e diz por quê."""
    com_preco = cliente_de_prova(TransporteFixo('{"a": 1}'))
    com_preco.gerar(SISTEMA_COMPLETO, "x")
    com_preco.gerar(SISTEMA_ASSET, "y")
    r = com_preco.resumo()

    assert r["chamadas"] == 2 and r["falhas"] == 0
    assert r["por_papel"] == {"asset": 1, "conjunto": 1}
    assert r["tokens_entrada"] == 2 * TOKENS_ENTRADA
    assert r["tokens_saida"] == 2 * TOKENS_SAIDA
    assert abs(r["custo_usd"] - 2 * CUSTO_POR_CHAMADA) < 1e-9, r["custo_usd"]
    assert r["sem_custo"] == 0 and not r["motivo_sem_custo"]
    assert r["latencia_s"] >= 0

    sem_preco = cliente_de_prova(TransporteFixo('{"a": 1}'),
                                 preco_entrada_mi=None, preco_saida_mi=None)
    sem_preco.gerar(SISTEMA_COMPLETO, "x")
    s = sem_preco.resumo()
    assert s["custo_usd"] is None, "custo sem preço configurado tem de ser None"
    assert s["sem_custo"] == 1 and "não configurado" in s["motivo_sem_custo"]
    assert s["tokens_saida"] == TOKENS_SAIDA, "token é medido mesmo sem preço"

    sem_uso = cliente_de_prova(TransporteFixo('{"a": 1}'))
    sem_uso.transporte = lambda sistema, usuario: Resposta("{}")   # provedor mudo
    sem_uso.gerar(SISTEMA_COMPLETO, "x")
    assert sem_uso.resumo()["custo_usd"] is None
    return (f"US$ {2 * CUSTO_POR_CHAMADA:.4f} em 2 chamadas · sem preço → None · "
            f"provedor sem uso → None")


def prova_papel_vira_instrucao_de_sistema() -> str:
    """O rótulo de papel não pode chegar cru à API como system instruction."""
    transporte = TransporteFixo('{"a": 1}')
    llm = cliente_de_prova(transporte)
    llm.gerar(SISTEMA_COMPLETO, "<prompt>")
    llm.gerar(SISTEMA_ASSET, "<prompt>")
    llm.gerar("um system prompt de verdade", "<prompt>")

    enviados = [s for s, _ in transporte.chamadas]
    assert enviados[0] == SISTEMAS[SISTEMA_COMPLETO]
    assert enviados[1] == SISTEMAS[SISTEMA_ASSET]
    assert enviados[2] == "um system prompt de verdade", "system alheio foi trocado"
    assert SISTEMA_COMPLETO not in enviados, "o rótulo de papel vazou para a API"
    assert [c.papel for c in llm.telemetria] == ["conjunto", "asset", "outro"]
    return "conjunto e asset traduzidos · system de terceiro preservado"


# ── runner ──────────────────────────────────────────────────────────────────

PROVAS = [
    ("render: preenche tudo", prova_render_preenche_tudo),
    ("render: valor vem da fonte", prova_render_usa_a_fonte),
    ("render: erra sem valor", prova_render_erra_quando_falta_valor),
    ("render: erra com valor órfão", prova_render_erra_quando_sobra_valor),
    ("render: recusa entrada torta", prova_render_recusa_entrada_torta),
    ("render: casa com o contrato", prova_render_casa_com_o_contrato),
    ("render: amostra do corpus", prova_amostra_do_corpus),
    ("cliente: satisfaz o Protocol", prova_cliente_satisfaz_o_protocolo),
    ("cliente: cascata roda igual", prova_cascata_roda_igual_com_os_dois),
    ("cliente: JSON torto reparado", prova_json_torto_e_recuperado),
    ("cliente: ilegível não levanta", prova_conteudo_ilegivel_nao_levanta),
    ("cliente: transporte ≠ conteúdo", prova_falha_de_transporte_e_distinguivel),
    ("cliente: telemetria não inventa", prova_telemetria_mede_e_nao_inventa),
    ("cliente: papel vira sistema", prova_papel_vira_instrucao_de_sistema),
]


def main() -> int:
    print("═" * 78)
    print("RENDER + CLIENTE — nenhuma chamada de rede, nenhuma chave lida.")
    print("═" * 78)

    falhas = 0
    for nome, prova in PROVAS:
        try:
            detalhe = prova()
        except Exception as exc:  # noqa: BLE001 — o runner reporta tudo
            falhas += 1
            print(f"✗ {nome:<34} {type(exc).__name__}: {exc}")
            continue
        print(f"✓ {nome:<34} {detalhe}")

    print("─" * 78)
    print(f"{len(PROVAS) - falhas}/{len(PROVAS)} provas passaram")
    print("═" * 78)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())


# ── a vertical do operador atravessa a porta ────────────────────────────────
#
# ⚠️ Este teste existe por um defeito real de 19/08/2026: o parâmetro `vertical`
# foi acrescentado a `encomendar()` e NÃO a `escrever()`, que é a porta que o
# backend chama. A rota estourou em produção com
# `escrever() got an unexpected keyword argument 'vertical'`.
#
# A lição é sobre assinatura de porta: acrescentar um parâmetro na função
# interna sem acrescentá-lo em quem a envolve produz um erro que só aparece na
# chamada real — nenhum teste de `encomendar()` o pegaria.

def test_escrever_aceita_vertical_como_encomendar():
    """As duas assinaturas têm de andar juntas — `escrever` é a porta."""
    import inspect
    from volc_ads.copy import encomendar as enc

    assert "vertical" in inspect.signature(enc.encomendar).parameters
    assert "vertical" in inspect.signature(enc.escrever).parameters, (
        "escrever() é quem o backend chama; sem o parâmetro a rota estoura"
    )


def test_vertical_do_operador_vence_a_da_entidade():
    """Marcar `informativo` no portão tem de mudar a copy, não só a prova."""
    from volc_ads.copy import encomendar as enc

    class _Origem:
        vertical = "financeiro"
        nicho = "Maquininha"; slug = "maquininha"; pais = "BR"; idioma = "pt"
        url_final = "https://a.com/x"; url_procedencia = "wp"
        resumo_da_pesquisa = ""; fatos = []
        dominio = "a.com"; opportunity_id = 1; run_id = 1; project_id = 1

    class _Ck:
        origem = _Origem(); grupos = []; conta = None

    pedido, _ = enc.encomendar(_Ck(), keywords=["saque fgts"], vertical="informativo")
    assert pedido.vertical == "informativo", (
        f"a escolha do operador foi ignorada: veio {pedido.vertical!r}"
    )

    herdado, _ = enc.encomendar(_Ck(), keywords=["saque fgts"])
    assert herdado.vertical == "financeiro", "sem escolha, a entidade manda"


# ── a queda de tubo não pode derrubar a cascata ─────────────────────────────
#
# ⚠️ Medido em 19/08/2026, card 65: a escrita morreu com
# `RemoteProtocolError: Server disconnected without sending a response.` O
# diário ficou VAZIO e `segundos` nulo — a cascata inteira (~174 s e os tokens
# já pagos das rodadas anteriores) foi ao chão por uma queda de um instante.
#
# O cabeçalho deste módulo AFIRMAVA que retentar era trabalho da `PoliticaRetry`
# de `gads/client.py`. Ela é usada só em `volc_ads/subir.py`, o caminho do
# Google Ads; nunca tocou a copy. O item descrevia um orquestrador que não
# existe.

import httpx as _httpx
import pytest

from .cliente import ESPERAS_DE_TUBO, TENTATIVAS_DE_TUBO, _http, _transitorio


class _Resp:
    def __init__(self, codigo=200, corpo=None):
        self.status_code = codigo
        self._corpo = corpo if corpo is not None else {"ok": True}
        self.text = str(self._corpo)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _httpx.HTTPStatusError("erro", request=None, response=self)

    def json(self):
        return self._corpo


def test_queda_de_conexao_e_retentada_e_a_segunda_vale(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    tentativas = []

    def chamar():
        tentativas.append(1)
        if len(tentativas) == 1:
            raise _httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return _Resp(200, {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    assert _http(chamar)["candidates"]
    assert len(tentativas) == 2, "a segunda tentativa não aconteceu"


def test_desiste_depois_do_teto_e_diz_o_que_caiu(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    n = []

    def chamar():
        n.append(1)
        raise _httpx.RemoteProtocolError("Server disconnected without sending a response.")

    with pytest.raises(FalhaDeTransporte) as e:
        _http(chamar)
    assert len(n) == TENTATIVAS_DE_TUBO
    assert "RemoteProtocolError" in str(e.value)


@pytest.mark.parametrize("codigo", [429, 500, 503])
def test_sobrecarga_do_provedor_e_retentada(monkeypatch, codigo):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    n = []

    def chamar():
        n.append(1)
        return _Resp(codigo) if len(n) == 1 else _Resp(200, {"ok": 1})

    assert _http(chamar) == {"ok": 1}
    assert len(n) == 2


@pytest.mark.parametrize("codigo", [400, 401, 403, 404])
def test_erro_de_pedido_sobe_na_PRIMEIRA(monkeypatch, codigo):
    """Payload malformado e chave inválida vão errar de novo. Repetir só
    esconde o motivo atrás de três tentativas idênticas."""
    monkeypatch.setattr("time.sleep", lambda _s: None)
    n = []

    def chamar():
        n.append(1)
        return _Resp(codigo, "detalhe do erro")

    with pytest.raises(FalhaDeTransporte):
        _http(chamar)
    assert len(n) == 1, f"HTTP {codigo} não pode ser retentado"


def test_o_que_conta_como_transitorio():
    assert _transitorio(_httpx.RemoteProtocolError("x"))
    assert _transitorio(_httpx.ConnectError("x"))
    assert _transitorio(_httpx.ReadTimeout("x"))
    assert _transitorio(_httpx.HTTPStatusError("x", request=None, response=_Resp(429)))
    assert _transitorio(_httpx.HTTPStatusError("x", request=None, response=_Resp(502)))
    assert not _transitorio(_httpx.HTTPStatusError("x", request=None, response=_Resp(400)))
    assert not _transitorio(ValueError("json ruim"))


def test_a_espera_cresce_entre_tentativas():
    """Repetir imediatamente contra um provedor sobrecarregado é bater na mesma
    porta três vezes no mesmo segundo."""
    assert list(ESPERAS_DE_TUBO) == sorted(ESPERAS_DE_TUBO)
    assert ESPERAS_DE_TUBO[0] >= 1.0


# ── o corte de 60 segundos, e onde ele pega de verdade ──────────────────────
#
# ⚠️ ESTE BLOCO JÁ ESTEVE ERRADO. A primeira versão dizia que o corte era no
# TEMPO TOTAL e que `streamGenerateContent` resolvia. Metade certo — e a metade
# errada custou uma escrita inteira do card 65, que voltou a morrer aos
# 60,8 · 61,0 · 60,8 s COM o streaming no ar.
#
# Medido de novo em 19/08/2026, agora cronometrando o PRIMEIRO byte do SSE
# contra o prompt real do card 65 (payload de 77.276 bytes):
#
#     sem teto        1º byte NUNCA chegou · caiu aos 61,0 s · 0 blocos
#     nível medium    1º byte NUNCA chegou · caiu aos 60,9 s · 0 blocos
#     orçamento 32768 1º byte NUNCA chegou · caiu aos 60,8 s · 0 blocos
#     orçamento 24576 1º byte NUNCA chegou · caiu aos 60,8 s · 0 blocos
#     orçamento 16384 1º byte NUNCA chegou · caiu aos 60,8 s · 0 blocos
#     orçamento  8192 1× passou (44,3 s) · 2× caiu    ← cara ou coroa
#     orçamento  2048 1º byte aos 1,7 · 1,7 · 4,0 s   ← 3/3
#     nível    low    1º byte aos 1,7 · 1,6 · 3,7 s   ← 3/3
#
# O corte é no PRIMEIRO BYTE, não no total: enquanto o modelo pensa não há nada
# na linha, e o servidor fecha o socket aos ~60 s. Streaming só salva quem
# começa a falar antes disso.
#
# Descartados por medição, antes de chegar aqui: blip de rede (retentar não
# resolveu, 3/3), limite de taxa (8 chamadas seguidas de 56 mil ch passaram),
# tamanho de payload (idem) e o modelo (os três da tela responderam 200).

def test_o_endpoint_e_o_de_streaming():
    """Se alguém voltar para `:generateContent`, a copy volta a cair aos 60 s
    nas rodadas em que o modelo pensa mais — de forma intermitente, que é o
    pior jeito de reaparecer."""
    import inspect

    from .cliente import TransporteGemini

    fonte = inspect.getsource(TransporteGemini._uma_chamada)
    assert ":streamGenerateContent" in fonte
    assert '"alt": "sse"' in fonte


def test_a_escada_comeca_num_degrau_medido():
    """⚠️ Guarda contra "vamos deixar pensar mais um pouquinho".

    8192 passou 1 de 3 vezes; 4096, 16384, 24576, 32768 e o livre não passaram
    nenhuma. Qualquer degrau perto dos 60 s é cara ou coroa, e um degrau que
    falha custa 61 s de relógio e devolve zero. Se este teste quebrar, a
    pergunta não é "como faço ele passar" — é "eu medi o degrau novo?"."""
    from .cliente import ESCADA_DE_PENSAMENTO

    assert ESCADA_DE_PENSAMENTO[0] == {"thinkingBudget": 2048}
    for degrau in ESCADA_DE_PENSAMENTO:
        teto = degrau.get("thinkingBudget")
        assert teto is None or teto <= 2048, f"degrau não medido: {degrau}"
        assert degrau.get("thinkingLevel") in (None, "low"), f"degrau não medido: {degrau}"


def test_queda_sem_um_bloco_vira_tubo_mudo():
    """Zero blocos = o servidor cortou enquanto o modelo pensava. Remédio: descer
    a escada. Se isto virasse `RemoteProtocolError` genérico, `_http` gastaria
    três tentativas de 61 s e a cascata morreria com a conta já paga."""
    from .cliente import TuboMudo, _juntar_stream

    class _Stream:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_lines(self):
            raise _httpx.RemoteProtocolError("Server disconnected without sending a response.")
            yield  # pragma: no cover — só para ser gerador
        def read(self): return b""
        def raise_for_status(self): return None

    class _Http:
        def stream(self, *a, **k): return _Stream()

    with pytest.raises(TuboMudo):
        _juntar_stream(_Http(), "u", {}, {})


def test_queda_no_meio_do_stream_nao_e_tubo_mudo():
    """Já veio bloco = o servidor estava falando e a REDE piscou. Aí repetir
    igual tem chance real, e chamar isto de tubo mudo faria o motor descer a
    escada de pensamento à toa — piorando a copy por causa de um blip."""
    from .cliente import TuboMudo, _juntar_stream

    class _Stream:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_lines(self):
            yield 'data: {"candidates":[{"content":{"parts":[{"text":"come"}]}}]}'
            raise _httpx.RemoteProtocolError("caiu no meio")
        def read(self): return b""
        def raise_for_status(self): return None

    class _Http:
        def stream(self, *a, **k): return _Stream()

    with pytest.raises(_httpx.RemoteProtocolError) as e:
        _juntar_stream(_Http(), "u", {}, {})
    assert not isinstance(e.value, TuboMudo)


def test_http_nao_gasta_tentativa_em_tubo_mudo():
    """Medido 3/3: as três tentativas idênticas caíram aos ~61 s. Retentar aqui
    é queimar 183 s de relógio para chegar no mesmo lugar."""
    from .cliente import TuboMudo, _http

    n = []

    def chamar():
        n.append(1)
        raise TuboMudo("mudo")

    with pytest.raises(TuboMudo):
        _http(chamar)
    assert len(n) == 1, f"retentou {len(n)}x um tubo mudo"


def test_tubo_mudo_sobe_com_o_tipo():
    """Embrulhar em `FalhaDeTransporte` genérica apagaria a única informação que
    o transporte usa para descer a escada — e ele morreria sem tentar o degrau
    seguinte."""
    from .cliente import FalhaDeTransporte, TuboMudo, _http

    def chamar():
        raise TuboMudo("mudo")

    with pytest.raises(FalhaDeTransporte) as e:
        _http(chamar)
    assert type(e.value) is TuboMudo


def test_a_escada_desce_sozinha_quando_o_degrau_fica_mudo():
    """O laço inteiro: primeiro degrau mudo → segundo degrau → resposta. É este
    caminho que faz a escrita do card 65 terminar em vez de morrer."""
    from .cliente import (ESCADA_DE_PENSAMENTO, Config, TransporteGemini,
                          TuboMudo)
    import volc_ads.copy.cliente as mod

    vistos = []

    def falso(http, url, params, payload):
        vistos.append(payload["generationConfig"].get("thinkingConfig"))
        if len(vistos) == 1:
            raise TuboMudo("o primeiro degrau ficou mudo")
        return {"candidates": [{"content": {"parts": [{"text": '{"ok":1}'}]}}],
                "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3}}

    antigo = mod._juntar_stream
    mod._juntar_stream = falso
    try:
        r = TransporteGemini(Config(provedor="gemini", modelo="m", chave="k"))(
            "sistema", "usuário")
    finally:
        mod._juntar_stream = antigo

    assert vistos == [dict(ESCADA_DE_PENSAMENTO[0]), dict(ESCADA_DE_PENSAMENTO[1])]
    assert r.texto == '{"ok":1}'
    assert r.pensamento == "nível low", r.pensamento


def test_escada_esgotada_sobe_o_erro_em_vez_de_chamar_de_novo():
    """Se nem o degrau mais barato fala em 60 s, o problema não é pensamento.
    Uma quarta chamada de consolo custaria mais 61 s e esconderia a causa."""
    from .cliente import Config, TransporteGemini, TuboMudo
    import volc_ads.copy.cliente as mod

    n = []

    def falso(http, url, params, payload):
        n.append(1)
        raise TuboMudo("mudo")

    antigo = mod._juntar_stream
    mod._juntar_stream = falso
    try:
        with pytest.raises(TuboMudo):
            TransporteGemini(Config(provedor="gemini", modelo="m", chave="k"))("s", "u")
    finally:
        mod._juntar_stream = antigo

    from .cliente import ESCADA_DE_PENSAMENTO
    assert len(n) == len(ESCADA_DE_PENSAMENTO), f"chamou {len(n)}x"


def test_a_telemetria_diz_com_quanto_pensamento_a_copy_saiu():
    """Sem isto, uma copy escrita no degrau mais barato parece idêntica a uma
    escrita à vontade — e a pergunta "o teto piorou o texto?" não tem como ser
    feita depois."""
    from .cliente import ClienteLLM, Resposta

    def transporte(sistema, usuario):
        return Resposta('{"ok":1}', 10, 5, "m", pensamento="teto 2048")

    c = ClienteLLM(transporte=transporte, provedor="gemini", modelo="m")
    c.gerar("sistema", "usuário")
    assert c.telemetria[0].pensamento == "teto 2048"
    assert c.resumo()["pensamento"] == ["teto 2048"]


def test_junta_os_pedacos_na_ordem():
    from .cliente import _juntar_stream

    class _Stream:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_lines(self):
            yield 'data: {"candidates":[{"content":{"parts":[{"text":"{\\"a\\":"}]}}]}'
            yield ""
            yield 'data: {"candidates":[{"content":{"parts":[{"text":"1}"}]}}],'\
                  '"usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":2}}'
        def read(self): return b""
        def raise_for_status(self): return None

    class _Http:
        def stream(self, *a, **k): return _Stream()

    d = _juntar_stream(_Http(), "u", {}, {})
    assert d["candidates"][0]["content"]["parts"][0]["text"] == '{"a":1}'
    assert d["usageMetadata"]["promptTokenCount"] == 10


def test_uso_do_ultimo_pedaco_vence_e_nao_soma():
    """⚠️ `usageMetadata` é CUMULATIVO: cada bloco traz o total até ali. Somar
    os blocos multiplicaria a contagem de tokens — e com ela o custo na tela."""
    from .cliente import _juntar_stream

    class _Stream:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_lines(self):
            yield 'data: {"candidates":[{"content":{"parts":[{"text":"a"}]}}],'\
                  '"usageMetadata":{"candidatesTokenCount":5}}'
            yield 'data: {"candidates":[{"content":{"parts":[{"text":"b"}]}}],'\
                  '"usageMetadata":{"candidatesTokenCount":9}}'
        def read(self): return b""
        def raise_for_status(self): return None

    class _Http:
        def stream(self, *a, **k): return _Stream()

    d = _juntar_stream(_Http(), "u", {}, {})
    assert d["usageMetadata"]["candidatesTokenCount"] == 9, "somou em vez de pegar o último"


def test_pedaco_truncado_nao_derruba_a_resposta():
    """SSE pode entregar uma linha partida; a próxima fecha. Levantar aqui
    jogaria fora uma geração inteira por um pedaço de JSON."""
    from .cliente import _juntar_stream

    class _Stream:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_lines(self):
            yield 'data: {"candidates":[{"content":{"parts":[{"text":"ok"'   # truncado
            yield 'data: {"candidates":[{"content":{"parts":[{"text":"vale"}]}}]}'
        def read(self): return b""
        def raise_for_status(self): return None

    class _Http:
        def stream(self, *a, **k): return _Stream()

    assert _juntar_stream(_Http(), "u", {}, {})["candidates"][0]["content"]["parts"][0]["text"] == "vale"


def test_erro_de_status_le_o_corpo_antes_de_levantar():
    """Numa resposta em streaming o corpo ainda não foi baixado quando o status
    chega. Sem o `read()`, o operador veria "HTTP 400: " sem o motivo."""
    from .cliente import _juntar_stream

    leu = []

    class _Stream:
        status_code = 400
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_lines(self): return iter(())
        def read(self): leu.append(1); return b'{"error":"detalhe"}'
        def raise_for_status(self):
            raise _httpx.HTTPStatusError("400", request=None, response=self)
        text = '{"error":"detalhe"}'

    class _Http:
        def stream(self, *a, **k): return _Stream()

    with pytest.raises(_httpx.HTTPStatusError):
        _juntar_stream(_Http(), "u", {}, {})
    assert leu, "não leu o corpo antes de levantar — a mensagem sairia vazia"


def test_http_aceita_dicionario_pronto_do_stream():
    """`_juntar_stream` já devolve o dicionário montado; `_http` precisa
    reconhecê-lo para a retentativa continuar num lugar só."""
    from .cliente import _http

    assert _http(lambda: {"candidates": [], "usageMetadata": {}}) == {
        "candidates": [], "usageMetadata": {}}
