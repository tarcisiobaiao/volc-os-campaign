"""O REVISOR CONTEXTUAL COM MICROAJUSTES (reforma editorial, etapa B5).

## O defeito que isto conserta

O juiz antigo dava nota e reprovava: não consertava nada, não dizia o trecho, e
a página condenada morria inteira. Os validadores por palavra mandavam
reescrever o texto INTEIRO por uma expressão ("vagas limitadas", "sistema
oficial", "quero ver") — e a reescrita saía mais genérica a cada tentativa.

## A divisão de trabalho

- O LLM LÊ o contexto (texto, briefing, inventário com fontes, termos, de onde o
  leitor vem, para onde vai, identidade do publisher, pacote de políticas) e
  devolve achados com TRECHO EXATO, motivo e evidência, mais patches mínimos.
- O CÓDIGO decide o que pode mudar: campo permitido, `antes` único, sem URL,
  sem link, sem tag de bloco, sem número fora do inventário, dentro do limite
  de tamanho e de quantidade; só achado `bloqueante`/`ajuste` com evidência
  resolvível vira patch; estilo e oportunidade nunca. Depois dos patches, tudo
  é revalidado pelos validadores determinísticos; reprovou, a rodada é
  descartada.
- O código também confere a COERÊNCIA da decisão: afirmação não verificada não
  aprova; "aprovado" com bloqueante é incoerente; "aprovado" (rodada sem patch
  ou fim do "ajustar") com nota existencial ausente, não numérica, fora de 0-10
  ou abaixo de 7 não aprova — a regra fail-closed do juiz V1, com o MESMO
  conjunto de critérios (`criterios_existenciais`); decisão fora do vocabulário,
  timeout, exceção ou JSON ilegível vão para a PESSOA, com o texto intacto e o
  erro gravado. UMA chamada de revisão e no máximo UMA rodada de patches:
  não há segunda chamada ao modelo. Bloqueante que o patch não resolveu vai à
  pessoa.
- O pacote de políticas vencido é ALERTA de atualização (`policy_pack_stale`),
  não reprovação: a revisão segue com o pacote disponível.
- A PESSOA aprova o que o código não pode aprovar (`funnelforge decidir`), presa
  ao sha256 do conteúdo.

## O recibo

`recibo_sha256` cobre título SEO + meta description + corpo ANTES das
decorações de publicação. `step_publish` só publica com recibo `aprovado`
(do revisor ou da pessoa) cujo hash bate com o que vai ser entregue.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable

from funnelforge.config.settings import StepConfig
from funnelforge.domain.models import (
    Issue,
    PageRole,
    StepResult,
    StepStatus,
    derive_role,
)
from funnelforge.pipeline.doctrine import COMPLIANCE_NOTICE_TEXT
from funnelforge.pipeline.editorial_safety import html_issues
from funnelforge.pipeline.enhancers.gutenberg import AVISO_CANONICO_BLOCK
from funnelforge.pipeline.budget import OrcamentoEstourado
from funnelforge.pipeline.lp_template import validate_lp_content
from funnelforge.pipeline.retry_policy import separar_para_o_revisor
from funnelforge.pipeline.runner import LLMStepError
from funnelforge.pipeline.validators.briefing_contract import numeros
from funnelforge.pipeline.validators.checks import run_validators, tolerant_json_object
from funnelforge.prompts import render

VERSAO = "revisao-v1"
DECISOES: tuple[str, ...] = ("aprovado", "ajustar", "revisao_humana")
SEVERIDADES: tuple[str, ...] = ("bloqueante", "ajuste", "nota")
CATEGORIAS: tuple[str, ...] = ("erro_factual", "risco_politica", "congruencia_destino",
                               "identidade", "estilo", "oportunidade")
TIPOS_DE_EVIDENCIA: tuple[str, ...] = ("fato", "fonte", "politica", "identidade", "briefing",
                                       "intencao", "destino")
CATEGORIAS_SO_NOTA = frozenset({"estilo", "oportunidade"})
MAX_PATCHES_POR_RODADA = 8
# Uma chamada de revisão por página (diretriz do operador, 30/09/2026).
MAX_RODADAS = 1
ALERTA_PACOTE_VENCIDO = "policy_pack_stale"

# A TRAVA DAS NOTAS (paridade com o juiz V1, `steps._judge_page`): nota abaixo
# disto, ausente, não numérica ou fora de 0-10 num critério existencial exigido
# impede a aprovação automática.
NOTA_MINIMA_EXISTENCIAL = 7
MOTIVO_NOTAS_INSUFICIENTES = "notas_existenciais_insuficientes"
# A marca que o recibo do revisor carrega quando a trava foi aplicada. Recibo
# do revisor SEM ela (emitido antes da trava) não libera publicação.
VERSAO_DA_TRAVA = "trava-notas-v1"
# O marcador de nota do exemplo de saída, quando o modelo o copia no lugar do
# número (ele NÃO é JSON): vira `null`, a nota conta como inválida e os achados
# da resposta não se perdem.
_MARCADOR_DE_NOTA_RE = re.compile(r'("[^"\\\n]{1,80}"\s*:\s*)<0-10>')

_CAMPOS_LP_SIMPLES = ("hero_title", "hero_subtitle", "hero_subtitle_desktop", "article_title")
_CAMPOS_LP_RICOS = ("intro", "transition")
_CAMPO_LISTA_RE = re.compile(r"^(sections|faq)\[(\d+)\]\.(title|body|q|a)$")
_CAMPO_CTA_RE = re.compile(r"^cta_texts\[(\d+)\]$")
_TAGS_INLINE = frozenset({"strong", "em", "br"})

_RAW_HTML_RE = re.compile(r"<!--\s*wp:html(?![\w-])(?:(?!-->)[\s\S])*?-->[\s\S]*?"
                          r"<!--\s*/wp:html\s*-->", re.I)
_COMENTARIO_RE = re.compile(r"<!--[\s\S]*?-->")
_TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*>")
_EXECUTAVEL_RE = re.compile(r"<(script|style)\b[\s\S]*?</\1\s*>", re.I)
_ASIDE_RE = re.compile(r"<aside\b[\s\S]*?</aside\s*>", re.I)
_PARAGRAFO_BLOCO_RE = re.compile(r"<!--\s*wp:paragraph\b[^>]*-->[\s\S]*?<!--\s*/wp:paragraph\s*-->",
                                 re.I)
_P_SOLTO_RE = re.compile(r"<p\b[^>]*>[\s\S]*?</p>", re.I)
_LINK_RE = re.compile(r"<a\b[^>]*>([\s\S]*?)</a\s*>", re.I)
_BLOCO_RE = re.compile(r"<!--\s*(/?)wp:([a-z0-9/-]+)((?:(?!-->)[\s\S])*?)(/?)-->", re.I)
_BLOCOS_EDITAVEIS = frozenset({"paragraph", "heading", "list", "list-item", "buttons", "button"})
_BLOCOS_DE_BOTAO = frozenset({"buttons", "button"})
_URL_RE = re.compile(r"https?://\S+|\bwww\.\S+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}\b", re.I)
# B8/R4: pontos que se passam por "." num domínio ("golpe\u2024com\u2024br")
_PONTOS_DISFARCADOS = str.maketrans({c: "." for c in "\u2024\uff0e\u3002\ufe52\u2027\u00b7"})
# B8/R4: tag inline só nua (<strong>, </em>, <br/>): atributo esconde texto (style=display:none)
_TAG_INLINE_NUA_RE = re.compile(r"^</?(strong|em|br)\s*/?>$", re.I)
# B8/R4: número por extenso ("quarenta e cinco dias") — "um/uma" ficam de fora (artigo)
_NUMERO_POR_EXTENSO_RE = re.compile(
    r"\b(dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|onze|doze|treze|"
    r"quatorze|catorze|quinze|dezesseis|dezessete|dezoito|dezenove|vinte|trinta|quarenta|"
    r"cinquenta|sessenta|setenta|oitenta|noventa|cem|cento|duzentos|duzentas|trezentos|"
    r"quatrocentos|quinhentos|seiscentos|setecentos|oitocentos|novecentos|mil|milh[aã]o|"
    r"milh[oõ]es|bilh[aã]o|bilh[oõ]es|dobro|triplo|metade|dezena|d[uú]zia|centena)\b", re.I)
# B8/R4: número com o que vem colado a ele (unidade ou moeda): "30 dias", "R$ 1.518"
_NUMERO_COM_UNIDADE_RE = re.compile(
    r"(R\$\s*)?(\d[\d.,]*)(\s*%|\s+(?:dias?|m[eê]s|meses|anos?|semanas?|horas?|minutos?|"
    r"sal[aá]rios?|mil|milh[aã]o|milh[oõ]es|bilh[aã]o|bilh[oõ]es|reais|real|parcelas?|vezes|"
    r"vez|pontos?|kwh|km|kg)\b)?", re.I)
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']*)["\']', re.I)
_SECTION_WIDGET_RE = re.compile(r'<section\b[^>]*\bclass="[^"]*\bvw-', re.I)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _visivel(texto: str) -> str:
    """Texto visível: sem comentário, sem tag, entidades resolvidas, espaço único."""
    sem = _EXECUTAVEL_RE.sub(" ", _COMENTARIO_RE.sub(" ", texto or ""))
    return " ".join(html.unescape(_TAG_RE.sub(" ", sem)).split())


# ---------------------------------------------------------------------------
# o documento revisado e o recibo
# ---------------------------------------------------------------------------

def recibo_sha256(corpo: str, seotitle: str, metadescription: str) -> str:
    """O hash do que o leitor vê antes das decorações de publicação: título SEO
    (o H1 visível das internas), meta description e corpo."""
    carga = json.dumps({"corpo": corpo or "", "metadescription": metadescription or "",
                        "seotitle": seotitle or ""}, ensure_ascii=False, sort_keys=True)
    return _sha(carga)


@dataclass(frozen=True)
class Documento:
    """O conteúdo de uma página como o revisor o lê e o código o altera."""
    formato: str                      # "gutenberg" | "lp_json"
    corpo: str
    seotitle: str = ""
    metadescription: str = ""

    def sha256(self) -> str:
        return recibo_sha256(self.corpo, self.seotitle, self.metadescription)

    def _lp(self) -> dict:
        try:
            dados = json.loads(self.corpo)
        except (ValueError, TypeError):
            return {}
        return dados if isinstance(dados, dict) else {}

    def campos(self) -> dict[str, str]:
        """{campo: texto} de tudo que o revisor lê E pode mandar mudar."""
        saida: dict[str, str] = {}
        if self.formato == "lp_json":
            lp = self._lp()
            for k in (*_CAMPOS_LP_SIMPLES, "intro"):
                if isinstance(lp.get(k), str):
                    saida[k] = lp[k]
            for nome, subs in (("sections", ("title", "body")), ("faq", ("q", "a"))):
                for i, item in enumerate(lp.get(nome) or []):
                    if isinstance(item, dict):
                        for sub in subs:
                            if isinstance(item.get(sub), str):
                                saida[f"{nome}[{i}].{sub}"] = item[sub]
            if isinstance(lp.get("transition"), str):
                saida["transition"] = lp["transition"]
            for i, cta in enumerate(lp.get("cta_texts") or []):
                if isinstance(cta, str):
                    saida[f"cta_texts[{i}]"] = cta
        else:
            saida["corpo"] = self.corpo
        saida["seotitle"] = self.seotitle
        saida["metadescription"] = self.metadescription
        return saida

    def texto(self, campo: str) -> str | None:
        if campo == "widget":
            return self.widget_texto()
        return self.campos().get(campo)

    def widget_texto(self) -> str:
        """O texto visível do widget (somente leitura para o revisor)."""
        if self.formato != "gutenberg":
            return ""
        blocos = [b for b in _RAW_HTML_RE.findall(self.corpo) if _SECTION_WIDGET_RE.search(b)]
        return "\n".join(_visivel(b) for b in blocos)

    def eh_rico(self, campo: str) -> bool:
        if self.formato == "gutenberg":
            return campo == "corpo"
        m = _CAMPO_LISTA_RE.match(campo)
        return campo in _CAMPOS_LP_RICOS or bool(m and m.group(3) in ("body",))

    def com(self, campo: str, novo: str) -> "Documento":
        if campo == "seotitle":
            return replace(self, seotitle=novo)
        if campo == "metadescription":
            return replace(self, metadescription=novo)
        if self.formato == "gutenberg":
            if campo != "corpo":
                raise KeyError(campo)
            return replace(self, corpo=novo)
        lp = self._lp()
        m = _CAMPO_LISTA_RE.match(campo)
        c = _CAMPO_CTA_RE.match(campo)
        if m:
            lp[m.group(1)][int(m.group(2))][m.group(3)] = novo
        elif c:
            lp["cta_texts"][int(c.group(1))] = novo
        elif campo in (*_CAMPOS_LP_SIMPLES, *_CAMPOS_LP_RICOS):
            lp[campo] = novo
        else:
            raise KeyError(campo)
        return replace(self, corpo=json.dumps(lp, ensure_ascii=False))


def documento_de(draft: Any, seo: dict | None) -> Documento:
    seo = seo or {}
    formato = "lp_json" if getattr(draft, "format", "") == "lp_json" else "gutenberg"
    return Documento(formato=formato,
                     corpo=draft.content, seotitle=str(seo.get("seotitle") or ""),
                     metadescription=str(seo.get("metadescription") or ""))


def hash_do_conteudo(state: Any, numero: int) -> str:
    """O sha256 do conteúdo ATUAL da página (é o que o recibo e a decisão humana
    precisam repetir)."""
    draft = state.drafts.get(numero)
    if draft is None:
        return ""
    return documento_de(draft, state.seo.get(numero)).sha256()


def gerar_recibo(doc: Documento, origem: str, **extra: Any) -> dict:
    return {"decisao": "aprovado", "origem": origem, "sha256": doc.sha256(),
            "politica": VERSAO, "criado_em": _agora(), **extra}


def conferir_recibo(state: Any, numero: int) -> Issue | None:
    """None quando o recibo existe, é `aprovado` e bate com o conteúdo atual."""
    recibo = (getattr(state, "recibos", {}) or {}).get(numero)
    if not recibo or recibo.get("decisao") != "aprovado":
        return Issue(code="recibo_ausente",
                     message=("Sem recibo de revisão aprovado para esta página: ela não "
                              "sobe ao WordPress (revisor ou decisão humana primeiro)."))
    atual = hash_do_conteudo(state, numero)
    if recibo.get("sha256") != atual:
        return Issue(code="recibo_divergente",
                     message=(f"O conteúdo mudou depois da revisão (recibo {recibo.get('sha256')}"
                              f" × atual {atual}): nada é publicado sem nova revisão."))
    if recibo.get("origem") != "humano" and recibo.get("trava_de_notas") != VERSAO_DA_TRAVA:
        return Issue(code="recibo_sem_trava_de_notas",
                     message=("Recibo do revisor emitido sem a trava das notas existenciais "
                              "(anterior a ela): nada é publicado sem a reconferência, que o "
                              "`resume` faz sozinho, ou a decisão humana."))
    return None


def decidir_pagina(state: Any, numero: int, *, decisao: str, sha256: str, nota: str = "",
                   quem: str = "operador", agora: str | None = None) -> dict:
    """Grava a decisão HUMANA sobre a página, presa ao sha256 do conteúdo atual.

    Recusa (ValueError) decisão fora de aprovar|rejeitar, página sem rascunho e
    hash que não é o do conteúdo atual — a pessoa aprova o que leu, não outra
    versão. Quem aplica a decisão é o pipeline, no próximo `resume`."""
    if decisao not in ("aprovar", "rejeitar"):
        raise ValueError("decisão deve ser 'aprovar' ou 'rejeitar'")
    if numero not in state.drafts:
        raise ValueError(f"a página {numero} não tem rascunho neste run")
    atual = hash_do_conteudo(state, numero)
    if (sha256 or "").strip().lower() != atual:
        raise ValueError(f"sha256 não confere com o conteúdo atual da página {numero}: "
                         f"o conteúdo atual é {atual}")
    registro = {"decisao": decisao, "sha256": atual, "nota": nota or "", "quem": quem or "",
                "quando": agora or _agora(),
                "revisor_tinha_decidido": (state.revisoes.get(numero) or {}).get("decisao")}
    state.decisoes_humanas[numero] = registro
    return registro


# ---------------------------------------------------------------------------
# o aviso canônico: posição estrutural ANTES da revisão (não regex depois)
# ---------------------------------------------------------------------------

def _eh_o_aviso(trecho: str) -> bool:
    return _visivel(trecho) == " ".join(COMPLIANCE_NOTICE_TEXT.split())


def posicionar_aviso_canonico(corpo: str) -> tuple[str, dict]:
    """Tira SÓ os parágrafos cujo texto é EXATAMENTE o aviso canônico e põe um
    rodapé canônico no fim. Parágrafo legítimo que menciona "utilidade pública"
    fica (a regex antiga da publicação apagava qualquer um). Idempotente."""
    removidos = 0

    def _tira(m: re.Match) -> str:
        nonlocal removidos
        if _eh_o_aviso(m.group(0)):
            removidos += 1
            return ""
        return m.group(0)

    bloco = re.compile(_PARAGRAFO_BLOCO_RE.pattern + r"[ \t]*\n*", re.I)
    sem = bloco.sub(_tira, corpo)
    solto = re.compile(_P_SOLTO_RE.pattern + r"[ \t]*\n*", re.I)
    sem = solto.sub(_tira, sem)
    novo = sem.rstrip() + "\n\n" + AVISO_CANONICO_BLOCK
    return novo, {"etapa": "aviso_canonico", "removidos": removidos, "acrescentado": True,
                  "alterou": novo != corpo, "sha256_antes": _sha(corpo),
                  "sha256_depois": _sha(novo)}


# ---------------------------------------------------------------------------
# achados
# ---------------------------------------------------------------------------

@dataclass
class Referencias:
    """O que EXISTE para ser citado como evidência (o resto é invenção)."""
    fatos: set[str] = field(default_factory=set)
    fatos_nao_citaveis: set[str] = field(default_factory=set)
    fontes: dict[str, str] = field(default_factory=dict)
    politicas_bloqueantes: set[str] = field(default_factory=set)
    politicas_nota: set[str] = field(default_factory=set)
    destinos: dict[str, str] = field(default_factory=dict)
    termos: set[str] = field(default_factory=set)
    paa: int = 0
    anuncio: int = 0


def _refs(valor: Any) -> list[str]:
    if isinstance(valor, str):
        return [v.strip() for v in re.split(r"[,;]", valor) if v.strip()]
    if isinstance(valor, (list, tuple)):
        return [str(v).strip() for v in valor if str(v).strip()]
    return []


def _ref_valida(tipo: str, ref: str, refs: Referencias) -> tuple[bool, str | None]:
    """(válida, rebaixamento) — rebaixamento = a evidência só sustenta nota."""
    sem_prefixo = ref.split(":", 1)[1] if ":" in ref and not ref.startswith("http") else ref
    if tipo == "fato":
        return sem_prefixo in refs.fatos, None
    if tipo == "fonte":
        return (sem_prefixo in refs.fontes or ref in refs.fontes.values()
                or ref.rstrip("/") in {u.rstrip("/") for u in refs.fontes.values()}), None
    if tipo == "politica":
        if sem_prefixo in refs.politicas_bloqueantes:
            return True, None
        if sem_prefixo in refs.politicas_nota:
            return True, "politica_classe_c"
        return False, None
    if tipo == "destino":
        alvos = {v.strip("/") for v in refs.destinos.values()}
        return (sem_prefixo in refs.destinos or ref.strip("/") in alvos), None
    if tipo == "intencao":
        if ref.startswith("termo:"):
            return ref[len("termo:"):].strip() in refs.termos, None
        if ref.startswith("paa:"):
            n = ref[len("paa:"):].strip()
            return n.isdigit() and 1 <= int(n) <= refs.paa, None
        if ref.startswith("anuncio:"):
            n = ref[len("anuncio:"):].strip()
            return n.isdigit() and 1 <= int(n) <= refs.anuncio, None
        return ref.startswith(("tensao", "briefing", "intencao")), None
    return bool(ref), None                                  # briefing, identidade


def _ref_resolvida(tipo: str, ref: str) -> bool:
    """B8/R5: o código consegue conferir a evidência contra algo que existe?
    `briefing`, `identidade` e a intenção genérica (tensao/briefing/intencao)
    aceitam qualquer ref: o achado vale (pode bloquear e mandar ao humano), mas
    NUNCA vira patch automático — é o caminho do re-achatamento (decisão 7)."""
    if tipo in ("briefing", "identidade"):
        return False
    if tipo == "intencao":
        return ref.startswith(("termo:", "paa:", "anuncio:"))
    return True


def validar_achados(achados: Any, doc: Documento, refs: Referencias) -> list[dict]:
    """Normaliza os achados do modelo. Achado com trecho que não existe no campo,
    campo inexistente ou evidência que não se resolve vira NOTA marcada
    `invalido` — o código não trata invenção como verdade. Estilo, oportunidade
    e política de classe C nunca passam de nota (`rebaixado`)."""
    saida: list[dict] = []
    for i, bruto in enumerate(achados if isinstance(achados, list) else [], start=1):
        if not isinstance(bruto, dict):
            continue
        evid = bruto.get("evidencia") if isinstance(bruto.get("evidencia"), dict) else {}
        a = {"id": str(bruto.get("id") or f"sem_id_{i}"),
             "severidade": str(bruto.get("severidade") or "").strip().lower(),
             "severidade_do_modelo": str(bruto.get("severidade") or "").strip().lower(),
             "categoria": str(bruto.get("categoria") or ""),
             "campo": str(bruto.get("campo") or ""),
             "trecho": str(bruto.get("trecho") or ""),
             "motivo": str(bruto.get("motivo") or ""),
             "evidencia": {"tipo": str(evid.get("tipo") or ""), "ref": evid.get("ref")},
             "invalido": None, "rebaixado": None, "sem_patch_automatico": None}
        texto = doc.texto(a["campo"])
        if a["severidade"] not in SEVERIDADES:
            a["invalido"] = "severidade_invalida"
        elif a["categoria"] not in CATEGORIAS:
            a["invalido"] = "categoria_invalida"
        elif texto is None:
            a["invalido"] = "campo_inexistente"
        elif not a["trecho"].strip() or a["trecho"] not in texto:
            a["invalido"] = "trecho_inexistente"
        elif not a["motivo"].strip():
            a["invalido"] = "motivo_ausente"
        elif a["evidencia"]["tipo"] not in TIPOS_DE_EVIDENCIA:
            a["invalido"] = "evidencia_invalida"
        else:
            lista = _refs(a["evidencia"]["ref"])
            if not lista:
                a["invalido"] = "evidencia_inexistente"
            for ref in lista:
                ok, rebaixo = _ref_valida(a["evidencia"]["tipo"], ref, refs)
                if not ok:
                    a["invalido"] = "evidencia_inexistente"
                    break
                if rebaixo:
                    a["rebaixado"] = rebaixo
                if not _ref_resolvida(a["evidencia"]["tipo"], ref):
                    a["sem_patch_automatico"] = "evidencia_nao_resolvivel"
        if (a["invalido"] is None and a["categoria"] in CATEGORIAS_SO_NOTA
                and a["severidade"] != "nota"):
            a["rebaixado"] = "estilo_nunca_bloqueia"
        if a["invalido"] or a["rebaixado"]:
            a["severidade"] = "nota"
        saida.append(a)
    return saida


def _patchavel(achado: dict | None) -> bool:
    return bool(achado and not achado.get("invalido") and not achado.get("rebaixado")
                and not achado.get("sem_patch_automatico")
                and achado["severidade"] in ("bloqueante", "ajuste")
                and achado["categoria"] not in CATEGORIAS_SO_NOTA)


# ---------------------------------------------------------------------------
# patches
# ---------------------------------------------------------------------------

@dataclass
class RegrasDePatch:
    numeros_permitidos: set[str] = field(default_factory=set)
    max_patches: int = MAX_PATCHES_POR_RODADA


def _sobrepoe(ini: int, fim: int, spans: list[tuple[int, int]]) -> bool:
    return any(ini < b and a < fim for a, b in spans)


def _spans(regex: re.Pattern, texto: str) -> list[tuple[int, int]]:
    return [m.span() for m in regex.finditer(texto)]


def _tags_nao_inline(texto: str) -> list[tuple[int, int]]:
    return [m.span() for m in _TAG_RE.finditer(texto) if m.group(1).lower() not in _TAGS_INLINE]


def _bloco_que_contem(texto: str, pos: int) -> str | None:
    """O bloco Gutenberg MAIS INTERNO aberto em `pos` (None fora de bloco)."""
    pilha: list[str] = []
    for m in _BLOCO_RE.finditer(texto):
        if m.start() >= pos:
            break
        if m.group(4) == "/":                                # bloco vazio auto-fechado
            continue
        nome = m.group(2).lower()
        if m.group(1) == "/":
            if nome in pilha:
                while pilha and pilha.pop() != nome:
                    pass
        else:
            pilha.append(nome)
    return pilha[-1] if pilha else None


def _regiao(doc: Documento, campo: str, texto: str, ini: int, fim: int) -> str | None:
    """Motivo de recusa quando [ini, fim) cai em região que o revisor não mexe."""
    protegidas = (_spans(_COMENTARIO_RE, texto) + _spans(_EXECUTAVEL_RE, texto)
                  + _tags_nao_inline(texto))
    if doc.formato == "gutenberg" and campo == "corpo":
        protegidas += _spans(_RAW_HTML_RE, texto) + _spans(_ASIDE_RE, texto)
        protegidas += [m.span() for m in _PARAGRAFO_BLOCO_RE.finditer(texto)
                       if COMPLIANCE_NOTICE_TEXT[:40] in m.group(0)]
    if _sobrepoe(ini, fim, protegidas):
        return "regiao_protegida"
    dentro_de_link = [(m.start(1), m.end(1)) for m in _LINK_RE.finditer(texto)
                      if m.start(1) <= ini and fim <= m.end(1)]
    if doc.formato == "gutenberg" and campo == "corpo":
        bloco = _bloco_que_contem(texto, ini)
        if bloco not in _BLOCOS_EDITAVEIS:
            return "fora_de_bloco_editavel"
        if bloco in _BLOCOS_DE_BOTAO:
            return None if dentro_de_link else "fora_de_bloco_editavel"
    if dentro_de_link:
        return "texto_de_link"
    return None


def _urls(texto: str) -> set[str]:
    return {m.group(0).lower() for m in _URL_RE.finditer(texto.translate(_PONTOS_DISFARCADOS))}


def _numeros_com_unidade(texto: str) -> list[tuple[str, str]]:
    """(dígitos, forma) de cada número: a forma guarda separadores, moeda e a
    palavra seguinte, para "R$ 1.518"→"R$ 15,18" e "30 dias"→"30 meses" não
    passarem por "mesmos dígitos"."""
    saida = []
    for m in _NUMERO_COM_UNIDADE_RE.finditer(texto):
        bruto = m.group(2).rstrip(".,")
        digitos = re.sub(r"\D", "", bruto).lstrip("0") or "0"
        forma = " ".join(((m.group(1) or "").strip() + " " + bruto + " "
                          + (m.group(3) or "").strip()).split()).lower()
        saida.append((digitos, forma))
    return saida


def _checar_numeros(antes: str, depois: str, regras: RegrasDePatch) -> str | None:
    if len(_NUMERO_POR_EXTENSO_RE.findall(depois)) > len(_NUMERO_POR_EXTENSO_RE.findall(antes)):
        return "numero_novo"
    if numeros(depois) - numeros(antes) - set(regras.numeros_permitidos):
        return "numero_novo"
    formas_antes = {f for _d, f in _numeros_com_unidade(antes)}
    for digitos, forma in _numeros_com_unidade(depois):
        if forma in formas_antes:
            continue
        # mesmos dígitos do trecho original em outra forma = magnitude/unidade trocada
        if digitos in numeros(antes) or any(d == digitos for d, _f in _numeros_com_unidade(antes)):
            return "numero_alterado"
    return None


def _checar_depois(antes: str, depois: str, rico: bool, regras: RegrasDePatch) -> str | None:
    if _urls(depois) - _urls(antes):
        return "url_nova"
    if re.search(r"<\s*a\b|href\s*=", depois, re.I):
        return "link_novo"
    if "<!--" in depois or "-->" in depois:
        return "tag_nao_permitida"
    tags = [t.lower() for t in re.findall(r"</?\s*([a-zA-Z][a-zA-Z0-9-]*)", depois)]
    if tags and (not rico or any(t not in _TAGS_INLINE for t in tags)):
        return "tag_nao_permitida"
    if any(not _TAG_INLINE_NUA_RE.match(t) for t in re.findall(r"<[^>]*>?", depois)):
        return "tag_nao_permitida"
    for t in ("strong", "em"):
        abre = len(re.findall(rf"<{t}\b", depois, re.I))
        if abre != len(re.findall(rf"</{t}\s*>", depois, re.I)):
            return "tag_nao_permitida"
    motivo_numero = _checar_numeros(antes, depois, regras)
    if motivo_numero:
        return motivo_numero
    if len(depois) > max(1.5 * len(antes), len(antes) + 200):
        return "tamanho_excedido"
    return None


def aplicar_patches(doc: Documento, patches: Any, achados: dict[str, dict],
                    regras: RegrasDePatch) -> tuple[Documento, list[dict], list[dict]]:
    """Aplica, em ordem, os patches que o código aceita. Devolve (documento,
    aplicados, recusados); cada recusa diz o motivo."""
    novo = doc
    aplicados: list[dict] = []
    recusados: list[dict] = []
    for i, bruto in enumerate(patches if isinstance(patches, list) else []):
        registro = ({k: str(bruto.get(k) or "") for k in ("achado", "campo", "antes", "depois")}
                    if isinstance(bruto, dict) else {"bruto": str(bruto)[:200]})

        def recusar(motivo: str) -> None:
            recusados.append({**registro, "estado": "recusado", "motivo": motivo})

        if not isinstance(bruto, dict):
            recusar("patch_invalido")
            continue
        if i >= regras.max_patches:
            recusar("limite_de_patches")
            continue
        campo, antes, depois = registro["campo"], registro["antes"], registro["depois"]
        if campo == "widget":
            recusar("campo_somente_leitura")
            continue
        texto = novo.campos().get(campo)
        if texto is None:
            recusar("campo_inexistente")
            continue
        achado = achados.get(registro["achado"])
        if achado is None:
            recusar("achado_inexistente")
            continue
        if not _patchavel(achado) or achado["campo"] != campo:
            recusar("achado_nao_patchavel")
            continue
        if not antes.strip():
            recusar("antes_vazio")
            continue
        n = texto.count(antes)
        if n == 0:
            recusar("antes_ausente")
            continue
        if n > 1:
            recusar("antes_duplicado")
            continue
        ini = texto.index(antes)
        motivo = _regiao(novo, campo, texto, ini, ini + len(antes))
        if motivo is None:
            motivo = _checar_depois(antes, depois, novo.eh_rico(campo), regras)
        if motivo is not None:
            recusar(motivo)
            continue
        novo = novo.com(campo, texto[:ini] + depois + texto[ini + len(antes):])
        aplicados.append({**registro, "estado": "aplicado"})
    return novo, aplicados, recusados


def assinatura_estrutural(doc: Documento) -> dict:
    """O que um patch NUNCA pode mudar: hrefs, comentários de bloco, widget."""
    if doc.formato == "gutenberg":
        return {"hrefs": _HREF_RE.findall(doc.corpo),
                "blocos": [m.group(0) for m in _BLOCO_RE.finditer(doc.corpo)],
                "widget": _RAW_HTML_RE.findall(doc.corpo)}
    lp = doc._lp()
    return {"chaves": sorted(lp), "secoes": len(lp.get("sections") or []),
            "faq": len(lp.get("faq") or []), "ctas": len(lp.get("cta_texts") or []),
            "hrefs": _HREF_RE.findall(doc.corpo)}


# ---------------------------------------------------------------------------
# as notas existenciais (a regra fail-closed do juiz V1)
# ---------------------------------------------------------------------------

def _papel_da_pagina(pagina: dict) -> PageRole:
    try:
        return PageRole(str(pagina.get("papel") or "").strip().upper())
    except ValueError:
        return derive_role(str(pagina.get("slug") or ""))


def criterios_existenciais(pagina: dict | None) -> tuple[str, ...]:
    """Os critérios cuja nota o código exige para aprovar, os MESMOS do juiz V1
    (`steps._judge_page`), lidos das mesmas fontes:
    `editorial: True` → `steps.EDITORIAL_EXISTENTIAL_CRITERIA`, sem subtrair nada
    pelo papel; `editorial: False` → `steps._existential_criteria_for(papel)`.
    Sem essa informação ou com valor que não é bool (revisão avulsa, contexto
    montado à mão) → o MAIS ESTRITO: a união dos dois conjuntos."""
    # import adiado: `steps` importa este módulo
    from funnelforge.pipeline import steps
    pagina = pagina if isinstance(pagina, dict) else {}
    editorial = pagina.get("editorial")
    if editorial is True:
        return tuple(steps.EDITORIAL_EXISTENTIAL_CRITERIA)
    do_papel = tuple(steps._existential_criteria_for(_papel_da_pagina(pagina)))
    if editorial is False:
        return do_papel
    return tuple(dict.fromkeys(tuple(steps.EDITORIAL_EXISTENTIAL_CRITERIA) + do_papel))


def _nota_valida(valor: Any) -> bool:
    """Número inteiro de 0 a 10 (7.0 conta como 7). O V1 recusa 7.5 (o `Verdict`
    não aceita fração), então aqui também."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return False
    if isinstance(valor, float) and not (math.isfinite(valor) and valor.is_integer()):
        return False
    return 0 <= valor <= 10


def _como_escrito(valor: Any) -> str:
    try:
        texto = json.dumps(valor, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        texto = repr(valor)
    return texto[:60]


def avaliar_notas_existenciais(notas: Any, criterios: tuple[str, ...]) -> dict:
    """Confere cada critério exigido: ausente, não numérico, fora de 0-10 ou
    abaixo da mínima vira `notas_existenciais_insuficientes:<criterio>=<valor>`.
    Nota ausente conta como reprovação, como no V1 (lá, ausente = 0)."""
    notas = notas if isinstance(notas, dict) else {}
    avaliadas: dict[str, Any] = {}
    ausentes: list[str] = []
    insuficientes: list[str] = []
    for criterio in criterios:
        if criterio not in notas:
            avaliadas[criterio] = None
            ausentes.append(criterio)
            insuficientes.append(f"{MOTIVO_NOTAS_INSUFICIENTES}:{criterio}=ausente")
            continue
        valor = notas[criterio]
        avaliadas[criterio] = valor
        if not _nota_valida(valor) or valor < NOTA_MINIMA_EXISTENCIAL:
            insuficientes.append(
                f"{MOTIVO_NOTAS_INSUFICIENTES}:{criterio}={_como_escrito(valor)}")
    return {"criterios": list(criterios), "minima": NOTA_MINIMA_EXISTENCIAL,
            "avaliadas": avaliadas, "ausentes": ausentes, "insuficientes": insuficientes}


def _notas_que_impedem(rod: dict) -> list[str]:
    return list((rod.get("notas_existenciais") or {}).get("insuficientes") or [])


def reconferir_notas_da_revisao(registro: dict, pagina: dict | None) -> dict:
    """A trava aplicada de novo às notas GRAVADAS numa revisão já feita (a da
    rodada 1, que é a única chamada). Serve à retomada de run revisado antes da
    trava: nenhuma chamada ao modelo, só as notas que ele devolveu na época."""
    rodadas = (registro or {}).get("rodadas") or []
    notas = rodadas[0].get("notas") if rodadas and isinstance(rodadas[0], dict) else None
    return avaliar_notas_existenciais(notas, criterios_existenciais(pagina))


def _objeto_da_resposta(texto: str) -> tuple[Any, bool]:
    """O JSON da resposta. Se ele só não parseia porque o modelo copiou o
    marcador `<0-10>` do exemplo, o marcador vira `null` (nota inválida) e o
    resto da resposta vale. Devolve (dados, marcador_copiado)."""
    try:
        return tolerant_json_object(texto), False
    except (ValueError, TypeError):
        if not _MARCADOR_DE_NOTA_RE.search(texto or ""):
            raise
    return tolerant_json_object(_MARCADOR_DE_NOTA_RE.sub(r"\1null", texto)), True


# ---------------------------------------------------------------------------
# o contexto e o prompt
# ---------------------------------------------------------------------------

@dataclass
class ContextoDaRevisao:
    """Tudo o que o revisor recebe, e as réguas que o código aplica."""
    pagina: dict
    briefing_texto: str = ""
    inventario_texto: str = ""
    origem: dict = field(default_factory=dict)
    destinos: list[dict] = field(default_factory=list)
    ctas: list[dict] = field(default_factory=list)
    termos: dict = field(default_factory=dict)
    identidade: dict = field(default_factory=dict)
    politicas: dict = field(default_factory=dict)
    localizadores: list[dict] = field(default_factory=list)
    referencias: Referencias = field(default_factory=Referencias)
    numeros_permitidos: set[str] = field(default_factory=set)
    revalidar: Callable[[Documento], list[Issue]] | None = None
    normalizar: Callable[[Documento], tuple[Documento, dict | None]] | None = None
    pacote_vencido: bool = False


_MARCA_DE_DADO_RE = re.compile(r"<\s*(/?)\s*dados_nao_confiaveis", re.I)


def _dado(tipo: str, texto: str) -> str:
    """Um bloco de DADO não confiável. Qualquer marca do bloco que venha dentro
    do dado é neutralizada — um texto de fonte não consegue fechar o bloco e
    falar como instrução."""
    limpo = _MARCA_DE_DADO_RE.sub(lambda m: "‹" + m.group(1) + "dados_nao_confiaveis",
                                  str(texto or ""))
    return f'<dados_nao_confiaveis tipo="{tipo}">\n{limpo}\n</dados_nao_confiaveis>'


def _texto_do_documento(doc: Documento) -> str:
    linhas = []
    for campo, valor in doc.campos().items():
        linhas.append(f"=== CAMPO {campo} ===\n{valor}")
    return "\n".join(linhas)


def _linhas_da_origem(origem: dict) -> str:
    linhas: list[str] = []
    for r in origem.get("rotas") or []:
        linhas.append(f"- vem de {r.get('de')} (\"{r.get('h1_de', '')}\"): rótulo planejado "
                      f"\"{r.get('rotulo_planejado', '')}\"; rótulo publicado "
                      f"\"{r.get('rotulo_publicado') or 'não disponível'}\"; motivo: "
                      f"{r.get('motivo') or 'não informado'}")
    if not linhas:
        linhas.append("- nenhuma rota do funil aponta para esta página")
    anuncio = origem.get("anuncio") or {}
    if anuncio.get("estado") == "presente":
        textos = list(anuncio.get("titulos") or []) + list(anuncio.get("descricoes") or [])
        linhas.append("ANÚNCIO QUE TRAZ O LEITOR (promessa a cumprir): " + " | ".join(textos))
    else:
        linhas.append(f"ANÚNCIO: ausente ({anuncio.get('motivo_ausencia') or 'não informado'})")
    return "\n".join(linhas)


def _linhas_dos_destinos(destinos: list[dict], ctas: list[dict]) -> str:
    linhas = ["DESTINOS PLANEJADOS (o que cada um entrega):"]
    for d in destinos:
        linhas.append(f"- {d.get('id')} [{d.get('tipo')}] {d.get('destino')} — "
                      f"\"{d.get('h1') or ''}\" — entrega: {d.get('entrega') or 'não declarada'}")
    if len(linhas) == 1:
        linhas.append("- nenhum destino planejado")
    linhas.append("BOTÕES ESCRITOS NA PÁGINA (rótulo → destino):")
    for c in ctas:
        linhas.append(f"- \"{c.get('rotulo')}\" → {c.get('href') or c.get('destino') or '?'}"
                      f" (destino {c.get('destino_id') or 'fora do plano'})")
    if not ctas:
        linhas.append("- nenhum botão encontrado")
    return "\n".join(linhas)


def _linhas_dos_termos(termos: dict) -> str:
    estado = termos.get("estado") or "ausente"
    if estado == "presente":
        return (f"TERMOS DE BUSCA OBSERVADOS (janela {termos.get('janela')}): "
                + ", ".join(f"\"{t}\"" for t in termos.get("amostra") or []))
    if estado == "vazio_confirmado":
        return f"TERMOS DE BUSCA: consulta feita em {termos.get('janela')}: 0 termos."
    return (f"TERMOS DE BUSCA: NÃO COLETADOS — {termos.get('motivo_ausencia') or 'sem motivo'}."
            " Não presuma termos.")


def _linhas_dos_localizadores(localizadores: list[dict]) -> str:
    if not localizadores:
        return "nenhum"
    return "\n".join(f"- [{loc.get('codigo')}] trecho \"{loc.get('trecho') or '?'}\": "
                     f"{loc.get('mensagem')}" for loc in localizadores)


def montar_prompt_do_revisor(doc: Documento, ctx: ContextoDaRevisao, *,
                             rodada: int = 1) -> str:
    """O prompt da ÚNICA chamada de revisão. `rodada` é aceito só por
    compatibilidade com `scripts/avaliar_revisor.py`; não muda o prompt."""
    blocos = {
        "texto": _dado("texto", _texto_do_documento(doc)),
        "widget": _dado("widget", doc.widget_texto() or "(esta página não tem widget)"),
        "briefing": _dado("briefing", ctx.briefing_texto or "BRIEFING AUSENTE."),
        "inventario": _dado("inventario", ctx.inventario_texto or "INVENTÁRIO AUSENTE."),
        "origem": _dado("origem", _linhas_da_origem(ctx.origem)),
        "destinos": _dado("destinos", _linhas_dos_destinos(ctx.destinos, ctx.ctas)),
        "termos": _dado("termos", _linhas_dos_termos(ctx.termos)),
        "localizadores": _dado("localizadores",
                               _linhas_dos_localizadores(ctx.localizadores)),
    }
    politicas = ctx.politicas or {}
    criterios = criterios_existenciais(ctx.pagina)
    return render(
        "revisor",
        pagina=ctx.pagina,
        criterios=criterios, nota_minima=NOTA_MINIMA_EXISTENCIAL,
        # sem número copiável: no canário o modelo devolveu o 0 do exemplo
        exemplo_de_notas="{" + ", ".join(f'"{c}": <0-10>' for c in criterios) + "}",
        blocos=blocos, campos=list(doc.campos()), tem_widget=bool(doc.widget_texto()),
        identidade=ctx.identidade or {},
        regras=politicas.get("regras") or [], notas_c=politicas.get("notas_c") or [],
        pacote=politicas.get("resumo") or {}, max_patches=MAX_PATCHES_POR_RODADA,
        compliance_notice_text=COMPLIANCE_NOTICE_TEXT,
        ha_termos=bool(ctx.referencias.termos),
    )


# ---------------------------------------------------------------------------
# a execução (rodadas, coerência, falha fechada)
# ---------------------------------------------------------------------------

@dataclass
class ResultadoDaRevisao:
    decisao: str
    documento: Documento
    registro: dict
    telemetria: StepResult


def revalidacao_basica(doc: Documento) -> list[Issue]:
    """Contratos objetivos que valem para qualquer conteúdo revisado."""
    issues: list[Issue] = []
    if doc.formato == "lp_json":
        try:
            dados = json.loads(doc.corpo)
        except (ValueError, TypeError):
            return [Issue(code="lp_schema", message="LP JSON ilegível depois do patch.")]
        issues += validate_lp_content(dados)
    else:
        issues += html_issues(doc.corpo)
        issues += run_validators(["gutenberg_blocks"], doc.corpo,
                                 {"allow_sanitized_widget_script": True})
    issues += run_validators(["seo_limits"], "", {"parsed": {
        "metadescription": doc.metadescription, "seotitle": doc.seotitle}})
    return separar_para_o_revisor(issues)[0]


def _somar(total: StepResult, parcial: StepResult | None) -> None:
    if parcial is None:
        return
    total.attempts += parcial.attempts
    total.prompt_tokens += parcial.prompt_tokens
    total.completion_tokens += parcial.completion_tokens
    total.cost_usd += parcial.cost_usd
    total.latency_ms += parcial.latency_ms
    if parcial.model_used:
        total.model_used = parcial.model_used


def _chave_da_issue(issue: Issue) -> tuple[str, str]:
    return issue.code, re.sub(r"\d+(?:[.,]\d+)*", "#", issue.message or "")


def _lista_de_dicts(valor: Any) -> list[dict]:
    return [v for v in valor if isinstance(v, dict)] if isinstance(valor, list) else []


def executar_revisao(doc: Documento, ctx: ContextoDaRevisao, *, runner: Any, cfg: StepConfig,
                     run_id: str, numero: int) -> ResultadoDaRevisao:
    """UMA chamada do revisor sobre `doc` e, se ele pedir ajuste, no máximo UMA
    rodada de patches aplicada pelo código, conferida só por validadores
    determinísticos (não há segunda chamada ao modelo). Nunca levanta: qualquer
    falha vira `revisao_humana` com o texto de entrada intacto e o erro gravado.
    Pacote de políticas vencido é alerta (`policy_pack_stale`), não motivo."""
    cfg = cfg.model_copy(update={"web_search": False, "validators": []})
    telemetria = StepResult(step=f"revisor_p{numero}", status=StepStatus.OK)
    registro: dict[str, Any] = {
        "versao": VERSAO, "pagina": numero, "decisao": None, "motivos": [], "erro": None,
        "sha256_entrada": doc.sha256(), "sha256": None, "rodadas": [],
        "pacote": (ctx.politicas or {}).get("resumo") or {"vencido": ctx.pacote_vencido},
        "localizadores": list(ctx.localizadores),
        "conteudo_de_entrada": doc.corpo,
        "seo_de_entrada": {"seotitle": doc.seotitle, "metadescription": doc.metadescription},
        "revisado_em": _agora(), "alertas": [],
    }
    if ctx.pacote_vencido:
        valido_ate = ((ctx.politicas or {}).get("resumo") or {}).get("valido_ate")
        registro["alertas"].append({
            "codigo": ALERTA_PACOTE_VENCIDO,
            "mensagem": (f"Pacote de políticas vencido (válido até {valido_ate or '?'}): a "
                         "revisão usou o pacote disponível; regenere com "
                         "scripts/gerar_pacote_revisor.py.")})

    def fechar(decisao: str, final: Documento, motivos: list[str],
               erro: str | None = None) -> ResultadoDaRevisao:
        registro["decisao"] = decisao
        registro["motivos"] = list(dict.fromkeys(registro["motivos"] + motivos))
        registro["erro"] = erro
        registro["sha256"] = final.sha256()
        telemetria.issues = [Issue(code=a["codigo"], message=a["mensagem"])
                             for a in registro["alertas"]]
        if decisao == "aprovado":
            telemetria.status = StepStatus.OK
        else:
            telemetria.status = StepStatus.FAILED
            telemetria.issues = list(telemetria.issues) + [Issue(
                code="revisao_humana",
                message=("Revisão não aprovou sozinha (" + ", ".join(registro["motivos"])
                         + (f"; erro: {erro}" if erro else "") + "). A página espera a "
                         "decisão humana: funnelforge decidir <run> --pagina "
                         f"{numero} --decisao aprovar|rejeitar --sha256 {registro['sha256']}"))]
        return ResultadoDaRevisao(decisao, final, registro, telemetria)

    try:
        prompt = montar_prompt_do_revisor(doc, ctx)
        nome = f"revisor_p{numero}"
        try:
            texto, res = runner.run_llm_step(
                nome, cfg, [{"role": "user", "content": prompt}], ctx={}, run_id=run_id)
        except LLMStepError as exc:
            _somar(telemetria, exc.step_result)
            return fechar("revisao_humana", doc, ["falha_do_provedor"], erro=exc.motivo)
        _somar(telemetria, res)
        try:
            dados, marcador_copiado = _objeto_da_resposta(texto)
        except (ValueError, TypeError) as exc:
            return fechar("revisao_humana", doc, ["json_ilegivel"],
                          erro=f"json_ilegivel: {type(exc).__name__}")
        if not isinstance(dados, dict):
            return fechar("revisao_humana", doc, ["json_ilegivel"],
                          erro="json_ilegivel: não é objeto")
        decisao = str(dados.get("decisao") or "").strip().lower()
        achados = validar_achados(dados.get("achados"), doc, ctx.referencias)
        afirmacoes_brutas = dados.get("afirmacoes_nao_verificadas")
        afirmacoes = _lista_de_dicts(afirmacoes_brutas)
        # B8/R1: afirmação não verificada em QUALQUER forma impede aprovar;
        # achados fora de lista é resposta fora do contrato (não "nenhum achado")
        fora_do_contrato = ((bool(afirmacoes_brutas) and not afirmacoes)
                            or (bool(dados.get("achados"))
                                and not isinstance(dados.get("achados"), list)))
        patches = dados.get("patches") if isinstance(dados.get("patches"), list) else []
        rod: dict[str, Any] = {
            "rodada": 1, "decisao_do_modelo": decisao, "decisao_efetiva": None,
            "achados": achados, "afirmacoes_nao_verificadas": afirmacoes,
            "patches_propostos": patches, "patches_aplicados": [], "patches_recusados": [],
            "preservado": (dados.get("preservado")
                           if isinstance(dados.get("preservado"), list) else []),
            "notas": dados.get("notas") if isinstance(dados.get("notas"), dict) else {},
            "revalidacao": [], "normalizacao": None,
            # as notas descrevem o texto ANTES de qualquer patch
            "notas_existenciais": avaliar_notas_existenciais(
                dados.get("notas"), criterios_existenciais(ctx.pagina)),
        }
        if marcador_copiado:
            rod["marcador_de_nota_copiado"] = True
        registro["rodadas"].append(rod)
        if decisao not in DECISOES:
            return fechar("revisao_humana", doc, ["decisao_invalida"])
        if fora_do_contrato:
            rod["afirmacoes_nao_verificadas_brutas"] = str(afirmacoes_brutas)[:2000]
            return fechar("revisao_humana", doc, ["json_fora_do_contrato"])
        # B8/R3: a severidade DECLARADA pelo modelo conta — um bloqueante
        # rebaixado por evidência inválida não vira patch e fica pendente.
        bloqueantes_brutos = [a for a in achados if a["severidade_do_modelo"] == "bloqueante"]
        bloqueantes = [a for a in achados if a["severidade"] == "bloqueante"]
        no_widget = [f"bloqueante_em_widget:{a['id']}" for a in bloqueantes
                     if a["campo"] == "widget"]
        if no_widget:
            return fechar("revisao_humana", doc, no_widget)
        if decisao == "aprovado" and patches:
            decisao = "ajustar"
            rod["normalizacao_da_decisao"] = "aprovado_com_patches_tratado_como_ajustar"
        rod["decisao_efetiva"] = decisao
        if decisao == "revisao_humana":
            return fechar("revisao_humana", doc, ["decidido_pelo_revisor"])
        if decisao == "aprovado":
            if afirmacoes:
                return fechar("revisao_humana", doc, ["aprovado_com_afirmacao_nao_verificada"])
            if bloqueantes_brutos:
                return fechar("revisao_humana", doc, ["aprovado_com_bloqueante"])
            insuficientes = _notas_que_impedem(rod)
            if insuficientes:
                return fechar("revisao_humana", doc, insuficientes)
            return fechar("aprovado", doc, [])
        # "ajustar": a ÚNICA rodada de microajuste, aplicada pelo código. Não há
        # segunda chamada de revisão: o resultado é conferido só pelos
        # validadores determinísticos e pela regra "todo bloqueante resolvido".
        novo, aplicados, recusados = aplicar_patches(
            doc, patches, {a["id"]: a for a in achados},
            RegrasDePatch(numeros_permitidos=set(ctx.numeros_permitidos)))
        rod["patches_aplicados"], rod["patches_recusados"] = aplicados, recusados
        if not aplicados:
            return fechar("revisao_humana", doc, ["nenhum_patch_aplicado"])
        if assinatura_estrutural(novo) != assinatura_estrutural(doc):
            return fechar("revisao_humana", doc, ["estrutura_alterada"])
        if ctx.normalizar is not None:
            normalizado, reg = ctx.normalizar(novo)
            rod["normalizacao"] = reg
            if _HREF_RE.findall(normalizado.corpo) != _HREF_RE.findall(novo.corpo):
                return fechar("revisao_humana", doc, ["estrutura_alterada"])
            novo = normalizado
        revalidar = ctx.revalidar or revalidacao_basica
        # Só reprova o que o PATCH introduziu. A chave ignora números da
        # mensagem ("Jaccard 0.75" × "0.76" é a MESMA reprovação).
        ja_havia = {_chave_da_issue(i) for i in revalidar(doc)}
        novas = [i for i in revalidar(novo) if _chave_da_issue(i) not in ja_havia]
        rod["revalidacao"] = [i.model_dump() for i in novas]
        if novas:
            return fechar("revisao_humana", doc, ["revalidacao_reprovou"])
        pendentes = []
        for a in bloqueantes_brutos:
            dele = [p for p in aplicados if p["achado"] == a["id"]]
            resolvido = bool(dele) and all(
                p["antes"] not in (novo.texto(p["campo"]) or "") for p in dele)
            if not resolvido:
                pendentes.append(f"bloqueante_nao_resolvido:{a['id']}")
        # afirmação sem fato só sai da lista se o trecho dela sumiu do campo
        for i, af in enumerate(afirmacoes, 1):
            trecho = str(af.get("trecho") or "").strip()
            campo = str(af.get("campo") or "")
            onde = ([novo.texto(campo) or ""] if novo.texto(campo) is not None
                    else list(novo.campos().values()))
            if not trecho or any(trecho in t for t in onde):
                pendentes.append(f"afirmacao_nao_verificada_restante:{i}")
        # as notas são da rodada 1 (texto ANTES do patch) e não há segunda
        # chamada: nada prova que o patch resolveu a nota baixa — vai à pessoa
        notas_baixas = _notas_que_impedem(rod)
        if notas_baixas and not pendentes:
            # o patch passou em tudo o que o código confere; só a trava o retém.
            # Ele segue registrado como PROPOSTA para a pessoa decidir.
            rod["retida_pela_trava_de_notas"] = True
        pendentes += notas_baixas
        if pendentes:
            return fechar("revisao_humana", doc, pendentes)
        rod["mantida"] = True
        return fechar("aprovado", novo, [])
    except OrcamentoEstourado:
        raise                  # o teto de gasto é do pipeline: ele registra e para
    except Exception as exc:  # noqa: BLE001 - revisão nunca derruba o pipeline: fecha
        return fechar("revisao_humana", doc, ["excecao_na_revisao"],
                      erro=f"{type(exc).__name__}: {str(exc)[:300]}")
