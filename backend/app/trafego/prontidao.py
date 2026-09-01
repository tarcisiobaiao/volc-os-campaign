"""Os quatro portões do lançamento Search, e o que cada um exige de prova.

## Por que este módulo existe

"Pronto" virou uma palavra sem sujeito. Uma campanha pode estar pronta para
NASCER e completamente despreparada para ser ATIVADA — e até 01/09/2026 nada no
sistema dizia a diferença. O risco não é teórico: uma campanha em Smart Bidding
sem sinal de conversão chegando otimiza para nada e gasta o orçamento inteiro
aprendendo o que ninguém mediu.

Os quatro portões separam perguntas que têm respostas diferentes:

    G0  NASCIMENTO    o recibo, a idempotência e a atomicidade seguram a criação?
    G1  MENSURAÇÃO    existe meta de conversão observada e sinal chegando?
    G2  OBSERVAÇÃO    depois de criada, conseguimos reler e diagnosticar?
    G3  ATIVAÇÃO      despausar é seguro, e o lance tem no que aprender?

⚠️ A regra que este módulo impõe: **G0 não implica G1**. O canário pausado
atravessa G0 sozinho — ele não gasta, não entra em leilão e existe para colher o
veredito de política sobre recurso persistido. Mas nenhuma dessas coisas prova
que a medição funciona, e por isso `smart_bidding_eligible` NUNCA sai `True` por
falta de evidência contrária. Ausência de prova é `INDETERMINADO`, não permissão.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.trafego import perfil_de_mensuracao as pdm
from app.trafego import plano_mensuracao as pm

# Os estados possíveis de cada portão. `INDETERMINADO` é o default deliberado:
# quem não mediu não sabe, e não saber não é o mesmo que estar pronto.
PRONTO = "PRONTO"
#: Leu alguma coisa verdadeira, e não o bastante para afirmar prontidão. É o
#: estado que impede "consultei um recurso próximo" de virar "está pronto".
PARCIAL = "PARCIAL"
NAO_PRONTO = "NAO_PRONTO"
INDETERMINADO = "INDETERMINADO"
NAO_APLICAVEL = "NAO_APLICAVEL"

ESTADOS = (PRONTO, PARCIAL, NAO_PRONTO, INDETERMINADO, NAO_APLICAVEL)


@dataclass(frozen=True)
class Prontidao:
    """O que se sabe sobre poder nascer, medir, observar e ativar.

    Frozen porque isto vira resposta HTTP e entra no dossiê: um objeto mutável
    deixaria alguém "melhorar" um veredito depois que ele foi apresentado.
    """

    #: ⚠️ O PLANO está pronto para criar — a campanha ainda NÃO nasceu.
    #:
    #: Estes dois campos foram um só, e o nome era `campaign_birth`. Ele saía
    #: PRONTO no `/provar`, que não cria nada: o relatório chegou a dizer
    #: "CAMPAIGN_BIRTH_READY ✅" sem existir campanha, recibo ou id externo.
    #: "Nascer" é um fato sobre o mundo, não sobre o plano.
    creation_plan_ready: str = INDETERMINADO
    #: Só vira PRONTO depois de mutate + recibo fechado + releitura na conta.
    campaign_birth: str = INDETERMINADO
    conversion_goal_status: str = INDETERMINADO
    #: ⚠️ SEPARADO do Data Manager de propósito. Data Manager é UMA fonte de
    #: sinal, não a única: tag do Google, importação GA4 e upload offline são
    #: caminhos legítimos. Exigir Data Manager para uma conta que converte por
    #: tag declararia despreparo onde não há.
    conversion_signal_status: str = INDETERMINADO
    #: As fontes de sinal efetivamente OBSERVADAS. Vazia = nenhuma foi
    #: comprovada, e isso é diferente de "não existe nenhuma".
    #:
    #: ⚠️ TUPLA, e não lista — ver `__post_init__`. `para_json` continua
    #: emitindo `list(...)`, então o JSON e o contrato da tela não mudam.
    signal_sources: Sequence[str] = ()
    measurement_readiness: str = INDETERMINADO
    data_manager_status: str = INDETERMINADO
    observability_status: str = INDETERMINADO
    #: ⚠️ Nunca derivado por otimismo. Ver `avaliar`.
    smart_bidding_eligible: bool = False
    activation_blockers: Sequence[str] = ()
    #: ⚠️ O SUBCONJUNTO MATERIAL de `activation_blockers`: os que dizem que a
    #: campanha não pode APRENDER ou não pode ser OBSERVADA. Ele existe separado
    #: porque `activation_blockers` mistura naturezas — uma recusa de política
    #: ("ativar não é ato deste fluxo") e uma de medição ("nenhuma conversão
    #: chegou") fecham a mesma porta por motivos que não se comparam, e só a
    #: segunda contradiz `smart_bidding_eligible`.
    #:
    #: É contra ESTE campo que a coerência é imposta, em `__post_init__`.
    activation_blockers_materiais: Sequence[str] = ()
    #: Por onde o sinal PODERIA chegar. ⚠️ DIAGNÓSTICO, nunca prova: auto-tagging
    #: ligado, tag configurada e importação declarada descrevem o caminho, não o
    #: tráfego nele. Nada daqui move `conversion_signal_status`.
    signal_paths: Sequence[str] = ()
    notas: Dict[str, Any] = field(default_factory=dict)
    #: O plano canônico de mensuração desta campanha, quando alguém o leu.
    #:
    #: ⚠️ `None` é o caso normal e NÃO significa "não há plano": significa que
    #: ninguém leu os três recursos que decidem a meta efetiva. É ele que torna
    #: `conversion_goal_status=PRONTO` alcançável — e sem um ramo alcançável,
    #: "Smart Bidding está bloqueado" seria uma afirmação infalsificável, que
    #: passaria com qualquer entrada e não provaria nada.
    plano_de_mensuracao: Optional["pm.PlanoDeMensuracao"] = None
    #: O plano CALCULADO sobreviveu à requisição? ⚠️ Era literal fixo na rota
    #: (`routers/trafego.py`), fora do alcance de qualquer portão. Ativar com
    #: base num plano que não existe no banco é ativar com base numa tela.
    plano_persistido: bool = False
    #: A política em vigor cobre o ato de ATIVAR? ⚠️ Default `False`, e ele é o
    #: ponto: uma chamada que esqueça o parâmetro produz recusa, nunca permissão.
    ativacao_autorizada_por_politica: bool = False
    #: O perfil de mensuração desta campanha, quando alguém o declarou.
    perfil: Optional["pdm.PerfilDeMensuracao"] = None

    def __post_init__(self) -> None:
        # ⚠️ `frozen=True` impede REBIND de atributo e não impede mutação do
        # que o atributo aponta. Sem estas três cópias, `avaliar` devolvia os
        # MESMOS objetos que usa por dentro, e
        # `r.activation_blockers.append("...")` alterava um veredito já
        # apresentado — exatamente o que a docstring desta classe diz que ela
        # existe para impedir. Tupla e dict novo fecham as duas portas.
        object.__setattr__(self, "signal_sources", tuple(self.signal_sources))
        object.__setattr__(self, "activation_blockers",
                           tuple(self.activation_blockers))
        object.__setattr__(self, "activation_blockers_materiais",
                           tuple(self.activation_blockers_materiais))
        object.__setattr__(self, "signal_paths", tuple(self.signal_paths))
        object.__setattr__(self, "notas", dict(self.notas))

        # ⚠️ A COERÊNCIA VIRA INVARIANTE DO TIPO, e não uma asserção de teste.
        #
        # `smart_bidding_eligible=True` ao lado de um bloqueador MATERIAL é a
        # resposta que afirma duas coisas opostas sobre o mesmo mundo — e ela
        # aconteceu: com `auto_tagging=True` e `frescor=vazio_confirmado`, o
        # veredito saía elegível carregando "não recebeu NENHUMA conversão" na
        # lista ao lado. É o mesmo defeito que `Portao.__post_init__` já proíbe
        # em `contrato_canais` ("PERMITIDO com bloqueador"), e ele precisava
        # existir aqui também.
        #
        # ⚠️ Contra os MATERIAIS, e não contra a lista inteira: um bloqueio de
        # política não contradiz a elegibilidade de lance, e exigir lista vazia
        # tornaria a elegibilidade inalcançável por um motivo que nada tem a ver
        # com medir.
        if self.smart_bidding_eligible and self.activation_blockers_materiais:
            raise ValueError(
                "Smart Bidding elegível com bloqueador material de mensuração "
                "ou observabilidade: "
                f"{'; '.join(self.activation_blockers_materiais)}. As duas "
                "afirmações não podem valer ao mesmo tempo.")
        for b in self.activation_blockers_materiais:
            if b not in self.activation_blockers:
                raise ValueError(
                    f"bloqueador material fora da lista principal: {b!r}")


    # ── os nomes canônicos dos SETE portões ─────────────────────────────────
    #
    # ⚠️ PROPRIEDADES, e não renomeação dos campos. Os nomes antigos
    # (`measurement_readiness`, `observability_status`, `data_manager_status`)
    # são o contrato que `src/types/trafego.ts` já consome e que os testes já
    # afirmam; trocá-los quebraria a tela sem nenhum ganho de verdade. Os dois
    # vocabulários saem no JSON lado a lado, e a aposentadoria dos antigos tem
    # condição explícita: quando nenhum consumidor de `src/` os ler.

    @property
    def measurement_ready(self) -> str:
        return self.measurement_readiness

    @property
    def smart_bidding_ready(self) -> str:
        """O estado de `smart_bidding_eligible`, com a distinção que falta ao bool.

        ⚠️ PROPRIEDADE DERIVADA, e não um campo. Um campo tornaria possível
        construir uma resposta em que o estado e o booleano discordam sobre a
        mesma pergunta — e dois campos da mesma resposta HTTP se contradizendo
        é um defeito que esta casa já pegou duas vezes. Derivado, ele não pode
        divergir: não há como escrevê-lo.

        ⚠️ E a distinção que ele acrescenta é operacional, não cosmética.
        `False` colapsava duas conclusões OPOSTAS: "lemos a conta e não há
        sinal" pede instrumentação a conferir; "não conseguimos ler" pede
        leitura a repetir.
        """
        if self.smart_bidding_eligible:
            return PRONTO
        if INDETERMINADO in (self.measurement_readiness,
                             self.observability_status):
            return INDETERMINADO
        return NAO_PRONTO

    @property
    def activation_ready(self) -> str:
        """Despausar é seguro? ⚠️ O portão que não existia.

        Havia `activation_blockers` — a lista de razões — e nenhum campo que
        respondesse à pergunta. Uma lista vazia lida como permissão é o default
        otimista que este módulo recusa em todos os outros portões, e que aqui
        entrava pela ausência do campo.

        Ele exige TRÊS coisas que Smart Bidding não exige, e é por isso que os
        dois não podem ser o mesmo campo:

          1. autorização de POLÍTICA — a autorização em vigor cobre criar
             pausada e nada além; ativar é outro ato;
          2. plano PERSISTIDO — plano calculado não é plano gravado. `/provar`
             calcula e mostra, e nada sobrevive à requisição;
          3. observabilidade — despausar sem conseguir reler é autorizar às
             cegas.

        ⚠️ Também derivado, e pela mesma razão: "ativação PRONTA" ao lado de um
        bloqueador material afirmaria duas coisas opostas sobre o mesmo mundo.
        Como propriedade, a contradição é impossível de escrever — que é mais
        forte que uma guarda que a detecta.
        """
        if (self.measurement_readiness == PRONTO
                and self.observability_status == PRONTO
                and self.ativacao_autorizada_por_politica
                and self.plano_persistido
                and not self.activation_blockers_materiais):
            return PRONTO
        if INDETERMINADO in (self.measurement_readiness,
                             self.observability_status):
            return INDETERMINADO
        return NAO_PRONTO

    @property
    def observability_ready(self) -> str:
        return self.observability_status

    @property
    def data_manager_ready(self) -> str:
        return self.data_manager_status

    def portoes(self) -> Dict[str, str]:
        """Os SETE, cada um respondendo a UMA pergunta.

        ⚠️ "Pronto" sem sujeito virou uma palavra vazia, e é por isso que eles
        estão separados: poder NASCER não diz nada sobre poder MEDIR, e nenhum
        dos dois diz nada sobre poder ATIVAR.
        """
        return {
            "creation_plan_ready": self.creation_plan_ready,
            "campaign_birth": self.campaign_birth,
            "measurement_ready": self.measurement_ready,
            "observability_ready": self.observability_ready,
            "activation_ready": self.activation_ready,
            "smart_bidding_ready": self.smart_bidding_ready,
            "data_manager_ready": self.data_manager_ready,
        }

    def para_json(self) -> Dict[str, Any]:
        return {
            **self.portoes(),
            "plano_persistido_no_portao": self.plano_persistido,
            "perfil_de_mensuracao": (None if self.perfil is None
                                     else self.perfil.json()),
            "creation_plan_ready": self.creation_plan_ready,
            "campaign_birth": self.campaign_birth,
            "conversion_goal_status": self.conversion_goal_status,
            "conversion_signal_status": self.conversion_signal_status,
            "signal_sources": list(self.signal_sources),
            "measurement_readiness": self.measurement_readiness,
            "data_manager_status": self.data_manager_status,
            "observability_status": self.observability_status,
            "smart_bidding_eligible": self.smart_bidding_eligible,
            "activation_blockers": list(self.activation_blockers),
            "activation_blockers_materiais":
                list(self.activation_blockers_materiais),
            "signal_paths": list(self.signal_paths),
            "notas": dict(self.notas),
            # ⚠️ Campo de PRIMEIRA CLASSE, e não uma chave dentro de `notas`.
            # `notas` é prosa para o operador; o plano é estrutura que a tela lê
            # campo a campo — meta efetiva, fonte, frescor, bloqueadores. Enfiá-lo
            # em `notas` obrigaria o navegador a adivinhar a forma de algo que o
            # servidor já conhece.
            "plano_de_mensuracao": (
                None if self.plano_de_mensuracao is None
                else self.plano_de_mensuracao.para_json()),
        }


def avaliar(
    *,
    plano_valido: bool = False,
    recibo_registrado: bool,
    metas_da_conta: Optional[Dict[str, Any]],
    fontes_de_sinal_observadas: Optional[List[str]] = None,
    data_manager_operante: bool = False,
    coleta_pos_criacao_provada: bool = False,
    estrategia_lance: str = "MANUAL_CPC",
    plano_de_mensuracao: Optional[pm.PlanoDeMensuracao] = None,
    plano_persistido: bool = False,
    perfil: Optional[pdm.PerfilDeMensuracao] = None,
    ativacao_autorizada_por_politica: bool = False,
) -> Prontidao:
    """O veredito, calculado só do que foi de fato observado.

    ⚠️ `metas_da_conta=None` significa "não conseguimos ler", e NÃO "não há
    meta". Os dois viram estados diferentes de propósito: colapsá-los faria uma
    falha de leitura parecer uma conta sem meta, e uma conta sem meta parecer
    uma falha de leitura. As duas confusões levam a decisões opostas.

    ⚠️ `plano_de_mensuracao` é o que torna `PRONTO` ALCANÇÁVEL — e isso não é
    conveniência, é o que faz o portão poder ser provado. Enquanto o ramo
    `PRONTO` fosse inalcançável, "Smart Bidding está bloqueado" passaria com
    QUALQUER entrada, inclusive com uma conta perfeitamente medida: um teste
    que não pode falhar não prova nada. Com o plano, existem os dois lados —
    e é o par que vira prova.
    """
    bloqueios: List[str] = []
    #: ⚠️ O subconjunto MATERIAL. Cada `_bloquear` decide a natureza no ponto em
    #: que a razão nasce — quem escreve a razão é quem sabe se ela é sobre medir
    #: ou sobre outra coisa. Classificar depois, por texto, seria adivinhar.
    materiais: List[str] = []

    def _bloquear(razao: str, *, material: bool = True) -> None:
        bloqueios.append(razao)
        if material:
            materiais.append(razao)

    notas: Dict[str, Any] = {}

    # ⚠️ DUAS PERGUNTAS DIFERENTES, e confundi-las produziu um relatório que
    # dizia "pronto para nascer ✅" sem existir campanha nenhuma.
    plano_pronto = PRONTO if plano_valido else INDETERMINADO
    nascimento = PRONTO if recibo_registrado else NAO_PRONTO
    if not recibo_registrado:
        notas["campaign_birth"] = (
            "a campanha ainda NÃO nasceu. Este campo só vira PRONTO depois de "
            "mutate + recibo fechado + releitura do id externo na conta")

    # ── G1: meta de conversão ────────────────────────────────────────────────
    #
    # ⚠️ O PLANO TEM PRECEDÊNCIA, e o motivo é que ele responde a pergunta certa.
    #
    # `metas_da_conta` é uma GAQL sobre `conversion_action`: ela diz quais ações
    # a CONTA marcou como primárias. `plano_de_mensuracao` leu os TRÊS recursos
    # que decidem o efetivo — `customer_conversion_goal`,
    # `campaign_conversion_goal` e `conversion_goal_campaign_config
    # .goal_config_level`. Quando o plano existe, é ele que manda; o ramo antigo
    # continua abaixo, palavra por palavra, para quem não o passa.
    if plano_de_mensuracao is not None:
        meta = plano_de_mensuracao.meta_efetiva
        if meta.resolvida and plano_de_mensuracao.acao_alvo is not None:
            # ⚠️ ESTE É O ÚNICO RAMO QUE DEVOLVE `PRONTO`, e ele exige as duas
            # coisas: meta efetiva resolvida E uma ação de conversão eleita por
            # semântica. Meta sem ação seria um objetivo sem nada que o meça;
            # ação sem meta seria uma medida que o lance não persegue.
            meta_status = PRONTO
            alvo = plano_de_mensuracao.acao_alvo
            notas["conversion_goal"] = (
                f"meta efetiva RESOLVIDA no nível {meta.nivel}: "
                + ", ".join(sorted(m.semantica
                                   for m in (meta.metas_biddable or ())))
                + f". A ação que a mede é #{alvo.id} ({alvo.nome}), da conta "
                + f"{alvo.owner_customer_id or 'não lida'}.")
            # ⚠️ O PLANO CONTINUA TENDO RAZÕES DEPOIS QUE A META ABRE.
            #
            # Este era o único dos três ramos que não empilhava
            # `plano.bloqueadores`, e o efeito é que destino não resolvido e
            # frescor não comprovado sumiam de `activation_blockers` EXATAMENTE
            # quando o portão da meta abria — a resposta afirmava prontidão sem
            # a razão que ela mesma carregava no campo vizinho. Reproduzido por
            # dois revisores independentes.
            for _r in plano_de_mensuracao.bloqueadores:
                _bloquear(_r)
        elif (meta.nivel_estado in pm.ESTADOS_SEM_CONCLUSAO
              or meta.metas_biddable is None
              # ⚠️ E a leitura das AÇÕES também decide o estado. Sem esta
              # condição, uma GAQL de `conversion_action` que cai sozinha —
              # as cinco leituras são independentes e nenhuma aborta a outra —
              # produzia NAO_PRONTO: um veredito sobre a conta derivado de uma
              # falha de rede. Era pior que o comportamento anterior, em que
              # qualquer falha virava INDETERMINADO.
              or plano_de_mensuracao.acoes_estado in pm.ESTADOS_SEM_CONCLUSAO):
            meta_status = INDETERMINADO
            notas["conversion_goal"] = (
                "a leitura da meta efetiva não completou: "
                + (meta.causa or "sem causa registrada")
                + ". Ausência de leitura não é ausência de meta.")
            for _r in plano_de_mensuracao.bloqueadores:
                _bloquear(_r)
        else:
            # Leu as três, e a conclusão é que não há o que perseguir. Isso é
            # NAO_PRONTO — um fato sobre a conta, e não uma lacuna nossa.
            #
            # ⚠️ A causa vem do PLANO, e não de uma frase fixa. "Não há meta
            # biddable" e "há meta biddable e nenhuma ação primária que a meça"
            # são conclusões diferentes, com conserto diferente, e uma frase
            # única apagaria a distinção justamente no caso medido na conta
            # real.
            meta_status = NAO_PRONTO
            notas["conversion_goal"] = (
                plano_de_mensuracao.acao_alvo_causa
                or "as metas efetivas foram lidas e nenhuma é biddable: uma "
                   "campanha em lance automático otimizaria para nada.")
            for _r in plano_de_mensuracao.bloqueadores:
                _bloquear(_r)
        notas["conversion_actions_primarias"] = [
            {"id": a.id, "nome": a.nome, "categoria": a.categoria,
             "owner_customer_id": a.owner_customer_id}
            for a in plano_de_mensuracao.acoes if a.primaria_efetiva
        ]
    elif metas_da_conta is None:
        meta_status = INDETERMINADO
        notas["conversion_goal"] = (
            "não foi possível ler as metas da conta; ausência de leitura não é "
            "ausência de meta")
        _bloquear("metas de conversão não lidas")
    elif metas_da_conta.get("primaria"):
        # ⚠️ PARCIAL, E NÃO PRONTO — e a diferença é o que foi de fato lido.
        #
        # O que existe hoje é uma GAQL sobre `conversion_action`, que devolve as
        # ações e o `primary_for_goal` de cada uma. Isso NÃO é a meta efetiva da
        # campanha. A doc oficial (evidence/GOOGLE-ADS-DOCS-2026-09-01.md) é
        # explícita: o efetivo exige `customer_conversion_goal`,
        # `campaign_conversion_goal` e sobretudo
        # `conversion_goal_campaign_config.goal_config_level`, que diz se quem
        # manda é a conta ou a campanha. Nenhuma dessas três é consultada.
        #
        # Medido na Portal Mundo Mais em 01/09/2026: NOVE ações ENABLED, OITO
        # com `primary_for_goal=true`. Dizer "a ação primária" no singular
        # apagaria sete delas. `PARCIAL` diz o que se sabe sem inventar o resto.
        primarias = [a for a in (metas_da_conta.get("acoes") or ())
                     if a.get("primaria")]
        meta_status = PARCIAL
        # ⚠️ `len(primarias)`, e não `len(primarias) or 1`. O `or 1` fazia a
        # frase afirmar "1 ação" quando `metas_da_conta` traz `primaria` e não
        # traz `acoes` — enquanto `conversion_actions_primarias`, logo abaixo,
        # saía vazia. Dois campos da MESMA resposta se contradiziam, e quem
        # lesse o número acreditaria nele.
        notas["conversion_goal"] = (
            f"leitura PARCIAL: {len(primarias)} ação(ões) com "
            "primary_for_goal=true em `conversion_action`. Isso não é a meta "
            "EFETIVA: ela exige customer_conversion_goal, campaign_conversion_goal "
            "e conversion_goal_campaign_config.goal_config_level, que ainda não "
            "são consultados. A campanha herda as metas da conta, e sobrescrever "
            "exigiria CampaignConversionGoal — ato separado, e a API só ATUALIZA "
            "goals, nunca cria nem remove")
        notas["conversion_actions_primarias"] = [
            {"id": a.get("id"), "nome": a.get("nome"),
             "categoria": a.get("categoria")} for a in primarias]
        _bloquear(
            "meta de conversão efetiva não lida (faltam customer_conversion_goal "
            "e conversion_goal_campaign_config)")
    else:
        meta_status = NAO_PRONTO
        notas["conversion_goal"] = (
            "a conta não tem ação de conversão primária: uma campanha em lance "
            "automático otimizaria para nada")
        _bloquear("conta sem ação de conversão primária")

    # ── G1: sinal chegando ───────────────────────────────────────────────────
    #
    # ⚠️ SINAL ≠ DATA MANAGER. A primeira versão tratava os dois como a mesma
    # coisa e exigia Data Manager operante para declarar medição. Isso está
    # errado em conta que converte por tag do Google ou importação GA4: ela tem
    # sinal chegando e seria declarada despreparada por não usar uma via que
    # não precisa. Data Manager é UMA fonte, e a que ainda não existe aqui.
    fontes = list(fontes_de_sinal_observadas or ())
    caminhos: List[str] = []
    if plano_de_mensuracao is not None:
        # ⚠️ CAPACIDADE E PROVA SAEM SEPARADAS, e é essa separação que conserta
        # o defeito. Auto-tagging ligado, tag configurada e importação declarada
        # dizem por onde a conversão PODERIA chegar; nenhuma delas diz que
        # alguma chegou. Empilhá-las em `fontes` fazia uma conta com
        # `auto_tagging=True` e ZERO conversão medida sair com sinal PRONTO e
        # Smart Bidding elegível — carregando, na lista ao lado, o bloqueador
        # que dizia que nenhuma conversão chegou.
        caminhos = list(pm.caminhos_de_sinal_declarados(plano_de_mensuracao))
        if not fontes:
            # `fontes_de_sinal_observadas` explícito continua tendo precedência:
            # quem o passa está AFIRMANDO ter observado algo que este módulo não
            # tem como conferir.
            fontes = list(pm.fontes_de_sinal_observadas(plano_de_mensuracao))
    if fontes:
        sinal = PRONTO
        notas["conversion_signal"] = (
            "sinal COMPROVADO: " + ", ".join(fontes))
    else:
        sinal = NAO_PRONTO
        # ⚠️ A frase distingue os dois desfechos, porque eles pedem coisas
        # opostas: caminho declarado e sem conversão é problema de
        # instrumentação — a tag está lá e não dispara; nenhum caminho e nenhuma
        # conversão é problema anterior, não há por onde medir.
        if caminhos:
            notas["conversion_signal"] = (
                "há caminho declarado para o sinal (" + ", ".join(caminhos)
                + ") e NENHUMA conversão observada. Caminho não é tráfego: o "
                "que decide o lance é conversão chegando, não a via existir.")
            _bloquear(
                "há caminho de mensuração configurado e nenhuma conversão "
                "observada. A via existe e não está trazendo evento — é "
                "instrumentação a conferir, não configuração a criar.")
        else:
            notas["conversion_signal"] = (
                "nenhuma fonte de sinal foi COMPROVADA nesta leitura (tag do "
                "Google, importação GA4, upload offline ou Data Manager). Lista "
                "vazia significa 'não comprovado', e não 'não existe'")
            _bloquear("nenhuma fonte de sinal de conversão comprovada")
    if caminhos:
        notas["signal_paths"] = (
            "vias por onde o sinal PODERIA chegar — inventário, não prova: "
            + ", ".join(caminhos))

    # ⚠️ O DESTINO ENTRA NO PORTÃO, e a primeira versão o ignorava.
    #
    # Reproduzido em 02/09/2026: com `data_manager_operante=True` e um plano
    # sem ação eleita — logo sem `operating_account_id` e sem
    # `product_destination_id` — o portão saía `PRONTO`. Pronto para mandar
    # evento para lugar nenhum.
    #
    # "Operante" descreve a NOSSA fila. "Destino resolvido" descreve para ONDE
    # o evento vai, e a Data Manager resolve destino por conta DONA + id
    # NUMÉRICO da ação. Sem o segundo, o primeiro não significa nada — e mandar
    # para a conta errada não é um erro barulhento.
    destino_resolvido = (plano_de_mensuracao is not None
                         and plano_de_mensuracao.destino.resolvido)
    if data_manager_operante and destino_resolvido:
        dm_status = PRONTO
    elif data_manager_operante:
        dm_status = NAO_PRONTO
        causa_do_destino = (
            (plano_de_mensuracao.destino.causa
             if plano_de_mensuracao is not None else None)
            or "nenhum plano de mensuração foi lido, então não há destino a "
               "resolver")
        notas["data_manager"] = (
            "a ingestão offline foi declarada operante e o DESTINO não está "
            f"resolvido: {causa_do_destino}")
        # ⚠️ NÃO material: ele não impede aprender nem observar. Contá-lo como
        # material declararia despreparo de MEDIÇÃO numa conta que mede por tag
        # do Google e nunca vai usar ingestão offline.
        _bloquear(
            "Data Manager declarado operante sem destino resolvido (conta dona "
            "+ id numérico da ação): o envio não tem para onde ir.",
            material=False)
    else:
        dm_status = NAO_PRONTO
        notas["data_manager"] = (
            "a ingestão de conversão offline pela Data Manager API não está "
            "operante: fila, lote, envio e diagnóstico existem como contrato, "
            "não como execução. Isso NÃO bloqueia por si só uma conta cuja "
            "conversão venha de tag ou GA4")

    # Medir exige meta efetiva E ao menos um caminho de sinal comprovado. Ter
    # uma sem a outra não é meia medição — é nenhuma, porque o lance aprende do
    # que chega, não do que foi declarado.
    if meta_status == PRONTO and sinal == PRONTO:
        medicao = PRONTO
    elif meta_status == INDETERMINADO or sinal == INDETERMINADO:
        medicao = INDETERMINADO
    else:
        medicao = NAO_PRONTO

    # ── G2: observação pós-criação ───────────────────────────────────────────
    observacao = PRONTO if coleta_pos_criacao_provada else INDETERMINADO
    if not coleta_pos_criacao_provada:
        notas["observabilidade"] = (
            "a releitura pós-criação ainda não foi exercida contra uma campanha "
            "real; o coletor contínuo lê apenas campanhas ENABLED")

    # ── G3: ativação e Smart Bidding ─────────────────────────────────────────
    #
    # ⚠️ AQUI MORA A REGRA QUE ESTE MÓDULO EXISTE PARA IMPOR.
    #
    # `smart_bidding_eligible` só é `True` quando medição está PRONTA. Não há
    # ramo que o ligue por ausência de bloqueio conhecido: um sistema que
    # conclui "elegível" porque não achou problema está afirmando algo sobre o
    # mundo a partir do que ele não olhou.
    # ⚠️ G2 GOVERNA G3 JUNTO COM G1.
    #
    # A primeira versão fazia `smart_bidding_eligible` depender só de medição.
    # A alegação "não liga por ausência de bloqueio" continuava verdadeira, mas
    # os quatro portões não governavam juntos: dava para ter elegibilidade com
    # `observability_status=INDETERMINADO` e `activation_blockers` VAZIO — ou
    # seja, autorizado a otimizar sem conseguir observar o que acontece depois.
    elegivel = medicao == PRONTO and observacao == PRONTO
    if observacao != PRONTO:
        _bloquear(
            "observabilidade pós-criação não provada: sem releitura, um "
            "desvio de entrega ou de política não seria notado")
    if not elegivel and estrategia_lance != "MANUAL_CPC":
        # ⚠️ NÃO material: é a CONSEQUÊNCIA das razões acima, e não uma razão
        # independente. Contá-la como material duplicaria a mesma causa e faria
        # a lista sugerir dois problemas onde há um.
        _bloquear(
            f"estratégia {estrategia_lance} exige sinal de conversão provado",
            material=False)
    notas["manual_cpc"] = (
        "Manual CPC pode existir no canário pausado sem Data Manager. Isso não "
        "autoriza ativação nem implica prontidão de ROI")

    # ── G3b: ATIVAÇÃO — as razões; o estado é derivado no tipo ──────────────
    #
    # ⚠️ Ele exige TRÊS coisas que Smart Bidding não exige, e é por isso que os
    # dois não podem ser o mesmo campo:
    #
    #   1. autorização de POLÍTICA — a autorização em vigor cobre criar pausada
    #      e nada além; ativar é outro ato. O default é `False`, de modo que uma
    #      chamada que esqueça o parâmetro produz recusa, nunca permissão;
    #   2. plano PERSISTIDO — plano calculado não é plano gravado. `/provar`
    #      calcula e mostra, e nada sobrevive à requisição. Ativar com base nele
    #      é ativar com base numa tela, e semanas depois ninguém consegue dizer
    #      o que o operador viu quando decidiu;
    #   3. observabilidade — despausar sem conseguir reler é autorizar às cegas.
    #
    # ⚠️ E a recíproca vale: sem política, a ativação fecha e a MEDIÇÃO continua
    # provada. Colapsar os dois faria uma recusa administrativa parecer uma
    # conta que não mede.
    if not ativacao_autorizada_por_politica:
        _bloquear(
            "a autorização em vigor cobre criar pausada e nada além; ativar é "
            "outro ato, e ele não foi autorizado.",
            material=False)
    if not plano_persistido:
        # ⚠️ NÃO material: a campanha aprende igual com o plano fora do banco.
        # O que ela não pode é ser ativada de forma prestável de contas. Contá-lo
        # como material derrubaria `smart_bidding_eligible` por um motivo que
        # não é sobre medir — e a invariante do tipo levantaria.
        _bloquear(
            "o plano de mensuração desta campanha não está PERSISTIDO: o que "
            "se sabe sobre a medição dela não sobreviveu à requisição, e "
            "ativar com base nisso é ativar com base numa tela.",
            material=False)

    return Prontidao(
        plano_persistido=plano_persistido,
        ativacao_autorizada_por_politica=ativacao_autorizada_por_politica,
        perfil=perfil,
        creation_plan_ready=plano_pronto,
        campaign_birth=nascimento,
        conversion_goal_status=meta_status,
        conversion_signal_status=sinal,
        signal_sources=fontes,
        measurement_readiness=medicao,
        data_manager_status=dm_status,
        observability_status=observacao,
        smart_bidding_eligible=elegivel,
        activation_blockers=bloqueios,
        activation_blockers_materiais=materiais,
        signal_paths=caminhos,
        notas=notas,
        plano_de_mensuracao=plano_de_mensuracao,
    )


# ═══════════════════════════════════════════════════════════════════════════
# O PORTÃO DO CAMINHO DE ESCRITA
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️ Tudo acima é DIAGNÓSTICO: `/provar` calcula os portões, projeta na resposta
# e ninguém é obrigado a obedecer. Medido em 02/09/2026 contra a base `26a58c4`:
#
#     PROVAR diz: smart_bidding_eligible = False
#     PROVAR diz: bloqueadores = 5
#     ATOS: ['ler_plano','abrir','despachar','registrar_plano','MUTATE', …]
#
# `/subir` nunca chamou `avaliar`. O `estrategia_lance` do corpo atravessava
# `Escolha` até o executor sem passar por portão nenhum, e o risco ficava contido
# só porque a campanha nasce PAUSED por literal e o engine não tem função de
# ativação — duas defesas que ninguém escolheu como portão de lance, e que a
# primeira pessoa a despausar pelo painel do Google desfaz.
#
# Este bloco é a diferença entre um veredito e um portão.


class PortaoFechado(RuntimeError):
    """A estratégia pedida exige prova que esta conta não tem. Nada foi enviado."""


class LanceSemMedicao(PortaoFechado):
    """Lance automático sem meta efetiva resolvida e sinal chegando."""


class LanceSemValor(PortaoFechado):
    """Lance por VALOR sem nenhuma regra de valor declarada nem lida."""


#: As estratégias que NÃO aprendem de conversão. Uma lista fechada, e curta.
#:
#: ⚠️ `MANUAL_CPC` é o padrão da casa. Recusá-lo porque a conta não mede
#: transformaria uma conta sem conversão numa conta sem campanha — e o canário
#: pausado existe justamente para colher veredito de política sem depender de
#: medição. O portão é sobre APRENDER, não sobre nascer.
ESTRATEGIAS_SEM_APRENDIZADO: tuple[str, ...] = ("MANUAL_CPC",)

#: As que otimizam pelo VALOR de cada conversão, e não pela contagem.
ESTRATEGIAS_QUE_EXIGEM_VALOR: tuple[str, ...] = ("MAXIMIZE_CONVERSION_VALUE",)


def exigir_para_criacao(*, estrategia_lance: str,
                        prontidao: Prontidao) -> None:
    """Recusa criar em lance automático o que a conta não sabe medir.

    Levanta `PortaoFechado`; devolve `None` quando pode seguir.

    ⚠️ O portão olha `measurement_ready`, e NÃO `smart_bidding_ready`. A
    diferença é o instante: `smart_bidding_ready` exige observabilidade
    pós-criação, que por definição não existe antes de a campanha nascer.
    Exigi-la aqui tornaria `MANUAL_CPC` a única estratégia possível para sempre
    — um portão que nunca abre não protege, só esconde a decisão.

    ⚠️ `INDETERMINADO` RECUSA. Uma falha de leitura do Google não é permissão.
    O plano de ignorância continua deixando a campanha NASCER — pausada, com os
    portões fechados —, e deixa de permitir que ela nasça APRENDENDO.
    """
    estrategia = str(estrategia_lance or "MANUAL_CPC").strip().upper()
    if estrategia in ESTRATEGIAS_SEM_APRENDIZADO:
        return

    if prontidao.measurement_ready != PRONTO:
        razoes = list(prontidao.activation_blockers_materiais) or [
            "a medição desta conta não foi provada nesta leitura"]
        raise LanceSemMedicao(
            f"{estrategia} exige meta de conversão efetiva resolvida e sinal "
            f"CHEGANDO, e a medição está {prontidao.measurement_ready}: "
            + "; ".join(razoes)
            + ". Nada foi enviado ao Google. Suba em MANUAL_CPC — que não "
              "aprende de conversão e por isso não depende desta prova — ou "
              "conserte a medição antes.")

    if estrategia in ESTRATEGIAS_QUE_EXIGEM_VALOR:
        # ⚠️ VALOR NÃO É CONVERSÃO, e este sistema não lê
        # `conversion_action.value_settings` em nenhuma das cinco leituras
        # GAQL. Sem ele, o único lastro possível é uma regra de valor DECLARADA
        # no perfil de mensuração. Otimizar pelo valor sem nenhum dos dois é
        # perseguir um número que pode ser zero em todas as linhas.
        regra = None if prontidao.perfil is None else prontidao.perfil.regra_de_valor
        if regra is None or regra.modo == pdm.VALOR_SEM_VALOR:
            raise LanceSemValor(
                f"{estrategia} otimiza pelo VALOR de cada conversão, e nenhuma "
                "regra de valor foi declarada no perfil de mensuração. Este "
                "sistema também não lê `conversion_action.value_settings`, "
                "então não há como provar que a ação eleita carrega valor. "
                "Nada foi enviado ao Google: declare a regra de valor do perfil "
                "ou suba em MAXIMIZE_CONVERSIONS, que otimiza pela contagem.")
