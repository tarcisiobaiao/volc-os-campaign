"""O quadro de alertas de entrega — projeção PURA do snapshot persistido.

## O gate que este arquivo fecha

Medido em 24/08/2026: `GET /api/trafego/alertas` chamava `volc_ads.entrega`, que
roda ~5 GAQL **por conta** em tempo de render. O `Layout` monta o sino em TODA
página, então abrir qualquer tela do produto — o Pautador, o Redator, o
dashboard antigo — custava rede para o Google. Três contas, cinco consultas,
cada navegação.

O conserto não é "chamar menos": é **não chamar**. Este módulo responde a mesma
pergunta lendo o que a varredura já gravou em Postgres. Nenhum import de
`volc_ads` nem de `google.ads` aparece aqui, e há quatro testes que instalam um
bloqueio de import e falham se algum caminho de render tentar carregá-los.

## A dificuldade real, e como ela foi resolvida

`AlertaDeEntrega` (em `src/types/trafego.ts`) pede quatro coisas que não tinham
campo no contrato do inventário nem coluna no espelho: `horas_ligada`, `razoes`,
`aprovacao_do_anuncio` e `alteracoes`. Havia três saídas, e duas eram ruins:

· **reduzir a tela** — tirar os campos. Perde-se o alerta que existe: "ligada há
  22 horas, uma impressão, R$ 0,00" foi exatamente o achado de 20/08 que nenhuma
  tela mostrava;
· **inventar o dado** — preencher com zero ou com texto genérico. É o defeito
  que este domínio inteiro existe para não cometer;
· **estender o snapshot** — que é o que foi feito.

`horas_ligada` sai de `trafego_evento`: a varredura passou a registrar a
transição de estado de cada campanha, então "desde quando está ENABLED" é uma
consulta ao diário, não uma pergunta à conta. `razoes` são derivadas do espelho
— o que a conta respondeu sobre veiculação, verba, lance e entrega. O que **não**
é derivável de nada que temos sai como `null`, e o quadro traz um campo
`nao_sabemos` dizendo exatamente o quê: a tela informa que não sabe, em vez de
mostrar um vazio que parece "está tudo bem".

## Regra A dentro do alerta

Todo alerta carrega a `leitura` de onde ele saiu. Um alerta é uma afirmação
sobre AGORA ("esta campanha não está gastando"), e ele nasce de um dado do
passado. Sem a idade visível, um snapshot de ontem produz um alerta com cara de
tempo real — que é pior que não alertar, porque o operador age.

Uma conta cuja última varredura falhou continua no quadro, com o carimbo da
última leitura BOA e uma linha em `faltou`. Sumir com ela seria transformar "não
consegui ler" em "está tudo bem", que são fatos opostos (regra C).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from app.trafego import dominio as dom
from app.trafego import inventario as inv

log = logging.getLogger("volc.trafego.alertas")

#: Versão do contrato do quadro. Sobe quando um consumidor precisa ser avisado.
VERSAO_ALERTAS = 1

#: O tipo de evento que a varredura apenda quando o estado de uma campanha muda.
#: ⚠️ O nome é acordo entre `sincronizador.py` (produtor) e este módulo
#: (consumidor); mudá-lo num lugar só faz `horas_ligada` virar `null` em silêncio
#: — e `null` aqui é um resultado legítimo, então nada denunciaria.
TIPO_ESTADO = "trafego.campanha.estado"

#: O prefixo da `chave_de_agrupamento` desses eventos em `trafego_evento`.
def chave_de_estado(volc_campaign_id: str) -> str:
    """A chave que agrupa todas as transições de estado de UMA campanha."""
    return f"{TIPO_ESTADO}:{volc_campaign_id}"


# ── o que a projeção não consegue responder ─────────────────────────────────
#
# Declarado como dado, e não escondido num `null` silencioso. A tela precisa
# saber a diferença entre "não há nada a dizer" e "não temos como saber".

#: Aprovação do anúncio. Vive numa entidade filha da campanha, que o núcleo não
#: nomeia (gate do SPEC §9.4) e a varredura comum não lê. Enquanto não houver
#: leitura dela no snapshot, o campo sai `null`.
NAO_SEI_APROVACAO = (
    "aprovacao_do_anuncio: o espelho é da CAMPANHA; a aprovação é de uma "
    "entidade filha que a varredura comum não lê. Sai null."
)

#: Quem mexeu e por onde. `change_event` do Google Ads é uma consulta à CONTA, e
#: fazê-la no render é exatamente o custo que esta rota deixou de pagar. O que
#: sabemos é a transição que NÓS observamos — não o autor dela.
NAO_SEI_AUTORIA = (
    "alteracoes.origem/quem: quem alterou vive no histórico da conta, que só uma "
    "consulta ao Google responderia. As transições são as que a varredura viu."
)


# ── as formas do contrato ───────────────────────────────────────────────────


@dataclass(frozen=True)
class AlteracaoObservada:
    """Uma mudança de estado que a VARREDURA viu — não o histórico do Google.

    A distinção está no campo, não só no comentário: `origem` e `quem` saem
    `null` porque não os observamos. Preenchê-los com "varredura" diria que fomos
    nós que mexemos, e a única coisa pior que não saber é afirmar errado.
    """

    quando: str
    campo: str
    de: Optional[str]
    para: Optional[str]
    origem: Optional[str]
    quem: Optional[str]
    resumo: str


@dataclass(frozen=True)
class Alerta:
    """Uma campanha ligada que não gastou, projetada do snapshot.

    Espelha `AlertaDeEntrega` de `src/types/trafego.ts` campo a campo, com dois
    acréscimos que o contrato ainda não declara e que estão no pedido ao
    integrador: `leitura` (regra A — de quando é este número) e `presenca`.
    """

    customer_id: str
    customer_name: str
    campaign_id: str
    campaign_name: str
    status: str
    veiculacao: str
    horas_ligada: Optional[float]
    impressoes: Optional[int]
    cliques: Optional[int]
    custo: Optional[float]
    lance: Optional[float]
    orcamento: Optional[float]
    teto_de_cliques: Optional[int]
    razoes: List[str]
    aprovacao_do_anuncio: Optional[str]
    sintoma: str
    revisar: List[str]
    alteracoes: List[Dict[str, Any]]
    presenca: str
    leitura: Optional[Dict[str, Any]]
    volc_campaign_id: str


@dataclass(frozen=True)
class ContaNoQuadro:
    customer_id: str
    nome: str
    ligadas: Optional[int]
    erro: Optional[str]
    frescor: str
    leitura: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class Quadro:
    """O envelope. `QuadroDeAlertas` mais o frescor — e frescor não é enfeite.

    O quadro antigo não tinha `frescor` porque era calculado na hora: a resposta
    era, por construção, do instante em que aparecia. Lendo do snapshot isso
    deixa de ser verdade, e o campo passa a ser obrigatório — um alerta sem idade
    visível é a regra A quebrada no lugar onde ela mais custa.
    """

    versao: int
    alertas: List[Alerta]
    verificadas: int
    contas: List[ContaNoQuadro]
    horas_ate_alertar: int
    frescor: str
    leitura: Optional[Dict[str, Any]]
    parcial: bool
    faltou: List[Dict[str, Any]]
    nao_sabemos: List[str] = field(default_factory=list)

    def json(self) -> Dict[str, Any]:
        import dataclasses  # noqa: PLC0415 — só na serialização

        return dataclasses.asdict(self)


# ── a porta ─────────────────────────────────────────────────────────────────


class FonteDeAlertas(Protocol):
    """De onde o quadro sai. Postgres, sempre — nunca a conta de anúncios.

    Mapeamento com `supabase/migrations/v9_01_trafego_inventario.sql`:

    · `contas()` → `trafego_snapshot_conta`. Mesmas colunas que
      `inventario.FonteDeInventario.contas`, e pela mesma razão: o desfecho da
      última tentativa é o que decide o que uma linha de campanha significa.

    · `campanhas()` → `trafego_campanha` ⋈ `trafego_campanha_espelho`, todas as
      campanhas das contas pedidas. **Não** filtre por `estado_externo` no banco:
      uma campanha que a varredura viu `PAUSED` na leitura anterior e não
      conseguiu reler agora tem de aparecer para virar `faltou`, e o filtro a
      esconderia justamente no caso em que não se sabe nada dela.

    · `transicoes_de_estado()` → `trafego_evento` de tipo `TIPO_ESTADO`, por
      `chave_de_agrupamento`, em ordem crescente de `ocorrido_em`. É deste
      diário que `horas_ligada` sai.
    """

    async def contas(self) -> List[Dict[str, Any]]:
        ...

    async def campanhas(self) -> List[Dict[str, Any]]:
        ...

    async def transicoes_de_estado(
        self, volc_campaign_ids: Sequence[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        ...


# ── derivações ──────────────────────────────────────────────────────────────


def _dt(valor: Any) -> Optional[datetime]:
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        d = valor
    else:
        try:
            d = datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _micros_para_moeda(micros: Any) -> Optional[float]:
    """Micros → unidade da moeda. `None` sobrevive; zero sobrevive.

    Regra B na conversão: `micros or 0` transformaria "não medi" em "R$ 0,00", e
    R$ 0,00 é exatamente a afirmação que o alerta faz. Um alerta que nasce de
    uma divisão descuidada não é alerta, é ruído com aparência de fato.
    """
    if micros is None or micros == "":
        return None
    try:
        return int(micros) / 1_000_000
    except (TypeError, ValueError):
        return None


def horas_ligada(
    transicoes: Sequence[Dict[str, Any]], agora: datetime
) -> Optional[float]:
    """Há quantas horas a conta responde `ENABLED` para esta campanha.

    Sai do diário `trafego_evento`, e a leitura é simples: a ÚLTIMA transição
    observada. Se ela terminou em `ENABLED`, a campanha está ligada desde então;
    se terminou em qualquer outra coisa, ela não está ligada e a pergunta não se
    aplica.

    ⚠️ Devolve `None` quando não há transição nenhuma — e `None` NÃO é zero. Uma
    campanha que já estava ligada antes de o diário existir tem estado conhecido
    e antiguidade desconhecida; chamar isso de "ligada há 0 horas" faria uma
    campanha parada há um mês parecer recém-criada, e `merece_alerta()` recusa
    alertar sem esse número justamente por isso.
    """
    ordenadas = sorted(
        (t for t in transicoes if _dt(t.get("ocorrido_em"))),
        key=lambda t: _dt(t.get("ocorrido_em")),  # type: ignore[arg-type]
    )
    if not ordenadas:
        return None
    ultima = ordenadas[-1]
    if str(ultima.get("para") or "").strip().upper() != dom.LIGADA:
        return None
    quando = _dt(ultima.get("ocorrido_em"))
    if quando is None:
        return None
    return max((agora - quando).total_seconds() / 3600.0, 0.0)


def alteracoes_observadas(
    transicoes: Sequence[Dict[str, Any]],
) -> List[AlteracaoObservada]:
    """As transições que a varredura viu, da mais nova para a mais velha."""
    saida: List[AlteracaoObservada] = []
    ordenadas = sorted(
        (t for t in transicoes if _dt(t.get("ocorrido_em"))),
        key=lambda t: _dt(t.get("ocorrido_em")),  # type: ignore[arg-type]
        reverse=True,
    )
    for t in ordenadas:
        quando = _dt(t.get("ocorrido_em"))
        de = t.get("de")
        para = t.get("para")
        saida.append(AlteracaoObservada(
            quando=quando.isoformat() if quando else "",
            campo="estado_externo",
            de=str(de) if de else None,
            para=str(para) if para else None,
            # Não observamos autoria; ver NAO_SEI_AUTORIA.
            origem=None,
            quem=None,
            resumo=(f"a varredura viu o estado mudar de {de or '—'} para "
                    f"{para or '—'}"),
        ))
    return saida


def razoes_do_espelho(linha: Dict[str, Any], *, conta_falhou: bool) -> List[str]:
    """O que o espelho permite AFIRMAR sobre esta campanha, em português.

    ⚠️ Mudança de significado declarada. No contrato, `razoes` é "o texto do
    Google, como ele escreveu" — `campaign.primary_status_reasons`, que só uma
    consulta à conta traz. Aqui são observações derivadas do que está gravado.

    Preferir isso a uma lista vazia tem uma razão prática: lista vazia significa
    "o Google não disse nada", e é uma afirmação que não podemos fazer sem ter
    perguntado. Cada linha abaixo descreve um FATO do espelho, e nenhuma delas
    infere causa — é a diferença entre "a veiculação está X" e "a campanha está
    parada porque X".
    """
    razoes: List[str] = []

    if conta_falhou:
        razoes.append(
            "a última varredura desta conta falhou: os números abaixo são do "
            "último snapshot bom, não de agora"
        )

    veiculacao = str(linha.get("veiculacao") or "").strip()
    if veiculacao and veiculacao.upper() != "SERVING":
        razoes.append(f"a conta responde veiculação {veiculacao}")

    presenca = str(linha.get("presenca") or "").strip()
    if presenca:
        razoes.append(f"presença com ressalva: {presenca}")

    if _dt(linha.get("entrega_lida_em")) is None:
        razoes.append("a entrega desta campanha não pôde ser medida na varredura")

    if linha.get("verba_diaria_micros") is None:
        razoes.append("a varredura não leu verba diária para esta campanha")

    if linha.get("lance_micros") is None:
        razoes.append(
            "a varredura não leu lance para esta campanha — sem ele não há teto "
            "de cliques"
        )

    return razoes


# ── montagem ────────────────────────────────────────────────────────────────


def _leitura(quando: Any, agora: datetime) -> Optional[Dict[str, Any]]:
    lida = inv.leitura_de(quando, agora)
    return {"lido_em": lida.lido_em, "idade_s": lida.idade_s} if lida else None


def alerta_projetado(
    linha: Dict[str, Any],
    *,
    conta: Dict[str, Any],
    conta_falhou: bool,
    transicoes: Sequence[Dict[str, Any]],
    agora: datetime,
) -> Optional[Alerta]:
    """Uma linha do espelho vira alerta — ou `None`, quando não é alerta.

    A decisão é do domínio (`dom.merece_alerta`), não daqui: o sino, a aba
    Atenção e este quadro precisam concordar, e concordam por usarem a mesma
    função em vez de três cópias parecidas.
    """
    horas = horas_ligada(transicoes, agora)
    custo_micros = dom.inteiro_ou_nulo(linha.get("custo_micros"))
    impressoes = dom.inteiro_ou_nulo(linha.get("impressoes"))
    cliques = dom.inteiro_ou_nulo(linha.get("cliques"))
    estado = str(linha.get("estado_externo") or "")

    # ⚠️ Regra A: sem carimbo de entrega, os números não são emitidos. Sem eles
    # `merece_alerta` recusa por `custo_micros is None`, que é o comportamento
    # certo — mas a campanha ainda aparece na aba Atenção por `pede_atencao`.
    if _dt(linha.get("entrega_lida_em")) is None:
        impressoes = cliques = custo_micros = None

    if not dom.merece_alerta(
        estado_externo=estado, custo_micros=custo_micros, horas_ligada=horas
    ):
        return None

    sintoma = dom.sintoma_de_entrega(
        estado_externo=estado, impressoes=impressoes, cliques=cliques
    ) or dom.SEM_IMPRESSAO

    lance = dom.inteiro_ou_nulo(linha.get("lance_micros"))
    verba = dom.inteiro_ou_nulo(linha.get("verba_diaria_micros"))

    return Alerta(
        customer_id=str(linha.get("customer_id") or inv.SEM_CONTA),
        customer_name=str(conta.get("nome") or ""),
        campaign_id=str(linha.get("campaign_id") or ""),
        campaign_name=str(linha.get("nome") or ""),
        status=estado,
        veiculacao=str(linha.get("veiculacao") or ""),
        horas_ligada=horas,
        impressoes=impressoes,
        cliques=cliques,
        custo=_micros_para_moeda(custo_micros),
        lance=_micros_para_moeda(lance),
        orcamento=_micros_para_moeda(verba),
        teto_de_cliques=inv.teto_de_cliques(
            verba, lance, inv.estrategia_canonica(linha.get("estrategia"))
        ),
        razoes=razoes_do_espelho(linha, conta_falhou=conta_falhou),
        # Não derivável do snapshot; ver NAO_SEI_APROVACAO.
        aprovacao_do_anuncio=None,
        sintoma=sintoma,
        revisar=list(dom.ordem_de_revisao(sintoma)),
        alteracoes=[
            {
                "quando": a.quando, "campo": a.campo, "de": a.de, "para": a.para,
                "origem": a.origem, "quem": a.quem, "resumo": a.resumo,
            }
            for a in alteracoes_observadas(transicoes)
        ],
        presenca=dom.presenca_projetada(
            linha.get("presenca"), conta_falhou=conta_falhou
        ),
        # Regra A: a idade do dado viaja colada ao alerta.
        leitura=_leitura(linha.get("entrega_lida_em") or linha.get("lido_em"), agora),
        volc_campaign_id=str(linha.get("volc_campaign_id") or ""),
    )


async def montar_quadro(
    fonte: FonteDeAlertas, *, agora: Optional[datetime] = None
) -> Quadro:
    """O quadro inteiro, a partir do snapshot. Zero consultas ao Google Ads.

    A ordem importa e é a mesma de `inventario.montar_inventario`: primeiro as
    contas — é o desfecho da varredura delas que decide o que a presença de cada
    campanha significa —, depois as campanhas, depois o diário de estados.
    """
    agora = agora or datetime.now(timezone.utc)

    linhas_de_conta = await fonte.contas()
    estado_da_conta: Dict[str, Dict[str, Any]] = {}
    faltou: List[Dict[str, Any]] = []

    for bruta in linhas_de_conta:
        c = inv.normalizar_linha_de_conta(bruta)
        cid = str(c.get("customer_id") or "")
        if not cid:
            continue
        f = inv.frescor_da_conta(c, agora)
        estado_da_conta[cid] = {"linha": c, "frescor": f}
        if f == inv.FALHOU:
            faltou.append({
                "customer_id": cid,
                "escopo": "conta",
                "motivo": str(c.get("motivo") or
                              "a última varredura desta conta falhou; os alertas "
                              "abaixo saem do último snapshot bom"),
            })
        elif f == inv.PARCIAL:
            faltou.append({
                "customer_id": cid,
                # O escopo viaja dentro do motivo: o schema canônico tem
                # UMA coluna de texto para a tentativa, não duas.
                "escopo": "conta",
                "motivo": str(c.get("motivo") or
                              "parte da varredura desta conta não voltou"),
            })

    campanhas = await fonte.campanhas()
    ids = [str(l.get("volc_campaign_id") or "") for l in campanhas]
    transicoes = await fonte.transicoes_de_estado([i for i in ids if i])

    alertas: List[Alerta] = []
    ligadas_por_conta: Dict[str, int] = {}
    verificadas = 0

    for linha in campanhas:
        cid = str(linha.get("customer_id") or inv.SEM_CONTA)
        info = estado_da_conta.get(cid, {})
        conta_falhou = info.get("frescor") == inv.FALHOU
        if str(linha.get("estado_externo") or "").strip().upper() == dom.LIGADA:
            verificadas += 1
            ligadas_por_conta[cid] = ligadas_por_conta.get(cid, 0) + 1
        alerta = alerta_projetado(
            linha,
            conta=info.get("linha", {}),
            conta_falhou=conta_falhou,
            transicoes=transicoes.get(str(linha.get("volc_campaign_id") or ""), ()),
            agora=agora,
        )
        if alerta is not None:
            alertas.append(alerta)

    contas: List[ContaNoQuadro] = []
    for cid in sorted(set(list(estado_da_conta) + list(ligadas_por_conta))):
        info = estado_da_conta.get(cid, {})
        linha = info.get("linha", {})
        f = info.get("frescor", inv.NUNCA_LIDO)
        contas.append(ContaNoQuadro(
            customer_id=cid,
            nome=str(linha.get("nome") or ""),
            # ⚠️ `None` e não zero quando ninguém perguntou; zero MEDIDO quando
            # a conta respondeu e nenhuma campanha estava ligada. Regra B na
            # contagem: "não perguntei" e "perguntei e não há nenhuma" levam a
            # ações opostas, e a primeira é a que some da tela se for tratada
            # como benigna.
            ligadas=(None if (cid not in estado_da_conta
                              or f == inv.NUNCA_LIDO)
                     else ligadas_por_conta.get(cid, 0)),
            erro=(str(linha.get("motivo")) if f == inv.FALHOU and linha.get("motivo")
                  else None),
            frescor=f,
            leitura=_leitura(linha.get("ultima_leitura_boa_em"), agora),
        ))

    boas = [c.leitura for c in contas if c.leitura]
    envelope = max(boas, key=lambda l: int(l["idade_s"])) if boas else None

    return Quadro(
        versao=VERSAO_ALERTAS,
        alertas=alertas,
        verificadas=verificadas,
        contas=contas,
        horas_ate_alertar=dom.HORAS_ATE_ALERTAR,
        frescor=dom.frescor_do_conjunto([c.frescor for c in contas]),
        leitura=envelope,
        parcial=bool(faltou),
        faltou=faltou,
        nao_sabemos=[NAO_SEI_APROVACAO, NAO_SEI_AUTORIA],
    )


# ═══════════════════════════════════════════════════════════════════════════
# O ponto de troca — mesma história de `inventario.fabricar_fonte`
# ═══════════════════════════════════════════════════════════════════════════


def fabricar_fonte(base: str, chave: str) -> FonteDeAlertas:
    """A implementação da porta vive em `app/trafego/persistencia.py` (Frente A).

    Import tardio de propósito: um import no topo faria este módulo — que é o
    caminho de render do sino — depender da infraestrutura em tempo de carga.
    """
    try:
        from app.trafego import persistencia  # noqa: PLC0415
    except ImportError as exc:
        raise inv.PersistenciaAusente(
            "não há camada de acesso ao snapshot: `app/trafego/persistencia.py` "
            f"não está instalada. O schema canônico é {inv.SCHEMA_CANONICO} e a "
            "porta que ela precisa satisfazer é `alertas.FonteDeAlertas`."
        ) from exc
    return persistencia.FonteDeAlertasSupabase(base, chave)


#: Reexportado para o teste de gate: nenhuma tabela fora desta lista.
TABELAS_DO_QUADRO: Tuple[str, ...] = (
    "trafego_snapshot_conta", "trafego_campanha", "trafego_campanha_espelho",
    "trafego_evento",
)
