"""A camada de acesso REAL do inventário de Tráfego — as seis tabelas canônicas.

## O defeito que este módulo existe para fechar

Até esta rodada, `inventario.FonteSupabase` consultava `volc_trafego_conta` e
`volc_trafego_campanha`, e `sincronizador.RepositorioSupabase` escrevia nelas e
em `volc_trafego_sincronizacao`. **Nenhum schema deste repositório cria essas
três tabelas.** Contra um banco real, toda rota do Hub responde 404 do
PostgREST; as suítes passavam porque as duas classes eram dubladas em teste.

O schema canônico é `supabase/migrations/v9_01_trafego_inventario.sql`, e ele
não é um rename daquelas três — é uma remodelagem:

    volc_trafego_conta          → trafego_snapshot_conta
    volc_trafego_campanha       → trafego_campanha        (IDENTIDADE)
                                + trafego_campanha_espelho (ESPELHO)
    volc_trafego_sincronizacao  → trafego_evento          (diário append-only)

A divisão do meio é o conserto de E-08 em forma de schema: **dado DECLARADO e
dado ESPELHADO não dividem tabela**, então nenhum gatilho de espelho alcança uma
declaração. Foi um gatilho de espelho reescrevendo uma declaração
(`status_source = 'auto'`) que tornou a procedência de `campaigns` inalcançável
por construção.

## O que este módulo NÃO faz

**Não decide nada.** Ele traduz nome de campo, escolhe tabela e monta query
param. Toda regra continua em `dominio.py` e `inventario.py`, e as duas
traduções que parecem regra têm o motivo escrito no lugar em que acontecem:

· `presente` → NULL na escrita (a API tem sete valores de presença, o banco
  guarda seis + NULL);
· `parcial` sobrevive como resultado de tentativa, em vez de virar `ok` — se
  virasse, `frescor_da_conta()` responderia `recente` para uma conta que não
  entregou metade do que foi pedido.

## Por que a leitura sai de uma VIEW, e não de um JOIN aqui

A listagem precisa de identidade, espelho, vínculo ativo e frescor da conta na
MESMA linha — quatro tabelas. Montado aqui, isso vira uma consulta por campanha,
e o pior do N+1 não é a lentidão: é que ele **some do plano de consulta**. Um
`EXPLAIN` na consulta principal mostraria um plano barato e honesto, e as outras
cinquenta requisições não apareceriam em lugar nenhum. As views
`trafego_inventario_campanha` e `trafego_inventario_conta` (seção 12 da
migration) resolvem o join no banco, e são `security_invoker = true` para não
virarem um túnel por cima da RLS das seis tabelas.

## Por que a tradução de filtros está DUPLICADA aqui

`inventario.FonteSupabase` tem funções equivalentes, e este módulo poderia
chamá-las. Não chama de propósito: aquela classe é justamente a que vai ser
APAGADA quando a troca acontecer, e um módulo novo não pode nascer dependendo do
objeto que ele substitui. A equivalência entre as duas traduções é PROVADA
enquanto as duas existirem — `test_trafego_persistencia.py` compara os query
params das duas para uma bateria de filtros, e o teste se auto-pula no dia em
que a classe antiga sair.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.trafego import dominio as dom
from app.trafego import inventario as inv

log = logging.getLogger("volc.trafego.persistencia")

# ── os nomes canônicos, num lugar só ────────────────────────────────────────
#
# ⚠️ Se um destes nomes divergir da migration, a rota volta a falhar contra um
# banco real exatamente como falhava antes. `test_trafego_persistencia.py` roda
# um cluster descartável, aplica a v9_01 e confere coluna por coluna o
# `CONTRATO_DE_COLUNAS` abaixo contra `information_schema` — é o único gate que
# não pode ser satisfeito por um dublê.

def _para_datetime(bruto: Any) -> Optional[datetime]:
    """ISO 8601 do PostgREST -> datetime ciente de fuso. `None` continua `None`.

    O `Z` final é trocado por `+00:00` porque `fromisoformat` só passou a
    aceitá-lo no Python 3.11, e este módulo não escolhe a versão de quem o roda.
    """
    if not bruto:
        return None
    if isinstance(bruto, datetime):
        return bruto
    try:
        return datetime.fromisoformat(str(bruto).replace("Z", "+00:00"))
    except ValueError:
        return None


TABELA_CAMPANHA = "trafego_campanha"
TABELA_ESPELHO = "trafego_campanha_espelho"
TABELA_SNAPSHOT = "trafego_snapshot_conta"
TABELA_EVENTO = "trafego_evento"
TABELA_VINCULO = "trafego_vinculo"
#: O `campaign_measurement_plan` de P05-T12 (migration v12_02). Append-only, e
#: a ÚNICA porta de escrita é a função abaixo — `service_role` não tem INSERT.
TABELA_PLANO_DE_MENSURACAO = "trafego_campanha_plano_de_mensuracao"

#: A função Postgres que grava o plano. Idempotente pela impressão: a MESMA
#: leitura gravada duas vezes devolve a mesma linha, e não uma segunda.
RPC_REGISTRAR_PLANO = "volc_registrar_plano_de_mensuracao"

#: A migration que cria a tabela e a função acima. O nome aparece na mensagem de
#: erro porque um operador diante de "a função não existe" precisa saber QUAL
#: arquivo aplicar — e não sair procurando.
MIGRATION_DO_PLANO = "supabase/migrations/v12_02_plano_de_mensuracao.sql"

#: Os códigos do PostgREST para "o objeto que você pediu não existe no schema
#: cache". `PGRST202` é função; `PGRST205` é tabela. Os dois significam, aqui, a
#: mesma coisa: a v12_02 não foi aplicada neste banco.
_CODIGOS_DE_OBJETO_AUSENTE = ("PGRST202", "PGRST205")


class PlanoIndisponivel(RuntimeError):
    """Não deu para gravar o plano. NÃO significa que o plano é inválido.

    ⚠️ A distinção com `PlanoRecusado` não é estética: as duas exigem reações
    opostas. Indisponível é "o banco não respondeu, ou a migration não está
    aplicada" — o operador não tem o que corrigir no pedido. Recusado é "uma das
    seis invariantes disparou" — o plano não devia ter sido montado assim.
    Colapsá-las mandaria alguém repetir para sempre uma chamada que vai recusar
    de novo.
    """

    def __init__(self, mensagem: str, *, migration_ausente: bool = False):
        super().__init__(mensagem)
        #: `True` quando o banco respondeu que a FUNÇÃO/TABELA não existe. É o
        #: único caso em que a saída é aplicar um arquivo, e não tentar de novo.
        self.migration_ausente = migration_ausente


class PlanoRecusado(RuntimeError):
    """Uma guarda da v12_02 disparou. A linha não entrou, e não devia entrar.

    `codigo` é o SQLSTATE, no mesmo desenho de `ledger.LedgerRecusou`: classe 23
    (integridade), `22023`, `P0001` e `P0002` são recusa de regra; o resto é
    defeito de infraestrutura e vira `PlanoIndisponivel`.
    """

    def __init__(self, mensagem: str, *, codigo: str = "", detalhe: Any = None):
        super().__init__(mensagem)
        self.codigo = codigo
        self.detalhe = detalhe


def _e_recusa_de_regra(codigo: str) -> bool:
    """O mesmo predicado de `ledger._e_recusa_de_regra`, e de propósito.

    Duas tabelas do mesmo domínio classificando SQLSTATE de formas diferentes
    seria a maneira mais barata de fazer a mesma falha virar 409 numa rota e 503
    noutra.
    """
    return bool(codigo) and (
        codigo in ("P0001", "P0002", "22023") or codigo.startswith("23")
    )


def erro_de_plano(exc: Any) -> RuntimeError:
    """`httpx.HTTPStatusError` do PostgREST → a exceção tipada desta camada.

    Função de módulo e PURA: ela é testável sem banco e sem rota, e a tradução
    mora num lugar só. A rota nunca lê `response.json()` — se lesse, a
    classificação passaria a existir em dois lugares, e o dia em que os dois
    discordassem ninguém saberia qual estava certo.
    """
    resposta = getattr(exc, "response", None)
    status = getattr(resposta, "status_code", 0)
    codigo, mensagem = "", ""
    if resposta is not None:
        try:
            corpo = resposta.json()
        except Exception:  # noqa: BLE001
            corpo = None
        if isinstance(corpo, dict):
            codigo = str(corpo.get("code") or "")
            mensagem = str(corpo.get("message") or "")[:2000]
        else:
            mensagem = str(getattr(resposta, "text", "") or exc)[:500]

    if codigo in _CODIGOS_DE_OBJETO_AUSENTE or (
            status == 404 and RPC_REGISTRAR_PLANO in mensagem):
        return PlanoIndisponivel(
            f"a função {RPC_REGISTRAR_PLANO} não existe neste banco "
            f"({mensagem or 'sem detalhe'}): aplique {MIGRATION_DO_PLANO} "
            "antes de criar campanha. Nada foi enviado ao Google.",
            migration_ausente=True)
    if _e_recusa_de_regra(codigo):
        return PlanoRecusado(mensagem or str(exc), codigo=codigo,
                             detalhe=None)
    return PlanoIndisponivel(
        f"o registro do plano respondeu {status}: {mensagem or exc}")

VIEW_CAMPANHAS = "trafego_inventario_campanha"
VIEW_CONTAS = "trafego_inventario_conta"

#: Quem escreveu. Viaja em `criada_por` e em `produtor` para que o diário diga a
#: origem de cada linha sem depender de quem estiver lendo o log.
PRODUTOR_VARREDURA = "varredura"

#: O tipo dos eventos que ESTE módulo apenda. Deliberadamente diferente do
#: `sincronizacao.conta.*` que o gatilho `trafego_snapshot_registra_tentativa`
#: escreve: são dois registros da mesma tentativa, por produtores diferentes, e
#: fundi-los faria a contagem "cada tentativa virou evento" contar duas vezes.
TIPO_REGISTRO = "sincronizacao.registro"

#: A presença que a view projeta para uma campanha SEM linha de espelho. Está
#: fora dos seis estados de propósito — ver o comentário da view. Aqui ela é
#: constante só para que o teste possa afirmar que este módulo NUNCA a grava.
PRESENCA_NAO_ESPELHADA = "nao_espelhada"

#: O que este módulo lê e escreve, relação por relação. Serve a UM propósito:
#: ser conferido contra o schema de verdade. Não use como fonte de nada mais —
#: a fonte do schema é a migration.
CONTRATO_DE_COLUNAS: Dict[str, Tuple[str, ...]] = {
    TABELA_PLANO_DE_MENSURACAO: (
        "plano_id", "impressao", "versao", "customer_id", "login_customer_id",
        "campaign_id", "volc_campaign_id", "chave_intencao",
        "nivel", "nivel_estado", "nivel_herdado", "custom_conversion_goal",
        "metas_da_conta_estado", "metas_da_campanha_estado", "metas_biddable",
        "meta_resolvida", "acoes_estado", "acao_alvo_id", "acao_alvo_owner_id",
        "acao_alvo_tipo", "acao_alvo_semantica", "acao_alvo_causa",
        "destino_resolvido", "destino_operating_account_id",
        "destino_product_destination_id", "destino_causa",
        "frescor_estado", "frescor_ultima_em", "frescor_dias",
        "frescor_conversoes", "marcacao_estado", "auto_tagging",
        "conversion_tracking_id", "conversion_tracking_owner_id",
        "conversion_tracking_status", "aceitou_termos_de_dados", "fuso",
        "completo", "bloqueadores", "payload", "api_versao", "lido_em",
        "registrado_em",
    ),
    TABELA_CAMPANHA: (
        "volc_campaign_id", "customer_id", "campaign_id", "criada_por",
        "procedencia", "campaign_lineage_id",
    ),
    TABELA_ESPELHO: (
        "volc_campaign_id", "lido_em", "presenca", "nome", "estado_externo",
        "veiculacao", "canal", "canal_bruto", "estrategia", "estrategia_bruta",
        "url_final", "lance_micros", "verba_diaria_micros",
        "impressoes", "cliques", "custo_micros", "moeda", "entrega_lida_em",
    ),
    TABELA_SNAPSHOT: (
        "customer_id", "nome", "tentativa_em", "tentativa_resultado",
        "tentativa_motivo", "tentativa_escopo", "tentativa_duracao_ms",
        "leitura_boa_em", "leitura_boa_campanhas", "leitura_boa_duracao_ms",
    ),
    TABELA_EVENTO: (
        "evento_id", "ocorrido_em", "registrado_em", "tipo",
        "chave_de_agrupamento", "produtor", "sujeito_tipo", "sujeito_id",
        "customer_id", "volc_campaign_id", "carga",
    ),
    VIEW_CONTAS: (
        "customer_id", "nome", "tentativa_em", "tentativa_resultado",
        "tentativa_motivo", "tentativa_duracao_ms", "escopo_parcial",
        "leitura_boa_em", "leitura_boa_campanhas", "leitura_boa_duracao_ms",
        "vazio_confirmado",
    ),
    VIEW_CAMPANHAS: (
        "volc_campaign_id", "campaign_lineage_id", "customer_id", "campaign_id",
        "procedencia", "presenca", "lido_em", "nome", "estado_externo",
        "veiculacao", "canal", "estrategia", "url_final",
        "lance_micros", "verba_diaria_micros",
        "impressoes", "cliques", "custo_micros", "moeda", "entrega_lida_em",
        "opportunity_id", "project_id", "funnel_run_id",
        "vinculo_confirmado_por", "vinculo_confirmado_em",
        "tentativa_resultado", "atencao",
        "procedencia_desconhecida", "sem_vinculo",
    ),
}

#: As colunas da IDENTIDADE dentro de uma linha de campanha vinda do
#: sincronizador. Tudo que não está aqui é ESPELHO. A lista é explícita, e não
#: derivada por exclusão, porque uma coluna nova cair no lado errado por engano é
#: como a procedência acabou dentro de uma tabela com gatilho de espelho.
_CAMPOS_DE_IDENTIDADE = ("volc_campaign_id", "customer_id", "campaign_id",
                         "criada_por", "campaign_lineage_id")


# ═══════════════════════════════════════════════════════════════════════════
# TRADUÇÃO DE FILTROS — de `FiltrosDoInventario` para query param do PostgREST
# ═══════════════════════════════════════════════════════════════════════════


def _in(valores: Sequence[Any]) -> str:
    """`in.(a,b)` do PostgREST, com aspas em quem tem vírgula ou espaço."""
    partes = []
    for v in valores:
        s = str(v)
        partes.append(f'"{s}"' if any(ch in s for ch in ', "') else s)
    return f"in.({','.join(partes)})"


def params_de_contas(filtros: "inv.FiltrosDoInventario") -> Dict[str, Any]:
    p: Dict[str, Any] = {"select": "*", "order": "customer_id.asc"}
    if filtros.conta:
        p["customer_id"] = _in(filtros.conta)
    return p


def _familia_falha(plano: "inv.PlanoDeConsulta") -> Optional[str]:
    """A cláusula das contas que NÃO puderam ser lidas.

    A presença armazenada é a última verdade conhecida, não o que vale agora —
    por isso o filtro de PRESENÇA não se aplica a esta família: aplicá-lo
    esconderia justamente as campanhas sobre as quais não se pode afirmar nada.

    ⚠️ **O filtro de ATENÇÃO aplica-se, e igual ao da outra família.**

    Ele era descartado aqui, e isso produzia dois defeitos que a auditoria
    provou contra banco real:

      · `atencao=false` devolvia `None` e **apagava a conta inteira** da
        listagem — inclusive o histórico removido, que a própria view calcula
        como `atencao = false`. A aba "sem atenção" ficava sem as campanhas que
        mais claramente não pedem atenção;
      · a contagem do sino somava todas as campanhas da conta, enquanto
        `SELECT count(*) WHERE atencao` na mesma view devolvia outro número. O
        sino e a coluna discordavam — a regressão que a v9_02 fechou no SQL,
        voltando pela aplicação.

    A razão do descarte deixou de existir quando `atencao` virou COLUNA: ela já
    inclui `tentativa_resultado = 'falhou'` no primeiro ramo, e já exclui
    `removida` antes dele. O banco calcula a atenção da conta que falhou; repetir
    a regra aqui é a segunda definição que este projeto passa o tempo todo
    fechando.
    """
    if not plano.contas_falhas:
        return None
    partes = [f"customer_id.{_in(plano.contas_falhas)}"]
    if plano.filtros.atencao is True:
        partes.append("atencao.is.true")
    elif plano.filtros.atencao is False:
        partes.append("atencao.is.false")
    return partes[0] if len(partes) == 1 else f"and({','.join(partes)})"


def _familia_lida(plano: "inv.PlanoDeConsulta") -> Optional[str]:
    """A cláusula das contas lidas, onde os filtros armazenados valem."""
    if not plano.contas_lidas:
        return None
    f = plano.filtros
    partes = [f"customer_id.{_in(plano.contas_lidas)}"]
    if f.presenca:
        presencas = [v for v in f.presenca if v != inv.SINCRONIZACAO_FALHOU]
        if not presencas:
            return None
        partes.append(f"presenca.{_in(presencas)}")
    if f.atencao is True:
        partes.append("atencao.is.true")
    elif f.atencao is False:
        partes.append("atencao.is.false")
    return partes[0] if len(partes) == 1 else f"and({','.join(partes)})"


def _or_das_familias(plano: "inv.PlanoDeConsulta") -> str:
    ramos = [r for r in (_familia_falha(plano), _familia_lida(plano)) if r]
    if not ramos:
        # Nenhuma família elegível: uma cláusula impossível é melhor que
        # nenhuma, senão a consulta devolveria a tabela inteira.
        return "(customer_id.eq.__nenhuma__)"
    return f"({','.join(ramos)})"


def params_de_campanhas(plano: "inv.PlanoDeConsulta") -> Dict[str, Any]:
    """Todo filtro vira query param.

    Se um deles sumir daqui, ele passa a ser aplicado em Python — e a paginação
    começa a mentir, porque o limite corta ANTES do filtro.
    """
    f = plano.filtros
    p: Dict[str, Any] = {
        "select": "*",
        # ── a ordem, e por que ela começa pela conta ────────────────────────
        #
        # O envelope AGRUPA por conta (`montar_inventario`), então a conta tem
        # de ser a primeira chave: uma ordem global "atenção primeiro" partiria
        # cada conta em pedaços espalhados por várias páginas, e o cabeçalho de
        # grupo apareceria três vezes com três fatias da mesma conta.
        #
        # Dentro da conta, `ordem_operacional` responde "o que exige o operador
        # agora?" — 0 atenção, 1 ligada, 2 pausada, 3 demais presentes, 4
        # histórico. `volc_campaign_id` só desempata: sem ele a ordem dentro do
        # degrau seria indefinida e a paginação por keyset perderia o chão.
        "order": ("customer_id.asc,ordem_operacional.asc,"
                  "volc_campaign_id.asc"),
        "or": _or_das_familias(plano),
    }

    # ── o padrão que esconde história ──────────────────────────────────────
    #
    # Fica FORA do `or` das famílias, como `estado_externo`: vale igualmente
    # para conta lida e para conta que falhou. É deliberado e diferente do
    # filtro de presença.
    #
    # A regra C diz que a falha de uma conta não contamina as outras — e não é
    # violada aqui, porque `historico` não é uma afirmação sobre AGORA. Remoção
    # no Google Ads é terminal: uma campanha removida na última leitura boa
    # continua removida hoje, tenha a conta respondido ou não. Já `presenca`
    # descreve o que vale neste instante, e por isso ela continua fora.
    if not f.incluir_historico:
        p["historico"] = "is.false"

    # ⚠️ UM ÚNICO `and`, montado no fim.
    #
    # `and` é UMA chave de query string. Escrevê-la duas vezes não soma
    # condições: a segunda apaga a primeira, em silêncio, e a consulta continua
    # devolvendo linhas coerentes — só que de outro conjunto. Foi exatamente o
    # que acontecia entre a busca e o cursor: a página 1 filtrava pelo texto, o
    # cursor sobrescrevia a cláusula, e a página 2 devolvia o inventário inteiro
    # a partir daquele ponto. A tela não tinha como perceber — as linhas eram
    # verdadeiras, só não eram as que o operador pediu.
    #
    # É a mesma armadilha que o comentário do `or` já descrevia logo abaixo. O
    # conserto é estrutural, não uma segunda advertência: os termos entram numa
    # lista e só viram query param uma vez.
    clausulas: List[str] = []

    if f.busca:
        # Vai em `and`, e não em `or`, porque o `or` do topo já carrega as
        # famílias de conta. Dois `or` no mesmo nível seriam UM só para o
        # PostgREST: o segundo sobrescreveria o primeiro e a busca passaria a
        # ignorar o recorte de conta — devolvendo campanhas de contas que o
        # operador não pediu, com cara de resultado certo.
        #
        # O texto casa com o nome OU com o id externo: quem procura "FGTS"
        # digita o nome, quem veio do painel do Google cola o id.
        alvo = f.busca.replace("%", "")
        clausulas.append(f"or(nome.ilike.*{alvo}*,campaign_id.ilike.*{alvo}*)")
    if f.canal:
        p["canal"] = _in(f.canal)
    if f.estado_externo:
        p["estado_externo"] = _in(f.estado_externo)
    if f.procedencia:
        p["procedencia"] = _in(f.procedencia)
    if f.projeto:
        p["project_id"] = _in(f.projeto)
    if f.vinculado is True:
        p["opportunity_id"] = "not.is.null"
    elif f.vinculado is False:
        p["opportunity_id"] = "is.null"

    if plano.depois_de:
        cid, degrau, chave = plano.depois_de
        # Keyset de TRÊS colunas, na mesma ordem do `ORDER BY`. `or` já está
        # ocupado pelas famílias de conta, e o recorte do cursor entra como mais
        # um termo do `and`, ao lado da busca.
        #
        # A forma aninhada é a tradução direta de
        #     (a,b,c) > (A,B,C)
        # que o PostgREST não tem como tupla: `a > A` OU (`a = A` E (`b > B` OU
        # (`b = B` E `c > C`))). Achatar num `and` de três `gt` seria outra
        # consulta — devolveria só o que é maior nas três ao mesmo tempo, e
        # perderia a página inteira do degrau seguinte.
        clausulas.append(
            f"or(customer_id.gt.{cid},"
            f"and(customer_id.eq.{cid},"
            f"or(ordem_operacional.gt.{degrau},"
            f"and(ordem_operacional.eq.{degrau},"
            f"volc_campaign_id.gt.{chave}))))")

    if clausulas:
        p["and"] = f"({','.join(clausulas)})"
    return p


# ═══════════════════════════════════════════════════════════════════════════
# TRADUÇÃO DE LINHAS — do vocabulário do domínio para as colunas canônicas
# ═══════════════════════════════════════════════════════════════════════════


def _iso(valor: Any) -> Optional[str]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor)


def presenca_para_o_banco(valor: Any) -> Optional[str]:
    """`presente` vira NULL; o resto passa.

    A API tem SETE valores de presença e o banco guarda SEIS + NULL, e a
    diferença não é descuido: os seis nomeiam EXCEÇÕES, e nenhum deles nomeia o
    caso normal — que é a maioria das linhas. `presente` é a afirmação que a
    leitura monta a partir do nulo (`dominio.presenca_projetada`), não um valor
    armazenável: a CHECK `trafego_espelho_presenca_conhecida` o recusa.

    ⚠️ Sem esta tradução, TODA campanha viva faria a gravação do espelho estourar
    com violação de CHECK — e a varredura inteira da conta iria para o ramo de
    falha, apagando o inventário de uma conta que respondeu perfeitamente.
    """
    texto = str(valor or "").strip()
    if not texto or texto == dom.PRESENTE:
        return None
    return texto


def documento_de_plano_de_mensuracao(
        plano: Dict[str, Any], *,
        lido_em: str,
        volc_campaign_id: Optional[str] = None,
        vinculo: Optional[Dict[str, Any]] = None,
        api_versao: str = "v25") -> Dict[str, Any]:
    """`PlanoDeMensuracao.para_json()` → o documento da função Postgres.

    Função PURA e de módulo, como toda tradução aqui: ela é testável sem banco,
    e a classe só transporta. Recebe o JSON do domínio — e não o objeto — porque
    `persistencia.py` não importa `volc_ads` nem o SDK do Google, e essa
    fronteira é o que permite servir o inventário sem custo de rede externa.

    ⚠️ NENHUM `coalesce` para zero, em campo nenhum. O que o plano não sabe
    viaja `None` e o schema recusa a linha se `None` for incoerente com o estado
    declarado. Preencher com zero aqui seria contornar, do lado de fora, as seis
    invariantes que a v12_02 existe para defender.

    ⚠️ E `frescor_conversoes` é o caso mais fácil de errar: `0.0` é um zero
    MEDIDO e precisa chegar como `0`; ausência precisa chegar como `None`. Um
    `or 0` nesta linha destruiria a distinção que o schema, o domínio e a tela
    carregam em três camadas.

    ## `vinculo` — o que liga a linha pós-nascimento à pré

    ⚠️ Ele entra APENAS em `payload`, e não vira coluna. A tabela já tem a
    coluna que responde a pergunta consultável — `chave_intencao`, com índice
    próprio —, e o vínculo é a PROCEDÊNCIA daquela linha: de qual impressão ela
    veio, em que momento, e a ressalva de que os estados de leitura descrevem
    uma observação feita ANTES de a campanha existir.

    Sem essa ressalva, uma linha com `campaign_id` preenchido e
    `metas_da_campanha_estado='inelegivel'` seria lida, meses depois, como "a
    campanha existe e as metas dela são inelegíveis" — que é falso. O que é
    verdade é "quando isto foi lido, a campanha ainda não existia".
    """
    meta = plano.get("meta_efetiva") or {}
    alvo = plano.get("acao_alvo") or {}
    destino = plano.get("destino") or {}
    frescor = plano.get("frescor") or {}
    marcacao = plano.get("marcacao") or {}
    biddable = meta.get("metas_biddable")
    return {
        "impressao": plano.get("impressao"),
        "versao": plano.get("versao"),
        "customer_id": plano.get("customer_id"),
        "login_customer_id": plano.get("login_customer_id"),
        "campaign_id": plano.get("campaign_id"),
        "volc_campaign_id": volc_campaign_id,
        "chave_intencao": plano.get("chave_intencao"),
        "nivel": meta.get("nivel"),
        "nivel_estado": meta.get("nivel_estado"),
        # ⚠️ A herança declarada viaja como COLUNA, e não só como prosa em
        # `causa`. Sem ela, "o nível foi lido do recurso" e "o nível foi
        # inferido porque a campanha não existe" ficam indistinguíveis para
        # quem consultar o banco depois.
        "nivel_herdado": bool(meta.get("nivel_herdado")),
        "custom_conversion_goal": meta.get("custom_conversion_goal"),
        "metas_da_conta_estado": meta.get("metas_da_conta_estado"),
        "metas_da_campanha_estado": meta.get("metas_da_campanha_estado"),
        # ⚠️ `None` vira `[]` SÓ aqui, e a razão é que a coluna é `not null` e o
        # que ela guarda é a lista de semânticas — não a existência dela. Quem
        # carrega "não sei qual nível manda" é `nivel_estado`, ao lado.
        "metas_biddable": [m.get("semantica") for m in (biddable or [])],
        "meta_resolvida": bool(meta.get("resolvida")),
        "acoes_estado": plano.get("acoes_estado"),
        "acao_alvo_id": alvo.get("id"),
        "acao_alvo_owner_id": alvo.get("owner_customer_id"),
        "acao_alvo_tipo": alvo.get("tipo"),
        "acao_alvo_semantica": alvo.get("semantica"),
        "acao_alvo_causa": plano.get("acao_alvo_causa"),
        "destino_resolvido": bool(destino.get("resolvido")),
        "destino_operating_account_id": destino.get("operating_account_id"),
        "destino_product_destination_id": destino.get("product_destination_id"),
        "destino_causa": destino.get("causa"),
        "frescor_estado": frescor.get("estado"),
        "frescor_ultima_em": frescor.get("ultima_conversao_em"),
        "frescor_dias": frescor.get("dias_desde_a_ultima"),
        "frescor_conversoes": frescor.get("conversoes_na_janela"),
        "marcacao_estado": marcacao.get("estado"),
        "auto_tagging": marcacao.get("auto_tagging"),
        "conversion_tracking_id": marcacao.get("conversion_tracking_id"),
        "conversion_tracking_owner_id": marcacao.get(
            "conversion_tracking_owner_id"),
        "conversion_tracking_status": marcacao.get(
            "conversion_tracking_status"),
        "aceitou_termos_de_dados": marcacao.get("aceitou_termos_de_dados"),
        "fuso": marcacao.get("fuso"),
        "completo": bool(plano.get("completo")),
        "bloqueadores": list(plano.get("bloqueadores") or ()),
        # O plano inteiro sobrevive em `payload`: as colunas acima são o que se
        # consulta, e o payload é o que se audita. Uma coluna nova amanhã não
        # apaga o que foi lido hoje.
        "payload": (dict(plano) if vinculo is None
                    else {**plano, "vinculo": dict(vinculo)}),
        "api_versao": api_versao,
        "lido_em": _iso(lido_em),
    }


def linha_de_snapshot(linha: Dict[str, Any]) -> Dict[str, Any]:
    """Linha de conta do sincronizador → `trafego_snapshot_conta`.

    Duas colunas do vocabulário antigo NÃO têm destino aqui, e isso é decisão,
    não esquecimento: `moeda` e `fuso` da conta descrevem a CONTA, não a
    tentativa de leitura dela. Guardá-las na linha de snapshot faria um dado
    estável herdar o carimbo de uma tentativa que pode ter falhado. A moeda que
    a tela usa é a da campanha, que viaja no espelho com o carimbo dela.

    ⚠️ NULO É ENVIADO DE PROPÓSITO. A versão antiga removia as chaves nulas do
    payload para não apagar `ultima_leitura_boa_em` numa varredura que falhou.
    Isso resolvia um problema e criava outro: `tentativa_motivo` também
    sobrevivia, e uma leitura BOA depois de uma falha continuava exibindo o
    motivo da falha anterior como se fosse atual. Aqui o nulo vai, e quem
    preserva a última leitura boa é o gatilho
    `trafego_snapshot_preserva_ultima_boa` — no banco, onde a regra não depende
    de nenhum escritor lembrar dela.
    """
    # ⚠️ DOIS VOCABULÁRIOS PARA O MESMO DICIONÁRIO.
    #
    # Este mapeador nasceu esperando o vocabulário ANTIGO do sincronizador
    # (`lido_em`, `resultado`, `motivo`, `duracao_ms`). Enquanto ele era
    # escrito, a outra frente reescreveu o sincronizador para emitir as chaves
    # JÁ no vocabulário do destino (`tentativa_em`, `tentativa_resultado`, …).
    #
    # O resultado foi silencioso e caro: `linha.get("lido_em")` devolvia None
    # para todo campo, o payload saía inteiro nulo, e o banco recusava com
    # `23502 null value in column "tentativa_em"`. Silencioso porque nenhum
    # teste pegava — cada frente dublava a outra ponta com o próprio
    # vocabulário, e os dois dublês concordavam consigo mesmos.
    #
    # Só a primeira varredura REAL revelou. Aceitar os dois nomes é a correção
    # honesta: o destino primeiro, o legado como reserva, e um comentário
    # dizendo por que a ambiguidade existe em vez de fingir que não existe.
    def _de(destino: str, legado: str) -> Any:
        v = linha.get(destino)
        return v if v is not None else linha.get(legado)

    resultado = str(_de("tentativa_resultado", "resultado") or "ok").strip().lower()
    boa = _iso(_de("leitura_boa_em", "ultima_leitura_boa_em"))
    duracao = _de("tentativa_duracao_ms", "duracao_ms")
    return {
        "customer_id": str(linha.get("customer_id") or ""),
        "nome": linha.get("nome"),
        "tentativa_em": _iso(_de("tentativa_em", "lido_em")),
        "tentativa_resultado": resultado,
        "tentativa_motivo": _de("tentativa_motivo", "motivo"),
        "tentativa_escopo": _de("tentativa_escopo", "escopo_parcial"),
        "tentativa_duracao_ms": duracao,
        "leitura_boa_em": boa,
        # O par é indivisível pela CHECK `..._leitura_boa_completa`: sem o
        # instante, a contagem não entra. Mandar a contagem sozinha faria o
        # gatilho levantar, e o levantamento seria correto.
        "leitura_boa_campanhas": (_de("leitura_boa_campanhas", "lidas") if boa else None),
        "leitura_boa_duracao_ms": (duracao if boa else None),
    }


def identidade_de_campanha(linha: Dict[str, Any]) -> Dict[str, Any]:
    """A parte da linha que é DECLARAÇÃO do VOLC.

    `procedencia` não é enviada, e a omissão é a decisão: a varredura NÃO SABE
    quem criou a campanha. Declarar `descoberta` aqui seria afirmar que ninguém
    observou — a varredura só sabe que a campanha existe na conta, não como ela
    foi parar lá. A coluna fica no DEFAULT `desconhecida`, que é a ausência de
    declaração, e o gatilho de identidade permite resolvê-la UMA vez quando
    alguém souber. É o mesmo defeito de `status_source = 'auto'` visto do outro
    lado: lá o banco inventava a procedência; aqui ninguém inventa.
    """
    saida = {
        "volc_campaign_id": str(linha.get("volc_campaign_id") or ""),
        "customer_id": linha.get("customer_id"),
        "campaign_id": str(linha.get("campaign_id") or ""),
        "criada_por": str(linha.get("criada_por") or PRODUTOR_VARREDURA),
    }
    if linha.get("campaign_lineage_id"):
        saida["campaign_lineage_id"] = linha["campaign_lineage_id"]
    return saida


def espelho_de_campanha(linha: Dict[str, Any]) -> Dict[str, Any]:
    """A parte da linha que é o que a CONTA respondeu.

    Só entram colunas que existem em `trafego_campanha_espelho`. `customer_id` e
    `campaign_id` ficam de fora porque são identidade e já moram em
    `trafego_campanha` — repeti-los aqui criaria duas cópias do mesmo fato, que é
    a forma mais comum de duas verdades divergirem.
    """
    espelho: Dict[str, Any] = {
        "volc_campaign_id": str(linha.get("volc_campaign_id") or ""),
        "lido_em": _iso(linha.get("lido_em")),
        "presenca": presenca_para_o_banco(linha.get("presenca")),
    }
    for coluna in ("nome", "estado_externo", "veiculacao", "canal",
                   "canal_bruto", "estrategia", "estrategia_bruta",
                   "url_final", "lance_micros", "verba_diaria_micros", "moeda"):
        if coluna in linha:
            espelho[coluna] = linha[coluna]

    # ENTREGA — as quatro só entram JUNTAS e só com o carimbo. Sem
    # `entrega_lida_em` a CHECK `..._entrega_sem_carimbo` recusa a linha, e a
    # recusa está certa: um custo sem data é indistinguível de um custo de ontem.
    if linha.get("entrega_lida_em"):
        espelho["entrega_lida_em"] = _iso(linha["entrega_lida_em"])
        for coluna in ("impressoes", "cliques", "custo_micros"):
            espelho[coluna] = linha.get(coluna)
    return espelho


def evento_de_sincronizacao(registro: Dict[str, Any]) -> Dict[str, Any]:
    """O registro de observabilidade do sincronizador → `trafego_evento`.

    A chave de idempotência mora em `chave_de_agrupamento`, que é OPACA para o
    banco — nenhuma CHECK interpreta o formato dela e nenhum índice depende do
    significado.

    ⚠️ REGRA D EM FORMA DE CHAVE. Quando não há chave de idempotência, a chave
    derivada leva o INSTANTE, e não só a conta. Uma chave estável por conta faria
    toda varredura sem chave parecer "já rodei" para a seguinte — memorizando
    trabalho que ninguém pediu para memorizar. Com o instante, a chave derivada
    nunca casa com uma busca futura, que é exatamente o comportamento certo: o
    que não foi declarado idempotente não é idempotente.
    """
    cid = str(registro.get("customer_id") or "")
    quando = _iso(registro.get("iniciado_em"))
    chave = registro.get("chave_idempotencia") or f"{TIPO_REGISTRO}:{cid}:{quando}"
    carga = {k: v for k, v in registro.items()
             if k not in ("chave_idempotencia", "customer_id", "iniciado_em")}
    return {
        "ocorrido_em": quando,
        "tipo": f"{TIPO_REGISTRO}.{registro.get('resultado') or 'ok'}",
        "chave_de_agrupamento": str(chave),
        "produtor": "backend:sincronizador",
        "sujeito_tipo": "conta",
        "sujeito_id": cid,
        "customer_id": cid or None,
        "carga": carga,
    }


def registro_de_evento(evento: Dict[str, Any]) -> Dict[str, Any]:
    """`trafego_evento` → o dicionário que o sincronizador espera de volta.

    A carga é aberta ANTES do envelope, e a ordem importa: se um dia alguém
    gravar `customer_id` dentro da carga, o valor da COLUNA continua vencendo. A
    coluna é a que tem CHECK de formato; a carga é jsonb livre.
    """
    saida: Dict[str, Any] = dict(evento.get("carga") or {})
    saida["chave_idempotencia"] = evento.get("chave_de_agrupamento")
    saida["customer_id"] = evento.get("customer_id")
    saida["iniciado_em"] = evento.get("ocorrido_em")
    saida["evento_id"] = evento.get("evento_id")
    return saida


# ═══════════════════════════════════════════════════════════════════════════
# INFRAESTRUTURA — o transporte, e só ele
# ═══════════════════════════════════════════════════════════════════════════


class _Cliente:
    """HTTP sobre o PostgREST. Nenhuma regra mora aqui.

    ⚠️ Este objeto NÃO importa `volc_ads` nem o SDK do Google, e é por isso que
    o inventário pode ser servido no caminho de render sem custo de rede externa.
    O import é o gate; não há como "só desta vez".
    """

    def __init__(self, base: str, chave: str, *, timeout_s: float = 30.0) -> None:
        self.base = (base or "").rstrip("/")
        self.chave = chave or ""
        self.timeout_s = timeout_s

    @property
    def habilitado(self) -> bool:
        return bool(self.base and self.chave)

    # Compatibilidade com quem lia `FonteSupabase.habilitada` (feminino).
    @property
    def habilitada(self) -> bool:
        return self.habilitado

    def _headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        h = {"apikey": self.chave, "Authorization": f"Bearer {self.chave}",
             "Content-Type": "application/json"}
        if prefer:
            h["Prefer"] = prefer
        return h

    async def _req(self, metodo: str, alvo: str, **kw: Any) -> Any:
        import httpx  # noqa: PLC0415 — mantém o módulo importável sem rede

        async with httpx.AsyncClient(timeout=self.timeout_s) as cli:
            r = await cli.request(metodo, f"{self.base}/rest/v1/{alvo}", **kw)
            r.raise_for_status()
            if r.status_code == 204 or not r.content:
                return None
            return r.json()

    async def _get(self, alvo: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        return (await self._req("GET", alvo, headers=self._headers(),
                                params=params)) or []

    async def _contar(self, alvo: str, params: Dict[str, Any]) -> int:
        """`HEAD` com `count=exact` e `limit=0`.

        O PostgREST devolve o total no cabeçalho `Content-Range` sem transferir
        linha nenhuma — é como a contagem do sino não depende do tamanho da
        página.
        """
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=self.timeout_s) as cli:
            r = await cli.head(f"{self.base}/rest/v1/{alvo}",
                               headers=self._headers("count=exact"),
                               params={**params, "limit": 0})
            r.raise_for_status()
            total = (r.headers.get("content-range") or "").rsplit("/", 1)[-1]
            return int(total) if total.isdigit() else 0

    async def _tudo(self, alvo: str, params: Dict[str, Any], *,
                    chave: str = "volc_campaign_id",
                    pagina: int = 1000) -> List[Dict[str, Any]]:
        """Todas as linhas, em páginas keyset — nunca "todas" numa tirada só.

        ⚠️ O PostgREST corta em `db-max-rows` (1000 por padrão) e **não avisa**:
        a resposta volta 200, com 1000 linhas, e nada nela diz que havia mais.
        É o mesmo defeito que `SupabaseService.select_all` existe para
        contornar, e aqui ele seria pior — o quadro de alertas mostraria "nenhum
        alerta" para as campanhas que ficaram do outro lado do corte.

        Keyset, e não `offset`: o inventário muda entre páginas, e um `offset`
        pularia ou repetiria linha sem nada dizendo isso.
        """
        saida: List[Dict[str, Any]] = []
        ultimo: Optional[str] = None
        while True:
            p = {**params, "order": f"{chave}.asc", "limit": pagina}
            if ultimo is not None:
                p[chave] = f"gt.{ultimo}"
            lote = await self._get(alvo, p)
            saida += lote
            if len(lote) < pagina:
                return saida
            ultimo = str(lote[-1].get(chave) or "")
            if not ultimo:
                # Sem chave não há como continuar, e continuar do zero seria um
                # laço infinito. Melhor devolver o que veio e dizer no log.
                log.warning("paginação de %s parou: linha sem %s", alvo, chave)
                return saida

    @staticmethod
    def _uniforme(linhas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """O PostgREST exige o MESMO conjunto de chaves em todas as linhas.

        Falta de chave vira `None` explícito — e é aí que mora a armadilha: uma
        campanha sem entrega no mesmo lote de uma com entrega passa a mandar
        `impressoes: null`, que SOBRESCREVE a última medida boa. Quem impede isso
        é o gatilho `trafego_espelho_preserva_ultima_boa`; sem ele, este método
        seria uma máquina de apagar medição.
        """
        if not linhas:
            return []
        chaves = sorted(set().union(*(set(l) for l in linhas)))
        return [{k: l.get(k) for k in chaves} for l in linhas]


# ═══════════════════════════════════════════════════════════════════════════
# LEITURA — implementa `inventario.FonteDeInventario`
# ═══════════════════════════════════════════════════════════════════════════


class FonteDeInventarioSupabase(_Cliente):
    """Lê o inventário das duas views canônicas. Nenhuma linha é filtrada aqui.

    Substitui `inventario.FonteSupabase`, que consultava `volc_trafego_conta` e
    `volc_trafego_campanha` — duas tabelas que nenhum schema deste repositório
    cria.
    """

    async def contas(self, filtros: "inv.FiltrosDoInventario") -> List[Dict[str, Any]]:
        return await self._get(VIEW_CONTAS, params_de_contas(filtros))

    async def campanhas(self, plano: "inv.PlanoDeConsulta") -> List[Dict[str, Any]]:
        p = params_de_campanhas(plano)
        # +1 para descobrir que existe página seguinte sem um COUNT do conjunto.
        p["limit"] = plano.limite + 1
        return await self._get(VIEW_CAMPANHAS, p)

    async def contagem(self, plano: "inv.PlanoDeConsulta") -> Dict[str, int]:
        """Total por conta, do GRUPO inteiro — não da página.

        Uma requisição `HEAD` por conta. Com as 3 contas da casa é barato; a
        partir de ~20 vale trocar por uma RPC de agregação, e o lugar de decidir
        isso é aqui, não na tela.

        ⚠️ `depois_de=None` é o ponto inteiro deste método. `dataclasses.replace`
        copia o que não foi nomeado, e o cursor viajava junto: a contagem passava
        a responder "quantas faltam depois deste ponto" enquanto a tela a
        apresentava como "quantas existem". O total ENCOLHIA a cada página, e
        chegava a zero na última — um número que se desmancha conforme o operador
        avança, sem nada na tela dizendo isso.
        """
        universo = dataclasses.replace(plano, depois_de=None)
        saida: Dict[str, int] = {}
        for cid in list(plano.contas_falhas) + list(plano.contas_lidas):
            recorte = dataclasses.replace(
                universo,
                contas_falhas=((cid,) if cid in plano.contas_falhas else ()),
                contas_lidas=((cid,) if cid in plano.contas_lidas else ()))
            saida[cid] = await self._contar(VIEW_CAMPANHAS,
                                            params_de_campanhas(recorte))
        return saida

    async def contagem_em_atencao(self, plano: "inv.PlanoDeConsulta") -> int:
        """Quantas campanhas pedem atenção, DENTRO dos filtros correntes.

        É desta contagem que o sino vive: ela não depende do tamanho da página e
        não custa nenhuma consulta ao Google. `atencao` é coluna da view, e o
        `CASE` que a calcula é a tradução literal de `dominio.pede_atencao()` —
        se as duas divergirem, o sino e a aba passam a discordar.
        """
        if plano.filtros.atencao is False:
            return 0
        recorte = dataclasses.replace(
            plano,
            # Mesmo motivo de `contagem()`: o sino conta o conjunto, não o que
            # sobrou depois da página corrente.
            depois_de=None,
            filtros=dataclasses.replace(plano.filtros, atencao=True))
        return await self._contar(VIEW_CAMPANHAS, params_de_campanhas(recorte))

    async def contagem_por_natureza(
            self, plano: "inv.PlanoDeConsulta") -> Tuple[int, int]:
        """`(operacionais, historicas)` — duas requisições `HEAD`, não uma.

        As duas nascem do MESMO plano com `incluir_historico` forçado, uma para
        cada lado. Forçar é o ponto: se herdassem o valor do operador, o número
        mudaria de significado conforme o botão de histórico — e a tela teria de
        saber em que regime está para ler o próprio total.

        `depois_de=None` pelo mesmo motivo de `contagem()`: são totais do
        conjunto, não do que sobrou depois da página.
        """
        base = dataclasses.replace(plano, depois_de=None)

        operacional = dataclasses.replace(
            base, filtros=dataclasses.replace(base.filtros,
                                              incluir_historico=False))
        # `historico=is.true` é o complemento exato do `is.false` que
        # `params_de_campanhas` emite no padrão — e ele entra AQUI, e não como
        # um terceiro estado do filtro, para a tradução continuar tendo um
        # único lugar que decide o recorte.
        params_historico = params_de_campanhas(
            dataclasses.replace(base,
                                filtros=dataclasses.replace(
                                    base.filtros, incluir_historico=True)))
        params_historico["historico"] = "is.true"

        return (
            await self._contar(VIEW_CAMPANHAS,
                               params_de_campanhas(operacional)),
            await self._contar(VIEW_CAMPANHAS, params_historico),
        )


class FonteDeReconciliacao(_Cliente):
    """O que a reconciliação precisa ler, e o que ela precisa gravar.

    Separada de `FonteDeInventarioSupabase` de propósito: o inventário é uma
    LISTAGEM paginada com filtros do operador, e a reconciliação precisa do
    universo INTEIRO das contas envolvidas — as duas perguntas têm formas
    diferentes e misturá-las faria uma delas herdar a paginação da outra.
    """

    #: As colunas que `reconciliacao.CampanhaConhecida` consome. Lista fechada:
    #: `select=*` traria o artigo inteiro de colunas que a regra não usa, e
    #: qualquer coluna nova do schema entraria no payload sem ninguém decidir.
    COLUNAS = ("volc_campaign_id,campaign_id,customer_id,nome,estado_externo,"
               "canal,historico,url_final,lido_em,campaign_lineage_id,"
               "vinculo_id,opportunity_id,funnel_run_id")

    async def campanhas_conhecidas(
            self, customer_ids: Sequence[str]) -> List[Dict[str, Any]]:
        """Todas as campanhas destas contas — inclusive as históricas.

        ⚠️ O histórico ENTRA aqui, ao contrário do inventário. A reconciliação
        precisa distinguir "não há campanha" de "há, e ela foi removida": a
        primeira libera a montagem, a segunda pede relançamento declarado. Sem a
        história, as duas responderiam a mesma coisa.
        """
        contas = [str(c) for c in customer_ids if str(c or "").strip()]
        if not contas:
            return []
        return await self._tudo(VIEW_CAMPANHAS, {
            "select": self.COLUNAS,
            "customer_id": _in(contas),
        })

    async def uma_campanha(self, volc_campaign_id: str) -> Optional[Dict[str, Any]]:
        """UMA campanha, pela identidade interna. `None` quando não existe.

        ⚠️ **Não varre o inventário.** `volc_campaign_id` é a chave primária de
        `trafego_campanha`, e o filtro `eq` resolve por índice. Reaproveitar a
        listagem paginada para achar uma linha custaria as famílias de conta, as
        contagens e o keyset — tudo para descartar tudo menos uma.

        Também não é uma segunda projeção: a view é a MESMA do inventário, e a
        página canônica mostra os mesmos fatos que a lista, sob outra forma.
        Duas projeções da mesma campanha divergiriam no dia em que uma delas
        ganhasse coluna.
        """
        chave = str(volc_campaign_id or "").strip()
        if not chave:
            return None
        linhas = await self._get(VIEW_CAMPANHAS, {
            "select": "*",
            "volc_campaign_id": f"eq.{chave}",
            "limit": 1,
        })
        return linhas[0] if linhas else None

    async def confirmar_vinculo(self, linha: Dict[str, Any]) -> Dict[str, Any]:
        """Grava a decisão humana. `regra` e `evidencia` são obrigatórias.

        A tabela recusa vínculo sem regra (`trafego_vinculo_regra_nao_vazia`) e
        sem quem confirmou. Não é formalidade: um vínculo sem regra visível é
        uma caixa-preta que o operador não tem como contestar depois, e vínculo
        errado contamina atribuição de receita de forma permanente (ADR-09).

        Devolve a linha gravada, com o `vinculo_id`, para o recibo.
        """
        criada = await self._req(
            "POST", TABELA_VINCULO,
            headers=self._headers("return=representation"),
            json=[linha])
        return (criada or [{}])[0]

    async def desfazer_vinculo(self, vinculo_id: str, *, por: str,
                               motivo: Optional[str]) -> Dict[str, Any]:
        """Desvincular é operação de primeira classe, não exceção (ADR-09).

        ⚠️ `UPDATE`, e nunca `DELETE`. A linha fica: é ela que guarda quem
        vinculou, quando, com que regra e por que foi desfeito. Apagar deixaria
        a campanha sem vínculo e sem rastro de que houve um — indistinguível de
        uma campanha que nunca foi vinculada.
        """
        atualizada = await self._req(
            "PATCH", TABELA_VINCULO,
            headers=self._headers("return=representation"),
            params={"vinculo_id": f"eq.{vinculo_id}",
                    "desfeito_em": "is.null"},
            json={"desfeito_por": por,
                  "desfeito_em": datetime.now(timezone.utc).isoformat(),
                  "desfeito_motivo": motivo})
        return (atualizada or [{}])[0]


# ═══════════════════════════════════════════════════════════════════════════
# ESCRITA — implementa `sincronizador.RepositorioDeSnapshot`
# ═══════════════════════════════════════════════════════════════════════════


class RepositorioDePlanoDeMensuracao(_Cliente):
    """Grava e relê o `campaign_measurement_plan` (migration v12_02).

    ⚠️ A escrita passa pela FUNÇÃO `volc_registrar_plano_de_mensuracao`, e não
    por um `POST` na tabela — porque `service_role` não tem INSERT ali. A
    migration foi desenhada assim de propósito: a idempotência pela impressão
    mora dentro da função, numa transação só, e um INSERT direto a jogaria para
    o lado de quem chama, onde ela sumiria no primeiro retry.

    ⚠️ E o erro NÃO é engolido. Uma guarda do banco recusando (uma das seis
    invariantes) e o banco fora do ar exigem reações opostas: a primeira é um
    plano que não devia ter sido montado, a segunda é uma indisponibilidade.
    Colapsá-las num `return None` faria a rota tratar as duas como "não deu".
    """

    async def registrar(self, documento: Dict[str, Any]) -> Optional[str]:
        """Grava o plano e devolve o `plano_id`. Idempotente pela impressão.

        `None` quando o cliente não está habilitado — ambiente sem Supabase é
        estado, não erro. Quem chama decide o que fazer com esse `None`, e no
        caminho de `/subir` ele é RECUSA: criar campanha sem plano gravado
        produz exatamente a campanha que ninguém consegue explicar depois.

        ⚠️ As demais falhas sobem TIPADAS. `PlanoRecusado` é uma das seis
        invariantes disparando; `PlanoIndisponivel` é o banco fora do ar ou a
        migration não aplicada. A tradução mora em `erro_de_plano`, que é pura.
        """
        if not self.habilitado:
            return None
        import httpx  # noqa: PLC0415 — mantém o módulo importável sem rede

        try:
            resposta = await self._req(
                "POST", f"rpc/{RPC_REGISTRAR_PLANO}",
                headers=self._headers(), json={"documento": documento})
        except httpx.HTTPStatusError as exc:
            raise erro_de_plano(exc) from exc
        except httpx.HTTPError as exc:
            raise PlanoIndisponivel(
                f"o registro do plano não respondeu: {exc}") from exc
        # A função devolve `uuid`; o PostgREST o entrega como escalar JSON.
        if isinstance(resposta, list):
            resposta = resposta[0] if resposta else None
        return str(resposta) if resposta else None

    async def por_intencao(self, chave_intencao: str) -> List[Dict[str, Any]]:
        """Todas as linhas de UMA intenção, a mais recente primeiro.

        ⚠️ É esta leitura que prova "exatamente uma intenção une o pré e o
        pós-nascimento". A tabela é append-only e a impressão inclui o
        `campaign_id`, então a mesma intenção tem DUAS linhas depois de a
        campanha nascer: uma sem id, outra com. Elas não são duplicata — são a
        mesma decisão antes e depois de ela ter endereço.

        ⚠️ Filtra por `chave_intencao` sozinha, e isso é seguro porque a chave
        JÁ é um sha256 que inclui a conta e o MCC normalizados
        (`routers/trafego.py:_plano_aprovavel`). Duas contas nunca produzem a
        mesma chave, então não há como esta consulta atravessar a fronteira de
        conta — e há prova disso em `test_trafego_plano_persistido.py`.
        """
        chave = str(chave_intencao or "").strip()
        if not chave or not self.habilitado:
            return []
        return await self._get(TABELA_PLANO_DE_MENSURACAO, {
            "select": "*",
            "chave_intencao": f"eq.{chave}",
            "order": "versao.desc,registrado_em.desc",
        })

    async def por_prefixo_de_intencao(self, prefixo: str) -> List[Dict[str, Any]]:
        """As linhas cuja `chave_intencao` COMEÇA com `prefixo`.

        Existe para uma porta só: a reconciliação tardia, quando o operador tem
        a MARCA remota (`VOLC-CANARY-<12 hex>`) e não a chave inteira. A marca
        são os 12 primeiros hex do sha256 — 48 bits —, então este filtro NÃO é
        uma identidade: ele é um candidato, e quem chama tem de tratar duas
        chaves distintas como ambiguidade, nunca escolher a primeira.

        ⚠️ Exige 12 caracteres hex, no mínimo. Um prefixo curto varreria a
        tabela e devolveria planos de contas alheias — a chave inclui a conta,
        mas um prefixo de 2 caracteres não inclui nada.
        """
        pre = str(prefixo or "").strip().lower()
        if len(pre) < 12 or not all(c in "0123456789abcdef" for c in pre):
            return []
        if not self.habilitado:
            return []
        return await self._get(TABELA_PLANO_DE_MENSURACAO, {
            "select": "*",
            "chave_intencao": f"like.{pre}*",
            "order": "versao.desc,registrado_em.desc",
        })

    async def vigente_da_conta(self, customer_id: str
                               ) -> Optional[Dict[str, Any]]:
        """O plano mais recente desta conta, ou `None` quando não há nenhum.

        ⚠️ `None` aqui é "não há linha", e é DIFERENTE de um plano cujo
        `completo` é `false`. O primeiro diz que ninguém leu esta conta ainda; o
        segundo diz que alguém leu e a conta não está pronta. Quem chama precisa
        das duas respostas separadas.
        """
        chave = str(customer_id or "").strip()
        if not chave or not self.habilitado:
            return None
        linhas = await self._get(TABELA_PLANO_DE_MENSURACAO, {
            "select": "*",
            "customer_id": f"eq.{chave}",
            "order": "lido_em.desc,registrado_em.desc",
            "limit": 1,
        })
        return linhas[0] if linhas else None

    async def vigente_da_campanha(self, volc_campaign_id: str
                                  ) -> Optional[Dict[str, Any]]:
        """O plano mais recente de UMA campanha interna."""
        chave = str(volc_campaign_id or "").strip()
        if not chave or not self.habilitado:
            return None
        linhas = await self._get(TABELA_PLANO_DE_MENSURACAO, {
            "select": "*",
            "volc_campaign_id": f"eq.{chave}",
            "order": "lido_em.desc,registrado_em.desc",
            "limit": 1,
        })
        return linhas[0] if linhas else None


class RepositorioDeSnapshotSupabase(_Cliente):
    """Escreve o snapshot nas tabelas canônicas.

    Substitui `sincronizador.RepositorioSupabase`, que escrevia em
    `volc_trafego_conta`, `volc_trafego_campanha` e `volc_trafego_sincronizacao`.
    """

    # ── idempotência ────────────────────────────────────────────────────────

    async def sincronizacao_por_chave(self, chave: str) -> Optional[Dict[str, Any]]:
        """O registro mais recente daquela chave, ou `None`.

        ⚠️ Devolve TAMBÉM o que falhou, e isso é a regra D funcionando, não um
        descaso. Filtrar a falha aqui pareceria mais seguro e seria pior: quem
        chama precisa VER que a tentativa anterior falhou para decidir refazer o
        trabalho. Idempotência existe para não repetir trabalho FEITO, e falha
        não é trabalho feito — é justamente o que o retry veio refazer.

        Append-only significa que a mesma chave pode ter várias linhas (falhou,
        depois deu certo). A mais recente é a que responde.
        """
        linhas = await self._get(TABELA_EVENTO, {
            "select": "*",
            "chave_de_agrupamento": f"eq.{chave}",
            "tipo": f"like.{TIPO_REGISTRO}.*",
            "order": "ocorrido_em.desc,registrado_em.desc",
            "limit": 1,
        })
        return registro_de_evento(linhas[0]) if linhas else None

    async def ultima_sincronizacao(self, customer_id: str) -> Optional[Dict[str, Any]]:
        linhas = await self._get(TABELA_EVENTO, {
            "select": "*",
            "customer_id": f"eq.{customer_id}",
            "tipo": f"like.{TIPO_REGISTRO}.*",
            "order": "ocorrido_em.desc,registrado_em.desc",
            "limit": 1,
        })
        return registro_de_evento(linhas[0]) if linhas else None

    async def registrar_sincronizacao(self, registro: Dict[str, Any]) -> Dict[str, Any]:
        """Apenda a observabilidade da varredura no diário.

        `INSERT` simples, sem `on_conflict`: o diário é append-only e o gatilho
        `trafego_evento_append_only` recusa UPDATE. Um upsert aqui não teria como
        funcionar — e o fato de não ter para onde escrever por cima é a
        propriedade, não a limitação.
        """
        linhas = await self._req(
            "POST", TABELA_EVENTO,
            headers=self._headers("return=representation"),
            json=[evento_de_sincronizacao(registro)])
        return registro_de_evento((linhas or [{}])[0]) or registro

    # ── snapshot da conta ───────────────────────────────────────────────────

    async def gravar_conta(self, linha: Dict[str, Any]) -> None:
        await self._req("POST", TABELA_SNAPSHOT,
                        headers=self._headers("resolution=merge-duplicates"),
                        params={"on_conflict": "customer_id"},
                        json=[linha_de_snapshot(linha)])

    # ── campanhas: identidade e espelho, nesta ordem ────────────────────────

    async def gravar_campanhas(self, linhas: List[Dict[str, Any]]) -> None:
        """Duas gravações, e a ordem é obrigatória.

        A identidade vai primeiro porque o espelho tem FK para ela: gravar o
        espelho antes falharia com violação de chave estrangeira para toda
        campanha nova. É a mesma disciplina da ordem "campanhas antes da conta"
        no sincronizador — quando o processo morre no meio, o estado que sobra
        precisa ser um estado honesto.

        A identidade usa `ignore-duplicates`, e não `merge-duplicates`, porque
        ela é IMUTÁVEL: um upsert reenviaria `criada_por` a cada varredura e o
        gatilho `trafego_campanha_identidade_imutavel` levantaria — corretamente,
        porque origem não se reescreve. `DO NOTHING` diz o que se quer dizer: a
        varredura declara identidade se ainda não houver; ela nunca a corrige.

        ⚠️ O `on_conflict` cobre a chave primária. Uma colisão no índice
        `trafego_campanha_identidade_externa_ux` (mesma conta e campanha com
        OUTRO `volc_campaign_id`) NÃO é ignorada, e não deve ser: ela significa
        que a derivação da identidade quebrou, e descobrir isso agora é melhor
        que descobrir depois com dois endereços para a mesma campanha.
        """
        if not linhas:
            return
        await self._req(
            "POST", TABELA_CAMPANHA,
            headers=self._headers("resolution=ignore-duplicates"),
            params={"on_conflict": "volc_campaign_id"},
            json=self._uniforme([identidade_de_campanha(l) for l in linhas]))
        await self._req(
            "POST", TABELA_ESPELHO,
            headers=self._headers("resolution=merge-duplicates"),
            params={"on_conflict": "volc_campaign_id"},
            json=self._uniforme([espelho_de_campanha(l) for l in linhas]))

    # ═══════════════════════════════════════════════════════════════════
    # A PORTA QUE O SINCRONIZADOR EXIGE
    # ═══════════════════════════════════════════════════════════════════
    #
    # As duas frentes desenharam a mesma coisa com formas diferentes. Esta
    # classe nasceu com uma API PLANA (`campanhas`, `gravar_campanhas`), e o
    # `sincronizador.RepositorioDeSnapshot` pede uma API DIVIDIDA
    # (`identidades`/`espelhos`, `declarar_identidades`/`gravar_espelhos`).
    #
    # A dividida venceu, e não por antiguidade: ela espelha o split do schema
    # canônico, onde identidade (o que o VOLC declara) e espelho (o que a conta
    # respondeu) são tabelas separadas de propósito. Uma porta que junta as
    # duas convida quem a usa a tratá-las como uma coisa só — que é exatamente
    # o que E-08 custou caro para separar.
    #
    # Os métodos planos continuam, porque `alertas.py` e a leitura os usam. Não
    # são um segundo caminho de escrita: `gravar_campanhas` é a composição dos
    # dois abaixo, e há teste que compara os payloads.
    #
    # `conferir_porta()` no sincronizador foi o que revelou o descasamento — em
    # tempo de execução, com os oito nomes que faltavam, em vez de um
    # `AttributeError` no meio da primeira varredura real.

    async def rodada_concluida(self, chave: str) -> Optional[Dict[str, Any]]:
        """A rodada com esta chave já terminou? Só SUCESSO conta.

        Delegado a `sincronizacao_por_chave`. O filtro de fracasso mora no
        sincronizador, que é quem sabe a regra: memorizar falha faria o retry
        responder "já rodei" sem nunca ter lido nada.
        """
        return await self.sincronizacao_por_chave(chave)

    async def registrar_evento(self, evento: Dict[str, Any]) -> None:
        """Apenda no diário. `trafego_evento` não aceita UPDATE nem DELETE."""
        if not evento:
            return
        await self._req("POST", TABELA_EVENTO,
                        headers=self._headers("return=minimal"),
                        json=self._uniforme([evento]))

    async def ultima_tentativa(self, customer_id: str) -> Optional[datetime]:
        """Quando a conta foi tentada pela última vez — para o limite de taxa.

        Devolve `datetime`, não o registro inteiro: quem chama só precisa saber
        se já passou tempo suficiente, e devolver o registro convidaria a
        decidir outra coisa a partir dele.
        """
        linha = await self.ultima_sincronizacao(customer_id)
        if not linha:
            return None
        bruto = linha.get("tentativa_em") or linha.get("ocorrido_em")
        return _para_datetime(bruto)

    async def identidades(self, customer_id: str) -> Dict[str, Dict[str, Any]]:
        """As identidades da conta, indexadas por `campaign_id` externo.

        Indexado por `campaign_id` e não por `volc_campaign_id` porque quem
        chama tem em mãos o que a conta respondeu, e é por ali que a varredura
        descobre se aquela campanha já tem endereço interno.
        """
        linhas = await self._req(
            "GET", TABELA_CAMPANHA,
            headers=self._headers(),
            params={"select": "*", "customer_id": f"eq.{customer_id}"}) or []
        return {str(l.get("campaign_id")): l for l in linhas if l.get("campaign_id")}

    async def declarar_identidades(self, linhas: List[Dict[str, Any]]) -> None:
        """Declara identidade para quem ainda não tem. NUNCA corrige.

        `ignore-duplicates`, não `merge`: a identidade é imutável, e um upsert
        reenviaria `criada_por` a cada varredura — o gatilho
        `trafego_campanha_identidade_imutavel` levantaria, corretamente.
        """
        if not linhas:
            return
        await self._req(
            "POST", TABELA_CAMPANHA,
            headers=self._headers("resolution=ignore-duplicates"),
            params={"on_conflict": "volc_campaign_id"},
            json=self._uniforme(list(linhas)))

    async def espelhos(self, customer_id: str) -> Dict[str, Dict[str, Any]]:
        """Os espelhos da conta, indexados por `volc_campaign_id`.

        O espelho não guarda `customer_id` — ele mora na identidade —, então a
        seleção passa pelo relacionamento. Índice por `volc_campaign_id` porque
        é a chave que o espelho de fato tem.
        """
        ids = await self.identidades(customer_id)
        chaves = [str(l.get("volc_campaign_id")) for l in ids.values()
                  if l.get("volc_campaign_id")]
        if not chaves:
            return {}
        linhas = await self._req(
            "GET", TABELA_ESPELHO,
            headers=self._headers(),
            params={"select": "*",
                    "volc_campaign_id": f"in.({','.join(chaves)})"}) or []
        return {str(l.get("volc_campaign_id")): l for l in linhas
                if l.get("volc_campaign_id")}

    async def gravar_espelhos(self, linhas: List[Dict[str, Any]]) -> None:
        """A leitura corrente. `merge-duplicates` porque o espelho É reescrito.

        Ao contrário da identidade: o espelho existe justamente para mudar a
        cada varredura. O gatilho de preservação decide, coluna a coluna, o que
        sobrevive a uma leitura que não mediu.
        """
        if not linhas:
            return
        await self._req(
            "POST", TABELA_ESPELHO,
            headers=self._headers("resolution=merge-duplicates"),
            params={"on_conflict": "volc_campaign_id"},
            json=self._uniforme(list(linhas)))

    async def gravar_snapshot_de_conta(self, linha: Dict[str, Any]) -> None:
        """O carimbo da conta. Delegado a `gravar_conta`, que já o faz."""
        await self.gravar_conta(linha)

    async def marcar_ausentes(self, customer_id: str, vistos: Sequence[str],
                              quando: datetime) -> int:
        """As campanhas da conta que a varredura NÃO viu viram `nao_encontrada`.

        Duas requisições, e não uma, porque o espelho não guarda `customer_id`
        nem `campaign_id` — os dois moram na identidade. Descobrir quem marcar
        exige a tabela de identidade, e o PostgREST não faz `UPDATE ... FROM`.

        A alternativa seria derivar o alvo do formato do `volc_campaign_id`
        (`gads-<conta>-<campanha>`), com um `like`. Recusada: acoplaria a
        persistência à REGRA DE DERIVAÇÃO da identidade, que é do domínio, e um
        dia em que ela mudasse este método passaria a marcar a conta errada em
        silêncio.

        ⚠️ Só é chamado depois de uma leitura BOA da camada comum. Numa varredura
        que falhou, ninguém pode afirmar ausência — e o sincronizador nem chega
        aqui nesse caminho.
        """
        # ⚠️ O FILTRO É POR `volc_campaign_id`, NÃO POR `campaign_id`.
        #
        # A porta diz, na própria docstring: "`vistos` são `volc_campaign_id`,
        # não `campaign_id`". A versão anterior filtrava por `campaign_id` e
        # comparava um id externo do Google ("24155028398") contra uma lista de
        # UUIDs internos. A comparação NUNCA casava, então "quem eu não vi"
        # devolvia TODAS as campanhas da conta.
        #
        # Medido na primeira varredura real: as 84 campanhas das três contas
        # foram lidas com sucesso e gravadas como `nao_encontrada` — o
        # inventário afirmava que nada existia, logo depois de encontrar tudo.
        # E como `presenca <> 'presente'` é termo da regra de atenção, os 84
        # apareciam pedindo atenção: o alerta marcando o universo, que é o
        # mesmo que alerta nenhum.
        #
        # Nenhum teste pegou porque o dublê aceitava qualquer nome de coluna.
        params: Dict[str, Any] = {"select": "volc_campaign_id",
                                  "customer_id": f"eq.{customer_id}"}
        if vistos:
            params["volc_campaign_id"] = f"not.{_in(vistos)}"
        alvos = [str(l.get("volc_campaign_id")) for l in
                 await self._get(TABELA_CAMPANHA, params)]
        if not alvos:
            return 0

        linhas = await self._req(
            "PATCH", TABELA_ESPELHO,
            headers=self._headers("return=representation"),
            params={
                "volc_campaign_id": _in(alvos),
                # Já marcada continua marcada. Reescrever só empurraria
                # `lido_em` para frente sem nenhum fato novo por trás.
                #
                # ⚠️ `presenca=neq.nao_encontrada` SOZINHO não serve, e o motivo
                # é a diferença entre este schema e o antigo: aqui `presente` é
                # NULO, e `<>` nunca casa com nulo. O filtro simples deixaria de
                # fora exatamente as campanhas vivas — as únicas que podem
                # SUMIR. O `or` com `is.null` é o que faz a marcação alcançar
                # quem precisa ser marcado.
                "or": f"(presenca.is.null,presenca.neq.{inv.NAO_ENCONTRADA})",
            },
            json={"presenca": inv.NAO_ENCONTRADA, "lido_em": quando.isoformat()})
        return len(linhas or [])


# ═══════════════════════════════════════════════════════════════════════════
# ALERTAS — implementa `alertas.FonteDeAlertas`
# ═══════════════════════════════════════════════════════════════════════════


class FonteDeAlertasSupabase(_Cliente):
    """O quadro de alertas, saindo do Postgres. NUNCA da conta de anúncios.

    Medido em 24/08/2026: `/api/trafego/alertas` rodava ~5 GAQL por conta em
    tempo de render, e o sino chama essa rota em toda página do produto — abrir
    qualquer tela custava rede para o Google. Aqui não há caminho para lá: este
    módulo não importa `volc_ads` nem o SDK, e o import é o gate.
    """

    async def contas(self) -> List[Dict[str, Any]]:
        """Todas as contas com snapshot. O desfecho da última tentativa é o que
        decide o que cada linha de campanha significa, então ele vem primeiro."""
        return await self._tudo(VIEW_CONTAS, {"select": "*"},
                                chave="customer_id")

    async def campanhas(self) -> List[Dict[str, Any]]:
        """Todas as campanhas das contas conhecidas, SEM filtrar por estado.

        Filtrar `estado_externo` no banco esconderia exatamente o caso que o
        quadro precisa mostrar: uma campanha que a varredura viu `PAUSED` antes
        e não conseguiu reler agora tem de aparecer para virar `faltou`. O
        filtro a apagaria justamente quando não se sabe nada dela.
        """
        return await self._tudo(VIEW_CAMPANHAS, {"select": "*"})

    async def transicoes_de_estado(
        self, volc_campaign_ids: Sequence[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """O diário de transições de estado, por campanha.

        ⚠️ `TIPO_ESTADO` e `chave_de_estado()` são importados de `alertas.py`, e
        não copiados. O próprio módulo avisa que o tipo é um acordo entre
        produtor e consumidor e que mudá-lo num lugar só faz `horas_ligada`
        virar `null` em silêncio — uma cópia aqui seria o segundo lugar. O
        import é tardio para não amarrar a ordem de carga dos dois módulos.

        Consulta em lotes porque a chave viaja na URL: um `in.(...)` com mil
        chaves estoura o limite de tamanho do request, e estourar seria um erro
        de rede sem relação visível com a causa.
        """
        from app.trafego import alertas as alr  # noqa: PLC0415

        ids = [str(i) for i in volc_campaign_ids if i]
        saida: Dict[str, List[Dict[str, Any]]] = {i: [] for i in ids}
        for inicio in range(0, len(ids), 200):
            lote = ids[inicio:inicio + 200]
            por_chave = {alr.chave_de_estado(i): i for i in lote}
            linhas = await self._get(TABELA_EVENTO, {
                "select": "*",
                "tipo": f"eq.{alr.TIPO_ESTADO}",
                "chave_de_agrupamento": _in(list(por_chave)),
                "order": "ocorrido_em.asc",
            })
            for linha in linhas:
                dono = por_chave.get(str(linha.get("chave_de_agrupamento") or ""))
                if dono is None:
                    continue
                # `de`/`para` moram na carga; `ocorrido_em` é coluna. A coluna
                # vence se um dia os dois existirem: ela é a que tem tipo.
                transicao = dict(linha.get("carga") or {})
                transicao["ocorrido_em"] = linha.get("ocorrido_em")
                saida[dono].append(transicao)
        return saida


# ---------------------------------------------------------------------------
# APELIDO DE COMPATIBILIDADE — condição de aposentadoria declarada
# ---------------------------------------------------------------------------
# `sincronizador.fabricar_repositorio()` chama `persistencia.RepositorioSupabase`.
# O nome canônico aqui é `RepositorioDeSnapshotSupabase`, simétrico com
# `FonteDeInventarioSupabase` e com a porta que ele satisfaz
# (`RepositorioDeSnapshot`) — e o nome curto é justamente o da classe REMOVIDA
# de `sincronizador.py`, que reusá-lo confundiria com o que foi apagado.
#
# O apelido existe para a troca acontecer sem as duas frentes precisarem
# aterrissar no mesmo commit. APOSENTADORIA: quando `fabricar_repositorio()`
# passar a citar o nome longo, esta linha sai — e `pedidos_ao_integrador`
# registra o pedido.
RepositorioSupabase = RepositorioDeSnapshotSupabase
