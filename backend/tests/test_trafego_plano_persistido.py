"""O caminho produtivo do plano de mensuração: prova → confirmação → escrita.

## O buraco que este arquivo fecha

Antes desta entrega, `RepositorioDePlanoDeMensuracao` e
`documento_de_plano_de_mensuracao` tinham ZERO chamadores de produção — a
migration v12_02 existia, a RPC governada existia, o domínio existia, a tela
existia, e **nada gravava**. O plano de mensuração era calculado em `/provar`,
projetado na resposta HTTP e descartado. `/subir` sequer o montava.

O efeito: a campanha nascia e o que se sabia sobre a mensuração dela no instante
da decisão não sobrevivia à requisição. Depois do nascimento não havia como
dizer, com prova, o que o operador viu quando apertou o botão.

## A ordem que estes testes defendem

    reprova (selo)  →  idempotência remota (LEITURA)
                    →  ledger.abrir  →  ledger.despachar
                    →  PLANO PERSISTIDO          ← esta entrega
                    →  sb.subir (a ÚNICA chamada que muta)
                    →  fechar_sucesso (declara a identidade em trafego_campanha)
                    →  PLANO VINCULADO ao campaign_id   ← esta entrega

Cada seta é uma afirmação testável, e a que mais importa é a penúltima: se a
escrita do plano falhar, **o Google não é chamado**. Persistir depois do mutate
seria registrar o que se sabia depois de já ter gasto a decisão.

## O que este arquivo NÃO faz

Nada aqui toca rede, Supabase ou Google. A fixture `_rede_bloqueada` derruba o
teste se qualquer socket for aberto — é o mesmo desenho de
`test_trafego_ledger_producao.py`, e ela é a prova 15 da missão (zero mutação
externa) rodando em toda função deste módulo, não uma promessa em prosa.
"""
from __future__ import annotations

from types import SimpleNamespace
import asyncio
import socket

import httpx
import pytest
from fastapi import HTTPException

from app.trafego import (
    canario,
    ledger as led,
    persistencia as pers,
    plano_mensuracao as pm,
    sincronizador,
)
from app.routers import trafego
from app.seguranca.identidade import Identidade

from test_trafego_canario import (  # noqa: E402
    _instalar_portas_hermeticas,
    _payload_da_rota,
)


@pytest.fixture(autouse=True)
def _rede_bloqueada(monkeypatch: pytest.MonkeyPatch):
    """PROVA 15 — nenhuma mutação externa, em nenhum teste deste arquivo.

    Não é uma promessa: é um `pytest.fail` dentro de `socket.connect`. Um teste
    que abrisse conexão morreria aqui, com o nome do teste no relatório.
    """
    def recusar_rede(_socket, _address):
        pytest.fail("teste do plano persistido tentou abrir conexão de rede")

    monkeypatch.setattr(socket.socket, "connect", recusar_rede)
    monkeypatch.setattr(socket.socket, "connect_ex", recusar_rede)


@pytest.fixture(autouse=True)
def _plano_nao_lido_por_padrao(monkeypatch: pytest.MonkeyPatch):
    """A leitura do plano é CINCO consultas GAQL. Aqui ela nunca acontece.

    ⚠️ `_impressao_aprovada` roda `/provar` de verdade para obter o selo, e
    `/provar` lê o plano. Sem este dublê o socket abriria antes de qualquer
    teste chegar ao que ele quer provar — e `_rede_bloqueada` derrubaria tudo
    pelo motivo errado. Quem precisa de um plano de verdade instala o seu em
    `_montar`, que sobrescreve este.
    """
    from app.trafego import contas as ct

    async def sem_plano(*_a, **_k):
        return None

    def sem_metas(*_a, **_k):
        raise RuntimeError("leitura de metas desligada neste arquivo de teste")

    monkeypatch.setattr(trafego, "_plano_de_mensuracao", sem_plano)
    # ⚠️ A SEGUNDA porta, e ela é a que de fato abria socket.
    #
    # `_prontidao_do_lancamento` chama `contas.meta_de_conversao`, que desce até
    # `volc_ads.gads.client.cliente` — e `cliente` é `lru_cache`. Com
    # `~/google-ads.yaml` presente, `load_from_storage` REFRESCA o token, ou
    # seja, fala com o Google antes de qualquer consulta.
    #
    # A suíte inteira passa hoje porque algum módulo importado antes já povoou
    # esse cache. Depender disso é depender de ordem de import: este arquivo
    # roda sozinho e continua hermético. A rota captura a exceção e segue com
    # `metas=None`, que é o caminho honesto de "não consegui ler".
    monkeypatch.setattr(ct, "meta_de_conversao", sem_metas)


IDENTIDADE = Identidade(
    sub="operador-sub-1", email="tarcisio@agenciavolc.com.br",
    papel="ADMIN", origem="teste",
)

#: A campanha que o executor devolve como criada, nos testes de sucesso.
CAMPANHA = "24183717006"


# ═══════════════════════════════════════════════════════════════════════════
# Dublês — fiéis à forma real, e com DIÁRIO COMPARTILHADO
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ O diário é ÚNICO e atravessa ledger, repositório de plano e executor. É a
# única forma de provar ORDEM entre três objetos diferentes: um diário por
# objeto provaria que cada um foi chamado, e nunca que um veio antes do outro.


class LedgerDeTeste:
    """Um ledger que registra a ordem dos atos no diário compartilhado."""

    def __init__(self, *, diario: list, disponivel: bool = True,
                 erro_no_fechar_erro: Exception | None = None):
        self.diario = diario
        self._disponivel = disponivel
        self._erro_no_fechar_erro = erro_no_fechar_erro

    @property
    def disponivel(self) -> bool:
        return self._disponivel

    async def abrir(self, **kw):
        self.diario.append(("abrir", kw))
        return {"idempotency_key": "volc-ga-0000-abcdef0123456789",
                "item_id": "item-1", "lote_id": "lote-1",
                "intencao_id": "int-1", "reaproveitado": False}

    async def despachar(self, **kw):
        self.diario.append(("despachar", kw))
        return led.Despacho(item_id="item-1", lote_id="lote-1",
                            recibo_id="recibo-1", tentativa=1)

    async def fechar_sucesso(self, **kw):
        self.diario.append(("fechar_sucesso", kw))
        return {"id_externo": kw["id_externo"], "item_estado": "criada_pausada",
                "desfecho": "sucesso"}

    async def fechar_erro(self, **kw):
        self.diario.append(("fechar_erro", kw))
        if self._erro_no_fechar_erro is not None:
            raise self._erro_no_fechar_erro
        return {"desfecho": "erro"}

    async def fechar_sem_resposta(self, **kw):
        self.diario.append(("fechar_sem_resposta", kw))
        return {"desfecho": "sem_resposta"}

    async def conta_externa_do_item(self, item_id: str):
        self.diario.append(("conta_externa_do_item", {"item_id": item_id}))
        return canario.CONTA

    async def reconciliar(self, **kw):
        self.diario.append(("reconciliar", kw))
        return {"desfecho": "sucesso", "id_externo": kw.get("id_externo"),
                "item_estado": "criada_pausada"}


class RepoDePlanoDeTeste:
    """Um `RepositorioDePlanoDeMensuracao` que guarda o documento em memória.

    ⚠️ Ele reproduz a IDEMPOTÊNCIA PELA IMPRESSÃO que a função Postgres tem, e
    não uma versão simplificada dela. Um dublê que sempre insere provaria uma
    idempotência que só existe no teste — e a linha 985 da migration
    (`select plano_id ... where impressao = ...; if existente is not null then
    return existente`) é exatamente o que a prova 6 precisa exercitar.
    """

    def __init__(self, *, diario: list, habilitado: bool = True,
                 erro: Exception | None = None,
                 erro_no_vinculo: Exception | None = None,
                 devolve_vazio: bool = False):
        self.diario = diario
        self.habilitado = habilitado
        self._erro = erro
        self._erro_no_vinculo = erro_no_vinculo
        # ⚠️ O caso que a revisão adversarial encontrou: a RPC responde 200 com
        # corpo `null`/`[]` e o repositório real devolve `None` SEM levantar.
        # Um dublê que sempre devolve id esconderia exatamente esse buraco.
        self._devolve_vazio = devolve_vazio
        self.documentos: list[dict] = []
        self._por_impressao: dict[str, str] = {}

    async def registrar(self, documento):
        vinculado = bool((documento.get("payload") or {}).get("vinculo"))
        self.diario.append(("registrar_plano", documento))
        if self._erro is not None and not vinculado:
            raise self._erro
        if self._erro_no_vinculo is not None and vinculado:
            raise self._erro_no_vinculo
        if not self.habilitado or self._devolve_vazio:
            return None
        impressao = documento["impressao"]
        if impressao in self._por_impressao:
            return self._por_impressao[impressao]
        plano_id = f"plano-{len(self.documentos) + 1}"
        # A linha como o PostgREST a devolveria: o documento MAIS o id que a
        # função Postgres cunhou.
        self.documentos.append({**documento, "plano_id": plano_id})
        self._por_impressao[impressao] = plano_id
        return plano_id

    async def por_intencao(self, chave_intencao: str):
        self.diario.append(("por_intencao", {"chave_intencao": chave_intencao}))
        if not self.habilitado:
            return []
        return [d for d in reversed(self.documentos)
                if d.get("chave_intencao") == chave_intencao]

    async def por_prefixo_de_intencao(self, prefixo: str):
        self.diario.append(("por_prefixo_de_intencao", {"prefixo": prefixo}))
        if not self.habilitado or len(str(prefixo or "")) < 12:
            return []
        return [d for d in reversed(self.documentos)
                if str(d.get("chave_intencao") or "").startswith(prefixo)]

    # ── leitura de conveniência para os testes ──────────────────────────────

    @property
    def gravados(self) -> list[dict]:
        return self.documentos

    def do_nascimento(self) -> dict | None:
        """O documento que carrega o vínculo pós-nascimento, se houver."""
        return next((d for d in self.documentos
                     if (d.get("payload") or {}).get("vinculo")), None)


def _recibo_do_executor(estado: str, *, campaign_id: str = CAMPANHA,
                        customer_id: str = canario.CONTA,
                        falha=None, explicacao: str = ""):
    """A forma REAL de `volc_ads.subir.Recibo`, com os estados REAIS.

    ⚠️ `Recibo` NÃO tem campo `campaign_id`: o id só existe dentro de
    `Criado.resource_name`, na forma `customers/<conta>/campaigns/<id>`. Um
    dublê que expusesse `campaign_id` direto provaria uma extração que a rota
    não faz.
    """
    from volc_ads import subir as sb

    criados = ()
    if estado == sb.ACEITO:
        criados = (
            SimpleNamespace(
                posicao=0, tipo="campaign_budget_result",
                resource_name=f"customers/{customer_id}/campaignBudgets/9"),
            SimpleNamespace(
                posicao=1, tipo="campaign_result",
                resource_name=f"customers/{customer_id}/campaigns/{campaign_id}"),
        )
    return SimpleNamespace(
        estado=estado, carimbo="20260831_120000",
        customer_id=canario.CONTA, login_customer_id=canario.MCC,
        nome_campanha="VOLC-CANARY-teste", n_operacoes=72,
        impressao="a" * 64, motivo="canário pausado com aprovação humana",
        criados=criados, request_id="req-1", linhagem=(), falha=falha,
        explicacao=explicacao,
    )


# ═══════════════════════════════════════════════════════════════════════════
# O plano que atravessa — montado do domínio real, nunca de um dicionário
# ═══════════════════════════════════════════════════════════════════════════


def _acao(id_numerico: str = "7498530235", *, owner: str | None = "1234567890"):
    return pm.AcaoDeConversao(
        id=id_numerico,
        resource_name=f"customers/{owner or canario.CONTA}/conversionActions/{id_numerico}",
        owner_customer_id=owner,
        nome="Compra no site",
        categoria="PURCHASE", origem="WEBSITE",
        tipo="WEBPAGE", status="ENABLED", primaria=True,
    )


def _plano_lido(*, customer_id: str = canario.CONTA,
                login_customer_id: str = canario.MCC,
                chave_intencao: str = "c" * 64,
                campaign_id: str | None = None,
                acao: pm.AcaoDeConversao | None = None,
                metas: tuple[pm.Meta, ...] = ()) -> pm.PlanoDeMensuracao:
    """Um plano REAL, com meta resolvida e ação eleita — não o de ignorância.

    A ação eleita e a meta biddable existem porque as provas 9 e 10 precisam de
    um destino resolvido, e destino resolvido exige, no schema, dono e id
    numérico casando com a ação eleita.
    """
    alvo = _acao() if acao is None else acao
    biddable = metas or (pm.Meta(categoria="PURCHASE", origem="WEBSITE",
                                 biddable=True),)
    meta = pm.MetaEfetiva(
        nivel="CUSTOMER", nivel_estado=pm.INELEGIVEL, nivel_herdado=True,
        metas_da_conta=biddable, metas_da_conta_estado=pm.COM_DADOS,
        metas_da_campanha=(), metas_da_campanha_estado=pm.INELEGIVEL,
        campaign_id=campaign_id,
    )
    return pm.montar(
        customer_id=customer_id, login_customer_id=login_customer_id,
        meta_efetiva=meta, acoes=(alvo,), acoes_estado=pm.COM_DADOS,
        campaign_id=campaign_id, chave_intencao=chave_intencao,
    )


def _montar(monkeypatch, *, ledger, repo_plano, subir, plano=None,
            diario: list | None = None):
    """Portas herméticas + ledger + repositório de plano + `subir` observável."""
    from volc_ads import subir as sb

    _instalar_portas_hermeticas(monkeypatch)
    monkeypatch.setattr(trafego, "_ledger", lambda: ledger)
    monkeypatch.setattr(trafego, "_repositorio_de_plano", lambda: repo_plano)
    monkeypatch.setattr(canario, "campanhas_com_marca", lambda **_: ())
    monkeypatch.setattr(canario, "campanhas_com_destino", lambda **_: ())
    monkeypatch.setattr(sb, "subir", subir)

    lido = _plano_lido() if plano is None else plano

    async def _plano_dublado(cid, mid, *, campaign_id=None, chave_intencao=None):
        if diario is not None:
            diario.append(("ler_plano", {"campaign_id": campaign_id,
                                         "chave_intencao": chave_intencao}))
        if lido is None:
            return None
        return pm.montar(
            customer_id=cid, login_customer_id=mid,
            meta_efetiva=lido.meta_efetiva, acoes=lido.acoes,
            acoes_estado=lido.acoes_estado, frescor=lido.frescor,
            marcacao=lido.marcacao, campaign_id=campaign_id,
            chave_intencao=chave_intencao,
        )

    monkeypatch.setattr(trafego, "_plano_de_mensuracao", _plano_dublado)

    async def _sem_registro_legado(*_a, **_k):
        return ""

    monkeypatch.setattr(trafego, "_registrar_campanha", _sem_registro_legado)


def _impressao_aprovada(monkeypatch):
    _instalar_portas_hermeticas(monkeypatch)
    prova = asyncio.run(trafego.provar(trafego.ProvarEntrada(**_payload_da_rota()),
                                       identidade=IDENTIDADE))
    return prova["autorizacao"]["plano_impressao"]


def _corpo(prova_impressao: str, **mudancas):
    return trafego.SubirEntrada(**{
        **_payload_da_rota(**mudancas),
        "motivo": "canário pausado com aprovação humana",
        "plano_impressao": prova_impressao,
        "confirmar_criacao_pausada": True,
    })


def _atos(diario: list) -> list[str]:
    return [nome for nome, _ in diario]


def _rodar(monkeypatch, *, recibo_ou_erro, repo_plano=None, diario=None,
           plano=None):
    """Roda `/subir` até o fim e devolve (saída-ou-exceção, diário, repo)."""
    from volc_ads import subir as sb

    diario = [] if diario is None else diario
    impressao = _impressao_aprovada(monkeypatch)
    ledger = LedgerDeTeste(diario=diario)
    repo = repo_plano or RepoDePlanoDeTeste(diario=diario)

    def subir_dublado(*_a, **_k):
        diario.append(("MUTATE", {}))
        if isinstance(recibo_ou_erro, Exception):
            raise recibo_ou_erro
        return recibo_ou_erro

    _montar(monkeypatch, ledger=ledger, repo_plano=repo, subir=subir_dublado,
            plano=plano, diario=diario)
    try:
        saida = asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))
    except HTTPException as exc:
        saida = exc
    return saida, diario, repo


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 1 — persistência falha ⇒ o Google NÃO é chamado
# ═══════════════════════════════════════════════════════════════════════════


def test_plano_que_nao_grava_impede_o_mutate(monkeypatch):
    """A prova central da missão, e a que justifica a ordem inteira.

    Uma campanha criada sem o plano de mensuração gravado é uma campanha sobre
    a qual ninguém consegue dizer depois o que se sabia quando ela nasceu. Se a
    única porta de escrita governada recusa, a resposta certa é NÃO CRIAR.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(
        diario=diario,
        erro=pers.PlanoIndisponivel("o PostgREST respondeu 503"))
    saida, diario, _ = _rodar(monkeypatch, recibo_ou_erro=None,
                              repo_plano=repo, diario=diario)

    assert isinstance(saida, HTTPException)
    assert saida.status_code == 503
    assert "MUTATE" not in _atos(diario), (
        "a persistência do plano falhou e o Google foi chamado assim mesmo")
    assert "registrar_plano" in _atos(diario)


def test_recusa_de_guarda_do_schema_tambem_impede_o_mutate(monkeypatch):
    """Uma das seis invariantes da v12_02 disparando é 409, não 503.

    ⚠️ E a diferença importa: 503 é "o banco não respondeu, tente de novo"; 409
    é "este plano não devia ter sido montado". Colapsá-las mandaria o operador
    repetir uma chamada que vai recusar de novo, para sempre.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(
        diario=diario,
        erro=pers.PlanoRecusado(
            "destino resolvido sem conta dona", codigo="23514"))
    saida, diario, _ = _rodar(monkeypatch, recibo_ou_erro=None,
                              repo_plano=repo, diario=diario)

    assert isinstance(saida, HTTPException)
    assert saida.status_code == 409
    assert "MUTATE" not in _atos(diario)


def test_a_falha_da_persistencia_fecha_o_recibo_e_deixa_o_item_reentravel(monkeypatch):
    """O recibo já está `em_voo` quando a escrita do plano falha.

    Abortar sem fechá-lo deixaria a camada 4 da v10_03 bloqueando este item
    para sempre — a campanha nunca foi criada e ninguém conseguiria tentar de
    novo. `fechar_erro` é o desfecho honesto: a plataforma nem foi consultada.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(diario=diario,
                              erro=pers.PlanoIndisponivel("sem banco"))
    _, diario, _ = _rodar(monkeypatch, recibo_ou_erro=None, repo_plano=repo,
                          diario=diario)

    saida, diario, _ = _rodar(monkeypatch, recibo_ou_erro=None, repo_plano=repo,
                              diario=diario)
    atos = _atos(diario)
    assert atos.index("despachar") < atos.index("registrar_plano")
    assert "fechar_erro" in atos, (
        "o recibo ficou `em_voo` depois de uma falha que provou que nada saiu")
    # ⚠️ E a RESPOSTA precisa dizer isso. Um 503 que só diz "nada foi enviado"
    # manda o operador tentar de novo sem lhe dar `item_id` nem `recibo_id`, e
    # sem dizer se a porta do reenvio está aberta.
    d = saida.detail
    assert d["item_id"] == "item-1"
    assert d["recibo_id"] == "recibo-1"
    assert d["reenvio_permitido"] is True
    assert d["proxima_acao"] == "reenviar"


def test_repositorio_desabilitado_e_recusa_e_nao_permissao(monkeypatch):
    """Sem Supabase configurado não há onde gravar o plano — e isso é 503.

    É o mesmo raciocínio que já vale para o ledger (`routers/trafego.py:3066`):
    um processo sem persistência pode provar à vontade, porque `/provar` não
    escreve nada. O que ele não pode é escrever.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(diario=diario, habilitado=False)
    saida, diario, _ = _rodar(monkeypatch, recibo_ou_erro=None,
                              repo_plano=repo, diario=diario)

    assert isinstance(saida, HTTPException)
    assert saida.status_code == 503
    assert "MUTATE" not in _atos(diario)


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 2 — a ORDEM: o plano é registrado ANTES do mutate
# ═══════════════════════════════════════════════════════════════════════════


def test_o_plano_e_gravado_antes_do_mutate_e_nao_depois(monkeypatch):
    """⚠️ Este teste FALHA se alguém mover a escrita para depois de `sb.subir`.

    É o par exato do item 2 da lista de contraprovas da missão: "plano
    registrado depois do mutate → teste deve falhar".
    """
    from volc_ads import subir as sb

    saida, diario, repo = _rodar(
        monkeypatch, recibo_ou_erro=_recibo_do_executor(sb.ACEITO))

    atos = _atos(diario)
    assert "MUTATE" in atos
    assert atos.index("registrar_plano") < atos.index("MUTATE"), (
        f"o plano foi gravado depois do mutate: {atos}")
    assert not isinstance(saida, HTTPException)


def test_a_sequencia_inteira_dos_atos_e_a_declarada(monkeypatch):
    """A ordem completa, e não só o par plano/mutate.

    Ler o plano ANTES de `abrir` não é estética: a leitura são cinco consultas
    GAQL com teto de 30s, e se ela rodasse depois do `abrir` um timeout deixaria
    um recibo `em_voo` órfão para uma chamada que nunca saiu.
    """
    from volc_ads import subir as sb

    _, diario, _ = _rodar(monkeypatch,
                          recibo_ou_erro=_recibo_do_executor(sb.ACEITO))

    atos = [a for a in _atos(diario)
            if a in ("ler_plano", "abrir", "despachar", "registrar_plano",
                     "MUTATE", "fechar_sucesso")]
    assert atos == ["ler_plano", "abrir", "despachar", "registrar_plano",
                    "MUTATE", "fechar_sucesso", "registrar_plano"], atos


def test_o_plano_pre_nascimento_nasce_sem_campaign_id(monkeypatch):
    """A campanha ainda não existe quando o plano é gravado. Ele diz isso."""
    from volc_ads import subir as sb

    _, _, repo = _rodar(monkeypatch,
                        recibo_ou_erro=_recibo_do_executor(sb.ACEITO))

    primeiro = repo.gravados[0]
    assert primeiro["campaign_id"] is None
    assert primeiro["volc_campaign_id"] is None
    assert primeiro["metas_da_campanha_estado"] == pm.INELEGIVEL, (
        "invariante 6 da v12_02: campanha que não nasceu não tem meta de campanha")


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 3 — sucesso remoto ⇒ vínculo com campaign_id, na MESMA intenção
# ═══════════════════════════════════════════════════════════════════════════


def test_sucesso_vincula_o_mesmo_plano_ao_campaign_id(monkeypatch):
    from volc_ads import subir as sb

    saida, _, repo = _rodar(monkeypatch,
                            recibo_ou_erro=_recibo_do_executor(sb.ACEITO))

    assert not isinstance(saida, HTTPException)
    vinculado = repo.do_nascimento()
    assert vinculado is not None, "nenhum plano foi vinculado ao nascimento"
    assert vinculado["campaign_id"] == CAMPANHA
    assert vinculado["volc_campaign_id"] == sincronizador.volc_campaign_id(
        canario.CONTA, CAMPANHA)


def test_exatamente_uma_intencao_une_o_pre_e_o_pos_nascimento(monkeypatch):
    """Duas linhas, uma intenção. É esta a costura que o vínculo existe para provar."""
    from volc_ads import subir as sb

    _, _, repo = _rodar(monkeypatch,
                        recibo_ou_erro=_recibo_do_executor(sb.ACEITO))

    assert len(repo.gravados) == 2
    chaves = {d["chave_intencao"] for d in repo.gravados}
    assert len(chaves) == 1, f"duas intenções para o mesmo lançamento: {chaves}"
    assert repo.gravados[0]["campaign_id"] is None
    assert repo.gravados[1]["campaign_id"] == CAMPANHA


def test_o_vinculo_e_linha_nova_e_nunca_um_update(monkeypatch):
    """Append-only: a linha pós-nascimento tem impressão PRÓPRIA.

    ⚠️ Reaproveitar a impressão faria a função Postgres devolver a linha antiga
    e descartar o vínculo em silêncio — a idempotência por impressão viraria
    perda de dado.
    """
    from volc_ads import subir as sb

    _, _, repo = _rodar(monkeypatch,
                        recibo_ou_erro=_recibo_do_executor(sb.ACEITO))

    antes, depois = repo.gravados
    assert antes["impressao"] != depois["impressao"]
    assert depois["versao"] > antes["versao"]


def test_o_vinculo_preserva_a_impressao_anterior_e_o_instante_da_leitura(monkeypatch):
    """A linha pós-nascimento é a MESMA observação, agora endereçada.

    `lido_em` é preservado de propósito: ele carimba quando a conta foi lida, e
    o vínculo não releu nada. Carimbar `now()` aqui afirmaria uma leitura que
    ninguém fez.
    """
    from volc_ads import subir as sb

    _, _, repo = _rodar(monkeypatch,
                        recibo_ou_erro=_recibo_do_executor(sb.ACEITO))

    antes, depois = repo.gravados
    vinculo = depois["payload"]["vinculo"]
    assert vinculo["impressao_anterior"] == antes["impressao"]
    assert vinculo["momento"] == "pos_nascimento"
    assert vinculo["observado_antes_do_nascimento"] is True
    assert depois["lido_em"] == antes["lido_em"], (
        "o vínculo carimbou uma leitura nova que não aconteceu")


def test_a_falha_do_vinculo_nao_derruba_a_campanha_ja_criada(monkeypatch):
    """A campanha existe na conta quando o vínculo é tentado.

    Falhar a resposta aqui trocaria um problema de registro por um de
    veiculação — e o operador ficaria sem o recibo de uma campanha que existe.
    O desfecho honesto é 200 com o aviso nomeado.
    """
    from volc_ads import subir as sb

    diario: list = []
    repo = RepoDePlanoDeTeste(
        diario=diario,
        erro_no_vinculo=pers.PlanoIndisponivel("banco caiu depois do mutate"))
    saida, _, _ = _rodar(monkeypatch,
                         recibo_ou_erro=_recibo_do_executor(sb.ACEITO),
                         repo_plano=repo, diario=diario)

    assert not isinstance(saida, HTTPException)
    aviso = saida["recibo"]["plano_de_mensuracao"]["vinculo"]
    assert aviso["vinculado"] is False
    assert aviso["proxima_acao"] == "reconciliar"


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 4 — resposta ausente ⇒ nenhum campaign_id inventado
# ═══════════════════════════════════════════════════════════════════════════


def test_indeterminado_nao_inventa_campaign_id_no_plano(monkeypatch):
    from volc_ads import subir as sb

    saida, _, repo = _rodar(
        monkeypatch, recibo_ou_erro=_recibo_do_executor(sb.INDETERMINADO))

    assert isinstance(saida, HTTPException)
    assert saida.status_code == 504
    assert repo.do_nascimento() is None, (
        "a chamada não respondeu e mesmo assim um plano nasceu com campaign_id")
    assert all(d["campaign_id"] is None for d in repo.gravados)


def test_recusa_respondida_nao_vincula_e_nao_afirma_que_a_campanha_existe(monkeypatch):
    from volc_ads import subir as sb

    saida, _, repo = _rodar(
        monkeypatch, recibo_ou_erro=_recibo_do_executor(sb.RECUSADO))

    assert isinstance(saida, HTTPException)
    assert saida.status_code == 502
    assert repo.do_nascimento() is None
    assert len(repo.gravados) == 1, (
        "a recusa gravou um segundo plano; só a leitura pré-nascimento é verdade")


def test_excecao_desconhecida_depois_do_mutate_nao_vincula(monkeypatch):
    """`OSError` depois do mutate pode ter a campanha JÁ criada.

    Sem prova de que ela existe, inventar o vínculo seria inventar o id.
    """
    saida, diario, repo = _rodar(monkeypatch,
                                 recibo_ou_erro=OSError("disco cheio"))

    assert isinstance(saida, HTTPException)
    assert saida.status_code == 504
    assert repo.do_nascimento() is None
    assert "MUTATE" in _atos(diario)


def test_o_504_indeterminado_entrega_a_marca_e_a_chave_para_reconciliar(monkeypatch):
    """⚠️ Defeito reproduzido: o 504 mandava reconciliar sem dar o critério.

    `ReconciliarEntrada` exige `campaign_id` OU `marca`, e o item que mais
    precisa de reconciliação é justamente o que não tem `campaign_id` — a
    chamada não respondeu. O corpo do 504 não carregava `marca`, então a única
    saída documentada pedia um dado que a própria resposta não entregava.
    """
    from volc_ads import subir as sb

    saida, _, _ = _rodar(
        monkeypatch, recibo_ou_erro=_recibo_do_executor(sb.INDETERMINADO))

    assert isinstance(saida, HTTPException)
    detalhe = saida.detail
    assert detalhe.get("marca"), "o 504 não entrega a marca que /reconciliar exige"
    assert detalhe.get("chave_intencao"), (
        "o 504 não entrega a chave que liga o plano à campanha perdida")


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 5 — reconciliação posterior vincula sem criar segunda intenção
# ═══════════════════════════════════════════════════════════════════════════


def _reconciliar(monkeypatch, *, encontradas, repo, ledger, diario,
                 chave: str | None = None):
    monkeypatch.setattr(trafego, "_ledger", lambda: ledger)
    monkeypatch.setattr(trafego, "_repositorio_de_plano", lambda: repo)
    monkeypatch.setattr(trafego, "_ler_campanha_na_conta",
                        lambda **_: tuple(encontradas))
    corpo = trafego.ReconciliarEntrada(
        item_id="item-1", customer_id=canario.CONTA,
        marca="VOLC-CANARY-" + ("d" * 12),
        chave_intencao=chave,
        login_customer_id=canario.MCC,
        motivo="leitura tardia depois do 504")
    return asyncio.run(trafego.reconciliar_lancamento(corpo, identidade=IDENTIDADE))


def test_reconciliar_vincula_o_mesmo_plano_a_campanha_descoberta(monkeypatch):
    """A campanha nasceu e a resposta se perdeu. A leitura tardia a encontra.

    O plano pré-nascimento já está no banco — foi gravado antes do mutate. A
    reconciliação NÃO cria outra intenção: ela acha a linha pela
    `chave_intencao` e grava a versão vinculada.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(diario=diario)
    # A linha pré-nascimento, como `/subir` a teria deixado.
    plano = _plano_lido(chave_intencao="d" * 64)
    asyncio.run(repo.registrar(pers.documento_de_plano_de_mensuracao(
        plano.para_json(), lido_em="2026-09-01T12:00:00+00:00")))
    ledger = LedgerDeTeste(diario=diario)

    saida = _reconciliar(
        monkeypatch, repo=repo, ledger=ledger, diario=diario,
        chave="d" * 64,
        encontradas=[{"campaign_id": CAMPANHA,
                      "campaign_name": "VOLC-CANARY-dddddddddddd / x",
                      "status": "PAUSED"}])

    vinculado = repo.do_nascimento()
    assert vinculado is not None, "a reconciliação não vinculou o plano"
    assert vinculado["campaign_id"] == CAMPANHA
    assert vinculado["chave_intencao"] == "d" * 64
    assert len({d["chave_intencao"] for d in repo.gravados}) == 1, (
        "a reconciliação criou uma segunda intenção")
    assert saida["plano_de_mensuracao"]["vinculo"]["vinculado"] is True


def test_reconciliar_sem_achar_nao_vincula_nada(monkeypatch):
    """Não achou não é "não existe" — e nenhuma das duas autoriza um vínculo."""
    diario: list = []
    repo = RepoDePlanoDeTeste(diario=diario)
    plano = _plano_lido(chave_intencao="d" * 64)
    asyncio.run(repo.registrar(pers.documento_de_plano_de_mensuracao(
        plano.para_json(), lido_em="2026-09-01T12:00:00+00:00")))
    ledger = LedgerDeTeste(diario=diario)

    _reconciliar(monkeypatch, repo=repo, ledger=ledger, diario=diario,
                 chave="d" * 64, encontradas=[])

    assert repo.do_nascimento() is None
    assert len(repo.gravados) == 1


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 6 — idempotência: repetir não cria segunda campanha nem segundo plano
# ═══════════════════════════════════════════════════════════════════════════


def test_gravar_o_mesmo_plano_duas_vezes_devolve_a_mesma_linha(monkeypatch):
    """A idempotência mora na impressão, e a impressão é do que DECIDE.

    Duas leituras iguais da mesma conta produzem a mesma impressão, e a função
    Postgres devolve o `plano_id` existente em vez de inserir. É o que torna
    seguro chamar isto de dentro de um retry.
    """
    repo = RepoDePlanoDeTeste(diario=[])
    doc = pers.documento_de_plano_de_mensuracao(
        _plano_lido().para_json(), lido_em="2026-09-01T12:00:00+00:00")

    a = asyncio.run(repo.registrar(doc))
    b = asyncio.run(repo.registrar(dict(doc, lido_em="2026-09-01T18:00:00+00:00")))

    assert a == b
    assert len(repo.gravados) == 1


def test_repetir_subir_de_verdade_nao_cria_segunda_campanha(monkeypatch):
    """⚠️ Esta prova REPETE a chamada. A versão anterior não repetia nada.

    Ela começava com a campanha artificialmente presente na conta e chamava
    `/subir` UMA vez — ou seja, provava a pré-checagem, não a idempotência. E o
    dublê de `campanhas_com_marca` devolvia sempre `()`, que é o mundo em que a
    proteção real está desligada.

    Aqui a conta é ESTADO: o que o primeiro `/subir` cria passa a ser o que o
    segundo encontra, que é como a conta de verdade se comporta.
    """
    from volc_ads import subir as sb

    diario: list = []
    impressao = _impressao_aprovada(monkeypatch)
    ledger = LedgerDeTeste(diario=diario)
    repo = RepoDePlanoDeTeste(diario=diario)
    conta: list[dict] = []

    def subir_dublado(*_a, **_k):
        diario.append(("MUTATE", {}))
        conta.append({"campaign_id": CAMPANHA,
                      "campaign_name": "VOLC-CANARY-teste"})
        return _recibo_do_executor(sb.ACEITO)

    _montar(monkeypatch, ledger=ledger, repo_plano=repo, subir=subir_dublado,
            diario=diario)
    monkeypatch.setattr(canario, "campanhas_com_marca",
                        lambda **_: tuple(conta))

    primeira = asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))
    assert primeira["recibo"]["plano_de_mensuracao"]["vinculo"]["vinculado"] is True

    with pytest.raises(HTTPException) as exc:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert exc.value.status_code == 409
    assert _atos(diario).count("MUTATE") == 1, (
        "a segunda chamada criou uma segunda campanha no mesmo leilão")
    # Duas linhas: a pré-nascimento e o vínculo. A repetição não acrescenta uma
    # terceira — e não acrescenta porque nem chegou a montar plano nenhum.
    assert len(repo.gravados) == 2


def test_a_pre_checagem_remota_para_antes_de_gravar_qualquer_plano(monkeypatch):
    """Um plano gravado aqui registraria a decisão de uma campanha que já
    existe — e o operador leria isso como se ele tivesse acabado de criá-la."""
    from volc_ads import subir as sb

    diario: list = []
    impressao = _impressao_aprovada(monkeypatch)
    ledger = LedgerDeTeste(diario=diario)
    repo = RepoDePlanoDeTeste(diario=diario)

    def subir_proibido(*_a, **_k):
        diario.append(("MUTATE", {}))
        return _recibo_do_executor(sb.ACEITO)

    _montar(monkeypatch, ledger=ledger, repo_plano=repo, subir=subir_proibido,
            diario=diario)
    monkeypatch.setattr(
        canario, "campanhas_com_marca",
        lambda **_: ({"campaign_id": CAMPANHA, "campaign_name": "x"},))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    assert exc.value.status_code == 409
    assert "MUTATE" not in _atos(diario)
    assert repo.gravados == []


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 7 e 8 — contas diferentes não colidem; intenções diferentes não se misturam
# ═══════════════════════════════════════════════════════════════════════════


def test_a_mesma_leitura_em_contas_diferentes_produz_impressoes_diferentes():
    """A conta entra na impressão. Sem isso, duas contas dividiriam uma linha.

    E a linha é única por impressão no banco — a segunda conta seria descartada
    em silêncio, herdando o veredito da primeira.
    """
    a = _plano_lido(customer_id="5478096539")
    b = _plano_lido(customer_id="2419582194")

    assert a.impressao() != b.impressao()


def test_a_chave_de_intencao_carrega_a_conta_e_por_isso_nao_colide(monkeypatch):
    """A `chave_intencao` é o sha256 do pedido aprovável COM a conta dentro.

    ⚠️ A conta que entra é a NORMALIZADA pelo portão `_no_escopo`, e não a do
    corpo cru — é o que impede que duas grafias da mesma conta gerem duas
    intenções.
    """
    _instalar_portas_hermeticas(monkeypatch)
    corpo = trafego.ProvarEntrada(**_payload_da_rota())

    uma = trafego._impressao_aprovavel(corpo, cid="5478096539", mid=canario.MCC)
    outra = trafego._impressao_aprovavel(corpo, cid="2419582194", mid=canario.MCC)

    assert uma != outra


def test_intencoes_diferentes_nao_compartilham_plano():
    """Nichos diferentes ⇒ chaves diferentes ⇒ impressões diferentes."""
    a = _plano_lido(chave_intencao="a" * 64)
    b = _plano_lido(chave_intencao="b" * 64)

    assert a.impressao() != b.impressao()


def test_por_intencao_nao_devolve_o_plano_de_outra_intencao():
    repo = RepoDePlanoDeTeste(diario=[])
    for chave in ("a" * 64, "b" * 64):
        asyncio.run(repo.registrar(pers.documento_de_plano_de_mensuracao(
            _plano_lido(chave_intencao=chave).para_json(),
            lido_em="2026-09-01T12:00:00+00:00")))

    achados = asyncio.run(repo.por_intencao("a" * 64))

    assert len(achados) == 1
    assert achados[0]["chave_intencao"] == "a" * 64


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 9 — o dono da ação pode diferir da conta operacional, e sobrevive
# ═══════════════════════════════════════════════════════════════════════════


def test_o_dono_da_acao_diferente_da_conta_operacional_atravessa_intacto(monkeypatch):
    """Conversion tracking centralizado no MCC é o caso NORMAL numa hierarquia.

    A Data Manager resolve o destino por conta DONA + id numérico. Gravar a
    conta operacional no lugar do dono não daria erro: daria silêncio, e a
    conversão não chegaria em lugar nenhum.
    """
    from volc_ads import subir as sb

    plano = _plano_lido(acao=_acao("7498530235", owner="1234567890"))
    _, _, repo = _rodar(monkeypatch,
                        recibo_ou_erro=_recibo_do_executor(sb.ACEITO),
                        plano=plano)

    doc = repo.gravados[0]
    assert doc["customer_id"] == canario.CONTA
    assert doc["acao_alvo_owner_id"] == "1234567890"
    assert doc["acao_alvo_owner_id"] != doc["customer_id"]
    assert doc["destino_operating_account_id"] == "1234567890", (
        "o destino apontou para a conta operacional, não para a dona da ação")
    assert doc["destino_product_destination_id"] == "7498530235"


def test_o_vinculo_nao_reescreve_o_dono_da_acao(monkeypatch):
    from volc_ads import subir as sb

    plano = _plano_lido(acao=_acao("7498530235", owner="1234567890"))
    _, _, repo = _rodar(monkeypatch,
                        recibo_ou_erro=_recibo_do_executor(sb.ACEITO),
                        plano=plano)

    antes, depois = repo.gravados
    assert depois["acao_alvo_owner_id"] == antes["acao_alvo_owner_id"]
    assert depois["destino_operating_account_id"] == "1234567890"


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 10 — Data Manager resolvido ≠ Data Manager pronto
# ═══════════════════════════════════════════════════════════════════════════


def test_destino_resolvido_nao_torna_o_data_manager_pronto(monkeypatch):
    """`destino_resolvido` diz que há ENDEREÇO. Não diz que alguém entregou lá.

    Um destino resolvido é conta dona + id numérico existindo. Prontidão de
    Data Manager exigiria um upload que aconteceu — e nenhum aconteceu. O plano
    gravado carrega as duas coisas em campos distintos para que ninguém as some.
    """
    from app.trafego import prontidao as pr

    plano = _plano_lido()
    assert plano.destino.resolvido is True

    veredito = pr.avaliar(
        plano_valido=True, recibo_registrado=False, metas_da_conta=None,
        plano_de_mensuracao=plano,
        data_manager_operante=False, coleta_pos_criacao_provada=False,
        estrategia_lance="MANUAL_CPC",
    ).para_json()
    assert veredito["data_manager_status"] != pr.PRONTO


def test_a_prova_declara_data_manager_nao_operante(monkeypatch):
    """`/provar` passa `data_manager_operante=False` — literal, não derivado."""
    _instalar_portas_hermeticas(monkeypatch)
    prova = asyncio.run(trafego.provar(trafego.ProvarEntrada(**_payload_da_rota()),
                                       identidade=IDENTIDADE))
    prontidao = prova.get("prontidao") or {}
    assert prontidao.get("data_manager_status") != "PRONTO"


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 11 — sinal observado ≠ caminho declarado
# ═══════════════════════════════════════════════════════════════════════════


def test_fonte_observada_e_caminho_declarado_nao_se_confundem():
    """Duas perguntas diferentes, duas funções diferentes, dois resultados.

    "Por onde o sinal CHEGA hoje" é observação; "por onde ele PODERIA chegar" é
    declaração. Uma tela que somasse as duas diria que a conta mede por um
    caminho que ninguém provou.
    """
    # ⚠️ Um plano com MARCAÇÃO lida — sem ela as duas listas saem vazias e a
    # comparação passaria por vacuidade, provando nada. Aqui há caminho
    # DECLARADO (auto-tagging ligado, tag no site) e nenhum sinal OBSERVADO,
    # que é exatamente o par que a distinção existe para separar.
    plano = _plano_lido()
    plano = pm.montar(
        customer_id=plano.customer_id, login_customer_id=plano.login_customer_id,
        meta_efetiva=plano.meta_efetiva, acoes=plano.acoes,
        acoes_estado=plano.acoes_estado,
        frescor=pm.Frescor(estado=pm.VAZIO_CONFIRMADO, conversoes_na_janela=0.0),
        marcacao=pm.InventarioDeMarcacao(
            estado=pm.COM_DADOS, auto_tagging=True,
            conversion_tracking_id="7466919994",
            conversion_tracking_owner_id="1234567890",
            conversion_tracking_status="CONVERSION_TRACKING_MANAGED_BY_SELF",
            acoes_com_tag=("7498530235",), fuso="America/Sao_Paulo"),
        chave_intencao=plano.chave_intencao)

    observadas = tuple(pm.fontes_de_sinal_observadas(plano))
    declarados = tuple(pm.caminhos_de_sinal_declarados(plano))

    assert declarados, "sem caminho declarado a comparação não prova nada"
    assert not observadas, (
        "o sinal está VAZIO_CONFIRMADO — nenhuma fonte pode ser dada como "
        "observada, ou caminho declarado virou prova de tráfego")
    assert set(observadas) != set(declarados)


def test_o_documento_gravado_carrega_os_estados_de_leitura_sem_colapso(monkeypatch):
    """Os seis estados viajam separados até a coluna. `falhou` ≠ `vazio_confirmado`."""
    from volc_ads import subir as sb

    _, _, repo = _rodar(monkeypatch,
                        recibo_ou_erro=_recibo_do_executor(sb.ACEITO))

    doc = repo.gravados[0]
    for coluna in ("nivel_estado", "metas_da_conta_estado",
                   "metas_da_campanha_estado", "acoes_estado",
                   "frescor_estado", "marcacao_estado"):
        assert doc[coluna] in pm.ESTADOS_DE_LEITURA, (
            f"{coluna}={doc[coluna]!r} não é um dos sete estados de leitura")


def test_zero_medido_e_ausencia_nao_viram_a_mesma_coluna():
    """`frescor_conversoes` distingue `0` de `None` — e o schema depende disso."""
    zero = pm.Frescor(estado=pm.VAZIO_CONFIRMADO, conversoes_na_janela=0.0,
                      ultima_conversao_em=None, dias_desde_a_ultima=None)
    nada = pm.frescor_nao_lido("ninguém leu")

    doc_zero = pers.documento_de_plano_de_mensuracao(
        pm.montar(customer_id=canario.CONTA, login_customer_id=canario.MCC,
                  frescor=zero, acoes_estado=pm.NAO_COLETADO).para_json(),
        lido_em="2026-09-01T12:00:00+00:00")
    doc_nada = pers.documento_de_plano_de_mensuracao(
        pm.montar(customer_id=canario.CONTA, login_customer_id=canario.MCC,
                  frescor=nada, acoes_estado=pm.NAO_COLETADO).para_json(),
        lido_em="2026-09-01T12:00:00+00:00")

    assert doc_zero["frescor_conversoes"] == 0
    assert doc_nada["frescor_conversoes"] is None


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 12 — PMax continua bloqueado pelos DOIS motivos, independentes
# ═══════════════════════════════════════════════════════════════════════════


def test_pmax_continua_fora_do_executor():
    """Motivo 1 — decisão de produto, com dono: o canal não tem construtor."""
    from app.trafego import contrato_canais as cc

    assert cc.CODIGO_PMAX_FORA_DO_EXECUTOR == "PMAX_FORA_DO_EXECUTOR"


def test_a_observabilidade_de_pmax_continua_nao_provada():
    """Motivo 2 — fato medido: ninguém provou que se consegue OLHAR uma PMax."""
    from app.trafego import contrato_canais as cc

    assert cc.CODIGO_PMAX_SEM_OBSERVABILIDADE == "pmax_observabilidade_nao_provada"


def test_os_dois_bloqueios_de_pmax_sao_independentes():
    """Fechar um não abre o outro — e é por isso que são dois códigos.

    Se a coleta de PMax fosse provada amanhã, o construtor continuaria ausente;
    se o construtor nascesse, a observabilidade continuaria não provada. Um
    código só faria o segundo morrer junto com o primeiro.
    """
    from app.trafego import contrato_canais as cc

    assert cc.CODIGO_PMAX_FORA_DO_EXECUTOR != cc.CODIGO_PMAX_SEM_OBSERVABILIDADE


def test_o_plano_persistido_nao_abre_a_criacao_de_pmax():
    """Nenhuma escrita nova alcança o canal que não tem construtor."""
    from volc_ads import subir as sb

    assert "PERFORMANCE_MAX" not in sb.CONSTRUTORES_POR_CANAL
    assert "PERFORMANCE_MAX" not in sb.PROVADORES_POR_CANAL


# ═══════════════════════════════════════════════════════════════════════════
# PROVA 14 — migration ausente ⇒ a rota falha FECHADO e didaticamente
# ═══════════════════════════════════════════════════════════════════════════


def test_migration_ausente_recusa_com_o_nome_do_que_falta(monkeypatch):
    """PGRST202 é "a função não existe" — ou seja, a v12_02 não foi aplicada.

    ⚠️ Isso NÃO pode virar um 500 nu nem um sucesso silencioso: o operador
    precisa ler qual migration falta, e a campanha não pode nascer sem o plano.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(
        diario=diario,
        erro=pers.PlanoIndisponivel(
            "a função volc_registrar_plano_de_mensuracao não existe neste banco: "
            "aplique supabase/migrations/v12_02_plano_de_mensuracao.sql",
            migration_ausente=True))
    saida, diario, _ = _rodar(monkeypatch, recibo_ou_erro=None,
                              repo_plano=repo, diario=diario)

    assert isinstance(saida, HTTPException)
    assert saida.status_code == 503
    assert "v12_02" in str(saida.detail)
    assert saida.detail["migration_ausente"] is True
    assert "MUTATE" not in _atos(diario)


def test_o_repositorio_traduz_pgrst202_em_migration_ausente():
    """A tradução mora no repositório, e não na rota — um lugar só."""
    exc = httpx.HTTPStatusError(
        "404", request=httpx.Request("POST", "http://x/rest/v1/rpc/x"),
        response=httpx.Response(
            404, json={"code": "PGRST202", "message": "Could not find the function"},
            request=httpx.Request("POST", "http://x/rest/v1/rpc/x")))

    erro = pers.erro_de_plano(exc)

    assert isinstance(erro, pers.PlanoIndisponivel)
    assert erro.migration_ausente is True
    assert "v12_02" in str(erro)


def test_uma_guarda_do_schema_nao_e_confundida_com_migration_ausente():
    exc = httpx.HTTPStatusError(
        "400", request=httpx.Request("POST", "http://x/rest/v1/rpc/x"),
        response=httpx.Response(
            400, json={"code": "23514",
                       "message": 'violates check constraint "trafego_plano_vinculo"'},
            request=httpx.Request("POST", "http://x/rest/v1/rpc/x")))

    erro = pers.erro_de_plano(exc)

    assert isinstance(erro, pers.PlanoRecusado)
    assert erro.codigo == "23514"


# ═══════════════════════════════════════════════════════════════════════════
# A identidade: campaign_id nunca é autoridade sem customer_id
# ═══════════════════════════════════════════════════════════════════════════


def test_a_identidade_do_recibo_exige_as_duas_metades():
    """`customers/<conta>/campaigns/<id>` — as duas metades, ou nenhuma.

    ⚠️ A rota extraía o id com `rsplit('/', 1)[-1]` e DESCARTAVA o segmento da
    conta sem compará-lo com o escopo. Um `resource_name` de outra conta viraria
    um `volc_campaign_id` derivado com a conta errada.
    """
    recibo = _recibo_do_executor("ACEITO", customer_id=canario.CONTA)

    conta, campanha = trafego._identidade_do_recibo(recibo)

    assert conta == canario.CONTA
    assert campanha == CAMPANHA


def test_recibo_de_outra_conta_nao_vira_identidade(monkeypatch):
    """A conta do `resource_name` tem de ser a conta do escopo.

    ⚠️ E a conferência precisa acontecer ANTES de o LEDGER carimbar. Esta prova
    nasceu fraca: ela olhava só o plano, e passava enquanto
    `_fechar_recibo_com_sucesso` já tinha derivado
    `volc_campaign_id(conta pedida, campanha alheia)` — dois endereços para a
    mesma campanha, cunhados antes de alguém reclamar.
    """
    from volc_ads import subir as sb

    recibo = _recibo_do_executor(sb.ACEITO, customer_id="9999999999")
    saida, diario, repo = _rodar(monkeypatch, recibo_ou_erro=recibo)

    assert repo.do_nascimento() is None, (
        "vinculou um plano a uma campanha de outra conta")
    atos = _atos(diario)
    assert "fechar_sucesso" not in atos, (
        "o ledger carimbou SUCESSO com um par (conta, campanha) que não existe")
    assert "fechar_sem_resposta" in atos, (
        "criou alguma coisa e não sabemos o quê: o desfecho honesto é "
        "`sem_resposta`, nunca sucesso")


def test_o_ledger_nunca_recebe_id_externo_de_outra_conta(monkeypatch):
    """O par (conta, campanha) que o ledger carimba é derivado, não montado."""
    from volc_ads import subir as sb

    _, diario, _ = _rodar(
        monkeypatch,
        recibo_ou_erro=_recibo_do_executor(sb.ACEITO, customer_id="9999999999"))

    for ato, kw in diario:
        if ato.startswith("fechar_"):
            assert kw.get("id_externo") in (None, ""), (
                f"{ato} recebeu id_externo={kw.get('id_externo')!r} de uma "
                "campanha que não é da conta do pedido")


# ═══════════════════════════════════════════════════════════════════════════
# Os achados da revisão adversarial de 01/09/2026
# ═══════════════════════════════════════════════════════════════════════════


def test_rpc_que_responde_sem_plano_id_impede_o_mutate(monkeypatch):
    """⚠️ HTTP 2xx NÃO é prova de que uma linha foi gravada.

    O repositório devolve `None` sem levantar quando a RPC responde 200 com
    corpo `null` ou `[]` — um contrato divergente ou uma resposta truncada
    produzem exatamente isso. Sem guarda, "não houve exceção" viraria "a linha
    existe", e a campanha nasceria com uma prova que ninguém tem.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(diario=diario, devolve_vazio=True)
    saida, diario, _ = _rodar(monkeypatch, recibo_ou_erro=None,
                              repo_plano=repo, diario=diario)

    assert isinstance(saida, HTTPException)
    assert saida.status_code == 503
    assert "MUTATE" not in _atos(diario), (
        "a RPC respondeu sem plano_id e o Google foi chamado assim mesmo")
    assert "plano_id" in str(saida.detail)


def test_fechamento_que_falha_proibe_o_reenvio_em_vez_de_prometê_lo(monkeypatch):
    """O recibo continuou `em_voo`. Mandar reenviar seria mandar bater numa
    porta que já sabemos estar trancada.

    Nada foi enviado ao Google — do lado dele reenviar é seguro. Mas a camada 4
    da v10_03 recusa a próxima tentativa enquanto houver recibo aberto, e a
    resposta precisa dizer isso em vez de prometer um reenvio impossível.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(diario=diario,
                              erro=pers.PlanoIndisponivel("sem banco"))
    impressao = _impressao_aprovada(monkeypatch)
    ledger = LedgerDeTeste(diario=diario,
                           erro_no_fechar_erro=RuntimeError("banco caiu de vez"))

    def subir_proibido(*_a, **_k):
        diario.append(("MUTATE", {}))
        raise AssertionError("o Google foi chamado")

    _montar(monkeypatch, ledger=ledger, repo_plano=repo, subir=subir_proibido,
            diario=diario)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(trafego.subir(_corpo(impressao), identidade=IDENTIDADE))

    d = exc.value.detail
    assert d["reenvio_permitido"] is False
    assert d["proxima_acao"] == "reconciliar_na_conta"
    assert "em_voo" in str(d["atencao"])
    assert "MUTATE" not in _atos(diario)


def test_reconciliar_recusa_campanha_que_nao_carrega_a_marca_da_intencao(monkeypatch):
    """⚠️ Mesma conta NÃO é prova de mesma campanha.

    A rota provava só que o item e a campanha pertenciam à mesma conta. Um
    operador que informasse o `campaign_id` de outra campanha qualquer da conta,
    junto da chave desta intenção, veria o plano ser vinculado a ela.

    O veto é pelo NOME e o vínculo continua sendo por id — e a diferença
    importa: um veto por nome nunca CRIA um vínculo errado, só impede um.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(diario=diario)
    plano = _plano_lido(chave_intencao="d" * 64)
    asyncio.run(repo.registrar(pers.documento_de_plano_de_mensuracao(
        plano.para_json(), lido_em="2026-09-01T12:00:00+00:00")))
    ledger = LedgerDeTeste(diario=diario)

    saida = _reconciliar(
        monkeypatch, repo=repo, ledger=ledger, diario=diario, chave="d" * 64,
        encontradas=[{"campaign_id": "77777777777",
                      "campaign_name": "Campanha antiga do cliente",
                      "status": "ENABLED"}])

    vinculo = saida["plano_de_mensuracao"]["vinculo"]
    assert vinculo["vinculado"] is False
    assert "marca desta intenção" in vinculo["porque"]
    assert repo.do_nascimento() is None


def test_o_plano_de_ignorancia_respeita_a_invariante_6_do_schema():
    """⚠️ Defeito reproduzido contra o schema REAL, depois de aplicar a v12_02.

    O plano de ignorância nasce SEM campanha — é essa a definição dele. A
    INVARIANTE 6 (`trafego_plano_campanha_inexistente_nao_tem_meta`) exige que,
    com `campaign_id` nulo, `metas_da_campanha_estado` seja `inelegivel`. O
    padrão de `meta_efetiva_nao_lida()` é `nao_coletado`, e a linha era recusada
    com 23514 na prova transacional contra o banco oficial.

    O efeito seria o oposto do que esta função existe para permitir: uma leitura
    do Google que falhasse impediria a criação da campanha, em vez de deixá-la
    nascer pausada com os bloqueadores gravados.

    `inelegivel` também é a resposta mais honesta — a campanha não existe, então
    a pergunta "quais são as metas DELA" não cabe ainda.
    """
    plano = trafego._plano_de_ignorancia(
        canario.CONTA, canario.MCC, chave_intencao="a" * 64)
    doc = pers.documento_de_plano_de_mensuracao(
        plano.para_json(), lido_em="2026-09-01T12:00:00+00:00")

    assert doc["campaign_id"] is None
    assert doc["metas_da_campanha_estado"] == pm.INELEGIVEL, (
        "invariante 6: campanha que não nasceu não tem meta de campanha")
    # E ele continua sendo um plano HONESTO de ignorância, não um plano vazio
    # que passaria por completo.
    assert doc["completo"] is False
    assert doc["bloqueadores"], "plano incompleto sem bloqueador nomeado é recusado"
    assert doc["meta_resolvida"] is False


def test_a_leitura_que_falha_ainda_deixa_a_campanha_nascer(monkeypatch):
    """A campanha nasce pausada mesmo quando o plano não pôde ser lido.

    Recusar aqui transformaria uma indisponibilidade do Google numa
    indisponibilidade do VOLC. O que impede a ATIVAÇÃO é o plano gravado, com
    `completo=false` e os bloqueadores nomeados — e ele é gravado.
    """
    from volc_ads import subir as sb

    saida, diario, repo = _rodar(
        monkeypatch, recibo_ou_erro=_recibo_do_executor(sb.ACEITO), plano=None)

    assert not isinstance(saida, HTTPException)
    assert "MUTATE" in _atos(diario)
    gravado = repo.gravados[0]
    assert gravado["completo"] is False
    assert gravado["bloqueadores"]
    assert gravado["metas_da_campanha_estado"] == pm.INELEGIVEL


def test_do_json_recusa_reconstruir_um_plano_que_mudaria_de_decisao():
    """Recalcular só é honesto se divergir LEVANTAR.

    `do_json` não copia os campos derivados: ele os recalcula. Se a eleição
    recalculada não bater com a gravada, este não é o mesmo plano — a impressão
    dele já é outra —, e devolvê-lo em silêncio faria a reconciliação vincular
    ao campaign_id uma decisão diferente da que o operador aprovou.
    """
    plano = _plano_lido()
    bruto = plano.para_json()
    bruto["acao_alvo"] = {**(bruto["acao_alvo"] or {}), "id": "9999999999"}

    with pytest.raises(ValueError, match="não é o mesmo plano"):
        pm.do_json(bruto)


def test_do_json_nao_ressuscita_click_ids_que_a_conta_nao_suporta():
    """Lista VAZIA gravada é "nenhum", e não o contrato completo.

    O `or CLICK_IDS` transformava `[]` nos três do default, invertendo o fato
    que a coluna guarda.
    """
    marcacao = pm.InventarioDeMarcacao(
        estado=pm.COM_DADOS, click_ids_suportados=())
    plano = pm.montar(customer_id=canario.CONTA, login_customer_id=canario.MCC,
                      marcacao=marcacao, acoes_estado=pm.NAO_COLETADO)

    de_volta = pm.do_json(plano.para_json())

    assert de_volta.marcacao.click_ids_suportados == ()


def test_do_json_herda_o_contrato_completo_quando_a_chave_esta_AUSENTE():
    """Ausência da chave é outra coisa: aí o default documentado vale."""
    bruto = pm.montar(customer_id=canario.CONTA,
                      login_customer_id=canario.MCC,
                      acoes_estado=pm.NAO_COLETADO).para_json()
    bruto["marcacao"].pop("click_ids_suportados")

    assert pm.do_json(bruto).marcacao.click_ids_suportados == pm.CLICK_IDS


def test_nenhum_vinculo_e_feito_por_nome_textual(monkeypatch):
    """O vínculo usa id numérico e conta. O nome da campanha não entra."""
    from volc_ads import subir as sb

    _, _, repo = _rodar(monkeypatch,
                        recibo_ou_erro=_recibo_do_executor(sb.ACEITO))

    doc = repo.do_nascimento()
    assert doc is not None
    texto = str(doc)
    assert "VOLC-CANARY-teste" not in texto, (
        "o nome da campanha entrou no documento do vínculo")


def test_volc_campaign_id_recusa_campanha_sem_conta():
    with pytest.raises(ValueError):
        sincronizador.volc_campaign_id("", CAMPANHA)
    with pytest.raises(ValueError):
        sincronizador.volc_campaign_id(canario.CONTA, "")


# ═══════════════════════════════════════════════════════════════════════════
# `/provar` continua sem escrever — e agora isso é afirmado, não só comentado
# ═══════════════════════════════════════════════════════════════════════════


def test_provar_nao_grava_plano_nenhum(monkeypatch):
    """⚠️ O comentário da rota dizia isso desde sempre e nenhum teste afirmava.

    "Plano calculado" e "plano persistido" são coisas diferentes, e `/provar`
    só produz a primeira.
    """
    diario: list = []
    repo = RepoDePlanoDeTeste(diario=diario)
    _instalar_portas_hermeticas(monkeypatch)
    monkeypatch.setattr(trafego, "_repositorio_de_plano", lambda: repo)

    asyncio.run(trafego.provar(trafego.ProvarEntrada(**_payload_da_rota()),
                               identidade=IDENTIDADE))

    assert repo.gravados == []
    assert "registrar_plano" not in _atos(diario)


def test_provar_diz_que_o_plano_nao_esta_persistido(monkeypatch):
    """A resposta separa o calculado do gravado, em vez de deixar a tela supor."""
    _instalar_portas_hermeticas(monkeypatch)
    prova = asyncio.run(trafego.provar(trafego.ProvarEntrada(**_payload_da_rota()),
                                       identidade=IDENTIDADE))

    persistencia_declarada = prova["prontidao"]["plano_persistido"]
    assert persistencia_declarada["persistido"] is False
    assert persistencia_declarada["plano_id"] is None
    assert "não" in persistencia_declarada["porque"].lower()
