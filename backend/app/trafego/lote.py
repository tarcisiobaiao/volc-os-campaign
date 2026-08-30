"""O lote de preparação: como criar N campanhas sem criar N+1 por acidente.

## O problema que este módulo resolve

Subir uma campanha é uma chamada de rede que pode responder três coisas:
`criou`, `recusou` e **nada**. A terceira é a única que importa aqui, porque as
outras duas já se resolvem sozinhas.

Quando a API não responde, o processo fica com uma pergunta que ele não tem como
responder sozinho: *criou?* Um executor otimista assume que não e reenvia — e
cria a segunda campanha, que gasta verba de verdade e disputa o mesmo leilão que
a primeira. Um executor pessimista assume que sim e marca como feito — e o lote
termina "verde" com uma campanha que nunca existiu.

Os dois erram. A saída não é escolher melhor: é **não precisar escolher**, e
para isso o estado tem de guardar a ignorância em vez de resolvê-la.

## As quatro camadas, e onde cada uma mora

| # | camada | onde |
|---|---|---|
| 1 | recibo escrito **antes** da chamada, com `desfecho='em_voo'` | `supabase/migrations/v10_01` §7 |
| 2 | item com recibo em voo **não pode** virar `falhou` | gatilho `trafego_item_estado_valido` §11.4 |
| 3 | no máximo **um** sucesso por `(chave, operação)` | índice `trafego_recibo_sucesso_unico_ux` |
| 4 | no máximo **uma** campanha por item, e vice-versa | índice `trafego_lote_item_campanha_ux` |

Nenhuma delas depende de o executor lembrar de nada. Este módulo é a metade
Python: ele **deriva** a chave, **nomeia** os estados e **decide** o próximo
passo — e cada uma dessas três coisas tem uma contraparte no banco que a
verifica.

## Por que a chave é derivada do conteúdo, e não sorteada

Uma chave sorteada (`uuid4()`) faz **toda retomada parecer uma criação nova**:
o processo cai, sobe de novo, sorteia outra chave, e as quatro camadas acima
deixam de reconhecer o que já foi enviado. Elas passam a proteger contra uma
duplicidade que não é a que acontece.

Derivada do conteúdo, a chave tem a propriedade que a retomada precisa:

* o operador **não** mudou nada → mesma chave → o sistema reconhece o que existe;
* o operador **mudou** o plano → chave diferente → é outra coisa, e é a verdade.

E ela viaja até a conta como rótulo, o que fecha o círculo: a verificação remota
pergunta "existe campanha com esta marca?" sem depender de nenhum id que talvez
nunca tenha voltado.

⚠️ **Duas definições da mesma regra, e o antídoto.** As transições de estado
estão aqui e nos gatilhos da `v10_01`. É o mesmo risco que `atencao` carrega
desde a v9_01, e o antídoto é o mesmo: `backend/tests/test_lote.py` lê o SQL e
compara as duas listas termo a termo. Mudar uma sem a outra derruba o teste.

Este módulo **não faz I/O**. Ele não importa `httpx`, não importa o SDK do
Google e não conhece o Supabase. O import é o gate; não há como "só desta vez".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# VOCABULÁRIO — os mesmos termos que as CHECKs da v10_01 aceitam
# ═══════════════════════════════════════════════════════════════════════════

#: Os estados do LOTE. Cada um é um lugar de onde se sai por um caminho
#: diferente, e nenhum deles é apagar a linha.
ESTADOS_DO_LOTE: Tuple[str, ...] = (
    "preparando", "validando", "aguardando_aprovacao", "aprovado",
    "executando", "interrompido", "concluido", "concluido_com_falhas",
    "recusado", "cancelado", "revertido",
)

#: Os estados do ITEM. `indeterminado` é o mais importante da lista — ver o
#: docstring do módulo.
ESTADOS_DO_ITEM: Tuple[str, ...] = (
    "planejado", "validado_local", "validado_remoto", "aprovado",
    "criando", "indeterminado", "criada_pausada", "verificada",
    "canario", "ativa", "falhou", "cancelada", "revertida",
)

#: Os quatro desfechos de um recibo. `sem_resposta` **não** é `erro`: erro
#: afirma que não criou; sem_resposta não afirma nada.
DESFECHOS_DE_RECIBO: Tuple[str, ...] = (
    "em_voo", "sucesso", "erro", "sem_resposta",
)

#: ⚠️ Tem de bater, termo a termo, com o array `permitidas` de
#: `trafego_lote_estado_valido()` na v10_01. `test_lote.py` compara os dois.
TRANSICOES_DO_LOTE: Tuple[Tuple[str, str], ...] = (
    ("preparando", "validando"),            ("preparando", "cancelado"),
    ("validando", "preparando"),            ("validando", "aguardando_aprovacao"),
    ("validando", "cancelado"),
    ("aguardando_aprovacao", "aprovado"),   ("aguardando_aprovacao", "recusado"),
    ("aguardando_aprovacao", "cancelado"),
    ("aprovado", "executando"),             ("aprovado", "cancelado"),
    ("executando", "concluido"),            ("executando", "concluido_com_falhas"),
    ("executando", "interrompido"),
    ("interrompido", "executando"),         ("interrompido", "cancelado"),
    ("concluido_com_falhas", "executando"), ("concluido_com_falhas", "revertido"),
    ("concluido", "revertido"),
)

#: ⚠️ Idem, para `trafego_item_estado_valido()`.
TRANSICOES_DO_ITEM: Tuple[Tuple[str, str], ...] = (
    ("planejado", "validado_local"),        ("planejado", "falhou"),
    ("planejado", "cancelada"),
    ("validado_local", "validado_remoto"),  ("validado_local", "planejado"),
    ("validado_local", "falhou"),           ("validado_local", "cancelada"),
    ("validado_remoto", "aprovado"),        ("validado_remoto", "falhou"),
    ("validado_remoto", "cancelada"),
    ("aprovado", "criando"),                ("aprovado", "cancelada"),
    ("criando", "criada_pausada"),          ("criando", "falhou"),
    ("criando", "indeterminado"),
    ("indeterminado", "criada_pausada"),    ("indeterminado", "criando"),
    ("indeterminado", "falhou"),
    ("criada_pausada", "verificada"),       ("criada_pausada", "falhou"),
    ("criada_pausada", "revertida"),
    ("verificada", "canario"),              ("verificada", "ativa"),
    ("verificada", "revertida"),
    ("canario", "ativa"),                   ("canario", "revertida"),
    ("ativa", "revertida"),
    ("falhou", "criando"),                  ("falhou", "planejado"),
    ("falhou", "cancelada"),
)

#: Os itens que **existem na conta**. Usado pelo resumo e pela contagem do
#: painel; é a mesma lista do `FILTER` de `trafego_lote_painel`.
ESTADOS_CRIADOS: Tuple[str, ...] = (
    "criada_pausada", "verificada", "canario", "ativa",
)

#: Ações que `proxima_acao()` pode devolver. Fechada de propósito: uma ação
#: nova aqui é uma ação nova na view, e as duas têm de nascer juntas.
ACOES: Tuple[str, ...] = (
    "verificar", "parar_duplicidade", "nada", "decidir_retomada",
    "ativar_canario", "ativar", "criar", "preparar",
)

#: As duas plataformas, e a sigla curta que entra na chave. Importar
#: `plataforma.PLATAFORMAS` aqui criaria uma dependência de módulo por um par de
#: constantes; `test_lote.py` prova que as duas listas concordam.
SIGLA_DA_PLATAFORMA: Dict[str, str] = {"GOOGLE_ADS": "gads", "META_ADS": "meta"}


class ErroDeLote(ValueError):
    """Recusa do domínio. Nunca vira 500 sem mensagem."""


# ═══════════════════════════════════════════════════════════════════════════
# A MÁQUINA DE ESTADOS
# ═══════════════════════════════════════════════════════════════════════════


def transicao_permitida(de: str, para: str, *, alvo: str = "item") -> bool:
    """`alvo` é `'lote'` ou `'item'`.

    Devolve `False` para termo desconhecido em vez de levantar: quem chama isto
    normalmente está validando entrada, e um estado inventado é uma resposta
    "não", não um acidente de programação.
    """
    tabela = TRANSICOES_DO_LOTE if alvo == "lote" else TRANSICOES_DO_ITEM
    return (de, para) in tabela


def estados_terminais(*, alvo: str = "item") -> Tuple[str, ...]:
    """Os estados de onde não se sai.

    Derivado da tabela de transições, e não escrito à mão: uma lista paralela
    ficaria desatualizada na primeira transição nova, e o sintoma seria um lote
    que a tela chama de encerrado e o executor continua tentando mexer.
    """
    tabela = TRANSICOES_DO_LOTE if alvo == "lote" else TRANSICOES_DO_ITEM
    todos = ESTADOS_DO_LOTE if alvo == "lote" else ESTADOS_DO_ITEM
    com_saida = {de for de, _ in tabela}
    return tuple(e for e in todos if e not in com_saida)


# ═══════════════════════════════════════════════════════════════════════════
# A CHAVE DE IDEMPOTÊNCIA
# ═══════════════════════════════════════════════════════════════════════════


def _canonico(valor: Any) -> str:
    """JSON estável: mesma entrada, mesmo texto, sempre.

    ⚠️ `sort_keys` não é cosmético. Sem ele, dois dicionários iguais escritos em
    ordens diferentes produziriam chaves diferentes — e a retomada deixaria de
    reconhecer o próprio plano, que é exatamente o defeito que a chave derivada
    existe para não ter.

    ⚠️ `float` é recusado na travessia (ver `_sem_float`) porque
    `repr(0.1 + 0.2)` não é `'0.3'`: um plano que passe por um `round()` numa
    versão do executor e não passe em outra mudaria de chave sem mudar de
    conteúdo.
    """
    return json.dumps(valor, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def _sem_float(valor: Any, caminho: str = "plano") -> None:
    if isinstance(valor, float):
        raise ErroDeLote(
            f"{caminho} carrega um float ({valor!r}). Dinheiro e lance viajam "
            f"em micros (int); um float faria a mesma campanha produzir duas "
            f"chaves em máquinas diferentes.")
    if isinstance(valor, Mapping):
        for k, v in valor.items():
            _sem_float(v, f"{caminho}.{k}")
    elif isinstance(valor, (list, tuple)):
        for i, v in enumerate(valor):
            _sem_float(v, f"{caminho}[{i}]")


def chave_de_idempotencia(*, intencao_id: str, plataforma: str,
                          conta_externa: str, canal: str, ordem: int,
                          plano: Mapping[str, Any]) -> str:
    """A chave que impede a segunda campanha.

    Ela é **derivada do conteúdo**, e o que entra na derivação é exatamente o
    que define "a mesma coisa":

    * `intencao_id` — dois lotes da mesma intenção com o mesmo plano são a mesma
      campanha; de intenções diferentes, não são;
    * `plataforma`, `conta_externa`, `canal` — a mesma campanha em outra conta é
      outra campanha (é a trinca de `IdentidadeDeCampanha`, sem o id externo,
      que ainda não existe);
    * `ordem` — duas campanhas idênticas *de propósito* dentro do mesmo lote
      (teste A/B declarado) continuam sendo duas;
    * `plano` — mudou o conteúdo, é outra coisa.

    O que **não** entra: o instante, o número da tentativa e qualquer coisa
    sorteada. Se entrassem, a retomada produziria chave nova e as quatro camadas
    de defesa deixariam de reconhecer o que já foi enviado.

    O formato cabe num rótulo do Google Ads e passa na CHECK
    `trafego_item_chave_valida` (`^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$`).
    """
    if plataforma not in SIGLA_DA_PLATAFORMA:
        raise ErroDeLote(
            f"plataforma {plataforma!r} não existe. As plataformas são: "
            f"{', '.join(sorted(SIGLA_DA_PLATAFORMA))}.")
    if not str(intencao_id or "").strip():
        raise ErroDeLote("chave sem intenção não é chave: ela deixaria de "
                         "distinguir campanhas de intenções diferentes.")
    if not str(conta_externa or "").strip():
        raise ErroDeLote("chave sem conta não é chave: a mesma campanha em "
                         "outra conta é outra campanha.")
    if not isinstance(ordem, int) or isinstance(ordem, bool) or ordem < 0:
        raise ErroDeLote(f"ordem inválida: {ordem!r}. Ela é a posição no lote.")
    if not isinstance(plano, Mapping) or not plano:
        raise ErroDeLote("plano vazio não identifica campanha nenhuma.")
    _sem_float(plano)

    materia = _canonico([
        str(intencao_id), plataforma, str(conta_externa), str(canal),
        int(ordem), plano,
    ])
    digest = hashlib.sha256(materia.encode("utf-8")).hexdigest()
    return f"volc-{SIGLA_DA_PLATAFORMA[plataforma]}-{ordem:04d}-{digest[:16]}"


# ═══════════════════════════════════════════════════════════════════════════
# O PLANEJAMENTO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ItemPlanejado:
    """Uma campanha candidata, antes de qualquer rede.

    `idempotency_key` já vem preenchida: ela nasce do plano, e não do envio.
    """

    ordem: int
    rotulo: str
    plano: Mapping[str, Any]
    idempotency_key: str
    estado: str = "planejado"


@dataclass(frozen=True)
class LotePlanejado:
    intencao_id: str
    blueprint_id: str
    plataforma: str
    conta_externa: str
    canal: str
    itens: Tuple[ItemPlanejado, ...]
    limite_concorrencia: Optional[int] = None
    quota_orcada: Optional[int] = None

    @property
    def chaves(self) -> Tuple[str, ...]:
        return tuple(i.idempotency_key for i in self.itens)


def planejar(*, intencao_id: str, blueprint_id: str, plataforma: str,
             conta_externa: str, canal: str,
             planos: Sequence[Mapping[str, Any]],
             rotulos: Optional[Sequence[str]] = None,
             limite_concorrencia: Optional[int] = None,
             quota_por_item: Optional[int] = None) -> LotePlanejado:
    """Monta o lote inteiro, de forma **determinística**.

    Rodar duas vezes com a mesma entrada produz as mesmas chaves. É essa
    propriedade — e não um registro em disco — que faz a retomada funcionar
    depois de uma queda que perdeu tudo o que estava em memória.

    `quota_por_item` vira `quota_orcada` do lote. Ele é uma DECLARAÇÃO do que
    esperamos gastar de operações, e não uma medida: o que a plataforma cobrou
    de fato entra em `quota_consumida`, com o carimbo dela (regra A e D).
    """
    if not planos:
        raise ErroDeLote("lote sem itens não é lote.")
    if rotulos is not None and len(rotulos) != len(planos):
        raise ErroDeLote(
            f"{len(rotulos)} rótulos para {len(planos)} planos. Um item sem "
            f"rótulo é uma linha que o operador não sabe o que é.")
    if limite_concorrencia is not None and limite_concorrencia < 1:
        raise ErroDeLote("limite de concorrência abaixo de 1 trava o lote.")

    itens: List[ItemPlanejado] = []
    vistas: Dict[str, int] = {}
    for i, plano in enumerate(planos):
        chave = chave_de_idempotencia(
            intencao_id=intencao_id, plataforma=plataforma,
            conta_externa=conta_externa, canal=canal, ordem=i, plano=plano)
        # ⚠️ Não pode acontecer — `ordem` entra na derivação —, e mesmo assim é
        # conferido: se um dia a derivação mudar e alguém tirar a ordem dela,
        # este `raise` é o que impede o lote de sair com duas campanhas
        # compartilhando a mesma chave. O banco também recusaria, mas ali o
        # estrago já teria chegado ao meio da execução.
        if chave in vistas:
            raise ErroDeLote(
                f"itens {vistas[chave]} e {i} produziram a mesma chave "
                f"({chave}). Duas campanhas com a mesma chave são uma só para "
                f"todas as defesas do lote.")
        vistas[chave] = i
        rotulo = (rotulos[i] if rotulos else
                  str(plano.get("nome") or f"item {i + 1}"))
        itens.append(ItemPlanejado(ordem=i, rotulo=rotulo, plano=plano,
                                   idempotency_key=chave))

    return LotePlanejado(
        intencao_id=str(intencao_id), blueprint_id=str(blueprint_id),
        plataforma=plataforma, conta_externa=str(conta_externa), canal=canal,
        itens=tuple(itens), limite_concorrencia=limite_concorrencia,
        quota_orcada=(None if quota_por_item is None
                      else quota_por_item * len(itens)))


# ═══════════════════════════════════════════════════════════════════════════
# O QUE FAZER A SEGUIR
# ═══════════════════════════════════════════════════════════════════════════


def proxima_acao(linha: Mapping[str, Any]) -> str:
    """A tradução literal do `CASE` de `trafego_item_situacao.proxima_acao`.

    ⚠️ **Duas definições da mesma regra.** Se esta função e a view discordarem,
    a tela e o executor passam a discordar sobre o mesmo item, e não há como
    saber qual está certo. `scripts/provar-ciclo-v10.sh` compara as duas contra
    um Postgres de verdade, linha a linha.

    A ordem dos ramos é a ordem da segurança, e o primeiro é o que fecha o caso
    do timeout: **recibo em voo sempre manda verificar, nunca reenviar.**
    """
    estado = str(linha.get("estado") or "")
    em_voo = linha.get("recibo_em_voo_id") is not None
    quantidade = linha.get("ultima_verificacao_quantidade")
    quantidade = 0 if quantidade is None else int(quantidade)

    if em_voo:
        return "verificar"
    if estado == "indeterminado":
        return "verificar"
    # Duas campanhas para a mesma chave já existem na conta. Não há escolha
    # automática correta entre elas: qual pausar depende de qual já gastou, qual
    # tem histórico e qual está vinculada a um funil. Isso é decisão humana.
    if quantidade >= 2:
        return "parar_duplicidade"
    if estado in ("cancelada", "revertida", "ativa"):
        return "nada"
    if estado == "falhou":
        return "decidir_retomada"
    if estado == "criada_pausada":
        return "verificar"
    if estado == "verificada":
        return "ativar_canario"
    if estado == "canario":
        return "ativar"
    if estado == "aprovado":
        return "criar"
    return "preparar"


@dataclass(frozen=True)
class PlanoDeRetomada:
    """O que fazer com um lote que parou no meio.

    Os quatro grupos são disjuntos e nomeiam ações diferentes de propósito:
    juntar `verificar` com `criar` numa lista só de "pendentes" é como se cria a
    segunda campanha.
    """

    verificar: Tuple[str, ...] = ()
    criar: Tuple[str, ...] = ()
    parar_duplicidade: Tuple[str, ...] = ()
    decidir_retomada: Tuple[str, ...] = ()
    #: ⚠️ Estes três existiam em `ACOES` e NÃO apareciam aqui. `retomada()` os
    #: calculava e jogava fora: um item cujo próximo passo é `ativar_canario`
    #: sumia do plano inteiro, e o operador via um roteiro com menos itens do
    #: que o lote tem — sem nada dizendo que faltava alguém. Um plano que
    #: descarta em silêncio é pior que um plano incompleto declarado.
    ativar_canario: Tuple[str, ...] = ()
    ativar: Tuple[str, ...] = ()
    preparar: Tuple[str, ...] = ()
    concluidos: Tuple[str, ...] = ()
    #: Quantos itens podem sair de uma vez. `None` = o executor decide.
    limite_concorrencia: Optional[int] = None

    @property
    def bloqueado(self) -> bool:
        """Duplicidade já consumada trava o lote inteiro.

        Não é excesso de zelo: se uma chave produziu duas campanhas, a derivação
        ou a conta estão fazendo algo que ninguém previu, e continuar criando os
        outros itens do mesmo lote é continuar sob a mesma suposição errada.
        """
        return bool(self.parar_duplicidade)

    @property
    def precisa_de_humano(self) -> Tuple[str, ...]:
        return self.parar_duplicidade + self.decidir_retomada


#: Os campos de `PlanoDeRetomada` que carregam item. Existe para a conta fechar
#: — ver a verificação no fim de `retomada()`.
_CAMPOS_DE_BALDE: Tuple[str, ...] = (
    "verificar", "criar", "parar_duplicidade", "decidir_retomada",
    "ativar_canario", "ativar", "preparar", "concluidos",
)


def retomada(linhas: Iterable[Mapping[str, Any]], *,
             limite_concorrencia: Optional[int] = None) -> PlanoDeRetomada:
    """Agrupa os itens pela ação que cada um pede.

    A entrada é o que `trafego_item_situacao` devolve. A saída é o roteiro do
    executor — e o ponto inteiro da separação é que **`criar` só recebe item que
    não tem nada em voo e não está indeterminado**.
    """
    baldes: Dict[str, List[str]] = {a: [] for a in ACOES}
    baldes_totais: List[str] = []
    for linha in linhas:
        item = str(linha.get("item_id") or "")
        baldes[proxima_acao(linha)].append(item)
        baldes_totais.append(item)

    plano = PlanoDeRetomada(
        verificar=tuple(baldes["verificar"]),
        criar=tuple(baldes["criar"]),
        parar_duplicidade=tuple(baldes["parar_duplicidade"]),
        decidir_retomada=tuple(baldes["decidir_retomada"]),
        ativar_canario=tuple(baldes["ativar_canario"]),
        ativar=tuple(baldes["ativar"]),
        preparar=tuple(baldes["preparar"]),
        concluidos=tuple(baldes["nada"]),
        limite_concorrencia=limite_concorrencia)

    # ⚠️ A conta tem de fechar. Enquanto três baldes eram descartados, um item
    # podia entrar e não sair em lugar nenhum — e nada nesta função reclamava.
    # A verificação é barata e transforma "esqueci de expor um balde novo" num
    # erro na primeira execução, em vez de num item que some.
    somados = sum(len(getattr(plano, campo)) for campo in _CAMPOS_DE_BALDE)
    if somados != len(baldes_totais):
        raise ErroDeLote(
            f"o plano de retomada expõe {somados} de {len(baldes_totais)} itens. "
            f"Alguma ação de `ACOES` não tem balde no plano, e itens estão "
            f"sumindo em silêncio.")
    return plano


def pode_executar(lote: Mapping[str, Any]) -> Tuple[bool, Optional[str]]:
    """`(pode, por_que_nao)`. Espelha o gatilho `trafego_lote_estado_valido`.

    Existir em Python **e** no banco não é duplicação inútil: aqui a recusa vira
    uma mensagem que o operador lê antes de clicar; lá ela vira a garantia de
    que nenhum caminho — nem um script solto, nem um endpoint esquecido —
    executa sem aprovação.
    """
    estado = str(lote.get("estado") or "")
    if not lote.get("aprovado_em"):
        return False, ("este lote não tem aprovação humana registrada. "
                       "O sistema sugere; o operador confirma.")
    if lote.get("cancelado_em"):
        return False, "este lote foi cancelado."
    if not transicao_permitida(estado, "executando", alvo="lote"):
        return False, (f"um lote em `{estado}` não vai para `executando`. "
                       f"As transições são as de TRANSICOES_DO_LOTE.")
    return True, None


# ═══════════════════════════════════════════════════════════════════════════
# ERRO POR ITEM, NUNCA POR LOTE
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ErroDeItem:
    """A falha de UM item. Ela não invalida nem mascara as demais (regra C).

    `carimbo` é obrigatório pela mesma razão que toda medida carrega o instante
    da leitura: um erro sem data é indistinguível de um erro de ontem, e é por
    ele que a retomada decide o que refazer.
    """

    item_id: str
    codigo: str
    mensagem: str
    carimbo: str
    detalhe: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.mensagem or "").strip():
            raise ErroDeLote(
                "erro sem mensagem é um rótulo que esconde a causa — o mesmo "
                "defeito de `sumiu da conta`.")
        if not str(self.carimbo or "").strip():
            raise ErroDeLote("erro sem carimbo é indistinguível de um erro de "
                             "ontem.")


@dataclass(frozen=True)
class ResultadoDoLote:
    """O desfecho agregado. `concluido_com_falhas` é normal, e não exceção."""

    criados: Tuple[str, ...]
    falhas: Tuple[ErroDeItem, ...]
    indeterminados: Tuple[str, ...]
    cancelados: Tuple[str, ...] = ()

    @property
    def estado_do_lote(self) -> str:
        """⚠️ `indeterminado` NÃO fecha o lote.

        Enquanto houver um item cujo destino ninguém conhece, o lote está
        `interrompido` — e não `concluido_com_falhas`, que afirmaria que todos
        os desfechos são conhecidos. Chamar de "concluído com falhas" um lote com
        item indeterminado é a forma mais silenciosa de a duplicidade escapar:
        ninguém verifica um lote encerrado.
        """
        if self.indeterminados:
            return "interrompido"
        if self.falhas:
            return "concluido_com_falhas"
        return "concluido"


def resumo_humano(lote: Mapping[str, Any],
                  itens: Sequence[Mapping[str, Any]]) -> str:
    """O texto que o operador lê. Texto, e não JSON.

    Um resumo que precisa de renderizador não é resumo — ele vai parar num log,
    num e-mail e numa mensagem de suporte, e nos três ele tem de ser legível.

    Ele diz primeiro o que **exige alguém**, e só depois o que correu bem: um
    resumo que começa por "12 criadas" faz o "1 indeterminada" desaparecer no
    meio da frase, e é justamente essa a linha que precisa de olho.
    """
    situacoes = [proxima_acao(i) for i in itens]
    total = len(itens)
    criadas = sum(1 for i in itens
                  if str(i.get("estado") or "") in ESTADOS_CRIADOS)
    duplicadas = situacoes.count("parar_duplicidade")
    verificar = situacoes.count("verificar")
    retomar = situacoes.count("decidir_retomada")

    partes: List[str] = []
    if duplicadas:
        partes.append(
            f"⚠️ {duplicadas} item(ns) com MAIS DE UMA campanha na conta — "
            f"o lote está travado até alguém decidir qual fica")
    if verificar:
        partes.append(
            f"{verificar} item(ns) aguardando verificação na conta "
            f"(não sabemos se a chamada criou; nenhum será reenviado)")
    if retomar:
        partes.append(f"{retomar} item(ns) falharam e esperam decisão de retomada")

    cabeca = (f"Lote {lote.get('lote_id', '(sem id)')} · "
              f"{lote.get('canal', '?')} na conta {lote.get('conta_externa', '?')} · "
              f"estado {lote.get('estado', '?')}")
    corpo = "; ".join(partes) if partes else "nada exige atenção agora"
    cauda = f"{criadas} de {total} campanha(s) criada(s), todas PAUSADAS."
    if not lote.get("aprovado_em"):
        cauda += " Ainda sem aprovação humana — nada será executado."
    return f"{cabeca}. {corpo}. {cauda}"
