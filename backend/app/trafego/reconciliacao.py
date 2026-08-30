"""A pergunta que o quadro de Oportunidades faz: **este funil já tem campanha?**

## O defeito que este módulo fecha

Até aqui a resposta vinha de uma coluna anulável de uma tabela legada:
`campaigns.funnel_run_id`. Quem não nasceu pela porta `/subir` é invisível para
ela — a linha não existe, ou existe com a coluna nula.

Medido em 26/08/2026 no Supabase oficial: `campaigns` tem **quatro** linhas, e
apenas uma delas tem `funnel_run_id`. As três campanhas de FGTS que a conta
`8017851692` mostra — duas removidas e uma **ENABLED, gastando agora** — não
têm linha nenhuma. O quadro respondia `campanhas_lancadas: 0` e oferecia
"montar campanha" para um funil que já tem campanha no ar.

O convite não é inofensivo: duas campanhas do mesmo termo, na mesma conta,
disputam o mesmo leilão com verba de verdade. Cada uma encarece a outra.

## A regra que substitui

A conta de anúncio é a autoridade sobre existência e estado (ADR-01). A
pergunta deixa de ser *"há linha no nosso cadastro?"* e passa a ser *"há, na
conta deste projeto, campanha que aponte para o destino deste funil?"*.

Ninguém aqui procura por "FGTS", nem por id de campanha, nem por nome. As regras
comparam **URL normalizada** e **identificadores externos**, e cada candidata
declara qual regra a trouxe. Uma sugestão sem regra visível não é oferecida
(SPEC 3.2) — porque o operador precisa poder discordar sabendo do quê.

## Sugerir não é vincular

Nada aqui grava vínculo. `correspondencia_provavel` é uma pergunta feita ao
operador, e a resposta dele vira uma linha em `trafego_vinculo`, com quem,
quando, qual regra casou e qual evidência — auditável, corrigível e reversível
(ADR-09).

O motivo de a confirmação ser humana está medido: um vínculo errado contamina a
atribuição de receita de forma permanente e silenciosa. O custo de confirmar
recai sobre o operador, e isso é deliberado.

## Este módulo é PURO

Sem I/O, sem banco, sem rede, sem framework. Ele recebe os fatos já lidos e
devolve o veredito. Quem lê é o router; quem grava é a persistência. É o mesmo
contrato de `dominio.py`, e pelo mesmo motivo: uma regra de negócio que precisa
de banco para ser testada acaba testada com dublê, e um dublê responde o que o
teste mandou responder.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# VOCABULÁRIO
# ═══════════════════════════════════════════════════════════════════════════

#: Vínculo humano confirmado, e a campanha está presente na conta.
VINCULADA = "vinculada"

#: Há sinal suficiente para revisão, insuficiente para afirmar o vínculo.
#: Não bloqueia por opinião: bloqueia porque montar outra campanha enquanto esta
#: pergunta está aberta cria duplicidade que ninguém decidiu criar.
CORRESPONDENCIA_PROVAVEL = "correspondencia_provavel"

#: Mais de uma candidata presente. **Nunca escolher em silêncio** — escolher
#: seria vincular o funil à campanha errada com toda a confiança, e o erro só
#: apareceria semanas depois, na atribuição de receita.
CONFLITO = "conflito"

#: Nenhuma candidata, depois de uma prova que pôde ser feita. Só aqui a
#: montagem é oferecida.
SEM_CAMPANHA = "sem_campanha"

#: Só há candidatas no histórico removido. Relançar é legítimo — aconteceu cinco
#: vezes com motivo declarado (E-05) — mas é decisão declarada, não convite.
SOMENTE_HISTORICO = "somente_historico"

ESTADOS: Tuple[str, ...] = (
    VINCULADA, CORRESPONDENCIA_PROVAVEL, CONFLITO, SEM_CAMPANHA,
    SOMENTE_HISTORICO,
)

# ── ações ───────────────────────────────────────────────────────────────────

MONTAR = "montar"
ABRIR_O_QUE_EXISTE = "abrir_o_que_existe"
CONFIRMAR_VINCULO = "confirmar_vinculo"
ABRIR_REVISAO = "abrir_revisao"
RELANCAR_DECLARADO = "relancar_declarado"

# ── regras, e a força de cada uma ───────────────────────────────────────────
#
# A força não é opinião: ela separa o que foi OBSERVADO na conta do que foi
# DECLARADO por nós. Uma declaração nossa pode estar desatualizada — alguém
# renomeia a campanha no painel do Google e ela deixa de ser verdade sem que
# nada aqui perceba. Uma observação, não.

FORTE = "forte"
MEDIO = "medio"

#: Observado na conta, **sem carimbo próprio**. Sustenta a candidata e não fecha
#: o vínculo sozinha.
#:
#: Existe porque `url_final` é preservada entre varreduras (v9_04) e o espelho
#: tem um carimbo só, o da varredura. Um valor que pode ser de três semanas atrás
#: não é observação de agora, e chamá-lo de `forte` seria promover a força em
#: silêncio — no degrau exato que uma composição futura usaria para dispensar a
#: confirmação humana.
#:
#: **Sai daqui quando existir `url_final_lida_em`.** Aí a regra volta a ser
#: `forte` quando o carimbo for recente, e continua `historica` quando não for.
HISTORICA = "historica"

#: A URL de destino lida do ANÚNCIO, na conta. É o sinal externo mais forte do
#: SPEC 3.2 — mas hoje ela viaja como `historica`, e não `forte`: ver
#: `HISTORICA`. O espelho não guarda quando a URL foi lida, e o gatilho da v9_04
#: a preserva entre varreduras.
REGRA_URL_DA_CONTA = "url_final_da_conta"

#: A URL que viaja no nome da campanha, terceiro campo da taxonomia
#: (`volc_ads/campanha/taxonomia.py`). É DECLARAÇÃO NOSSA espelhada de volta: o
#: nosso próprio lançador a escreveu ali. Vale como sinal e nunca como
#: identidade — um humano pode reescrever o nome no painel a qualquer momento.
REGRA_URL_NO_NOME = "url_no_nome_declarado"

#: A porta `/subir` gravou `campaigns.funnel_run_id` no lançamento. Declaração
#: nossa, com a mesma fragilidade: existe só para o que nasceu por aquela porta.
REGRA_LANCAMENTO_DECLARADO = "lancamento_declarado"

#: Mesma linhagem declarada. Forte porque linhagem é intenção registrada e
#: imutável (ADR-02) — mas hoje ela é nula em 100% das campanhas, e a regra
#: aparece em `sinais_ausentes` em vez de silenciosamente não existir.
REGRA_LINHAGEM = "linhagem_declarada"

FORCA_DA_REGRA: Dict[str, str] = {
    REGRA_URL_DA_CONTA: HISTORICA,
    REGRA_LINHAGEM: FORTE,
    REGRA_URL_NO_NOME: MEDIO,
    REGRA_LANCAMENTO_DECLARADO: MEDIO,
}


# ═══════════════════════════════════════════════════════════════════════════
# NORMALIZAÇÃO DE URL
# ═══════════════════════════════════════════════════════════════════════════

_ESQUEMA = re.compile(r"^https?://", re.IGNORECASE)
_WWW = re.compile(r"^www\.", re.IGNORECASE)

#: O WordPress devolve isto para um RASCUNHO, em vez do permalink. Anunciar essa
#: URL manda tráfego para um endereço que vai mudar — e comparar por ela casaria
#: funis diferentes entre si, porque a única parte estável é `?post_type=r`.
_RASCUNHO = re.compile(r"[?&]p=\d+|[?&]post_type=", re.IGNORECASE)


def url_normalizada(bruta: Any, *, sem_consulta: bool = False) -> Optional[str]:
    """A forma canônica de uma URL para comparação. `None` quando não serve.

    ⚠️ **Esta é a normalização que o banco já usa**, reproduzida termo a termo:
    o gatilho `clean_funnel_url` (vivo em `public.campaign_funnel_urls`) faz
    `TRIM` → remove `https?://` → remove `www.` → remove a barra final. Ele é a
    chave do join custo × receita, e usar outra normalização aqui faria dois
    lugares do sistema discordarem sobre o que é "a mesma página".

    ⚠️ **Não faz lowercase**, e a omissão é do gatilho, não descuido meu. O
    caminho de uma URL é sensível a maiúsculas em servidores Unix: `/r/FGTS` e
    `/r/fgts` podem ser páginas diferentes. Baixar o caso casaria duas URLs que
    o servidor trata como distintas.

    Devolve `None` para permalink de rascunho: comparar por ele casaria funis
    diferentes entre si, já que a parte estável é a mesma para todos.
    """
    texto = str(bruta or "").strip()
    if not texto:
        return None
    if _RASCUNHO.search(texto):
        return None
    texto = _ESQUEMA.sub("", texto)
    texto = _WWW.sub("", texto)
    if sem_consulta:
        texto = texto.split("#", 1)[0].split("?", 1)[0]
    texto = texto.rstrip("/")
    return texto or None


def destino_comparavel(bruta: Any) -> Optional[str]:
    """A URL como a RECONCILIAÇÃO a compara: sem parâmetro e sem fragmento.

    ⚠️ Diferente de `url_normalizada`, e a diferença é o ponto.

    A URL do anúncio quase sempre carrega marcação — `?utm_source=google`,
    `gclid`, o `final_url_suffix` da conta — e a `lp_url` do funil nunca carrega.
    Comparando com a query string, a regra MAIS FORTE do contrato erra
    exatamente onde ela mais vale: numa campanha real, com destino certo, e sem
    deixar rastro do porquê. O resultado seria `sem_campanha`, que libera a
    montagem.

    O preço é conhecido e menor: duas páginas que diferem SÓ pela query string
    passam a casar. Nas landing pages deste sistema o destino é um permalink
    `/r/slug` e a query só carrega marcação — mas é uma escolha, não uma
    verdade, e está escrita aqui para quem precisar revê-la.

    `url_normalizada` continua sendo a do gatilho `clean_funnel_url`, porque é
    ela que faz o join custo × receita no banco. As duas coexistem de propósito:
    são perguntas diferentes.
    """
    return url_normalizada(bruta, sem_consulta=True)


#: Separador de campos da taxonomia (`volc_ads/campanha/taxonomia.py`).
_SEP_CAMPO = " / "


def url_no_nome(nome: Any) -> Optional[str]:
    """A URL de destino que viaja no nome da campanha, já normalizada.

    O construtor de Search escreve o nome como
    `«sigla» - «sequência» / «tema» / «url»`, e o terceiro campo é a URL final
    (`volc_ads/campanha/search.py`). A conta espelha esse nome de volta.

    ⚠️ **Isto não é procurar por nome.** A busca não é por texto do tema, nem
    por palavra da campanha: é a extração de um campo ESTRUTURADO de uma
    convenção declarada, e o que sai dele é uma URL — que depois passa pela
    mesma normalização de todas as outras.

    Procura-se o segmento que PARECE URL, e não a posição 3, porque um tema com
    barra dentro deslocaria os campos. Um nome escrito à mão no painel do Google
    simplesmente não tem segmento nenhum com cara de URL, e a regra não dispara
    em vez de casar errado.
    """
    texto = str(nome or "")
    for parte in texto.split(_SEP_CAMPO):
        candidata = parte.strip()
        if _ESQUEMA.match(candidata):
            return destino_comparavel(candidata)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# OS FATOS QUE ENTRAM
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Funil:
    """O que se sabe de um funil publicado, sem nenhuma consulta a campanha."""

    opportunity_id: int
    run_id: Optional[int]
    project_id: Optional[int]
    #: A conta de anúncio do projeto. `None` quando o projeto não tem conta
    #: declarada — e aí a prova não pode ser feita, o que é dito e não escondido.
    customer_id: Optional[str] = None
    #: A URL da landing page, como o Redator a gravou.
    lp_url: Optional[str] = None
    #: As URLs das páginas publicadas. A da LP costuma ser a mesma de `lp_url`,
    #: mas nem sempre: `lp_url` é cópia desnormalizada.
    urls_publicadas: Tuple[str, ...] = ()
    campaign_lineage_id: Optional[str] = None

    def destinos(self) -> Tuple[str, ...]:
        """Toda URL deste funil, normalizada e sem repetição.

        A ordem é estável (`lp_url` primeiro) para a evidência sair sempre igual
        — evidência que muda de ordem entre duas leituras parece ter mudado de
        conteúdo.
        """
        vistas: List[str] = []
        for bruta in (self.lp_url, *self.urls_publicadas):
            u = destino_comparavel(bruta)
            if u and u not in vistas:
                vistas.append(u)
        return tuple(vistas)


@dataclass(frozen=True)
class CampanhaConhecida:
    """Uma campanha como o inventário a conhece. Vem da view, não do Google."""

    volc_campaign_id: str
    campaign_id: str
    customer_id: Optional[str]
    nome: str = ""
    estado_externo: Optional[str] = None
    canal: Optional[str] = None
    #: A conta declara esta campanha removida? Coluna da view (v9_03).
    historico: bool = False
    #: A URL lida do anúncio. `None` enquanto a varredura não a colheu.
    url_final: Optional[str] = None
    campaign_lineage_id: Optional[str] = None
    #: Quando o espelho leu esta campanha. Viaja para a evidência: uma URL de
    #: três semanas atrás e uma de agora sustentam a mesma regra com forças
    #: diferentes, e quem confirma o vínculo precisa ver a data.
    lido_em: Optional[str] = None
    #: Vínculo humano vivo, quando existe.
    vinculo_id: Optional[str] = None
    vinculo_opportunity_id: Optional[int] = None
    vinculo_run_id: Optional[int] = None


@dataclass(frozen=True)
class Sinal:
    """Por que esta campanha entrou como candidata."""

    regra: str
    forca: str
    evidencia: Dict[str, Any] = field(default_factory=dict)

    def json(self) -> Dict[str, Any]:
        return {"regra": self.regra, "forca": self.forca,
                "evidencia": dict(self.evidencia)}


@dataclass(frozen=True)
class Candidata:
    campanha: CampanhaConhecida
    sinais: Tuple[Sinal, ...]

    @property
    def presente(self) -> bool:
        return not self.campanha.historico

    def json(self) -> Dict[str, Any]:
        c = self.campanha
        return {
            "volc_campaign_id": c.volc_campaign_id,
            "externa": {"customer_id": c.customer_id,
                        "campaign_id": c.campaign_id},
            "nome": c.nome,
            "estado_externo": c.estado_externo,
            "canal": c.canal,
            "historico": c.historico,
            "vinculo_id": c.vinculo_id,
            "sinais": [s.json() for s in self.sinais],
        }


@dataclass(frozen=True)
class Reconciliacao:
    """O veredito sobre um funil, com tudo o que o sustenta."""

    opportunity_id: int
    run_id: Optional[int]
    estado: str
    candidatas: Tuple[Candidata, ...]
    #: Que regra não pôde correr, e por quê. É o que impede "sem campanha" de
    #: significar duas coisas: "provei e não há" e "não consegui provar".
    sinais_ausentes: Tuple[Dict[str, Any], ...]
    acao_permitida: str
    exige_confirmacao_humana: bool
    #: A montagem de campanha nova está liberada nesta linha?
    pode_montar: bool
    #: O relançamento declarado está oferecido?
    pode_relancar: bool

    def json(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "run_id": self.run_id,
            "estado": self.estado,
            "candidatas": [c.json() for c in self.candidatas],
            "sinais_ausentes": [dict(s) for s in self.sinais_ausentes],
            "acao_permitida": self.acao_permitida,
            "exige_confirmacao_humana": self.exige_confirmacao_humana,
            "pode_montar": self.pode_montar,
            "pode_relancar": self.pode_relancar,
        }


# ═══════════════════════════════════════════════════════════════════════════
# A COMPOSIÇÃO
# ═══════════════════════════════════════════════════════════════════════════


def _sinais_da_campanha(funil: Funil,
                        campanha: CampanhaConhecida,
                        legado_por_run: Dict[int, set]) -> Tuple[Sinal, ...]:
    """Toda regra que casa esta campanha com este funil. Vazio = não é candidata."""
    destinos = funil.destinos()
    sinais: List[Sinal] = []

    # 1 · a URL lida do anúncio, na conta. Observação.
    da_conta = destino_comparavel(campanha.url_final)
    if da_conta and da_conta in destinos:
        # ⚠️ **A URL da conta NÃO é promovida a observação atual.**
        #
        # O gatilho da v9_04 preserva `url_final` quando a leitura não a trouxe,
        # e o espelho tem UM carimbo só — `lido_em`, que é da varredura, não da
        # coluna. Não há como distinguir "o anúncio aponta para cá HOJE" de "o
        # anúncio apontava para cá quando a URL foi lida pela última vez".
        #
        # Enquanto não existir `url_final_lida_em`, a força declarada é
        # `historica`: ela sustenta a candidata e NÃO fecha o vínculo sozinha.
        # Chamá-la de `forte` seria apresentar como observação de agora um valor
        # que pode ser de três semanas atrás — e `forte` é justamente o degrau
        # que a composição usaria para dispensar a confirmação humana no dia em
        # que essa dispensa existir.
        #
        # A confirmação humana continua obrigatória de qualquer modo (ADR-09);
        # o que esta linha impede é a promoção SILENCIOSA da força.
        sinais.append(Sinal(REGRA_URL_DA_CONTA, HISTORICA, {
            "url": da_conta,
            "lida_de": "anuncio",
            # De quando é a varredura que trouxe a linha. Não é o carimbo da
            # URL: é o mais próximo que existe hoje.
            "lido_em": campanha.lido_em,
            "por_que_nao_e_forte": (
                "o espelho não guarda quando a URL foi lida; o gatilho a "
                "preserva entre varreduras, e o carimbo é da varredura, não da "
                "coluna"),
        }))

    # 2 · a URL que o nosso lançador escreveu no nome. Declaração espelhada.
    #
    # Só entra quando a regra 1 NÃO casou: com as duas, a evidência mostraria
    # dois sinais para o mesmo fato e uma composição futura os somaria como se
    # fossem independentes. Eles não são — a segunda é a origem da primeira.
    do_nome = url_no_nome(campanha.nome)
    if not da_conta and do_nome and do_nome in destinos:
        sinais.append(Sinal(REGRA_URL_NO_NOME, MEDIO,
                            {"url": do_nome, "lida_de": "nome_da_campanha"}))

    # 3 · a linhagem declarada, quando os dois lados a têm.
    if (funil.campaign_lineage_id
            and campanha.campaign_lineage_id
            and funil.campaign_lineage_id == campanha.campaign_lineage_id):
        sinais.append(Sinal(REGRA_LINHAGEM, FORTE,
                            {"campaign_lineage_id": funil.campaign_lineage_id}))

    # 4 · o lançamento declarado pela porta `/subir`.
    if funil.run_id is not None:
        if campanha.campaign_id in legado_por_run.get(funil.run_id, set()):
            sinais.append(Sinal(REGRA_LANCAMENTO_DECLARADO, MEDIO,
                                {"funnel_run_id": funil.run_id,
                                 "campaign_id": campanha.campaign_id}))

    return tuple(sinais)


def _ausentes(funil: Funil,
              candidatas: Sequence[Candidata],
              universo: Sequence[CampanhaConhecida]) -> Tuple[Dict[str, str], ...]:
    """As regras que não puderam correr, nomeadas.

    Sem isto, `sem_campanha` significaria duas coisas incompatíveis: "a conta foi
    lida e não há campanha para este funil" e "não consegui perguntar". A
    primeira libera a montagem; a segunda não deveria.
    """
    faltando: List[Dict[str, Any]] = []

    # ── `impede_prova` separa ausência de ausência ──────────────────────────
    #
    # Nem toda regra que não correu enfraquece a conclusão na mesma medida, e
    # tratar todas igual produz um dos dois defeitos:
    #
    #   · marcar tudo → todo cartão nasce com ressalva, o operador aprende a
    #     ignorá-la, e a ressalva morre no dia em que importa;
    #   · marcar nada → "não consegui provar" passa por "provei e não há", e a
    #     tela convida a montar uma segunda campanha para o mesmo termo.
    #
    # `impede_prova=True` significa: **não havia como comparar**. É diferente de
    # "comparei por um caminho mais fraco" e de "esta regra nunca se aplica aqui".
    if not funil.customer_id:
        faltando.append({
            "regra": "conta_do_projeto",
            "motivo": ("o projeto deste funil não tem conta de anúncio "
                       "declarada; sem conta não há onde procurar"),
            "impede_prova": True,
        })
    if funil.customer_id and not universo:
        # A conta existe, mas o inventário não conhece campanha nenhuma dela.
        # Isso NÃO é "a conta está vazia": é "esta conta nunca foi varrida", ou
        # "a varredura dela não chegou aqui". Sem nada com que comparar, não há
        # prova — e liberar a montagem com base numa lista vazia é afirmar
        # ausência a partir de silêncio.
        faltando.append({
            "regra": "varredura_da_conta",
            "motivo": ("o inventário não conhece nenhuma campanha desta conta; "
                       "ela pode nunca ter sido varrida"),
            "impede_prova": True,
        })
    if not funil.destinos():
        faltando.append({
            "regra": REGRA_URL_DA_CONTA,
            "motivo": ("este funil não tem URL publicada comparável — o "
                       "WordPress devolveu um permalink de rascunho, que muda "
                       "quando a página for publicada"),
            "impede_prova": True,
        })
    elif universo and not any(destino_comparavel(c.url_final) for c in universo):
        # ⚠️ O motivo não pode AFIRMAR uma comparação que talvez não tenha
        # acontecido. Se nenhuma campanha tem URL no nome — porque foram criadas
        # à mão, fora da taxonomia —, nada foi comparado por URL, e dizer "a
        # comparação usou a URL do nome" seria descrever um trabalho que não
        # houve. É a mesma classe de defeito que `sem_campanha` sem ressalva:
        # relatar prova onde só houve silêncio.
        pelo_nome = sum(1 for c in universo if url_no_nome(c.nome))
        if pelo_nome:
            faltando.append({
                "regra": REGRA_URL_DA_CONTA,
                "motivo": (f"nenhuma campanha desta conta tem URL de destino "
                           f"lida ainda; {pelo_nome} de {len(universo)} foram "
                           f"comparadas pela URL declarada no nome, que é sinal "
                           f"médio"),
                "impede_prova": False,
            })
        else:
            # Nem observada, nem declarada: não houve comparação por URL
            # nenhuma. Isso IMPEDE a prova — e é o caso de uma conta cujas
            # campanhas nasceram fora da taxonomia.
            faltando.append({
                "regra": REGRA_URL_DA_CONTA,
                "motivo": ("nenhuma campanha desta conta tem URL de destino — "
                           "nem lida do anúncio, nem declarada no nome. Não "
                           "houve comparação por URL"),
                "impede_prova": True,
            })
    if not funil.campaign_lineage_id:
        faltando.append({
            "regra": REGRA_LINHAGEM,
            # Nenhuma campanha tem linhagem hoje. Marcar isto como impedimento
            # poria ressalva em 100% dos cartões no primeiro dia.
            "motivo": "este funil não tem linhagem declarada",
            "impede_prova": False,
        })

    return tuple(faltando)


def reconciliar(funil: Funil,
                universo: Sequence[CampanhaConhecida],
                *,
                legado_por_run: Optional[Dict[int, set]] = None) -> Reconciliacao:
    """O veredito para UM funil, contra as campanhas conhecidas da conta dele.

    ## A escada, e por que ela tem esta ordem

    1. **Vínculo humano vivo** vence tudo. Alguém já respondeu esta pergunta, e
       reabri-la a cada carregamento transformaria uma decisão registrada em
       sugestão perpétua.
    2. **Mais de uma candidata presente** é conflito. Escolher em silêncio seria
       vincular à campanha errada com toda a confiança.
    3. **Uma candidata presente** é correspondência provável. Não vira vínculo
       sozinha: a confirmação é humana e auditável (ADR-09).
    4. **Só candidatas históricas** é `somente_historico`. Relançar continua
       legítimo, com motivo declarado.
    5. **Nenhuma candidata** é `sem_campanha` — e só aqui a montagem abre.

    ## Histórico não conta para conflito

    A FGTS tem TRÊS campanhas na conta: duas removidas e uma ligada. Contá-las
    todas daria conflito, e conflito bloquearia o operador por causa da própria
    história de relançamento — que aconteceu cinco vezes, com motivo declarado
    (E-05). O que disputa o mesmo leilão é o que está no ar; o que foi removido
    não disputa nada.
    """
    legado = legado_por_run or {}

    # A conta do projeto é PRÉ-REQUISITO, não sinal (ADR-03): sem ela não há
    # onde procurar, e comparar URL entre contas diferentes casaria a campanha
    # de um cliente com o funil de outro.
    if funil.customer_id:
        no_escopo = [c for c in universo if c.customer_id == funil.customer_id]
    else:
        no_escopo = []

    candidatas: List[Candidata] = []
    for campanha in no_escopo:
        sinais = _sinais_da_campanha(funil, campanha, legado)
        if sinais:
            candidatas.append(Candidata(campanha=campanha, sinais=sinais))

    # Ordem estável: presentes antes de históricas, depois por identidade. Sem
    # ela, duas leituras iguais devolveriam a mesma lista em ordens diferentes e
    # a tela pareceria ter mudado de resposta.
    candidatas.sort(key=lambda c: (c.campanha.historico,
                                   c.campanha.volc_campaign_id))

    ausentes = _ausentes(funil, candidatas, no_escopo)
    presentes = [c for c in candidatas if c.presente]

    vinculada = next(
        (c for c in presentes
         if c.campanha.vinculo_id
         and (c.campanha.vinculo_opportunity_id == funil.opportunity_id
              or (funil.run_id is not None
                  and c.campanha.vinculo_run_id == funil.run_id))),
        None)

    if vinculada is not None:
        estado, acao = VINCULADA, ABRIR_O_QUE_EXISTE
        pode_montar, pode_relancar, confirmar = False, False, False
    elif len(presentes) > 1:
        estado, acao = CONFLITO, ABRIR_REVISAO
        pode_montar, pode_relancar, confirmar = False, False, True
    elif len(presentes) == 1:
        estado, acao = CORRESPONDENCIA_PROVAVEL, CONFIRMAR_VINCULO
        pode_montar, pode_relancar, confirmar = False, False, True
    elif candidatas:
        estado, acao = SOMENTE_HISTORICO, RELANCAR_DECLARADO
        pode_montar, pode_relancar, confirmar = False, True, True
    else:
        estado, acao = SEM_CAMPANHA, MONTAR
        # ⚠️ Montar continua liberado, e isso é deliberado: quase todo funil
        # NOVO começa em rascunho, e bloquear aqui bloquearia o trabalho
        # legítimo — que é o jeito de a prova virar obstáculo e o operador
        # aprender a contorná-la.
        #
        # O que muda é a CONFIRMAÇÃO. Quando nenhuma regra pôde comparar, a
        # conclusão não é "provei e não há": é "não tive como provar". A
        # diferença viaja como `exige_confirmacao_humana`, e é o que permite à
        # tela avisar em vez de convidar.
        impedida = any(s.get("impede_prova") for s in ausentes)
        pode_montar, pode_relancar, confirmar = True, False, impedida

    return Reconciliacao(
        opportunity_id=funil.opportunity_id,
        run_id=funil.run_id,
        estado=estado,
        candidatas=tuple(candidatas),
        sinais_ausentes=ausentes,
        acao_permitida=acao,
        exige_confirmacao_humana=confirmar,
        pode_montar=pode_montar,
        pode_relancar=pode_relancar,
    )


def chave_do_funil(opportunity_id: Any,
                   run_id: Any) -> Tuple[int, Optional[int]]:
    """A chave de um funil no quadro: `(oportunidade, run)`.

    ⚠️ **Não é só a oportunidade.** Uma oportunidade pode ter mais de um run —
    é o caso normal quando o funil é reprocessado —, e os dois aparecem como
    cartões separados no quadro, com URLs diferentes.

    Chaveando só pela oportunidade, o segundo run sobrescreve o primeiro no
    dicionário e os dois cartões passam a exibir o MESMO veredito. Um deles
    receberia a resposta do outro: "sem campanha, pode montar" para um funil que
    tem campanha no ar, ou o contrário. Nada na tela denunciaria — os dois
    cartões pareceriam coerentes.
    """
    return (int(opportunity_id),
            int(run_id) if run_id is not None else None)


def reconciliar_muitos(
        funis: Iterable[Funil],
        universo: Sequence[CampanhaConhecida],
        *,
        legado_por_run: Optional[Dict[int, set]] = None,
) -> Dict[Tuple[int, Optional[int]], Reconciliacao]:
    """O veredito de vários funis contra o MESMO universo, lido uma vez só.

    Consultar por cartão custaria N idas ao banco numa tela que existe para ser
    rápida — e foi assim que o quadro passou a ter uma consulta escondida por
    linha antes de alguém somar.

    A chave é `(opportunity_id, run_id)`: ver `chave_do_funil`.
    """
    return {chave_do_funil(f.opportunity_id, f.run_id):
            reconciliar(f, universo, legado_por_run=legado_por_run)
            for f in funis}


# ═══════════════════════════════════════════════════════════════════════════
# O SENTIDO INVERSO — a campanha pergunta de quem ela é
# ═══════════════════════════════════════════════════════════════════════════
#
# Tudo acima responde "este FUNIL já tem campanha?", que é a pergunta do quadro
# de Oportunidades: quem chega ali quer saber se pode montar.
#
# O inventário faz a pergunta oposta. O operador está olhando uma campanha que a
# varredura encontrou na conta — a Maquininha, a FGTS — e o que ele precisa
# decidir é **de quem ela é**. Medido em 27/08/2026: as duas estão ENABLED,
# `procedencia: descoberta`, e `trafego_vinculo` tem zero linhas.
#
# ⚠️ Isto NÃO é um segundo motor de casamento. As regras, as forças e a
# normalização de URL são as mesmas de `_sinais_da_campanha` — o que muda é o
# lado por onde se entra e, principalmente, QUAL É O VEREDITO.
#
# O veredito do funil não serve à campanha. `conflito` ali significa "duas
# campanhas disputam este funil"; visto da campanha, o fato relevante é o
# oposto — "este funil também é disputado por outra campanha", que é uma
# ressalva, não o estado dela. Copiar o estado do funil para a campanha faria a
# tela dizer que a Maquininha está em conflito quando quem está é o funil.

#: Já existe decisão humana registrada. Nada a revisar.
ASSOCIADA = "associada"
#: Nenhum funil casou. Não é erro, e não é "campanha órfã": é o estado normal de
#: toda campanha que a varredura descobre antes de alguém responder.
SEM_CORRESPONDENCIA = "sem_correspondencia"
#: Um funil casou. É a pergunta que o operador pode responder com um clique — e
#: continua sendo pergunta, nunca vínculo (ADR-09).
CORRESPONDENCIA_UNICA = "correspondencia_unica"
#: Mais de um funil casou. A escolha é do operador, e escolher em silêncio aqui
#: vincularia receita ao funil errado.
MAIS_DE_UMA = "mais_de_uma_correspondencia"
#: Não houve como comparar. Distinto de `sem_correspondencia` pelo mesmo motivo
#: que `_ausentes` existe: "provei e não há" libera, "não consegui provar" não.
NAO_APURADA = "nao_apurada"

ESTADOS_DE_CORRESPONDENCIA: Tuple[str, ...] = (
    ASSOCIADA, SEM_CORRESPONDENCIA, CORRESPONDENCIA_UNICA, MAIS_DE_UMA,
    NAO_APURADA,
)


@dataclass(frozen=True)
class Correspondencia:
    """Um funil que casa com ESTA campanha, e tudo o que sustenta o casamento."""

    opportunity_id: int
    run_id: Optional[int]
    project_id: Optional[int]
    #: As URLs deste funil, normalizadas — o que o operador compara com o olho.
    destinos: Tuple[str, ...]
    sinais: Tuple[Sinal, ...]
    #: O veredito do FUNIL, dito como ressalva e não como estado da campanha.
    #: `conflito` aqui significa que outra campanha presente também aponta para
    #: este funil — e é isso que o operador precisa ver antes de confirmar.
    estado_do_funil: str
    #: Quantas OUTRAS campanhas presentes disputam este mesmo funil.
    outras_campanhas_presentes: int

    @property
    def forca_maxima(self) -> str:
        """A força do sinal mais forte. `historica` quando só há histórico.

        ⚠️ Ordem de precedência explícita, e não `max()` sobre a string: por
        acaso alfabético `medio` > `historica` > `forte`, e ordenar sinal de
        confiança por acidente de alfabeto é como uma evidência fraca passa a
        ser apresentada como a mais forte.
        """
        ordem = {FORTE: 3, MEDIO: 2, HISTORICA: 1}
        return max(self.sinais, key=lambda s: ordem.get(s.forca, 0)).forca

    def json(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "destinos": list(self.destinos),
            "sinais": [s.json() for s in self.sinais],
            "estado_do_funil": self.estado_do_funil,
            "outras_campanhas_presentes": self.outras_campanhas_presentes,
            "forca_maxima": self.forca_maxima,
        }


@dataclass(frozen=True)
class RevisaoDeCorrespondencia:
    """O que a tela de revisão precisa mostrar sobre UMA campanha."""

    volc_campaign_id: str
    estado: str
    correspondencias: Tuple[Correspondencia, ...]
    #: Por que não deu para comparar, quando não deu. Mesmo contrato de
    #: `Reconciliacao.sinais_ausentes`.
    sinais_ausentes: Tuple[Dict[str, Any], ...]
    #: A URL que o anúncio desta campanha aponta, normalizada. É o que o
    #: operador compara com o olho contra `Correspondencia.destinos` — e a
    #: projeção do inventário não a carrega, porque a listagem não compara URL.
    url_da_campanha: Optional[str] = None
    #: O vínculo vivo, quando já existe. É o que permite à tela oferecer
    #: desfazer em vez de confirmar.
    vinculo_id: Optional[str] = None
    vinculo_opportunity_id: Optional[int] = None
    vinculo_run_id: Optional[int] = None

    @property
    def exige_confirmacao_humana(self) -> bool:
        """Sempre que houver algo a confirmar. Nunca automático (ADR-09)."""
        return self.estado in (CORRESPONDENCIA_UNICA, MAIS_DE_UMA)

    def json(self) -> Dict[str, Any]:
        return {
            "volc_campaign_id": self.volc_campaign_id,
            "estado": self.estado,
            "url_da_campanha": self.url_da_campanha,
            "correspondencias": [c.json() for c in self.correspondencias],
            "sinais_ausentes": [dict(s) for s in self.sinais_ausentes],
            "vinculo": (None if not self.vinculo_id else {
                "vinculo_id": self.vinculo_id,
                "opportunity_id": self.vinculo_opportunity_id,
                "run_id": self.vinculo_run_id,
            }),
            "exige_confirmacao_humana": self.exige_confirmacao_humana,
        }


def correspondencias_da_campanha(
        alvo: CampanhaConhecida,
        funis: Sequence[Funil],
        universo: Sequence[CampanhaConhecida],
        *,
        legado_por_run: Optional[Dict[int, set]] = None,
) -> RevisaoDeCorrespondencia:
    """De quem é esta campanha? — com as MESMAS regras do sentido direto.

    A implementação roda `reconciliar` para cada funil contra o universo inteiro
    e recolhe os vereditos em que `alvo` aparece como candidata. Rodar contra o
    universo inteiro, e não só contra `alvo`, é o que preserva a informação de
    disputa: sem as outras campanhas, um funil que duas campanhas reivindicam
    pareceria exclusivo desta.

    ⚠️ `universo` PRECISA conter `alvo`. Se não contiver, a resposta seria
    `sem_correspondencia` — indistinguível de "comparei e nada casou", e o
    operador leria como prova o que foi um erro de montagem do chamador.
    """
    if not any(c.volc_campaign_id == alvo.volc_campaign_id for c in universo):
        raise ValueError(
            "a campanha alvo não está no universo comparado; a resposta seria "
            "'sem correspondência' por ausência de dado, e não por prova.")

    # Vínculo humano vivo encerra a pergunta. Reabri-la a cada carregamento
    # transformaria uma decisão registrada em sugestão perpétua — a mesma razão
    # pela qual `reconciliar` põe `vinculada` no topo da escada.
    if alvo.vinculo_id:
        return RevisaoDeCorrespondencia(
            volc_campaign_id=alvo.volc_campaign_id,
            estado=ASSOCIADA,
            url_da_campanha=destino_comparavel(alvo.url_final),
            correspondencias=(),
            sinais_ausentes=(),
            vinculo_id=alvo.vinculo_id,
            vinculo_opportunity_id=alvo.vinculo_opportunity_id,
            vinculo_run_id=alvo.vinculo_run_id,
        )

    # Sem conta na campanha não há como comparar: a conta é pré-requisito da
    # prova (ADR-03), e comparar URL entre contas casaria a campanha de um
    # cliente com o funil de outro.
    if not alvo.customer_id:
        return RevisaoDeCorrespondencia(
            volc_campaign_id=alvo.volc_campaign_id,
            estado=NAO_APURADA,
            url_da_campanha=destino_comparavel(alvo.url_final),
            correspondencias=(),
            sinais_ausentes=({
                "regra": "conta_da_campanha",
                "motivo": ("esta campanha não tem conta de anúncio "
                           "identificada; sem conta não há onde procurar"),
                "impede_prova": True,
            },),
        )

    # ⚠️ NÃO HAVER FUNIL É NÃO TER O QUE COMPARAR, e não "comparei e não achei".
    #
    # Medido em 27/08/2026: `projects` tem 2 linhas e só uma declara conta de
    # anúncio. Das 84 campanhas do inventário, **79** estão em contas sem
    # projeto — para elas o chamador devolve zero funis, e a versão anterior
    # respondia `sem_correspondencia` com `sinais_ausentes` vazio. A tela então
    # dizia "não associada ao VOLC · nada precisa ser feito agora" para 79
    # campanhas sobre as quais nenhuma comparação foi feita.
    #
    # É exatamente a distinção que `NAO_APURADA` existe para preservar.
    if not funis:
        return RevisaoDeCorrespondencia(
            volc_campaign_id=alvo.volc_campaign_id,
            estado=NAO_APURADA,
            correspondencias=(),
            sinais_ausentes=({
                "regra": "funil_publicado_na_conta",
                "motivo": ("não há funil publicado ligado a esta conta de "
                           "anúncio; sem funil não há com o que comparar"),
                "impede_prova": True,
            },),
            url_da_campanha=destino_comparavel(alvo.url_final),
        )

    achados: List[Correspondencia] = []
    ausentes: List[Dict[str, Any]] = []
    vistas: set = set()
    #: Quantos funis puderam de fato ser comparados com esta campanha.
    #:
    #: ⚠️ A conta é por FUNIL, e não um "algum `impede_prova` em qualquer
    #: lugar". Um único funil em rascunho — o WordPress devolve permalink
    #: provisório e `_ausentes` marca `impede_prova` — não pode invalidar a
    #: comparação contra os outros dois que tinham URL publicada. Agregar por
    #: cima faria a resposta virar "não consegui provar" sempre que existisse
    #: um rascunho na conta, que é o estado normal de quem está escrevendo.
    comparaveis = 0

    for funil in funis:
        veredito = reconciliar(funil, universo, legado_por_run=legado_por_run)
        minha = next((c for c in veredito.candidatas
                      if c.campanha.volc_campaign_id == alvo.volc_campaign_id),
                     None)

        # ⚠️ As ausências são colhidas SEMPRE, e não só quando a campanha casou.
        #
        # Colhê-las dentro do ramo do casamento fazia a lista ficar vazia
        # justamente no caso em que ela importa: quando nada casou, o operador
        # precisa saber se a prova pôde ser feita. "Provei e não há" libera ele
        # a tratar a campanha como órfã; "não consegui provar" não.
        if not any(s.get("impede_prova") for s in veredito.sinais_ausentes):
            comparaveis += 1

        for s in veredito.sinais_ausentes:
            chave = (s.get("regra"), s.get("motivo"))
            if chave not in vistas:
                vistas.add(chave)
                ausentes.append(dict(s))

        if minha is None:
            continue
        outras = sum(1 for c in veredito.candidatas
                     if c.presente
                     and c.campanha.volc_campaign_id != alvo.volc_campaign_id)
        achados.append(Correspondencia(
            opportunity_id=funil.opportunity_id,
            run_id=funil.run_id,
            project_id=funil.project_id,
            destinos=funil.destinos(),
            sinais=minha.sinais,
            estado_do_funil=veredito.estado,
            outras_campanhas_presentes=outras,
        ))
    # Ordem estável: sinal mais forte primeiro, depois pela identidade do funil.
    # Sem isso, duas leituras iguais mostrariam candidatos em ordens diferentes
    # e a tela pareceria ter mudado de opinião entre dois cliques.
    ordem = {FORTE: 0, MEDIO: 1, HISTORICA: 2}
    achados.sort(key=lambda c: (ordem.get(c.forca_maxima, 9),
                                c.opportunity_id,
                                c.run_id if c.run_id is not None else -1))

    if not achados:
        # Sem candidato, o estado depende de ALGUMA comparação ter sido
        # possível. Nenhuma comparação possível é "não consegui provar", que
        # não libera o operador a tratar a campanha como órfã; ao menos uma é
        # "comparei e não achei", que libera. As ausências continuam viajando
        # nos dois casos, para o operador ver o que ficou de fora.
        estado = SEM_CORRESPONDENCIA if comparaveis > 0 else NAO_APURADA
    elif len(achados) == 1:
        estado = CORRESPONDENCIA_UNICA
    else:
        estado = MAIS_DE_UMA

    return RevisaoDeCorrespondencia(
        volc_campaign_id=alvo.volc_campaign_id,
        estado=estado,
        url_da_campanha=destino_comparavel(alvo.url_final),
        correspondencias=tuple(achados),
        sinais_ausentes=tuple(ausentes),
    )
