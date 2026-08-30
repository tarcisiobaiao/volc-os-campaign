"""Renderiza o `PROMPT.md` — o único lugar do pacote que preenche placeholder.

## Por que existe

O `PROMPT.md` está pronto e ninguém o chama. Ele carrega a doutrina medida da
operação como gramática, e todo limite que ele cita tem de vir da MESMA fonte
que o validador usa — `campanha/limites.yaml` e `policy/spec.json`. Prompt com
limite escrito à mão e validador com limite lido do arquivo divergem em semanas;
foi assim que a lista do n8n virou folclore.

Este módulo é a metade que preenche. A outra metade — conferir a saída — é
`contrato.py`, e as duas partem do mesmo objeto: `Encomenda.pedido()` devolve o
`Pedido` que o `ciclo.py` usa para julgar. Pedir 15 títulos no prompt e conferir
13 no contrato é o defeito invisível que essa ligação impede.

## O que este módulo NÃO faz

Não escreve regra nova, não valida copy, não fala com modelo nenhum e não filtra
o que as fontes dizem. Em particular: a §8 renderiza a TRAVA 0 de
`limites.yaml → politica.proibidos` porque `campanha/validacao.py:checar_politica`
DE FATO reprova esses termos por substring e sem acento, antes de a copy chegar
ao Google. Medido nos 6.651 aprovados: `crédito` aparece 54× e em nenhum punido —
ou seja, a lista custa caro e não protege. Mas quem a mata é quem edita a fonte;
filtrar aqui faria o prompt MENTIR sobre o que a nossa esteira faz, e o modelo
escreveria texto que `search.construir()` recusa localmente.

## A regra de preenchimento, e por que ela é literal

Cada `{chave}` é substituída por `str.replace`. **Nunca `str.format`**: o bloco 12
do template é um esqueleto de JSON cheio de `{` e `}`, e `format` estouraria nele.
O padrão `RX_PLACEHOLDER` só casa `{minusculas_com_underscore}` — nenhum trecho do
bloco 12 casa (todos têm aspas, dois-pontos ou maiúscula), e a tag `{KeyWord:...}`
também não.

Placeholder sem valor é ERRO, não silêncio: um `{nicho}` literal chegando ao
modelo é defeito caro e invisível — o texto sai plausível e fora do nicho. Valor
sem placeholder também é erro, porque significa que o template mudou de nome e o
dado que alguém calculou está sendo jogado fora sem aviso.

Uso:
    from volc_ads.copy.render import Encomenda, Fato, montar
    prompt = montar(encomenda)
    pedido = encomenda.pedido()      # o MESMO contrato que o ciclo confere
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..policy.spec import IDIOMA_PADRAO, carregar as carregar_spec
from .contrato import MAX_CHARS, Pedido

_AQUI = Path(__file__).resolve().parent
TEMPLATE = _AQUI / "PROMPT.md"
LIMITES = _AQUI.parent / "campanha" / "limites.yaml"
CORPUS = _AQUI.parent / "dados" / "corpus" / "calibracao_copy.json"
MANIFESTO = _AQUI.parent / "dados" / "corpus" / "manifesto.json"

# Só minúscula e underscore entre chaves. Ver o cabeçalho: é o que separa
# placeholder de esqueleto JSON e de tag DKI.
RX_PLACEHOLDER = re.compile(r"\{[a-z][a-z0-9_]*\}")

# Enum da API v25 (`KeywordMatchType`), não escolha nossa.
MATCH_TYPES = ("EXACT", "PHRASE", "BROAD")

# ⚠️ O PROMPT PEDE MAIS DO QUE O CONTRATO COBRA — e ainda vale, mas NÃO para
# cobertura de raiz. O modelo entrega o MÍNIMO que se pede: medido três vezes em
# 19/08/2026 (pedi 4 e vieram 4; pedi 9 e vieram 9; pedi 2 descrições e vieram
# 2), então número do prompt igual ao do contrato faz a copy nascer na borda.
#
# A margem de cobertura de RAIZ foi removida no mesmo dia, e o motivo é medido:
# levar a raiz a 15 de 15 títulos devolveu a MESMA nota e os MESMOS itens que
# 4 de 15. Repetir o termo não é o que o Google pede — ver `C11` no contrato.
MARGEM_DO_PEDIDO = 2

# Os defaults de contagem vêm do `Pedido` do contrato — uma casa só. Escrevê-los
# aqui de novo criaria duas verdades sobre "quantos títulos são o normal".
_PADRAO = Pedido()

# Cada contagem tem um limite de item na API, e o nome da chave em `limites.yaml`
# não é adivinhável a partir do nome do recurso (`headline_rsa`, `snippet_valor`).
_CHAVE_LIMITE = {
    "n_headlines": "headline_rsa",
    "n_descriptions": "description_rsa",
    "n_sitelinks": "sitelink_texto",
    "n_callouts": "callout",
    "n_snippet": "snippet_valor",
}


class ErroDeRender(ValueError):
    """Defeito de renderização. Sempre acionável: diz o quê e onde consertar."""


class PlaceholderFaltando(ErroDeRender):
    """O template pede uma chave para a qual não há valor."""


class PlaceholderDesconhecido(ErroDeRender):
    """Há valor calculado para uma chave que o template não pede mais."""


# ── as fontes, lidas uma vez ────────────────────────────────────────────────


@lru_cache(maxsize=1)
def carregar_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def carregar_limites() -> dict:
    return yaml.safe_load(LIMITES.read_text(encoding="utf-8"))


def corpo(texto: str | None = None) -> str:
    """Só o que vai para o modelo — o cabeçalho do arquivo é documentação.

    As 40 primeiras linhas do `PROMPT.md` explicam ao DESENVOLVEDOR o que o
    template é e trazem a tabela de placeholders (onde aparece um `{chave}`
    genérico, que não é placeholder de verdade). Mandá-las ao modelo gastaria
    contexto ensinando-o sobre o próprio arquivo.
    """
    bruto = texto if texto is not None else carregar_template()
    if "\n---\n" not in bruto:
        raise ErroDeRender(
            "PROMPT.md sem a linha '---' que separa o cabeçalho do template. "
            "Sem ela não dá para saber onde começa o texto que vai ao modelo."
        )
    return bruto.split("\n---\n", 1)[1]


@lru_cache(maxsize=1)
def tipos_de_fato() -> tuple[str, ...]:
    """Os tipos válidos, lidos da seção 2 do próprio template.

    São eles que ligam a seção 2 às mecânicas da seção 5 ("mecânica cujo tipo de
    fato não está no inventário está DESABILITADA"). Manter uma cópia da lista
    aqui garantiria que um dia o template ganhasse `[valor]` e o render seguisse
    recusando — o erro que só aparece quando o operador jura que digitou certo.
    """
    linha = re.search(r"O tipo é o que alimenta[^\n]*\n([^\n]*)", corpo())
    tipos = tuple(re.findall(r"\[([a-z_]+)\]", linha.group(1))) if linha else ()
    if not tipos:
        raise ErroDeRender(
            "não achei a lista de tipos de fato na seção 2 do PROMPT.md "
            "(linha após 'O tipo é o que alimenta as mecânicas da seção 5:')"
        )
    return tipos


def conferir_limites() -> list[str]:
    """`limites.yaml` contra `contrato.MAX_CHARS`. Devolve as divergências.

    São dois arquivos legíveis por máquina que descrevem o MESMO limite da API,
    e nada os obrigava a concordar. Divergir aqui é o pior caso silencioso: o
    prompt pede 30 caracteres, o contrato aprova 45, e a reprovação chega da API
    depois de a campanha existir.
    """
    lim = carregar_limites()["texto"]
    pares = [
        (("headline", ""), "headline_rsa"),
        (("description", ""), "description_rsa"),
        (("sitelink", "title"), "sitelink_texto"),
        (("sitelink", "description1"), "sitelink_desc"),
        (("sitelink", "description2"), "sitelink_desc"),
        (("callout", ""), "callout"),
        (("snippet", ""), "snippet_valor"),
    ]
    fora = []
    for alvo, chave in pares:
        esperado = lim[chave]["max_chars"]
        if MAX_CHARS[alvo] != esperado:
            fora.append(
                f"{alvo}: contrato.MAX_CHARS={MAX_CHARS[alvo]} mas "
                f"limites.yaml[{chave}].max_chars={esperado}"
            )
    return fora


# ── os insumos ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Fato:
    """Uma afirmação que a página de destino sustenta, com onde conferir.

    `fonte` é copiada LITERALMENTE pelo modelo quando ele cita (seção 7). Fato
    sem fonte continua servindo de lastro para título, mas o prompt avisa que
    ele não é citável — melhor do que o modelo inventar a fonte.
    """

    id: str
    tipo: str
    texto: str
    fonte: str = ""

    def linha(self) -> str:
        fonte = self.fonte.strip() or (
            "não declarada — este fato NÃO pode ser citado como fonte"
        )
        return f"{self.id} [{self.tipo}] {self.texto.strip()}\n        fonte: {fonte}"


@dataclass(frozen=True)
class Encomenda:
    """Tudo que o prompt precisa saber, validado na construção.

    Frozen porque é o objeto que o prompt e o `Pedido` derivam: se alguém mudar
    `n_headlines` depois de renderizar, o prompt pede 15 e o contrato confere 12.
    """

    nicho: str
    url: str
    keywords: tuple[str, ...]
    fatos: tuple[Fato, ...] = ()
    nao_fatos: tuple[str, ...] = ()
    termos_de_busca: tuple[str, ...] = ()

    pais: str = "BR"
    idioma: str = ""            # vazio = deriva do país pelo spec
    ano: int = 0                # 0 = ano do relógio
    vertical: str = "informativo"
    tema_regulado: str = "nenhum"
    certificacoes: tuple[str, ...] = ()   # o que a CONTA comprovadamente tem
    match_type: str = "PHRASE"

    n_headlines: int = _PADRAO.n_headlines
    n_descriptions: int = _PADRAO.n_descriptions
    n_sitelinks: int = _PADRAO.n_sitelinks
    n_callouts: int = _PADRAO.n_callouts
    n_snippet: int = _PADRAO.n_snippet

    max_dki: int | None = None   # None = 1, ou 0 em BROAD (seção 10)
    amostra: tuple[str, ...] = ()
    origem_amostra: str = ""

    def __post_init__(self) -> None:
        sub = object.__setattr__   # frozen: normalizar exige a porta dos fundos
        if not self.nicho.strip():
            raise ErroDeRender("nicho vazio: o prompt inteiro se apoia nele")
        if not self.url.startswith("https://"):
            raise ErroDeRender(f"url precisa ser https (mesma regra do Brief): {self.url!r}")
        if not self.keywords:
            raise ErroDeRender(
                "sem keywords: a seção 9 é a base semântica do prompt e a seção 10 "
                "as usa como teste de DKI quando não há termo de busca colhido"
            )

        pais = self.pais.upper()
        if pais not in IDIOMA_PADRAO:
            raise ErroDeRender(
                f"país {pais!r} não está em policy.spec.IDIOMA_PADRAO "
                f"({', '.join(sorted(IDIOMA_PADRAO))})"
            )
        sub(self, "pais", pais)
        sub(self, "idioma", self.idioma or IDIOMA_PADRAO[pais])
        sub(self, "ano", self.ano or datetime.date.today().year)

        if self.match_type not in MATCH_TYPES:
            raise ErroDeRender(f"match_type {self.match_type!r} fora de {MATCH_TYPES}")

        temas = tuple(k for k in carregar_spec()["habilitacao"] if not k.startswith("_"))
        if self.tema_regulado not in temas + ("nenhum",):
            raise ErroDeRender(
                f"tema_regulado {self.tema_regulado!r} não existe em "
                f"policy/spec.json → habilitacao ({', '.join(temas)}, nenhum)"
            )

        # DKI em ad group BROAD é PROIBIDO pela seção 10, e o motivo é estrutural:
        # o que renderiza no leilão é a busca do usuário, não o fallback. Em BROAD
        # a busca pode ser qualquer coisa. Recusar em vez de corrigir em silêncio
        # porque quem pediu DKI em BROAD acha que vai ter DKI.
        if self.match_type == "BROAD" and self.max_dki:
            raise ErroDeRender(
                "max_dki > 0 com match_type BROAD: a seção 10 proíbe DKI em ad "
                "group BROAD. Passe max_dki=0 ou mude o match type."
            )
        sub(self, "max_dki", 0 if self.match_type == "BROAD"
            else (_PADRAO.max_dki if self.max_dki is None else self.max_dki))

        lim = carregar_limites()["texto"]
        for campo, chave in _CHAVE_LIMITE.items():
            n = getattr(self, campo)
            faixa = lim[chave]
            if not faixa["min_itens"] <= n <= faixa["max_itens"]:
                raise ErroDeRender(
                    f"{campo}={n} fora do que a API aceita para {chave}: "
                    f"{faixa['min_itens']}..{faixa['max_itens']} (limites.yaml)"
                )

        validos = tipos_de_fato()
        vistos: set[str] = set()
        for f in self.fatos:
            if f.tipo not in validos:
                raise ErroDeRender(
                    f"fato {f.id}: tipo {f.tipo!r} não existe na seção 2 do "
                    f"PROMPT.md ({', '.join(validos)})"
                )
            if f.id in vistos:
                raise ErroDeRender(
                    f"fato {f.id!r} repetido: a ancoragem endereça fato por id, "
                    f"e dois fatos com o mesmo id tornam a checagem 7 inútil"
                )
            vistos.add(f.id)

        divergentes = conferir_limites()
        if divergentes:
            raise ErroDeRender(
                "limites.yaml e contrato.MAX_CHARS discordam — o prompt pediria "
                "um limite e o contrato aprovaria outro:\n  " + "\n  ".join(divergentes)
            )

    # ── a ponte com o contrato ──────────────────────────────────────────────

    def pedido(self) -> Pedido:
        """O `Pedido` que julga a resposta desta encomenda.

        Existe para que prompt e contrato não possam divergir: são derivados do
        mesmo objeto, no mesmo instante.
        """
        return Pedido(
            n_headlines=self.n_headlines,
            n_descriptions=self.n_descriptions,
            n_sitelinks=self.n_sitelinks,
            n_callouts=self.n_callouts,
            n_snippet=self.n_snippet,
            idioma=self.idioma,
            fatos=tuple(f.id for f in self.fatos),
            headers_snippet=headers_snippet(self.idioma),
            max_dki=self.max_dki or 0,
            raiz_do_termo=self.raiz_do_termo(),
            raizes_do_termo=self.raizes_do_termo(),
            # A C10 roda o portão do lançamento, e é país × vertical que decide
            # quais regras do `spec.json` valem. Herdar da encomenda é o que
            # impede a cascata julgar com um conjunto e o `/provar` com outro.
            pais=self.pais,
            vertical=self.vertical,
            # A C11 mede VARIEDADE: quantas destas o anúncio espelha. Sem a
            # lista aqui, ela não tem contra o que medir e sai calada — que foi
            # o estado em que o motor ficou repetindo a raiz e tirando AVERAGE.
            keywords_do_grupo=tuple(self.keywords),
        )

    def raiz_do_termo(self) -> str:
        """A palavra que MAIS aparece nas keywords escolhidas.

        ⚠️ Não é o nicho, e a diferença importa. O nicho é como a casa chama o
        tema ("Maquininha de Cartão"); a raiz é o que as pessoas digitam. Medido
        no card 74 em 19/08/2026: 7 das 10 keywords contêm "maquininha", e é
        essa palavra que o Google procura nos títulos ao dar a nota.

        Devolve vazio quando nenhuma palavra domina — aí a checagem C9 se
        desliga sozinha, em vez de exigir cobertura de um termo inventado.
        """
        from collections import Counter

        from .contrato import sem_acento

        # Palavras curtas são preposição e artigo; 4 letras é o mesmo piso que
        # o contrato usa para contar repetição.
        cont: Counter = Counter()
        for k in self.keywords:
            vistas = set()
            for w in sem_acento(str(k).lower()).split():
                if len(w) >= 4 and w not in vistas:
                    vistas.add(w)
                    cont[w] += 1
        if not cont:
            return ""
        palavra, n = cont.most_common(1)[0]
        # Dominar é estar na MAIORIA das keywords. Abaixo disso não há termo
        # principal — há um cluster diverso, e exigir cobertura seria arbitrário.
        return palavra if n * 2 > len(self.keywords) else ""

    def raizes_do_termo(self, quantas: int = 3) -> tuple[str, ...]:
        """As palavras que MAIS aparecem nas keywords — no plural.

        ⚠️ UMA RAIZ NÃO BASTA, e o card 65 provou.

        `raiz_do_termo` escolhe uma por maioria. Nas 82 keywords daquele card
        ela devolveu `fgts` (56 ocorrências) e ignorou `saque` (55) e
        `aniversario` (46) — três termos praticamente empatados, porque o que a
        pessoa digita são FRASES: "consultar fgts pelo cpf", "saque aniversário
        fgts calendário".

        Cobrir só `fgts` deixou títulos como "Modalidade: Elegibilidade" e
        "Vantagens da Modalidade", que não carregam nenhum dos três. O Google
        devolveu Ad Strength **Ruim**, com "Inclua palavras-chave bastante
        usadas nos títulos" sem check.

        O piso de 25% é o que separa termo do cluster de palavra que apareceu:
        com 82 keywords, exige estar em ao menos 21 delas.
        """
        from collections import Counter

        from .contrato import sem_acento

        import re as _re

        cont: Counter = Counter()
        for k in self.keywords:
            vistas = set()
            # ⚠️ QUEBRA POR NÃO-ALFANUMÉRICO, não por espaço.
            #
            # `split()` deixava `saque-aniversario` como UM token. Com isso,
            # `aniversario` — que está em 46 das 82 keywords do card 65 — nunca
            # era contado, e `2026` subia ao pódio no lugar dele. O hífen é
            # separador de palavra na busca, não parte da palavra.
            for w in _re.split(r"[^a-z0-9]+", sem_acento(str(k).lower())):
                # ⚠️ ANO NÃO É TERMO DE BUSCA. `2026` aparecia em 31 das 82
                # keywords do card 65 e virou "raiz" — mas um título com
                # "2026" não demonstra relevância como "saque" demonstra. O
                # Google procura o ASSUNTO nos títulos, não o calendário.
                if len(w) >= 4 and not w.isdigit() and w not in vistas:
                    vistas.add(w)
                    cont[w] += 1
        total = len(self.keywords or ())
        if not cont or not total:
            return ()
        piso = max(2, total // 4)
        return tuple(p for p, n in cont.most_common(quantas) if n >= piso)


# ── os pedaços que viram texto ──────────────────────────────────────────────


def headers_snippet(idioma: str) -> tuple[str, ...]:
    """Os headers que a API aceita, por idioma, direto do `limites.yaml`.

    Idioma sem lista é ERRO e não fallback para pt: a API recusa header fora da
    lista do idioma do anúncio, então servir a lista pt-BR a uma campanha em
    espanhol garante a recusa lá na frente, com a campanha já montada.
    """
    chave = f"snippet_headers_{idioma}"
    lista = carregar_limites().get(chave)
    if not lista:
        raise ErroDeRender(
            f"campanha/limites.yaml não tem `{chave}`. Os headers oficiais estão "
            f"em volc_ads/google_ads_api/structured_snippets.md — acrescente a "
            f"lista de {idioma!r} lá antes de gerar copy neste idioma."
        )
    return tuple(lista)



def _bloco(itens, vazio: str) -> str:
    """Lista em bloco. Vazio NUNCA vira string vazia — vira declaração.

    Placeholder que renderiza nada deixa no prompt um título de seção seguido de
    silêncio, e o modelo preenche o silêncio sozinho. Dizer "vazia, e é isto que
    isso significa" custa uma linha e fecha a porta.
    """
    linhas = [str(i).strip() for i in itens if str(i).strip()]
    return "\n".join("  - " + i for i in linhas) if linhas else vazio


def _restricoes(spec: dict, enc: Encomenda) -> dict[str, str]:
    """As três faixas da seção 8, derivadas da severidade do spec.

    O corte não é só por severidade, porque severidade sozinha erra o sentido:
    `editorial.repeticao.na_lista` é `aviso` e não é termo REGULADO nenhum — é
    degradação de Ad Strength. O que marca "regulado" é a regra declarar
    `verticais`, porque é a vertical que aponta a certificação exigida em
    `habilitacao`. Daí:

      PROIBIDO   severidade erro ou bloqueio
      REGULADO   severidade aviso E com vertical declarada (→ tem certificação)
      OBSERVADO  severidade aviso sem vertical (degrada, não reprova)
    """
    regras = list(spec["estruturais"]) + spec["semanticas"].get(enc.idioma, [])
    faixas: dict[str, list[str]] = {"erro": [], "aviso": [], "observado": []}
    hab = spec["habilitacao"]

    for r in regras:
        verticais = r.get("verticais") or []
        if verticais and enc.vertical not in verticais:
            continue
        exemplos = (r.get("proibidos") or r["deteccao"].get("frases") or [])[:6]
        amostra = "; ".join(repr(e) for e in exemplos)
        linha = f"{r['titulo']}  [política {r['fonte']}]"
        if r.get("nota"):
            linha += f"\n      {r['nota']}"
        if amostra:
            linha += f"\n      dispara em: {amostra}"

        if r["severidade"] in ("erro", "bloqueio"):
            faixas["erro"].append(linha)
        elif verticais:
            exige = ", ".join(
                hab[v]["exige"] for v in verticais if v in hab and "exige" in hab[v]
            )
            faixas["aviso"].append(
                linha + (f"\n      certificação exigida: {exige}" if exige else "")
            )
        else:
            faixas["observado"].append(linha)

    versao = spec.get("versao", "?")
    contexto = f"idioma {enc.idioma!r} e vertical {enc.vertical!r}"
    return {
        nome: _bloco(
            linhas,
            f"  (nenhuma regra desta faixa no spec v{versao} para {contexto})",
        )
        for nome, linhas in faixas.items()
    }


def _habilitacao(spec: dict, enc: Encomenda) -> tuple[str, str]:
    """Devolve (certificações satisfeitas, aviso de habilitação).

    A habilitação é o portão que reprova a CAMPANHA inteira, independente do
    texto — e o default é fechado: sem declaração explícita, assume-se que a
    conta não tem. Torcer aqui produz anúncio FULLY_LIMITED, que é o precedente
    medido de `GOVERNMENT_DOCUMENTS_AND_OFFICIAL_SERVICES` (57 anúncios, 39
    contas).
    """
    hab = spec["habilitacao"]
    exigidas = {
        h["exige"] for k, h in hab.items()
        if not k.startswith("_") and enc.pais in h.get("paises_exigem", [])
    }
    tem = sorted(set(enc.certificacoes) & exigidas)
    # Certificação que a conta declara mas que país nenhum exige aqui não entra:
    # listá-la faria o modelo achar que destravou um termo que segue travado.
    certificacoes = ", ".join(tem) if tem else (
        f"nenhuma — a conta não declarou nenhuma das certificações que {enc.pais} exige"
    )

    if enc.tema_regulado == "nenhum":
        aviso = ("  (tema não regulado: nenhum portão de habilitação por país se "
                 "aplica a esta campanha)")
        return certificacoes, aviso

    porta = hab[enc.tema_regulado]
    if enc.pais not in porta.get("paises_exigem", []):
        aviso = (
            f"  ({enc.tema_regulado} não exige {porta['exige']} em {enc.pais}; "
            f"o spec lista: {', '.join(porta.get('paises_exigem', [])) or '—'})"
        )
        return certificacoes, aviso

    satisfeita = porta["exige"] in set(enc.certificacoes)
    estado = "SATISFEITA nesta conta" if satisfeita else "NÃO satisfeita nesta conta"
    aviso = (
        f"\nATENÇÃO — habilitação: {enc.tema_regulado} exige `{porta['exige']}` em "
        f"{enc.pais}, severidade `{porta['severidade']}`, e ela está {estado}.\n"
        f"  {porta.get('nota', '')}\n"
        f"  fonte: {porta['url']}\n"
    )
    if not satisfeita:
        aviso += (
            "  Enquanto ela não constar, todo termo da faixa REGULADO é tratado "
            "como PROIBIDO, e o texto precisa ser verdadeiro para um portal que "
            "EXPLICA o tema — nunca para quem presta o serviço.\n"
        )
    return certificacoes, aviso


def _cobertura(spec: dict, enc: Encomenda) -> str:
    """O quanto o validador local enxerga neste idioma. Muda o rigor da passada 2.

    `completa` só quando há regra semântica do idioma E regra específica da
    vertical — é o que a tabela do template manda. O eixo PAÍS não entra porque
    o spec não tem regra semântica por país: as listas nasceram em BR e MX, e o
    próprio template já declara isso ao modelo.
    """
    regras = spec["semanticas"].get(enc.idioma, [])
    da_vertical = [r for r in regras if enc.vertical in (r.get("verticais") or [])]
    if not regras:
        estado = "ausente"
    elif not da_vertical:
        estado = "parcial"
    else:
        estado = "completa"
    return (
        f"{estado} — {len(regras)} regra(s) semântica(s) para {enc.idioma!r} no "
        f"spec v{spec.get('versao', '?')}, {len(da_vertical)} específica(s) da "
        f"vertical {enc.vertical!r}"
    )


def _siglas(spec: dict, enc: Encomenda) -> str:
    """A união: as siglas do spec mais toda sigla que apareça num fato.

    ⚠️ O spec tem UMA lista de siglas permitidas, não uma por país — ela nasceu
    em pt-BR (FGTS, CPF, INSS). Para MX ou CO, a sigla local (CURP, RFC, RUT) só
    entra por esta união com os fatos. É por isso que a união existe: sem ela, o
    prompt mandaria escrever "Registro Único Tributario" por extenso num título
    de 30 caracteres.
    """
    do_spec: set[str] = set()
    for r in spec["estruturais"]:
        do_spec.update(r.get("permitidos") or [])
    dos_fatos: set[str] = set()
    for f in enc.fatos:
        dos_fatos.update(re.findall(r"\b[A-ZÁÉÍÓÚÑÜÇ]{2,}\b", f"{f.texto} {f.fonte}"))
    return ", ".join(sorted(do_spec | dos_fatos)) or "nenhuma"


# ── amostra do corpus ───────────────────────────────────────────────────────

# MEDIDO em 18/08/2026 sobre os 6.651 aprovados de `calibracao_copy.json`, com
# exatamente estas regexes: 602 títulos casam marcador exclusivo de pt, 596 casam
# marcador exclusivo de es, e a interseção é ZERO. O corpus é MISTO. Amostrar sem
# filtrar põe título em espanhol num prompt em português quase na metade das
# vezes — e a seção 5 manda tratar amostra fora do idioma como CONTRA-EXEMPLO.
_MARCA_IDIOMA = {
    "pt": re.compile(r"\b(você|não|veja|confira|inscrições|vagas|salário|edital)\b", re.I),
    "es": re.compile(r"[¿ñ]|\b(usted|aquí|más|inscripciones|convocatoria|trámite|cómo)\b", re.I),
}


def amostra_do_corpus(idioma: str, n: int = 24) -> tuple[tuple[str, ...], str]:
    """Devolve (títulos, origem declarada). Opt-in: o default de `Encomenda` é vazio.

    A amostra NÃO é obrigatória e o template tem ramo para ela vazia ("escreva no
    registro nativo do país"). Ela é opt-in porque o manifesto do corpus não
    registra idioma nem país por item — quem afirma que a amostra é do idioma do
    anúncio é este filtro, e ele é um marcador léxico, não um classificador.

    A seleção é espaçada, não aleatória: prompt tem de ser reproduzível para que
    duas gerações diferentes sejam do modelo, não do sorteio.
    """
    marca = _MARCA_IDIOMA.get(idioma)
    if marca is None:
        return (), (
            f"nenhuma — não há marcador léxico de {idioma!r} para filtrar o corpus "
            f"(a operação mediu pt e es)"
        )
    if not CORPUS.exists():
        return (), f"nenhuma — corpus ausente em {CORPUS}"

    aprovados = json.loads(CORPUS.read_text(encoding="utf-8"))["aprovados_search_limpos"]
    filtrados = [h for h in aprovados if marca.search(h)]
    if not filtrados:
        return (), f"nenhuma — nenhum dos {len(aprovados)} aprovados casa marcador de {idioma!r}"

    passo = max(1, len(filtrados) // n)
    escolhidos = tuple(filtrados[::passo][:n])

    manifesto = json.loads(MANIFESTO.read_text(encoding="utf-8")) if MANIFESTO.exists() else {}
    origem = (
        f"{len(escolhidos)} de {len(filtrados)} títulos APROVADOS e servindo que "
        f"casam marcador léxico de {idioma!r}, dentro dos {len(aprovados)} do corpus "
        f"da operação (colhido em {manifesto.get('capturado_em', '?')}, "
        f"{manifesto.get('contas_operacionais', '?')} contas). O manifesto NÃO "
        f"registra idioma nem país por item: quem afirma o idioma é o filtro léxico, "
        f"e o país não foi verificado"
    )
    return escolhidos, origem


# ── o preenchimento ─────────────────────────────────────────────────────────


def valores(enc: Encomenda) -> dict[str, str]:
    """Cada placeholder e o texto que entra no lugar dele.

    Público de propósito: é o que o banco de provas inspeciona para dizer de
    ONDE veio cada valor, sem ter de ler o prompt de 700 linhas renderizado.
    """
    spec = carregar_spec()
    lim = carregar_limites()
    certificacoes, aviso_hab = _habilitacao(spec, enc)
    restricoes = _restricoes(spec, enc)

    return {
        "{nicho}": enc.nicho,
        "{url}": enc.url,
        "{pais}": enc.pais,
        "{idioma}": enc.idioma,
        "{ano}": str(enc.ano),
        "{vertical}": enc.vertical,
        "{tema_regulado}": enc.tema_regulado,
        "{certificacoes_da_conta}": certificacoes,
        "{aviso_habilitacao}": aviso_hab,
        "{cobertura_semantica}": _cobertura(spec, enc),
        "{fatos}": _bloco(
            [f.linha() for f in enc.fatos],
            "  (nenhum fato fornecido — MODO SEM LASTRO, como define esta seção)",
        ),
        "{nao_fatos}": _bloco(
            enc.nao_fatos,
            "  (a página não declarou o que deliberadamente NÃO afirma. Trate a "
            "lista como desconhecida, não como vazia: afirme somente o que os "
            "FATOS sustentam)",
        ),
        "{keywords}": _bloco(enc.keywords, "  (sem keywords)"),
        "{termos_de_busca}": _bloco(
            enc.termos_de_busca,
            "  (vazia — nenhum termo de busca colhido ainda nesta campanha)",
        ),
        "{match_type}": enc.match_type,
        "{n_headlines}": str(enc.n_headlines),
        "{n_descriptions}": str(enc.n_descriptions),
        "{n_sitelinks}": str(enc.n_sitelinks),
        "{n_callouts}": str(enc.n_callouts),
        "{n_snippet}": str(enc.n_snippet),
        # As raízes são derivadas das keywords, não do nicho — ver
        # `raizes_do_termo()`. Sem termo dominante o prompt recebe o próprio
        # nicho e a C9 se desliga: exigir cobertura de um termo inventado é
        # pior que não exigir nada.
        #
        # ⚠️ `{raiz_do_termo}` (singular) saiu da tabela junto com o marcador do
        # template. O guard `PlaceholderDesconhecido` pegou o resto — é ele que
        # impede um dado calculado ficar sendo jogado fora em silêncio.
        # ⚠️ AS RAÍZES, NO PLURAL — e SÓ elas.
        #
        # Aqui havia também `{min_titulos_com_termo}`: quantos títulos deviam
        # carregar a raiz. Saiu em 19/08/2026, medido. Ver o bloco VARIEDADE DE
        # KEYWORDS no PROMPT.md e a `C11` no contrato: pedir mais repetição da
        # raiz não move a nota do Google, e gasta o título dizendo o que já foi
        # dito. Quem cobra cobertura agora é a variedade, não a raiz.
        "{raizes_do_termo}": ", ".join(enc.raizes_do_termo()) or enc.nicho,
        "{snippet_headers}": ", ".join(headers_snippet(enc.idioma)),
        # A TRAVA 0 é da NOSSA esteira (`campanha/validacao.py`), não do Google —
        # ver o cabeçalho deste módulo sobre por que ela é renderizada mesmo
        # sabendo que a medição a derrubou.
        "{termos_travados}": _bloco(
            lim["politica"]["proibidos"],
            "  (nenhum termo travado em campanha/limites.yaml)",
        ),
        "{restricoes_erro}": restricoes["erro"],
        "{restricoes_aviso}": restricoes["aviso"],
        "{restricoes_observado}": restricoes["observado"],
        "{siglas_permitidas}": _siglas(spec, enc),
        "{max_dki}": str(enc.max_dki),
        "{dki_permitido}": (
            f"sim, no máximo {enc.max_dki} título(s), só em invólucro nominal"
            if enc.max_dki
            else f"NÃO — zero títulos com DKI nesta campanha (match type {enc.match_type})"
        ),
        "{amostra_aprovados}": _bloco(
            enc.amostra,
            "  (sem amostra — escreva no registro nativo do país, e não vá buscar "
            "material nos EX: da seção 3)",
        ),
        "{origem_amostra}": enc.origem_amostra or "nenhuma amostra fornecida",
    }


def montar(enc: Encomenda, *, template: str | None = None) -> str:
    """Lê o PROMPT.md, preenche por `str.replace` e devolve o que vai ao modelo.

    `template` existe para o banco de provas encenar um template divergente — é
    a única forma de provar que o portão de placeholder reprova de verdade sem
    editar o arquivo real.
    """
    texto = corpo(template)
    tabela = valores(enc)
    pedidos = set(RX_PLACEHOLDER.findall(texto))

    faltando = pedidos - set(tabela)
    if faltando:
        raise PlaceholderFaltando(
            f"o template pede {sorted(faltando)} e não há valor para eles. Um "
            f"'{sorted(faltando)[0]}' literal chegando ao modelo não quebra nada "
            f"visivelmente — só produz copy fora do alvo."
        )
    sobrando = set(tabela) - pedidos
    if sobrando:
        raise PlaceholderDesconhecido(
            f"há valor calculado para {sorted(sobrando)}, que o template não pede "
            f"mais. Renderizar assim jogaria esse dado fora em silêncio."
        )

    for chave, valor in tabela.items():
        # Valor que carrega um placeholder do template seria substituído pela
        # volta seguinte do laço — e o resultado dependeria da ORDEM do dicionário.
        # Um fato que contenha o texto "{ano}" é defeito de entrada, não de render.
        intrusos = [p for p in RX_PLACEHOLDER.findall(valor) if p in pedidos]
        if intrusos:
            raise ErroDeRender(
                f"o valor de {chave} contém {intrusos} — texto de entrada não pode "
                f"trazer placeholder do template dentro de si"
            )
        texto = texto.replace(chave, valor)

    resto = sorted(set(RX_PLACEHOLDER.findall(texto)))
    if resto:  # cinto e suspensório: pega placeholder introduzido por um valor
        raise PlaceholderFaltando(f"sobrou placeholder após o preenchimento: {resto}")
    return texto


__all__ = [
    "Encomenda",
    "ErroDeRender",
    "Fato",
    "PlaceholderDesconhecido",
    "PlaceholderFaltando",
    "amostra_do_corpus",
    "conferir_limites",
    "corpo",
    "headers_snippet",
    "montar",
    "tipos_de_fato",
    "valores",
]
