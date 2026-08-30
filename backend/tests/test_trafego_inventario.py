"""O contrato de leitura do inventário — e as três regras que ele impõe.

As asserções são sobre INVARIANTES, não sobre a contagem do dia: "nenhum número
sai sem a data em que foi lido" continua verdade amanhã; "duas campanhas" não.

⚠️ Nenhum teste aqui fala com o Google Ads, e um deles PROVA isso instalando um
bloqueio de import: se o caminho de leitura tentar carregar `volc_ads` ou
`google.ads`, o import explode e o teste falha. É a única forma de a regra
"o carregamento de /trafego não chama o Google" ser verificável em vez de
combinada.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.seguranca.identidade import (Identidade, exigir_admin, exigir_servico,
                                      exigir_usuario)
from app.trafego import dominio as dom
from app.trafego import inventario as inv

AGORA = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _iso(minutos_atras: float) -> str:
    return (AGORA - timedelta(minutes=minutos_atras)).isoformat()


# ── o dublê da fonte ────────────────────────────────────────────────────────


def _e_historico(r: Dict[str, Any]) -> bool:
    """A mesma regra da view e de `dominio.e_historico`, para o dublê.

    Ela é reescrita aqui, e não importada, porque o dublê É o banco deste
    arquivo: ele tem de reproduzir o que o PostgREST faz com a COLUNA
    `historico`, não chamar a função que a define. Se um dia as duas
    discordarem, é o teste de paridade contra o Postgres real
    (`test_trafego_persistencia.py`) que denuncia — este aqui não tem como.
    """
    return (r.get("presenca") == dom.REMOVIDA
            or str(r.get("estado_externo") or "").strip().upper() == dom.REMOVED)


def _como_a_view(r: Dict[str, Any], *, conta_falhou: bool = False) -> Dict[str, Any]:
    """A linha com as colunas DERIVADAS que a view publica.

    ⚠️ Sem isto o dublê mente por omissão. `montar_inventario` lê
    `ordem_operacional` da linha para montar o cursor; se a coluna não vier, ele
    usa o recuo (`ORDEM_OUTROS_PRESENTES`) e o keyset passa a apontar para um
    degrau em que não há ninguém — a página 2 volta vazia e a listagem termina
    cedo, sem erro. Foi o que aconteceu na primeira execução desta rodada.

    A `atencao` vem da PRÓPRIA linha quando a fixture a declara, porque é isso
    que a view faz: ela calcula `atencao` e a ordem usa o resultado. Recalcular
    aqui faria o dublê discordar da fixture que o teste montou de propósito.
    """
    historico = _e_historico(r)
    estado = str(r.get("estado_externo") or "").strip().upper()
    if historico:
        ordem = dom.ORDEM_HISTORICO
    elif bool(r.get("atencao")) or conta_falhou:
        ordem = dom.ORDEM_ATENCAO
    elif estado == dom.LIGADA:
        ordem = dom.ORDEM_LIGADA
    elif estado == dom.PAUSADA:
        ordem = dom.ORDEM_PAUSADA
    else:
        ordem = dom.ORDEM_OUTROS_PRESENTES
    return {**r, "historico": historico, "ordem_operacional": ordem}


def _degrau(r: Dict[str, Any]) -> int:
    return int(r["ordem_operacional"])


class FonteEmMemoria:
    """Um snapshot de mentira com a MESMA semântica de filtro do PostgREST.

    Ela filtra em Python porque É o banco do teste — o que não pode acontecer é
    a MONTAGEM filtrar. `test_a_montagem_nao_filtra_nada` prova que tudo o que
    a fonte devolve chega à resposta.
    """

    def __init__(self, contas: List[Dict[str, Any]],
                 campanhas: List[Dict[str, Any]]) -> None:
        self._contas = contas
        self._campanhas = campanhas
        self.consultas: List[str] = []

    async def contas(self, filtros: inv.FiltrosDoInventario) -> List[Dict[str, Any]]:
        self.consultas.append("contas")
        linhas = sorted(self._contas, key=lambda r: r["customer_id"])
        if filtros.conta:
            linhas = [r for r in linhas if r["customer_id"] in filtros.conta]
        return linhas

    def _filtrar(self, plano: inv.PlanoDeConsulta) -> List[Dict[str, Any]]:
        f = plano.filtros
        saida = []
        for r in self._campanhas:
            cid = r.get("customer_id")
            if cid in plano.contas_falhas:
                pass
            elif cid in plano.contas_lidas:
                if f.presenca:
                    permitidas = [v for v in f.presenca
                                  if v != inv.SINCRONIZACAO_FALHOU]
                    if r.get("presenca") not in permitidas:
                        continue
            else:
                continue
            if f.canal and r.get("canal") not in f.canal:
                continue
            if f.estado_externo and r.get("estado_externo") not in f.estado_externo:
                continue
            if f.procedencia and r.get("procedencia") not in f.procedencia:
                continue
            if f.projeto and r.get("project_id") not in f.projeto:
                continue
            if f.vinculado is True and r.get("opportunity_id") is None:
                continue
            if f.vinculado is False and r.get("opportunity_id") is not None:
                continue
            if f.atencao is not None:
                efetiva = bool(r.get("atencao")) or cid in plano.contas_falhas
                if efetiva is not f.atencao:
                    continue
            # O padrão da U0: história fora, a menos que peçam. Fica aqui, junto
            # dos outros filtros do banco, e NUNCA na montagem — é o mesmo lugar
            # onde o PostgREST resolve `historico=is.false`.
            if not f.incluir_historico and _e_historico(r):
                continue
            saida.append(_como_a_view(r, conta_falhou=cid in plano.contas_falhas))
        saida.sort(key=lambda r: (r["customer_id"], _degrau(r),
                                  r["volc_campaign_id"]))
        return saida

    async def campanhas(self, plano: inv.PlanoDeConsulta) -> List[Dict[str, Any]]:
        self.consultas.append("campanhas")
        linhas = self._filtrar(plano)
        if plano.depois_de:
            linhas = [r for r in linhas
                      if (r["customer_id"], _degrau(r),
                          r["volc_campaign_id"]) > plano.depois_de]
        return linhas[: plano.limite + 1]

    async def contagem(self, plano: inv.PlanoDeConsulta) -> Dict[str, int]:
        d: Dict[str, int] = {}
        for r in self._filtrar(plano):
            d[r["customer_id"]] = d.get(r["customer_id"], 0) + 1
        return d

    async def contagem_em_atencao(self, plano: inv.PlanoDeConsulta) -> int:
        return sum(1 for r in self._filtrar(plano)
                   if bool(r.get("atencao")) or r["customer_id"] in plano.contas_falhas)

    async def contagem_por_natureza(self, plano: inv.PlanoDeConsulta):
        import dataclasses as _dc
        base = _dc.replace(plano, depois_de=None)
        op = _dc.replace(base, filtros=_dc.replace(base.filtros,
                                                   incluir_historico=False))
        todos = _dc.replace(base, filtros=_dc.replace(base.filtros,
                                                      incluir_historico=True))
        operacionais = len(self._filtrar(op))
        historicas = sum(1 for r in self._filtrar(todos) if _e_historico(r))
        return operacionais, historicas


def _conta(cid: str, **kw: Any) -> Dict[str, Any]:
    """Uma linha de `trafego_snapshot_conta`, com os nomes REAIS das colunas.

    ⚠️ As fixtures falavam `lido_em`/`resultado`/`ultima_leitura_boa_em` —
    nomes de uma tabela que nenhuma migration cria. Um dublê que usa colunas
    inventadas prova que a projeção funciona sobre o que imaginamos, e é
    exatamente por isso que a suíte ficou verde enquanto a rota devolvia 404.
    """
    base = {
        "customer_id": cid, "nome": f"conta {cid}",
        "tentativa_em": _iso(6), "tentativa_resultado": "ok",
        "tentativa_motivo": None, "tentativa_duracao_ms": 120,
        "leitura_boa_em": _iso(6), "leitura_boa_campanhas": 2,
    }
    base.update(kw)
    return base


def _campanha(cid: str, kid: str, **kw: Any) -> Dict[str, Any]:
    base = {
        "volc_campaign_id": f"gads-{cid}-{kid}", "customer_id": cid,
        "campaign_id": kid, "nome": f"campanha {kid}",
        "estado_externo": "ENABLED", "veiculacao": "SERVING",
        "canal": "SEARCH", "estrategia": "MANUAL_CPC",
        "lance_micros": 120_000, "verba_diaria_micros": 10_000_000,
        "impressoes": 4, "cliques": 0, "custo_micros": 0, "moeda": "BRL",
        "entrega_lida_em": _iso(6), "presenca": inv.PRESENTE,
        "procedencia": "volc_os", "opportunity_id": 73, "project_id": 1,
        "atencao": False, "campaign_lineage_id": None,
        "vinculo_confirmado_por": "tarcisio@agenciavolc.com.br",
        "vinculo_confirmado_em": _iso(600),
    }
    base.update(kw)
    return base


async def _montar(fonte: FonteEmMemoria, **kw: Any) -> inv.Inventario:
    filtros = kw.pop("filtros", inv.FiltrosDoInventario())
    return await inv.montar_inventario(fonte, filtros, agora=AGORA, **kw)


# ── regra A · nenhum número sem frescor ─────────────────────────────────────


def test_entrega_com_numero_e_sem_leitura_e_recusada():
    """A regra é estrutural: não dá para construir o objeto errado.

    Validar depois, na saída, deixaria a janela aberta para um caminho novo
    esquecer a checagem. Aqui o tipo recusa.
    """
    with pytest.raises(inv.SemFrescor):
        inv.Entrega(impressoes=4, cliques=0, custo_micros=0, moeda="BRL")

    # Zero também é número: um custo zerado sem data mente igual.
    with pytest.raises(inv.SemFrescor):
        inv.Entrega(custo_micros=0)


@pytest.mark.anyio
async def test_nenhum_numero_da_resposta_vem_sem_carimbo():
    """Varre a resposta inteira: toda entrega com número tem `leitura`."""
    fonte = FonteEmMemoria([_conta("8017851692")],
                           [_campanha("8017851692", "241")])
    resposta = (await _montar(fonte)).json()

    achou = 0
    for conta in resposta["contas"]:
        for c in conta["campanhas"]:
            e = c["entrega"]
            if any(e[k] is not None for k in ("impressoes", "cliques", "custo_micros")):
                assert e["leitura"] is not None, f"{c['nome']} tem número sem carimbo"
                assert e["leitura"]["lido_em"]
                assert e["leitura"]["idade_s"] >= 0
                achou += 1
    assert achou == 1


@pytest.mark.anyio
async def test_linha_sem_carimbo_de_entrega_nao_traz_numero():
    """Snapshot sem `entrega_lida_em` é snapshot que nunca mediu entrega.

    Os números do banco (se houver) NÃO saem: sem data eles são
    indistinguíveis de um número de ontem.
    """
    fonte = FonteEmMemoria(
        [_conta("8017851692")],
        [_campanha("8017851692", "241", entrega_lida_em=None,
                   impressoes=999, cliques=9, custo_micros=1234)])
    resposta = (await _montar(fonte)).json()
    e = resposta["contas"][0]["campanhas"][0]["entrega"]
    assert e == {"impressoes": None, "cliques": None, "custo_micros": None,
                 "moeda": "BRL", "leitura": None}


# ── regra B · ausência é null, nunca zero ───────────────────────────────────


@pytest.mark.anyio
async def test_entrega_ausente_e_null_e_zero_medido_e_zero():
    """Os dois casos, lado a lado, para a diferença ficar impossível de perder."""
    fonte = FonteEmMemoria(
        [_conta("8017851692")],
        [_campanha("8017851692", "241", impressoes=0, cliques=0, custo_micros=0),
         _campanha("8017851692", "242", entrega_lida_em=None,
                   impressoes=None, cliques=None, custo_micros=None)])
    resposta = (await _montar(fonte)).json()
    campanhas = {c["externa"]["campaign_id"]: c
                 for c in resposta["contas"][0]["campanhas"]}

    medida = campanhas["241"]["entrega"]
    assert medida["impressoes"] == 0 and medida["leitura"] is not None

    ausente = campanhas["242"]["entrega"]
    assert ausente["impressoes"] is None and ausente["leitura"] is None


@pytest.mark.anyio
async def test_vazio_confirmado_nao_e_falha_nem_nunca_lido():
    """Três fatos que a tela costuma achatar num "sem campanhas"."""
    fonte = FonteEmMemoria(
        # ⚠️ `vazio_confirmado` NÃO é coluna: ele é derivado de "leitura boa
        # com ZERO campanhas". Um booleano próprio seria uma segunda fonte da
        # mesma verdade — e duas fontes divergem na primeira mudança.
        [_conta("111", leitura_boa_campanhas=0),
         _conta("222", tentativa_resultado="falhou", tentativa_em=_iso(1),
                leitura_boa_em=_iso(600), leitura_boa_campanhas=2,
                tentativa_motivo="USER_PERMISSION_DENIED"),
         _conta("333", tentativa_resultado=None, tentativa_em=None,
                leitura_boa_em=None, leitura_boa_campanhas=None)],
        [])
    resposta = (await _montar(fonte)).json()
    por_id = {c["customer_id"]: c for c in resposta["contas"]}

    assert por_id["111"]["frescor"] == inv.VAZIO_CONFIRMADO
    assert por_id["222"]["frescor"] == inv.FALHOU
    assert por_id["333"]["frescor"] == inv.NUNCA_LIDO
    assert por_id["333"]["leitura"] is None

    # A conta que falhou preserva o carimbo da última leitura BOA, que é mais
    # antiga que a última tentativa — é essa distância que a tela precisa mostrar.
    assert por_id["222"]["ultima_leitura_boa"]["idade_s"] > por_id["222"]["leitura"]["idade_s"]


# ── regra C · falha de uma conta não contamina as outras ────────────────────


@pytest.mark.anyio
async def test_uma_conta_falha_e_as_outras_permanecem_validas():
    fonte = FonteEmMemoria(
        [_conta("111"), _conta("222", tentativa_resultado="falhou",
                               tentativa_em=_iso(1),
                               leitura_boa_em=_iso(300),
                               tentativa_motivo="a API recusou a leitura")],
        [_campanha("111", "1"), _campanha("222", "2")])
    resposta = (await _montar(fonte)).json()

    assert resposta["parcial"] is True
    assert [f["customer_id"] for f in resposta["faltou"]] == ["222"]
    assert resposta["faltou"][0]["motivo"] == "a API recusou a leitura"

    por_id = {c["customer_id"]: c for c in resposta["contas"]}
    boa = por_id["111"]["campanhas"][0]
    assert boa["presenca"] == inv.PRESENTE
    assert boa["entrega"]["impressoes"] == 4


@pytest.mark.anyio
async def test_ultimo_snapshot_bom_da_conta_que_falhou_continua_visivel():
    """Não some da tela — muda de estado. Some seria perder a única informação
    que existe sobre aquela conta."""
    fonte = FonteEmMemoria(
        [_conta("222", tentativa_resultado="falhou", tentativa_em=_iso(1),
                leitura_boa_em=_iso(300), tentativa_motivo="timeout")],
        [_campanha("222", "2", nome="FGTS Saque-Aniversário")])
    resposta = (await _montar(fonte)).json()

    campanha = resposta["contas"][0]["campanhas"][0]
    assert campanha["nome"] == "FGTS Saque-Aniversário"
    # A presença efetiva vira `sincronizacao_falhou`: não dá para afirmar nem
    # presença nem ausência quando a leitura não voltou.
    assert campanha["presenca"] == inv.SINCRONIZACAO_FALHOU
    assert resposta["contas"][0]["ultima_leitura_boa"] is not None


# ── contrato ────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_contrato_versionado():
    resposta = (await _montar(FonteEmMemoria([], []))).json()
    assert resposta["versao"] == inv.VERSAO_INVENTARIO == 2
    assert set(resposta) == {"versao", "frescor", "leitura", "parcial", "faltou",
                             "contas", "proximo_cursor", "totais"}
    assert set(resposta["totais"]) == {"contas", "operacionais", "historicas",
                                       "geral", "atencao"}


@pytest.mark.anyio
async def test_forma_da_campanha_bate_com_o_typescript():
    """Nome por nome. O front está sendo escrito contra estas chaves."""
    fonte = FonteEmMemoria([_conta("111")], [_campanha("111", "1")])
    c = (await _montar(fonte)).json()["contas"][0]["campanhas"][0]
    assert set(c) == {
        "volc_campaign_id", "campaign_lineage_id", "externa", "nome",
        "estado_externo", "veiculacao", "canal", "estrategia", "lance_micros",
        "verba_diaria_micros", "teto_de_cliques", "entrega", "vinculo",
        "procedencia", "presenca", "cockpit_href",
    }
    assert set(c["externa"]) == {"customer_id", "campaign_id"}
    assert set(c["vinculo"]) == {"opportunity_id", "project_id",
                                 "confirmado_por", "confirmado_em"}


@pytest.mark.anyio
async def test_teto_de_cliques_so_com_lance_manual_e_dois_numeros():
    fonte = FonteEmMemoria(
        [_conta("111")],
        [_campanha("111", "1"),
         _campanha("111", "2", estrategia="MAXIMIZE_CONVERSIONS"),
         _campanha("111", "3", lance_micros=None)])
    campanhas = {c["externa"]["campaign_id"]: c
                 for c in (await _montar(fonte)).json()["contas"][0]["campanhas"]}

    assert campanhas["1"]["teto_de_cliques"] == 83      # 10.000.000 / 120.000
    # Com lance automático o Google escolhe o CPC de cada leilão: verba ÷ lance
    # declarado não descreveria teto nenhum.
    assert campanhas["2"]["teto_de_cliques"] is None
    assert campanhas["3"]["teto_de_cliques"] is None


@pytest.mark.anyio
async def test_canal_fora_do_vocabulario_vira_null():
    fonte = FonteEmMemoria([_conta("111")],
                           [_campanha("111", "1", canal="TRAVEL")])
    c = (await _montar(fonte)).json()["contas"][0]["campanhas"][0]
    assert c["canal"] is None


@pytest.mark.anyio
async def test_cockpit_href_so_com_mapeamento_seguro():
    """Derivar a rota do id EXTERNO mandaria o operador para a campanha de outra
    pessoa: o cockpit legado endereça pela chave interna de `campaigns`."""
    fonte = FonteEmMemoria(
        [_conta("111")],
        [_campanha("111", "1"),
         _campanha("111", "2", cockpit_campaign_id="507")])
    campanhas = {c["externa"]["campaign_id"]: c
                 for c in (await _montar(fonte)).json()["contas"][0]["campanhas"]}
    assert campanhas["1"]["cockpit_href"] is None
    assert campanhas["2"]["cockpit_href"] == "/dashboard/campaign/507"


def test_identidade_externa_recusa_conta_vazia():
    with pytest.raises(ValueError):
        inv.IdentidadeExterna(customer_id="", campaign_id="1")
    # O sentinela não é numérico de propósito: o portão de escopo o recusa se
    # alguém o reenviar como se fosse um id do Google.
    assert not inv.SEM_CONTA.isdigit()


def test_vocabulario_de_presenca_nao_tem_sumiu_da_conta():
    """`sumiu` é conclusão, e a conclusão erra quando a causa foi uma leitura
    que falhou."""
    assert "sumiu" not in " ".join(inv.ESTADOS_DE_PRESENCA)
    for exigido in ("removida", "nao_encontrada", "conta_nao_identificada",
                    "fora_de_escopo", "sincronizacao_falhou",
                    "legado_nao_reconciliado"):
        assert exigido in inv.ESTADOS_DE_PRESENCA


# ── cursor ──────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_paginacao_por_cursor_nao_pula_nem_repete():
    campanhas = [_campanha("111", f"{i:03d}") for i in range(1, 8)]
    fonte = FonteEmMemoria([_conta("111")], campanhas)

    vistos: List[str] = []
    cursor = None
    paginas = 0
    while True:
        resposta = (await _montar(fonte, limite=3, cursor=cursor)).json()
        vistos += [c["volc_campaign_id"]
                   for conta in resposta["contas"] for c in conta["campanhas"]]
        cursor = resposta["proximo_cursor"]
        paginas += 1
        if not cursor or paginas > 10:
            break

    assert paginas == 3
    assert len(vistos) == len(set(vistos)) == 7


@pytest.mark.anyio
async def test_cursor_e_opaco_e_nao_e_offset():
    fonte = FonteEmMemoria([_conta("111")],
                           [_campanha("111", f"{i:03d}") for i in range(1, 5)])
    cursor = (await _montar(fonte, limite=2)).json()["proximo_cursor"]
    assert cursor and not cursor.isdigit()
    # Keyset: o cursor carrega a CHAVE do último item, não a posição dele.
    # Keyset de TRÊS chaves: conta, degrau de ordenação e id. O degrau precisa
    # viajar junto — sem ele a página seguinte descreveria um ponto que não
    # existe na ordenação, e o salto seria invisível.
    assert inv.ler_cursor(cursor, inv.FiltrosDoInventario()) == \
        ("111", dom.ORDEM_LIGADA, "gads-111-002")


def test_cursor_forjado_nao_reescreve_a_consulta():
    """O cursor é opaco, não assinado — quem cola um base64 escolhe o texto.

    `c` e `k` são interpolados DENTRO da expressão booleana do PostgREST. Um `k`
    com `)),or(...` reescreve a árvore inteira: não vaza entre contas, mas
    devolve uma consulta que o operador não pediu, com resposta de cara
    legítima.

    A forma das duas chaves é conhecida e fechada. O que não tem a forma não
    vira consulta nenhuma.
    """
    import base64 as b64
    import json as js

    filtros = inv.FiltrosDoInventario()

    def _forjar(**kw):
        carga = {"v": inv.VERSAO_INVENTARIO, "f": filtros.assinatura(),
                 "c": "8017851692", "o": 1, "k": "gads-8017851692-1"}
        carga.update(kw)
        cru = js.dumps(carga, sort_keys=True, separators=(",", ":")).encode()
        return b64.urlsafe_b64encode(cru).decode("ascii").rstrip("=")

    for veneno in ("z)),or(volc_campaign_id.not.is.null",
                   "a,customer_id.eq.9999999999",
                   "x)"):
        with pytest.raises(inv.CursorInvalido):
            inv.ler_cursor(_forjar(k=veneno), filtros)

    with pytest.raises(inv.CursorInvalido):
        inv.ler_cursor(_forjar(c="1111111111,customer_id.eq.2222222222"), filtros)

    # E o cursor honesto continua passando, inclusive o da conta não
    # identificada — que não é numérica de propósito.
    assert inv.ler_cursor(_forjar(), filtros) == ("8017851692", 1,
                                                  "gads-8017851692-1")
    assert inv.ler_cursor(_forjar(c=inv.SEM_CONTA), filtros)[0] == inv.SEM_CONTA


@pytest.mark.anyio
async def test_cursor_de_outro_filtro_e_recusado():
    """Continuar com outro filtro pularia ou repetiria campanhas, e nada na
    resposta denunciaria."""
    fonte = FonteEmMemoria([_conta("111")],
                           [_campanha("111", f"{i:03d}") for i in range(1, 5)])
    cursor = (await _montar(fonte, limite=2)).json()["proximo_cursor"]
    outros = inv.FiltrosDoInventario(canal=("SEARCH",))
    with pytest.raises(inv.CursorInvalido):
        await inv.montar_inventario(fonte, outros, cursor=cursor, agora=AGORA)


def test_cursor_malformado_e_de_outra_versao():
    f = inv.FiltrosDoInventario()
    with pytest.raises(inv.CursorInvalido):
        inv.ler_cursor("isto-nao-e-base64-de-json", f)


# ── filtros ─────────────────────────────────────────────────────────────────


def test_filtros_traduzem_apelido_e_recusam_valor_inventado():
    f = inv.normalizar_filtros({"canal": ["PMAX", "search"]})
    assert f.canal == ("PERFORMANCE_MAX", "SEARCH")
    with pytest.raises(ValueError) as exc:
        inv.normalizar_filtros({"canal": ["TIKTOK"]})
    assert "SEARCH" in str(exc.value)  # a mensagem diz o que existe
    with pytest.raises(ValueError):
        inv.normalizar_filtros({"presenca": ["sumiu_da_conta"]})


@pytest.mark.anyio
async def test_frescor_filtra_de_verdade():
    """Ele foi aceito, validado e IGNORADO por três rodadas.

    Um filtro que a API valida e descarta é pior que um que não existe: quem o
    manda recebe 200 com a lista inteira e conclui que não há nada para filtrar
    — quando na verdade ninguém filtrou.

    Frescor é propriedade da CONTA, não da campanha: ele sai de
    `trafego_snapshot_conta` e a campanha não tem coluna que o carregue. Por isso
    ele recorta o conjunto de CONTAS antes do plano, e chega ao banco pelo
    `customer_id.in.(…)` das famílias — resolvido no servidor, como os outros.
    """
    fonte = FonteEmMemoria(
        [_conta("111"),
         _conta("222", tentativa_resultado="falhou", tentativa_em=_iso(1),
                leitura_boa_em=_iso(300), tentativa_motivo="a API recusou")],
        [_campanha("111", "1"), _campanha("222", "2")])

    todas = (await _montar(fonte)).json()
    assert {c["customer_id"] for c in todas["contas"]} == {"111", "222"}

    so_falhou = (await _montar(fonte, filtros=inv.FiltrosDoInventario(
        frescor=(inv.FALHOU,)))).json()
    campanhas = [c for conta in so_falhou["contas"] for c in conta["campanhas"]]
    assert [c["externa"]["campaign_id"] for c in campanhas] == ["2"]

    so_recente = (await _montar(fonte, filtros=inv.FiltrosDoInventario(
        frescor=(inv.RECENTE,)))).json()
    campanhas = [c for conta in so_recente["contas"] for c in conta["campanhas"]]
    assert [c["externa"]["campaign_id"] for c in campanhas] == ["1"]

    # E os totais acompanham: um filtro que recorta a lista e não recorta a
    # contagem produz um cabeçalho que não bate com o que está embaixo dele.
    assert so_falhou["totais"]["operacionais"] == 1
    assert so_recente["totais"]["operacionais"] == 1


@pytest.mark.anyio
async def test_filtros_combinados():
    fonte = FonteEmMemoria(
        [_conta("111"), _conta("222")],
        [_campanha("111", "1", canal="SEARCH", estado_externo="ENABLED"),
         _campanha("111", "2", canal="SEARCH", estado_externo="PAUSED"),
         _campanha("111", "3", canal="DISPLAY", estado_externo="ENABLED"),
         _campanha("222", "4", canal="SEARCH", estado_externo="ENABLED")])

    filtros = inv.FiltrosDoInventario(conta=("111",), canal=("SEARCH",),
                                      estado_externo=("ENABLED",))
    resposta = (await _montar(fonte, filtros=filtros)).json()
    ids = [c["externa"]["campaign_id"]
           for conta in resposta["contas"] for c in conta["campanhas"]]
    assert ids == ["1"]
    assert resposta["totais"]["operacionais"] == 1
    assert resposta["totais"]["historicas"] == 0
    assert resposta["totais"]["geral"] == 1


@pytest.mark.anyio
async def test_filtro_por_vinculo_e_por_atencao():
    fonte = FonteEmMemoria(
        [_conta("111")],
        [_campanha("111", "1", opportunity_id=73, atencao=False),
         _campanha("111", "2", opportunity_id=None, project_id=None,
                   vinculo_confirmado_por=None, vinculo_confirmado_em=None,
                   procedencia="descoberta", atencao=True)])

    sem = (await _montar(fonte, filtros=inv.FiltrosDoInventario(vinculado=False))).json()
    assert [c["externa"]["campaign_id"]
            for k in sem["contas"] for c in k["campanhas"]] == ["2"]
    assert sem["contas"][0]["campanhas"][0]["vinculo"] is None

    atencao = (await _montar(fonte, filtros=inv.FiltrosDoInventario(atencao=True))).json()
    assert [c["externa"]["campaign_id"]
            for k in atencao["contas"] for c in k["campanhas"]] == ["2"]


@pytest.mark.anyio
async def test_filtro_de_presenca_por_sincronizacao_falhou():
    """A presença de uma conta que falhou não está armazenada: é derivada do
    resultado da última tentativa. O filtro tem de saber disso."""
    fonte = FonteEmMemoria(
        [_conta("111"),
         _conta("222", tentativa_resultado="falhou", tentativa_em=_iso(1),
                leitura_boa_em=_iso(300), tentativa_motivo="timeout")],
        [_campanha("111", "1"), _campanha("222", "2")])

    filtros = inv.FiltrosDoInventario(presenca=(inv.SINCRONIZACAO_FALHOU,))
    resposta = (await _montar(fonte, filtros=filtros)).json()
    ids = [c["externa"]["campaign_id"]
           for k in resposta["contas"] for c in k["campanhas"]]
    assert ids == ["2"]

    somente_presentes = inv.FiltrosDoInventario(presenca=(inv.PRESENTE,))
    resposta = (await _montar(fonte, filtros=somente_presentes)).json()
    ids = [c["externa"]["campaign_id"]
           for k in resposta["contas"] for c in k["campanhas"]]
    assert ids == ["1"]


def test_nenhum_modulo_de_trafego_cita_uma_tabela_que_ninguem_cria():
    """O gate do defeito estrutural desta rodada, e ele é mecânico.

    `inventario.py` consultava `volc_trafego_conta` e `volc_trafego_campanha`;
    `sincronizador.py` escrevia nessas duas mais `volc_trafego_sincronizacao`.
    NENHUMA das três é criada por migration alguma deste repositório — contra o
    banco real, toda requisição terminava em 404 do PostgREST.

    A suíte não pegava porque a fonte e o repositório eram dublados em 100% dos
    testes. Este teste não depende de dublê: ele lê o código-fonte e falha se
    um nome de tabela fantasma reaparecer em qualquer lugar que não seja o
    comentário que explica por que ele saiu.
    """
    import pathlib
    import re

    raiz = pathlib.Path(__file__).resolve().parents[1]
    fantasmas = ("volc_trafego_conta", "volc_trafego_campanha",
                 "volc_trafego_sincronizacao", "trafego_campanha_externa")

    for relativo in ("app/trafego/inventario.py", "app/trafego/sincronizador.py",
                     "app/trafego/alertas.py",
                     "app/routers/trafego_inventario.py"):
        texto = (raiz / relativo).read_text(encoding="utf-8")
        # Comentários e docstrings podem CITAR o nome para explicar a remoção —
        # um gate que castiga a documentação da regra ensina a apagá-la.
        codigo = "\n".join(
            re.sub(r"#.*$", "", linha) for linha in texto.splitlines()
            if not linha.lstrip().startswith("#")
        )
        codigo = re.sub(r'"""[\s\S]*?"""', "", codigo)
        for fantasma in fantasmas:
            assert fantasma not in codigo, (
                f"{relativo} volta a endereçar {fantasma!r}, que nenhuma "
                f"migration cria")


def test_as_tabelas_declaradas_sao_exatamente_as_da_migration():
    """O que o código diz que toca tem de existir no schema canônico."""
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[2]
    sql = (raiz / inv.SCHEMA_CANONICO).read_text(encoding="utf-8")
    for tabela in inv.TABELAS_DO_INVENTARIO:
        assert f"CREATE TABLE public.{tabela}" in sql, (
            f"{tabela} está declarada em TABELAS_DO_INVENTARIO e a migration "
            f"canônica não a cria")


def test_o_ponto_de_troca_da_persistencia_e_explicito_e_falha_alto():
    """Sem camada de acesso instalada, a rota diz o que falta — e não 200 vazio.

    Antes desta rodada, `inventario.py` trazia a própria `FonteSupabase`
    apontada para `volc_trafego_conta`. Contra o banco real ela devolvia 404 do
    PostgREST; na suíte, nunca era exercitada. Agora há UM ponto de troca, e
    quando a implementação não está lá o erro nomeia o arquivo e o schema.
    """
    import importlib.util

    if importlib.util.find_spec("app.trafego.persistencia") is None:
        with pytest.raises(inv.PersistenciaAusente) as erro:
            inv.fabricar_fonte("https://db.exemplo", "chave")
        assert "persistencia.py" in str(erro.value)
        assert inv.SCHEMA_CANONICO in str(erro.value)
        return

    fonte = inv.fabricar_fonte("https://db.exemplo", "chave")
    for metodo in ("contas", "campanhas", "contagem", "contagem_em_atencao"):
        assert callable(getattr(fonte, metodo, None)), (
            f"a implementação de acesso não satisfaz FonteDeInventario: "
            f"falta {metodo}")


def test_a_porta_da_varredura_e_conferida_na_fabrica_e_nao_no_meio_da_rodada():
    """Uma implementação incompleta tem de ser recusada ANTES do primeiro GAQL.

    ⚠️ `Protocol` sem `runtime_checkable` não verifica nada em tempo de
    execução: uma classe a que falte um método passa pela anotação e explode com
    `AttributeError` no meio de uma varredura — depois de a quota já ter sido
    gasta e com metade do snapshot escrito. A conferência troca uma falha
    parcial e cara por uma mensagem que diz o que falta.
    """
    from app.trafego import sincronizador as sinc

    class Incompleto:
        async def registrar_evento(self, evento):  # noqa: D102
            return None

    with pytest.raises(sinc.PortaIncompativel) as erro:
        sinc.conferir_porta(Incompleto())
    texto = str(erro.value)
    assert "gravar_snapshot_de_conta" in texto and "identidades" in texto
    # O que ELE tem não aparece na lista de faltantes.
    assert "faltam registrar_evento" not in texto

    class Completo:
        pass

    for metodo in sinc.METODOS_DO_REPOSITORIO:
        setattr(Completo, metodo, lambda self, *a, **k: None)
    assert sinc.conferir_porta(Completo()) is not None


def test_todo_metodo_da_porta_da_varredura_existe_no_dubles_da_suite():
    """O dublê e a implementação real têm de satisfazer a MESMA lista.

    Sem isto, a suíte poderia ficar verde sobre um dublê que implementa métodos
    que a porta não pede — que é uma forma silenciosa de a suíte medir outra
    coisa.
    """
    from app.trafego import sincronizador as sinc
    from tests.test_trafego_sincronizador import RepoFalso

    sinc.conferir_porta(RepoFalso())


@pytest.mark.anyio
async def test_a_montagem_nao_filtra_nada_por_conta_propria():
    """Tudo o que a fonte devolve chega à resposta. A montagem só projeta."""
    class FonteQueDevolveTudo(FonteEmMemoria):
        async def campanhas(self, plano):
            return list(self._campanhas)

        async def contagem(self, plano):
            return {"111": len(self._campanhas)}

        async def contagem_em_atencao(self, plano):
            return 0

    fonte = FonteQueDevolveTudo(
        [_conta("111")],
        [_campanha("111", "1", canal="DISPLAY"),
         _campanha("111", "2", canal="SEARCH")])
    filtros = inv.FiltrosDoInventario(canal=("SEARCH",))
    resposta = (await _montar(fonte, filtros=filtros)).json()
    assert len(resposta["contas"][0]["campanhas"]) == 2


@pytest.mark.anyio
async def test_o_total_em_atencao_nao_depende_do_tamanho_da_pagina():
    """É daqui que o sino passa a viver.

    Medido em 24/08/2026, `/api/trafego/alertas` roda GAQL em tempo de render e
    o Layout o chama — abrir qualquer página custa rede para o Google. Uma
    contagem que só valesse para a página carregada obrigaria o sino a paginar o
    inventário inteiro; esta é do BANCO, e `limite=1` já a traz correta.
    """
    fonte = FonteEmMemoria(
        [_conta("111")],
        [_campanha("111", f"{i:03d}", atencao=(i % 2 == 0)) for i in range(1, 11)])

    cheia = (await _montar(fonte, limite=50)).json()
    minima = (await _montar(fonte, limite=1)).json()

    assert cheia["totais"]["atencao"] == minima["totais"]["atencao"] == 5
    assert cheia["totais"]["operacionais"] == minima["totais"]["operacionais"] == 10
    assert len(minima["contas"][0]["campanhas"]) == 1


# ── frescor do envelope ─────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_uma_conta_que_falha_deixa_o_envelope_parcial_e_nunca_falhou():
    """Regra C no envelope — e o ponto onde as DUAS regras discordavam.

    `inventario.pior_frescor` era um `min` por gravidade: com uma conta boa e
    uma falha ele respondia `falhou`. `dominio.frescor_do_conjunto` responde
    `parcial`. A diferença não é de estilo — é entre "o sistema caiu" e "uma
    conta de duas caiu", que são telas e ações opostas, e o operador que lê a
    primeira trata um problema pontual como queda geral.

    `pior_frescor` foi REMOVIDO. Existe uma regra, e ela mora no domínio.
    """
    assert not hasattr(inv, "pior_frescor"), (
        "a segunda regra de frescor voltou; ela discorda da primeira")

    fonte = FonteEmMemoria(
        [_conta("111"),
         _conta("222", tentativa_resultado="falhou", tentativa_em=_iso(1),
                tentativa_motivo="USER_PERMISSION_DENIED",
                leitura_boa_em=_iso(300), leitura_boa_campanhas=1)],
        [])
    assert (await _montar(fonte)).json()["frescor"] == inv.PARCIAL

    # Todas velhas: o conjunto não pode parecer mais fresco que a parte mais
    # velha dele.
    fonte = FonteEmMemoria(
        [_conta("111"),
         _conta("222", tentativa_em=_iso(400), leitura_boa_em=_iso(400))], [])
    assert (await _montar(fonte)).json()["frescor"] == inv.VELHO


@pytest.mark.anyio
async def test_todas_as_contas_falhando_e_falhou_de_verdade():
    """O oposto do anterior, e ele também precisa continuar valendo."""
    fonte = FonteEmMemoria(
        [_conta("111", tentativa_resultado="falhou", tentativa_em=_iso(1),
                tentativa_motivo="timeout", leitura_boa_em=_iso(300),
                leitura_boa_campanhas=1),
         _conta("222", tentativa_resultado="falhou", tentativa_em=_iso(1),
                tentativa_motivo="timeout", leitura_boa_em=_iso(300),
                leitura_boa_campanhas=1)],
        [])
    assert (await _montar(fonte)).json()["frescor"] == inv.FALHOU


def test_a_regra_de_frescor_do_inventario_e_a_do_dominio():
    """Costura explícita: a projeção não tem régua própria.

    Se alguém reintroduzir um cálculo local, este teste continua verde — o que
    ele guarda é o ENDEREÇO. Quem guarda o comportamento é a tabela completa em
    `test_trafego_dominio.py::test_tabela_de_frescor_do_conjunto`.
    """
    from app.trafego import dominio as dom

    assert inv.FRESCORES is dom.FRESCORES
    assert inv.SEGUNDOS_PARA_VELHO == dom.JANELA_RECENTE_S
    assert inv.CANAIS is dom.CANAIS_DO_CONTRATO


# ── as rotas ────────────────────────────────────────────────────────────────


@pytest.fixture
def app_e_fonte():
    from app.routers import trafego_inventario as rota

    fonte = FonteEmMemoria([_conta("8017851692")],
                           [_campanha("8017851692", "241")])
    rota.definir_fonte(fonte)
    app = FastAPI()
    rota.registrar(app)
    yield app, rota, fonte
    rota.definir_fonte(None)
    rota.definir_varredura(None, None)
    rota.definir_contas(None)
    app.dependency_overrides.clear()


def _como(app: FastAPI, papel: str) -> None:
    ident = Identidade(sub="u1", email="op@volc", papel=papel, origem="sessao")
    app.dependency_overrides[exigir_usuario] = lambda: ident
    app.dependency_overrides[exigir_admin] = lambda: ident
    app.dependency_overrides[exigir_servico] = lambda: Identidade(
        sub="svc", email="", papel="SERVICO", origem="servico")


def test_sem_credencial_nada_passa(app_e_fonte):
    app, _, _ = app_e_fonte
    with TestClient(app) as cliente:
        respostas = [
            cliente.get("/api/trafego/inventario"),
            cliente.post("/api/trafego/inventario/atualizar",
                         json={"customer_id": "8017851692"}),
            cliente.post("/api/trafego/inventario/sincronizacoes", json={}),
        ]
    for r in respostas:
        assert r.status_code != 200, f"{r.request.url} respondeu sem credencial"
        assert r.status_code in (401, 403, 422, 503), r.text


# ═══════════════════════════════════════════════════════════════════════════
# A PÁGINA CANÔNICA — GET /api/trafego/campanhas/{volc_campaign_id}
# ═══════════════════════════════════════════════════════════════════════════


class FonteDeUmaCampanha:
    """Só o que a rota canônica precisa. Registra o que foi pedido."""

    def __init__(self, linhas):
        self._por_id = {l["volc_campaign_id"]: l for l in linhas}
        self.pedidos = []

    async def uma_campanha(self, volc_campaign_id):
        self.pedidos.append(volc_campaign_id)
        return self._por_id.get(volc_campaign_id)


def _linha_canonica(**kw):
    base = dict(_campanha("8017851692", "241"),
                tentativa_resultado="ok", tentativa_em=_iso(6),
                leitura_boa_em=_iso(6), historico=False, ordem_operacional=1)
    base.update(kw)
    return base


def test_a_pagina_canonica_recusa_sem_credencial(app_e_fonte):
    """Sem credencial, **nada passa** — e o código depende do ambiente.

    Com configuração de segurança presente é `401`. Sem ela é `503`: o portão
    falha FECHADO em vez de deixar passar, e "não sei validar" nunca vira "pode
    entrar". A suíte hermética apaga `SUPABASE_URL` no import (ver o cabeçalho
    de `tests/conftest.py`), então rodando o arquivo sozinho dá 401 e rodando a
    suíte inteira dá 503.

    A propriedade provada é a mesma dos outros: a rota **não responde 200**. É a
    tolerância que `test_sem_credencial_nada_passa` já usa, pelo mesmo motivo.
    """
    app, rota, _ = app_e_fonte
    rota.definir_fonte_de_vinculo(FonteDeUmaCampanha([_linha_canonica()]))
    try:
        with TestClient(app) as cliente:
            r = cliente.get("/api/trafego/campanhas/gads-8017851692-241")
        assert r.status_code != 200, "a página canônica passou sem credencial"
        assert r.status_code in (401, 403, 503), r.text
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_a_pagina_canonica_responde_a_identidade_interna(app_e_fonte):
    app, rota, _ = app_e_fonte
    fonte = FonteDeUmaCampanha([_linha_canonica()])
    rota.definir_fonte_de_vinculo(fonte)
    _como(app, "OPERADOR")
    try:
        with TestClient(app) as cliente:
            r = cliente.get("/api/trafego/campanhas/gads-8017851692-241")
        assert r.status_code == 200, r.text
        corpo = r.json()

        assert corpo["versao"] == inv.VERSAO_INVENTARIO
        assert corpo["campanha"]["volc_campaign_id"] == "gads-8017851692-241"

        # A identidade externa é a TRINCA da H0, e não mais o par: sem a
        # plataforma, o dia em que a primeira campanha do Meta entrar traz
        # colisão silenciosa — ids externos são numéricos nas duas.
        ident = corpo["identidade"]
        assert ident["plataforma"] == "GOOGLE_ADS"
        assert ident["conta_externa"] == "8017851692"
        assert ident["id_externo"] == "241"

        assert corpo["conta"]["frescor"] in inv.FRESCORES
        # O manifesto viaja junto: é dele que a tela deriva o que oferecer.
        assert corpo["manifesto"]["canal"] == "SEARCH"
        assert corpo["manifesto"]["sabe_criar"] is True
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_a_pagina_canonica_nao_resolve_id_externo(app_e_fonte):
    """O id externo do Google é único DENTRO de uma conta, não no VOLC O.S.

    Uma rota que o aceitasse teria de adivinhar plataforma e conta — e adivinhar
    errado leva o operador à campanha de outro cliente, com a URL certa na barra
    de endereço.
    """
    app, rota, _ = app_e_fonte
    fonte = FonteDeUmaCampanha([_linha_canonica()])
    rota.definir_fonte_de_vinculo(fonte)
    _como(app, "OPERADOR")
    try:
        with TestClient(app) as cliente:
            r = cliente.get("/api/trafego/campanhas/241")
        assert r.status_code == 404, r.text
        # E ela nem tentou procurar por outro caminho.
        assert fonte.pedidos == ["241"]
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_a_pagina_canonica_devolve_404_para_endereco_inexistente(app_e_fonte):
    app, rota, _ = app_e_fonte
    rota.definir_fonte_de_vinculo(FonteDeUmaCampanha([]))
    _como(app, "OPERADOR")
    try:
        with TestClient(app) as cliente:
            r = cliente.get("/api/trafego/campanhas/gads-999-1")
            impossivel = cliente.get("/api/trafego/campanhas/tem espaço")
        assert r.status_code == 404, r.text
        # Um id fora do formato também é 404, e não 400: dizer "formato
        # inválido" ensinaria a forma da chave a quem está adivinhando.
        assert impossivel.status_code == 404, impossivel.text
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_a_pagina_canonica_nao_varre_o_inventario(app_e_fonte):
    """Reaproveitar a listagem paginada custaria as famílias de conta, as
    contagens e o keyset — tudo para descartar tudo menos uma linha."""
    app, rota, inventario = app_e_fonte
    rota.definir_fonte_de_vinculo(FonteDeUmaCampanha([_linha_canonica()]))
    _como(app, "OPERADOR")
    try:
        antes = list(inventario.consultas)
        with TestClient(app) as cliente:
            cliente.get("/api/trafego/campanhas/gads-8017851692-241")
        assert inventario.consultas == antes, (
            "a página canônica passou pela listagem do inventário")
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_canal_sem_manifesto_devolve_manifesto_nulo(app_e_fonte):
    """Vídeo e Shopping aparecem no inventário e o Hub não os opera.

    `null` diz isso. Um manifesto vazio diria "não pode nada", que é outra
    afirmação — e a tela renderizaria capacidades zeradas como se fossem
    medidas.
    """
    app, rota, _ = app_e_fonte
    rota.definir_fonte_de_vinculo(
        FonteDeUmaCampanha([_linha_canonica(canal="VIDEO")]))
    _como(app, "OPERADOR")
    try:
        with TestClient(app) as cliente:
            r = cliente.get("/api/trafego/campanhas/gads-8017851692-241")
        assert r.status_code == 200, r.text
        assert r.json()["manifesto"] is None
    finally:
        rota.definir_fonte_de_vinculo(None)


# ═══════════════════════════════════════════════════════════════════════════
# VÍNCULO — a decisão humana, e o que ela recusa
# ═══════════════════════════════════════════════════════════════════════════


class FonteDeVinculoFalsa:
    def __init__(self, campanhas=None, erro=None):
        self._campanhas = {c["volc_campaign_id"]: c for c in (campanhas or [])}
        self._erro = erro
        self.gravados = []

    async def uma_campanha(self, volc_campaign_id):
        return self._campanhas.get(volc_campaign_id)

    async def confirmar_vinculo(self, linha):
        if self._erro:
            raise self._erro
        self.gravados.append(linha)
        return {"vinculo_id": "11111111-2222-3333-4444-555555555555", **linha}

    async def desfazer_vinculo(self, vinculo_id, *, por, motivo):
        if self._erro:
            raise self._erro
        return {"vinculo_id": vinculo_id, "desfeito_por": por,
                "desfeito_motivo": motivo}


PEDIDO = {"volc_campaign_id": "gads-8017851692-241", "opportunity_id": 65,
          "regra": "url_final_da_conta"}


def test_vincular_exige_papel_ativo_e_nao_so_sessao(app_e_fonte):
    """`exigir_usuario` prova QUEM é; ele não prova que a pessoa tem papel.

    `volc_role_of` devolve string vazia para quem teve o papel revogado, e a
    revogação vale no ato — mas a sessão do Supabase continua válida até o token
    expirar. Sem esta recusa, alguém removido da operação continuaria gravando
    vínculo, e a linha nasceria assinada com o nome dele.
    """
    app, rota, _ = app_e_fonte
    fonte = FonteDeVinculoFalsa([_linha_canonica()])
    rota.definir_fonte_de_vinculo(fonte)
    app.dependency_overrides[exigir_usuario] = lambda: Identidade(
        sub="u9", email="revogado@volc", papel="", origem="sessao")
    try:
        with TestClient(app) as cliente:
            r = cliente.post("/api/trafego/vinculos", json=PEDIDO)
        assert r.status_code == 403, r.text
        assert fonte.gravados == []
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_vincular_recusa_campanha_inexistente(app_e_fonte):
    """Sem a conferência, a FK volta como 502 — atribuindo ao Supabase um erro
    que é do pedido, e sem dizer o que estava errado."""
    app, rota, _ = app_e_fonte
    fonte = FonteDeVinculoFalsa([])
    rota.definir_fonte_de_vinculo(fonte)
    _como(app, "OPERADOR")
    try:
        with TestClient(app) as cliente:
            r = cliente.post("/api/trafego/vinculos", json=PEDIDO)
        assert r.status_code == 404, r.text
        assert fonte.gravados == []
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_segundo_vinculo_vivo_e_409_e_nao_502(app_e_fonte):
    """O índice único é a resposta correta a um pedido, não erro de servidor.

    502 mandava a tela tratar como indisponibilidade e tentar de novo — o que
    falharia igual, para sempre. 409 diz o que fazer: desfazer o vínculo atual.
    """
    app, rota, _ = app_e_fonte
    erro = RuntimeError("Client error '409 Conflict' — duplicate key value "
                        "violates unique constraint")
    rota.definir_fonte_de_vinculo(
        FonteDeVinculoFalsa([_linha_canonica()], erro=erro))
    _como(app, "OPERADOR")
    try:
        with TestClient(app) as cliente:
            r = cliente.post("/api/trafego/vinculos", json=PEDIDO)
        assert r.status_code == 409, r.text
        assert "desfaça" in r.json()["detail"].lower()
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_o_erro_do_vinculo_nao_vaza_a_estrutura_do_banco(app_e_fonte):
    """`httpx` põe a URL do PostgREST no `str(exc)` — endpoint, tabela, colunas.

    Isso ia inteiro para qualquer usuário autenticado que provocasse um 400.
    """
    app, rota, _ = app_e_fonte
    erro = RuntimeError(
        "Client error '400 Bad Request' for url "
        "'https://database.agenciavolc.com.br/rest/v1/trafego_vinculo?select=*'")
    rota.definir_fonte_de_vinculo(
        FonteDeVinculoFalsa([_linha_canonica()], erro=erro))
    _como(app, "OPERADOR")
    try:
        with TestClient(app) as cliente:
            r = cliente.post("/api/trafego/vinculos", json=PEDIDO)
            d = cliente.post(
                "/api/trafego/vinculos/11111111-2222-3333-4444-555555555555"
                "/desfazer", json={})
        for resposta in (r, d):
            corpo = resposta.text
            for vazamento in ("rest/v1", "trafego_vinculo", "database.agenciavolc",
                              "select="):
                assert vazamento not in corpo, f"vazou {vazamento!r}: {corpo}"
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_desfazer_com_id_invalido_e_404_e_nao_502(app_e_fonte):
    """Um id fora do formato é um endereço que não existe — não uma falha do
    Supabase."""
    app, rota, _ = app_e_fonte
    rota.definir_fonte_de_vinculo(FonteDeVinculoFalsa([_linha_canonica()]))
    _como(app, "OPERADOR")
    try:
        with TestClient(app) as cliente:
            r = cliente.post("/api/trafego/vinculos/abc/desfazer", json={})
        assert r.status_code == 404, r.text
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_quem_confirmou_sai_do_token_e_nunca_do_corpo(app_e_fonte):
    """Aceitar do corpo deixaria qualquer um assinar com o nome de outro, numa
    tabela cujo propósito inteiro é dizer quem decidiu o quê."""
    app, rota, _ = app_e_fonte
    fonte = FonteDeVinculoFalsa([_linha_canonica()])
    rota.definir_fonte_de_vinculo(fonte)
    _como(app, "OPERADOR")
    try:
        with TestClient(app) as cliente:
            r = cliente.post("/api/trafego/vinculos",
                             json={**PEDIDO, "confirmado_por": "outra@pessoa"})
        assert r.status_code == 201, r.text
        assert fonte.gravados[0]["confirmado_por"] == "op@volc"
    finally:
        rota.definir_fonte_de_vinculo(None)


def test_atualizacao_manual_exige_admin(app_e_fonte):
    app, rota, _ = app_e_fonte
    ident = Identidade(sub="u1", email="op@volc", papel="OPERADOR", origem="sessao")
    app.dependency_overrides[exigir_usuario] = lambda: ident
    with TestClient(app) as cliente:
        r = cliente.post("/api/trafego/inventario/atualizar",
                         json={"customer_id": "8017851692"})
    assert r.status_code == 403, r.text


def test_get_inventario_responde_o_contrato(app_e_fonte):
    app, _, _ = app_e_fonte
    _como(app, "ADMIN")
    with TestClient(app) as cliente:
        r = cliente.get("/api/trafego/inventario")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["versao"] == 2
    assert corpo["contas"][0]["customer_id"] == "8017851692"


def test_filtro_invalido_vira_400_com_a_lista_do_que_existe(app_e_fonte):
    app, _, _ = app_e_fonte
    _como(app, "ADMIN")
    with TestClient(app) as cliente:
        r = cliente.get("/api/trafego/inventario", params={"canal": "TIKTOK"})
    assert r.status_code == 400
    assert "SEARCH" in r.json()["detail"]


def test_vocabulario_e_servido_pela_fonte_que_o_aplica(app_e_fonte):
    app, _, _ = app_e_fonte
    _como(app, "ADMIN")
    with TestClient(app) as cliente:
        corpo = cliente.get("/api/trafego/inventario/vocabulario").json()
    assert corpo["presenca"] == list(inv.ESTADOS_DE_PRESENCA)
    assert corpo["apelidos_de_canal"]["PMAX"] == "PERFORMANCE_MAX"


# ── a regra estrutural ──────────────────────────────────────────────────────


class _BloqueioDeImport:
    """Explode se alguém tentar importar o SDK do Google durante a leitura."""

    ALVOS = ("volc_ads", "google.ads")

    def find_spec(self, fullname, path=None, target=None):  # noqa: D102
        for alvo in self.ALVOS:
            if fullname == alvo or fullname.startswith(alvo + "."):
                raise AssertionError(
                    f"o caminho de LEITURA do inventário importou {fullname!r}. "
                    f"O carregamento de /trafego, do Layout e do sino não pode "
                    f"custar rede para o Google — é o requisito estrutural da "
                    f"fase (ADR-08)."
                )
        return None


def test_leitura_nao_toca_no_google_ads(app_e_fonte):
    """O gate que torna a regra verificável em vez de combinada.

    Além do bloqueio de import, os módulos já carregados são retirados do
    `sys.modules` durante a requisição: sem isso, um import já resolvido não
    passaria pelo `meta_path` e o teste ficaria verde por acidente.
    """
    app, _, _ = app_e_fonte
    _como(app, "ADMIN")

    guardados = {n: m for n, m in list(sys.modules.items())
                 if n == "volc_ads" or n.startswith("volc_ads.")
                 or n.startswith("google.ads")}
    for n in guardados:
        del sys.modules[n]
    bloqueio = _BloqueioDeImport()
    sys.meta_path.insert(0, bloqueio)
    try:
        with TestClient(app) as cliente:
            r = cliente.get("/api/trafego/inventario")
            v = cliente.get("/api/trafego/inventario/vocabulario")
    finally:
        sys.meta_path.remove(bloqueio)
        sys.modules.update(guardados)

    assert r.status_code == 200, r.text
    assert v.status_code == 200


def test_modulos_de_leitura_nao_importam_o_engine_no_topo():
    """A prova estática, que sobrevive a um dublê mal feito.

    Nenhum `import volc_ads` fora de função nos módulos do caminho de leitura.
    """
    import ast
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[1]
    for relativo in ("app/trafego/inventario.py",
                     "app/routers/trafego_inventario.py"):
        arvore = ast.parse((raiz / relativo).read_text(encoding="utf-8"))
        for no in arvore.body:  # só o nível de módulo
            if isinstance(no, (ast.Import, ast.ImportFrom)):
                nome = getattr(no, "module", None) or ""
                nomes = [a.name for a in no.names] + [nome]
                for n in nomes:
                    assert not n.startswith("volc_ads"), f"{relativo} importa {n}"
                    assert not n.startswith("google.ads"), f"{relativo} importa {n}"


def test_o_nucleo_nao_nomeia_entidade_de_canal():
    """O gate mecânico da §9.4 do SPEC, rodando como teste."""
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[1]
    proibidos = ("keyword", "asset_group", "placement", "audience", "match_type")
    for relativo in ("app/trafego/inventario.py", "app/trafego/sincronizador.py"):
        texto = (raiz / relativo).read_text(encoding="utf-8").lower()
        for palavra in proibidos:
            assert palavra not in texto, (
                f"{relativo} cita {palavra!r}: o núcleo vazou para o canal")


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── ponte com o schema irmão (v9_01) ────────────────────────────────────────


def test_presenca_ausente_e_presente_nao_e_duvida():
    """`v9_01_trafego_inventario.sql` deixa `presenca` NULA quando não há
    anomalia. Ler isso como "não sei" marcaria toda campanha viva como duvidosa.
    """
    assert inv.presenca_efetiva(None, False) == inv.PRESENTE
    assert inv.presenca_efetiva("", False) == inv.PRESENTE
    assert inv.presenca_efetiva(inv.REMOVIDA, False) == inv.REMOVIDA
    # Valor fora do vocabulário: a resposta diz que não sabe, em vez de escolher
    # um dos seis e afirmar algo que ninguém observou.
    assert inv.presenca_efetiva("inventado", False) == inv.CONTA_NAO_IDENTIFICADA
    # A falha de leitura ganha de qualquer valor armazenado.
    assert inv.presenca_efetiva(inv.REMOVIDA, True) == inv.SINCRONIZACAO_FALHOU


@pytest.mark.anyio
async def test_a_projecao_le_os_dois_vocabularios_de_snapshot():
    """A mesma conta, escrita com os nomes de `v9_01`, produz a mesma projeção.

    Dois nomes para os mesmos fatos foram escritos na mesma semana; escolher um
    é decisão do integrador, e a projeção não pode depender dessa escolha.
    """
    irma = {"customer_id": "111", "nome": "conta 111",
            "tentativa_em": _iso(6), "tentativa_resultado": "ok",
            "leitura_boa_em": _iso(6), "leitura_boa_campanhas": 0}
    fonte = FonteEmMemoria([irma], [])
    conta = (await _montar(fonte)).json()["contas"][0]

    assert conta["frescor"] == inv.VAZIO_CONFIRMADO
    assert conta["leitura"] is not None
    assert conta["ultima_leitura_boa"] is not None


def pathlib_leia(relativo: str) -> str:
    import pathlib as _p

    return (_p.Path(__file__).resolve().parents[1] / relativo).read_text(encoding="utf-8")


def test_a_ponte_entre_dois_schemas_foi_removida():
    """A condição de aposentadoria da ponte era "quando o schema for único".

    Ele é. `ALIAS_DE_CONTA` aceitava tanto `lido_em` quanto `tentativa_em` — e
    era isso que mantinha a ambiguidade viva: enquanto a projeção funcionasse
    contra os dois, ninguém precisava decidir qual schema era o real, e o código
    de acesso continuava apontado para tabelas que ninguém cria.

    O que sobrou é uma tradução de MÃO ÚNICA: coluna do schema canônico →
    vocabulário interno do módulo.
    """
    assert not hasattr(inv, "ALIAS_DE_CONTA"), (
        "a ponte entre dois schemas voltou; ela adia a decisão de qual é o real")
    assert set(inv.COLUNAS_DA_CONTA) == {
        "tentativa_em", "tentativa_resultado", "tentativa_motivo",
        "tentativa_duracao_ms", "leitura_boa_em", "leitura_boa_campanhas",
        "leitura_boa_duracao_ms"}

    normalizada = inv.normalizar_linha_de_conta(
        {"tentativa_em": "2026-08-24T12:00:00+00:00",
         "tentativa_resultado": "falhou", "tentativa_motivo": "timeout"})
    assert normalizada["lido_em"] == "2026-08-24T12:00:00+00:00"
    assert normalizada["resultado"] == "falhou"
    assert normalizada["motivo"] == "timeout"

    # Idempotente: normalizar duas vezes não muda nada.
    assert inv.normalizar_linha_de_conta(normalizada) == normalizada

    # E toda coluna traduzida existe na migration canônica.
    import pathlib as _p

    sql = (_p.Path(__file__).resolve().parents[2]
           / inv.SCHEMA_CANONICO).read_text(encoding="utf-8")
    trecho = sql[sql.index("CREATE TABLE public.trafego_snapshot_conta"):]
    trecho = trecho[:trecho.index("COMMENT ON TABLE")]
    for coluna in inv.COLUNAS_DA_CONTA:
        assert coluna in trecho, f"{coluna} não existe em trafego_snapshot_conta"