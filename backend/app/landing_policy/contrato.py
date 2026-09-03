"""O contrato do DESTINO PAGO — o que uma página precisa provar antes de receber
clique comprado.

## Por que isto não é o `volc_ads/policy`

`volc_ads/policy/spec.py` é a política do **anúncio**: headline, description,
sitelink, `http_ok` do destino e habilitação por país/vertical. Ela olha o texto
que o Google revisa no leilão.

Este módulo é a política do **destino**: identidade do operador, classes de link
de saída, formulário e dado sensível, alegação financeira e divulgação,
implicação de vínculo governamental, originalidade/ponte, e — só ao vivo —
redirecionamento, cloaking e deriva. São superfícies diferentes, revisadas por
processos diferentes do Google, e uma não substitui a outra. Não há regra
duplicada entre os dois: o que é do anúncio fica lá, o que é da página fica aqui.

## Por que papel explícito, e não "LP"

O motor de funil já tem papéis editoriais (`LP`/`PRESELL`/`SOLUTION` em
`funnelforge.domain.models`). Eles descrevem a POSIÇÃO da página no funil — não
dizem se ela recebe clique pago. Uma `LP` pode nunca ter campanha; um artigo
orgânico pode virar destino de campanha amanhã. Foi essa ambiguidade que deixou
o destino pago ser avaliado pelas mesmas regras de um artigo editorial.

Aqui o papel é declarado, não derivado do slug:

    paid_destination    recebe clique comprado do Google Ads — regra mais dura
    editorial_solution  página interior do funil, sem clique comprado direto
    presell             pré-venda interior, sem clique comprado direto
    organic_article     artigo orgânico do portal
    conversion_page     página que COLETA dado do visitante (form, lead, cadastro)

## A regra que decide tudo: FECHA POR AUSÊNCIA

Para `paid_destination`, verificação que não pôde ser feita **não passa**. Ela
vira `desconhecido`, e desconhecido nunca fica verde. É o oposto do reflexo
natural do software ("não achei problema → aprovado"), e é deliberado: quem paga
o preço do falso verde é a conta inteira, suspensa sem aviso prévio.

Fonte da severidade de cada regra: `fontes_politica.json`, ao lado deste arquivo.
Regra sem fonte oficial do Google não entra — mesma doutrina do `volc_ads/policy`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# ── vocabulário de evidência ────────────────────────────────────────────────
#
# Idêntico ao do `publisher_quality.snapshot` de propósito: os dois artefatos
# são lidos pela mesma operação, e dois vocabulários de "não sei" seriam dois
# jeitos de esconder a mesma ausência.
STATUS_OBSERVADO = "observed"
STATUS_AUSENCIA_CONFIRMADA = "absent_confirmed"
STATUS_INDISPONIVEL = "unavailable"
STATUS_NAO_APLICAVEL = "not_applicable"
STATUS_FALHOU = "failed"

STATUSES = {
    STATUS_OBSERVADO,
    STATUS_AUSENCIA_CONFIRMADA,
    STATUS_INDISPONIVEL,
    STATUS_NAO_APLICAVEL,
    STATUS_FALHOU,
}

#: Status que contam como "a verificação aconteceu". Qualquer outro em uma
#: verificação EXIGIDA vira `desconhecido` — e desconhecido reprova.
STATUS_CONCLUSIVOS = {STATUS_OBSERVADO, STATUS_AUSENCIA_CONFIRMADA, STATUS_NAO_APLICAVEL}

SEVERIDADE_BLOQUEIO = "blocker"
SEVERIDADE_RISCO = "risk"
SEVERIDADE_OBSERVACAO = "observation"

SCHEMA_VERSION = "landing_policy_gate_receipt.v2"

#: A versão do CONTRATO — a FORMA da avaliação: quais verificações existem, o que
#: cada papel exige, em que ponto de portão. É diferente de `versao_da_fonte()`,
#: que é o hash do TEXTO das regras (`fontes_politica.json`).
#:
#: As duas mudam por motivos diferentes, e um recibo precisa das duas. Alguém pode
#: corrigir a redação de uma regra sem mudar a forma do contrato (muda só a fonte);
#: e alguém pode acrescentar uma verificação exigida sem tocar em regra nenhuma
#: (muda só o contrato). Um recibo que carregasse apenas uma das duas pareceria
#: reaproveitável depois de uma mudança que o invalidou.
POLICY_CONTRACT_VERSION = "paid_destination_policy_spine.v2"

#: Por quanto tempo uma observação AO VIVO continua valendo como prova de que o
#: destino está apto. Não é burocracia: uma página no ar muda sem avisar — plugin,
#: tema, rotação de anúncio, edição manual no WordPress — e um recibo de duas
#: semanas descreve um conteúdo que pode não existir mais.
#:
#: 24 h é o padrão porque a operação sobe campanha no mesmo dia em que aprova a
#: página. Quem precisar de outra janela passa `janela_de_frescor_s`; o que não
#: existe é a opção de não ter janela.
JANELA_DE_FRESCOR_PADRAO_S = 24 * 60 * 60

#: Teto de saltos de redirecionamento até a URL final. Zero salto é o normal de um
#: destino canônico; um salto (http→https, com/sem barra) é rotina de servidor.
#: Acima disso a cadeia começa a ser o assunto, e não o detalhe.
TETO_DE_SALTOS_PADRAO = 2

#: Carimbo determinístico para artefato gerado a partir de arquivo local, onde
#: "quando eu li" não é informação — é ruído que quebra a comparação byte a byte.
CARIMBO_DETERMINISTICO = "1970-01-01T00:00:00Z"


class PapelDestino(str, Enum):
    """O papel DECLARADO da página. Não é derivado do slug — ver docstring."""

    PAID_DESTINATION = "paid_destination"
    EDITORIAL_SOLUTION = "editorial_solution"
    PRESELL = "presell"
    ORGANIC_ARTICLE = "organic_article"
    CONVERSION_PAGE = "conversion_page"


class PontoDePortao(str, Enum):
    """Onde o portão roda. Muda o que é EXIGÍVEL, não o que é proibido.

    Antes da publicação não existe redirecionamento nem cloaking para observar —
    exigi-los ali seria reprovar toda página por uma ausência estrutural. Depois
    de no ar, não observá-los é justamente o buraco.
    """

    ARTEFATO_DE_GERACAO = "generation_artifact"
    PRE_PUBLICACAO_WORDPRESS = "pre_publication_wordpress"
    ELEGIBILIDADE_DESTINO_CAMPANHA = "campaign_destination_eligibility"


class Veredito(str, Enum):
    APROVADO = "approved"
    APROVADO_COM_RESSALVAS = "approved_with_notes"
    BLOQUEADO = "blocked"
    INDETERMINADO = "indeterminate"


@dataclass(frozen=True)
class Achado:
    """Um defeito observado, com a evidência que o sustenta.

    `evidencia` é sempre estrutural (contagem, host, trecho curto) — nunca o
    corpo inteiro da página, que tornaria o recibo um coletor de conteúdo.
    """

    codigo: str
    mensagem: str
    severidade: str = SEVERIDADE_RISCO
    evidencia: Any = None

    def para_json(self) -> dict[str, Any]:
        saida: dict[str, Any] = {
            "code": self.codigo,
            "severity": self.severidade,
            "message": self.mensagem,
        }
        if self.evidencia is not None:
            saida["evidence"] = self.evidencia
        return saida


@dataclass
class Verificacao:
    """O resultado de UMA verificação: o que foi olhado, com que desfecho.

    O `status` é tão importante quanto os achados. Uma verificação sem achados e
    com status `unavailable` significa "não consegui olhar" — e é exatamente
    isso que o portão precisa distinguir de "olhei e está limpo".
    """

    nome: str
    status: str
    achados: list[Achado] = field(default_factory=list)
    inventario: list[dict[str, Any]] = field(default_factory=list)
    detalhe: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status desconhecido em {self.nome!r}: {self.status!r}")

    @property
    def conclusiva(self) -> bool:
        return self.status in STATUS_CONCLUSIVOS

    def hash_inventario(self) -> str:
        return impressao(self.inventario)


def impressao(valor: Any) -> str:
    """SHA-256 do JSON canônico de `valor`.

    É o que permite ao recibo provar QUAL inventário foi avaliado sem carregar o
    inventário inteiro para dentro dele — e permite comparar duas avaliações da
    mesma página sem difundir 170 KB de HTML.
    """
    bruto = json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


# ── as verificações, por nome ───────────────────────────────────────────────
#
# Os nomes são o vocabulário compartilhado entre `varredura`, `portao`, `recibo`
# e os testes. Mudar um nome aqui quebra o recibo de propósito: um recibo antigo
# não deve parecer compatível com um portão que mudou de forma.
V_IDENTIDADE = "identity"
V_LINKS_EXTERNOS = "external_links"
V_FORMULARIOS = "forms_and_sensitive_data"
V_ALEGACOES = "claims_and_disclosures"
V_GOVERNO = "government_services"
V_CONTEUDO = "content_originality_and_congruence"
V_SEGURANCA = "destination_security_signals"
V_REDIRECIONAMENTO = "redirect_and_cloaking"
V_DERIVA = "live_drift"
#: A décima verificação, e a única que não olha a PÁGINA: ela olha o RECIBO.
#:
#: Ela existe porque "o conteúdo no ar é o aprovado?" pressupõe que exista um
#: aprovado. Sem recibo resolvível, `live_drift` responde `unavailable` e a
#: operação lê "não deu para comparar" — verdade, mas insuficiente: o problema
#: não é a comparação, é a ausência de aprovação. São dois defeitos diferentes e
#: a operação precisa de nomes diferentes para consertar o certo.
V_RECIBO = "approval_receipt"

TODAS_AS_VERIFICACOES = (
    V_IDENTIDADE,
    V_LINKS_EXTERNOS,
    V_FORMULARIOS,
    V_ALEGACOES,
    V_GOVERNO,
    V_CONTEUDO,
    V_SEGURANCA,
    V_REDIRECIONAMENTO,
    V_DERIVA,
    V_RECIBO,
)

#: O que precisa ter sido CONCLUSIVAMENTE verificado em cada ponto de portão,
#: para o papel `paid_destination`. Fora dessa lista a verificação ainda roda e
#: ainda produz achados — ela só não transforma "não deu para olhar" em reprova.
#: As verificações que, NO PONTO DE CAMPANHA, não podem sair `not_applicable`.
#:
#: ⚠️ ESTA TABELA EXISTE POR CAUSA DE UM FALSO VERDE MEDIDO.
#:
#: `not_applicable` está em `STATUS_CONCLUSIVOS` — e deve estar: antes de
#: publicar, redirecionamento e deriva realmente não existem, e chamá-los de
#: "não sei" seria reprovar toda página por uma impossibilidade estrutural.
#:
#: Mas `varrer_deriva` e `varrer_recibo` devolvem `not_applicable` quando não há
#: HTML ao vivo observado — e no ponto de CAMPANHA isso não é "não se aplica",
#: é "ninguém leu a página". Medido: com evidência de redirecionamento completa
#: e nenhuma leitura ao vivo, o portão de campanha devolvia
#: `paid_destination_ready=True` sem ter comparado hash aprovado nem conferido
#: recibo. O verde saía de duas ausências.
#:
#: Uma página que está no ar SEMPRE tem hash observável. `not_applicable` aqui
#: é impossível de boa-fé, e por isso vira desconhecido.
NAO_APLICAVEL_E_DESCONHECIDO_EM: dict[PontoDePortao, frozenset[str]] = {}

EXIGENCIAS_POR_PONTO: dict[PontoDePortao, frozenset[str]] = {
    # Antes de existir no ar: só o que o artefato consegue provar sobre si.
    PontoDePortao.ARTEFATO_DE_GERACAO: frozenset(
        {V_IDENTIDADE, V_LINKS_EXTERNOS, V_FORMULARIOS, V_ALEGACOES, V_GOVERNO, V_CONTEUDO}
    ),
    PontoDePortao.PRE_PUBLICACAO_WORDPRESS: frozenset(
        {V_IDENTIDADE, V_LINKS_EXTERNOS, V_FORMULARIOS, V_ALEGACOES, V_GOVERNO, V_CONTEUDO}
    ),
    # No ar, com campanha apontando: aqui redirecionamento, cloaking, deriva e o
    # RECIBO DE APROVAÇÃO deixam de ser inobserváveis. Não olhar vira o buraco.
    #
    # O recibo entra aqui e não nos dois pontos anteriores porque antes de
    # publicar não existe aprovação anterior para conferir — exigi-la ali
    # reprovaria toda página primeira por uma impossibilidade estrutural, que é
    # o mesmo erro que a tabela inteira existe para não cometer.
    PontoDePortao.ELEGIBILIDADE_DESTINO_CAMPANHA: frozenset(TODAS_AS_VERIFICACOES),
}

NAO_APLICAVEL_E_DESCONHECIDO_EM[PontoDePortao.ELEGIBILIDADE_DESTINO_CAMPANHA] = frozenset(
    # `V_IDENTIDADE` entra aqui por causa de `PaginaObservada.documento_parcial`:
    # ele deixa a identidade sair `not_applicable` antes da publicação, onde o
    # rodapé do tema ainda não existe. Numa leitura AO VIVO a página inteira
    # está no ar — "não se aplica" ali seria a mesma isenção, aplicada ao ponto
    # em que ela não tem desculpa.
    {V_DERIVA, V_IDENTIDADE, V_RECIBO, V_REDIRECIONAMENTO}
)


# ── severidade por papel ────────────────────────────────────────────────────
#
# O mesmo defeito não pesa o mesmo em toda página. Um artigo orgânico sem CNPJ
# no rodapé é um problema editorial; um DESTINO PAGO sem identidade do operador
# é a assinatura literal do que a política de `unacceptable business practices`
# descreve. A tabela abaixo é essa diferença, escrita uma vez.

#: Códigos que reprovam `paid_destination` e `conversion_page`, e viram risco
#: nos demais papéis.
_BLOQUEIA_NO_PAGO = frozenset({
    "IDENTIDADE_OPERADOR_AUSENTE",
    "IDENTIDADE_CONTATO_AUSENTE",
    "IDENTIDADE_CNPJ_DIVERGENTE",
    "IDENTIDADE_CREDENCIAL_NAO_COMPROVADA",
    "AFILIACAO_GOVERNAMENTAL_IMPLICITA",
    "AVISO_NAO_OFICIAL_AUSENTE",
    "LINK_GOVERNO_COM_ANCORA_DE_VALOR",
    "MARCA_GOVERNAMENTAL_COM_DESTINO_DIVERGENTE",
    "SERVICO_GOVERNAMENTAL_RESTRITO",
    "LINK_EXTERNO_NAO_CLASSIFICADO",
    "BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO",
    "MARCA_TERCEIRA_SEM_LASTRO",
    "CAMPO_CREDENCIAL_OBSERVADO",
    "FORMULARIO_DADO_SENSIVEL",
    "ALEGACAO_DE_RESULTADO_IMPROVAVEL",
    "ALEGACAO_FINANCEIRA_SEM_DIVULGACAO",
    "CONTEUDO_ORIGINAL_INSUFICIENTE",
    "PAGINA_PONTE",
    "DESTINO_INCONGRUENTE_COM_ANUNCIO",
    "REDIRECIONAMENTO_CROSS_DOMAIN",
    "DIVERGENCIA_RASTREADOR_USUARIO",
    "DERIVA_AO_VIVO",
    "CONTEUDO_MISTO",
    "SCRIPT_TERCEIRO_NAO_DECLARADO",
    "SCRIPT_REDIRECIONA_CLIENT_SIDE",
    # ── a espinha v2 ────────────────────────────────────────────────────────
    #
    # ⚠️ POLÍTICA INTERNA DO VOLC, MAIS RESTRITIVA QUE A DO GOOGLE.
    # O Google não proíbe hyperlink externo em destino pago; ele proíbe sugerir
    # vínculo e proíbe a página-ponte. Banir TODO hyperlink externo clicável no
    # `paid_destination` é decisão da casa, tomada depois que sete links
    # `caixa.gov.br` de âncora numérica foram ao ar na URL que a conta suspensa
    # anunciava. A regra anterior só barrava host NÃO CLASSIFICADO — governo com
    # âncora descritiva e fonte de pesquisa declarada passavam em silêncio.
    "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO",
    # O H1 é a promessa que o anúncio compra, e é lido antes de qualquer rodapé.
    # O aviso de não-vínculo no pé não desfaz uma manchete que diz que o governo
    # liberou algo.
    "TITULO_SUGERE_ORIGEM_OFICIAL",
    # Os três do recibo. Sem eles, "apto" é uma frase sem data e sem versão.
    "RECIBO_DE_APROVACAO_AUSENTE",
    "RECIBO_DE_APROVACAO_VENCIDO",
    "RECIBO_DE_POLITICA_DESATUALIZADO",
    # ⚠️ OS DOIS ABAIXO SAÍRAM DA REVISÃO ADVERSARIAL CRUZADA, e os dois eram
    # verde medido. A v2 conferia a METADATA do recibo — versão e frescor — e
    # não lia nem o veredito dele nem a que conteúdo ele se referia. Então um
    # recibo que dizia `paid_destination_ready: false`, e um recibo de OUTRA
    # página, satisfaziam a verificação `approval_receipt` do mesmo jeito.
    "RECIBO_NAO_APROVA_O_DESTINO",
    "RECIBO_DE_OUTRO_CONTEUDO",
    # `status_http` era coletado e não entrava em decisão nenhuma. Um destino
    # que devolve 404 ao revisor é o caso literal de "destinations that don't
    # work" — e `volc_ads/policy/spec.py::checar_destino` modelava exatamente
    # isto sem nunca ser chamado, "por falta de um status HTTP que ninguém
    # coleta". A barreira 3 passou a coletar.
    "DESTINO_NAO_RESPONDE",
    "CADEIA_DE_REDIRECIONAMENTO_EXCESSIVA",
    # ── promovidos de `_RISCO_SEMPRE` na v2, por contraprova ────────────────
    #
    # Os três já eram DETECTADOS; nenhum reprovava, em papel nenhum. O contrato
    # v1 tratava-os como sinal. A v2 os trata como bloqueio no papel estrito, e
    # continua tratando-os como risco no papel frouxo — o achado não some do
    # artigo orgânico, ele muda de peso, como toda a tabela.
    #
    # `VALOR_MONETARIO_MALFORMADO`: "2900.00 R$" dentro de um link para o banco
    # público é vazamento de máquina apresentado como cifra oficial. Contraprova
    # 11 da espinha v2.
    "VALOR_MONETARIO_MALFORMADO",
    # `DIVULGACAO_DE_MONETIZACAO_AUSENTE`: página monetizada que não diz que é
    # monetizada deixa o leitor sem como separar conteúdo de anúncio.
    # Contraprova 7.
    "DIVULGACAO_DE_MONETIZACAO_AUSENTE",
})

#: Códigos que são risco em toda parte — sinal real, mas não prova de violação.
#:
#: ⚠️ Três saíram desta lista na v2 (`VALOR_MONETARIO_MALFORMADO`,
#: `DIVULGACAO_DE_MONETIZACAO_AUSENTE`, `ANCORA_INCONGRUENTE_COM_DESTINO`) e
#: passaram a bloquear no papel estrito. Enquanto estiveram aqui, eles eram
#: detectados e nunca reprovavam nada — que é a forma educada de um portão dizer
#: "eu vi e deixei passar".
_RISCO_SEMPRE = frozenset({
    # ⚠️ `ANCORA_INCONGRUENTE_COM_DESTINO` FOI PROMOVIDO E DEPOIS DEVOLVIDO AQUI.
    #
    # A promoção durou uma revisão. Medido no papel estrito, ele reprovava CTA
    # interno banal: "Simule agora" → /rec/calculadora-do-saque/, "Continuar" →
    # /rec/regras-do-fgts/, "Leia mais" → qualquer coisa. A regra exige
    # interseção de tokens entre a âncora e o caminho, e um CTA bom quase nunca
    # repete o slug — ele diz o que o leitor GANHA, não onde ele vai.
    #
    # A contraprova 12 do briefing continua coberta pela metade que importa:
    # CTA EXTERNO cai em `LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO` e
    # `BOTAO_PARA_TERCEIRO_NAO_AUTORIZADO`, os dois bloqueios. A metade
    # "incongruente" é heurística textual, e heurística textual que reprova
    # é como um portão perde a autoridade que precisa ter nos outros 41 códigos.
    "ANCORA_INCONGRUENTE_COM_DESTINO",
    "REDIRECIONAMENTO_OBSERVADO",
    "SERVICE_WORKER_OU_PUSH_OBSERVADO",
    "OFUSCACAO_DE_SCRIPT_OBSERVADA",
    "FORMULARIO_SEM_POLITICA_DE_PRIVACIDADE",
    "CONTEUDO_DUPLICADO_ENTRE_DOMINIOS",
})

#: Papéis que carregam o peso do clique comprado ou do dado do visitante.
PAPEIS_ESTRITOS = frozenset({PapelDestino.PAID_DESTINATION, PapelDestino.CONVERSION_PAGE})


def severidade(codigo: str, papel: PapelDestino) -> str:
    """A severidade de `codigo` para `papel`.

    Código desconhecido vira BLOQUEIO no papel estrito. Isso é intencional: um
    achado novo que ninguém classificou não pode entrar em produção valendo
    "observação" só porque a tabela não foi atualizada.
    """
    if codigo in _RISCO_SEMPRE:
        return SEVERIDADE_RISCO
    if papel in PAPEIS_ESTRITOS:
        # Inclusive o código que NÃO está em `_BLOQUEIA_NO_PAGO` nem em
        # `_RISCO_SEMPRE`: é um código novo, ainda não classificado, e no papel
        # estrito ele bloqueia até alguém decidir o contrário por escrito.
        return SEVERIDADE_BLOQUEIO
    if codigo in _BLOQUEIA_NO_PAGO:
        return SEVERIDADE_RISCO
    return SEVERIDADE_OBSERVACAO


# ── fontes oficiais ─────────────────────────────────────────────────────────

_FONTES = Path(__file__).resolve().parent / "fontes_politica.json"

#: Hosts aceitos como AUTORIDADE de política. Nada fora daqui pode fundamentar
#: uma regra: fórum, blog de agência e thread de comunidade descrevem o que
#: alguém acha que aconteceu, não o que a política diz.
HOSTS_OFICIAIS = ("support.google.com", "policies.google.com", "developers.google.com")


def carregar_fontes(caminho: Path | None = None) -> dict[str, Any]:
    return json.loads((caminho or _FONTES).read_text(encoding="utf-8"))


def versao_da_fonte(fontes: dict[str, Any] | None = None) -> str:
    """A versão da política é o HASH do conteúdo, não um número que alguém sobe.

    Um recibo emitido hoje precisa dizer contra QUE texto de política ele foi
    emitido. Número manual mente quando alguém edita a matriz e esquece de
    incrementá-lo; hash não tem como mentir.
    """
    return impressao(fontes if fontes is not None else carregar_fontes())[:16]


def fonte_do_codigo(codigo: str, fontes: dict[str, Any] | None = None) -> dict[str, Any] | None:
    return (fontes if fontes is not None else carregar_fontes()).get("rules", {}).get(codigo)


def codigos_conhecidos() -> frozenset[str]:
    """Todo código que o portão pode emitir. É a lista que os testes cruzam com
    `fontes_politica.json` — regra sem fonte oficial não entra."""
    return frozenset(_BLOQUEIA_NO_PAGO | _RISCO_SEMPRE)
