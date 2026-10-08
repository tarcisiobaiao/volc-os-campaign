"""`chatgpt_plan_web_search`: a pesquisa do DOSSIÊ com web_search na Responses
API, autenticada pelo plano ChatGPT. Só este passo — o `OpenAIResponsesClient`
continua recusando `web_search` (`NaoSuportadoNoPlano`) em qualquer outra
chamada.

Reusa do cliente do motor: credencial, refresh, cabeçalhos e transporte HTTP.
Contrato próprio:

1. PESQUISA GROUNDED (web_search obrigatório, reasoning low): resposta curta,
   com `url_citation` por frase. O resultado é montado DOS EVENTOS do stream —
   neste servidor `response.completed.output` chega vazio (provado em
   07/10/2026); do `completed` só saem id, status, modelo e uso.
2. EVIDÊNCIAS: cada `url_citation` ancora o trecho de texto imediatamente
   anterior a ela → evidência `eN` com as URLs (canônicas) que a sustentam.
   `sources` = páginas consultadas; nunca viram fato sozinhas.
3. ESTRUTURAÇÃO (mesma autenticação, sem web_search, Structured Output
   estrito): recebe só o texto grounded, as evidências, as sources e os
   requisitos; cada fato aponta para um `evidencia_id`. O schema NÃO tem campo
   de URL: a fonte do fato é a URL citada da evidência, posta pelo código.
4. CONFERÊNCIA PELO CÓDIGO: evidência existe; afirmação sustentada pelo
   trecho; valor e ano da vigência presentes no trecho; requisitos e páginas
   do spec; conteúdo da página citada (lida ao vivo) confirma o valor/termos.
   O que falha não vira fato verificado — vai com o motivo.

Custo: o servidor não devolve preço neste modo — fica NÃO INFORMADO, nunca
US$ 0,00 como se fosse cobrança comprovada.
"""
from __future__ import annotations

import html as _html
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from funnelforge.config.settings import PREFIXO_DO_PLANO, StepConfig

AUTH_MODE = "chatgpt_plan"
RASTREIO = frozenset({"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                      "gclid", "fbclid", "msclkid"})
MAX_TOKENS_DA_PESQUISA = 2500
MAX_TOKENS_DA_ESTRUTURACAO = 4000
SOBREPOSICAO_MINIMA = 0.5        # termos da afirmação presentes no trecho citado
SOBREPOSICAO_NA_PAGINA = 0.4     # termos da afirmação presentes na página lida


def canonica(url: str | None) -> str:
    """Tira SÓ parâmetros de rastreio conhecidos; query funcional fica."""
    if not url:
        return ""
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if k.lower() not in RASTREIO]
    return urlunparse(p._replace(query=urlencode(q, doseq=True)))


def _chave(url: str) -> str:
    return canonica(url).rstrip("/")


# ---------------------------------------------------------------------------
# 1. montagem do stream
# ---------------------------------------------------------------------------

@dataclass
class Busca:
    item_id: str
    output_index: int | None
    status: str = ""
    eventos: list[str] = field(default_factory=list)
    action_type: str = ""
    queries: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)      # {url, titulo}


@dataclass
class Citacao:
    item_id: str
    content_index: int | None
    annotation_index: int | None
    url: str
    titulo: str | None
    inicio: int | None
    fim: int | None


@dataclass
class RespostaMontada:
    response_id: str = ""
    status: str = ""
    modelo: str = ""
    uso: dict = field(default_factory=dict)
    buscas: list[Busca] = field(default_factory=list)
    partes: list[dict] = field(default_factory=list)       # {item_id, content_index, texto}
    citacoes: list[Citacao] = field(default_factory=list)
    eventos: dict = field(default_factory=dict)
    falha: str = ""
    completed: bool = False
    output_no_completed: int = 0

    @property
    def texto(self) -> str:
        return "\n".join(p["texto"] for p in self.partes if p["texto"])


def _numeros(d: dict) -> dict:
    saida = {}
    for k, v in (d or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            saida[k] = v
        elif isinstance(v, dict):
            saida[k] = _numeros(v)
    return saida


def montar_stream(linhas: Iterable[str]) -> RespostaMontada:
    """Monta a resposta a partir dos EVENTOS, correlacionados por item_id,
    output_index, content_index e annotation_index."""
    r = RespostaMontada()
    itens: dict[str, dict] = {}
    ordem: list[str] = []
    textos: dict[tuple, dict] = {}
    anot: dict[tuple, dict] = {}
    for linha in linhas:
        if not linha or not linha.startswith("data:"):
            continue
        dado = linha[5:].strip()
        if dado == "[DONE]":
            break
        try:
            ev = json.loads(dado)
        except ValueError:
            continue
        t = str(ev.get("type", "?"))
        r.eventos[t] = r.eventos.get(t, 0) + 1
        item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
        iid = str(ev.get("item_id") or item.get("id") or "")
        if t in ("response.output_item.added", "response.output_item.done"):
            reg = itens.setdefault(iid, {"output_index": ev.get("output_index"),
                                         "type": item.get("type"), "eventos": []})
            reg["done" if t.endswith("done") else "added"] = item
            if iid not in ordem:
                ordem.append(iid)
        elif t.startswith("response.web_search_call."):
            reg = itens.setdefault(iid, {"output_index": ev.get("output_index"),
                                         "type": "web_search_call", "eventos": []})
            reg["eventos"].append(t.rsplit(".", 1)[1])
            if iid not in ordem:
                ordem.append(iid)
        elif t == "response.output_text.delta":
            textos.setdefault((iid, ev.get("content_index")), {"deltas": [], "done": None}
                              )["deltas"].append(str(ev.get("delta", "")))
        elif t == "response.output_text.done":
            textos.setdefault((iid, ev.get("content_index")), {"deltas": [], "done": None}
                              )["done"] = ev.get("text")
        elif t == "response.output_text.annotation.added":
            anot[(iid, ev.get("content_index"), ev.get("annotation_index"))] = (
                ev.get("annotation") or {})
        elif t == "response.completed":
            final = ev.get("response") or {}
            r.completed = True
            r.response_id = str(final.get("id") or "")
            r.status = str(final.get("status") or "")
            r.modelo = str(final.get("model") or "")
            r.uso = _numeros(final.get("usage") or {})
            r.output_no_completed = len(final.get("output") or [])
            break
        elif t in ("response.failed", "response.incomplete", "error"):
            bruto = ev.get("response") if isinstance(ev.get("response"), dict) else ev
            erro = bruto.get("error") or bruto.get("incomplete_details") or {"code": t}
            r.falha = f"{t}: {json.dumps(erro, ensure_ascii=False)[:300]}"
            break
    for iid in ordem:
        reg = itens[iid]
        item = reg.get("done") or reg.get("added") or {}
        if reg["type"] == "web_search_call":
            acao = item.get("action") or {}
            r.buscas.append(Busca(
                item_id=iid, output_index=reg["output_index"],
                status=str(item.get("status") or (reg["eventos"][-1] if reg["eventos"] else "")),
                eventos=list(reg["eventos"]), action_type=str(acao.get("type") or ""),
                queries=[str(q) for q in (acao.get("queries")
                                           or ([acao["query"]] if acao.get("query") else []))],
                sources=[{"url": canonica(s.get("url")), "titulo": s.get("title")}
                         for s in (acao.get("sources") or []) if s.get("url")]))
        elif reg["type"] == "message":
            indices = sorted({ci for (i2, ci) in textos if i2 == iid},
                             key=lambda x: (x is None, x))
            for ci in indices:
                t = textos[(iid, ci)]
                r.partes.append({"item_id": iid, "content_index": ci,
                                 "texto": t["done"] if t["done"] is not None
                                 else "".join(t["deltas"])})
                for (i2, c2, ai), a in sorted(anot.items(), key=lambda kv: (kv[0][2] or 0)):
                    if i2 == iid and c2 == ci and a.get("type") == "url_citation":
                        r.citacoes.append(Citacao(
                            item_id=iid, content_index=ci, annotation_index=ai,
                            url=canonica(a.get("url")), titulo=a.get("title"),
                            inicio=a.get("start_index"), fim=a.get("end_index")))
    return r


# ---------------------------------------------------------------------------
# 2. evidências ancoradas por citação
# ---------------------------------------------------------------------------

@dataclass
class Evidencia:
    id: str
    trecho: str
    urls: list[str]
    titulos: list[str]
    inicio: int
    fim: int
    na_source: list[bool]


_LINK_MD = re.compile(r"\(?\[[^\]]*\]\([^)]*\)\)?")


def evidencias(resp: RespostaMontada) -> tuple[list[Evidencia], list[str]]:
    """Cada url_citation sustenta o trecho logo antes dela (desde a citação
    anterior). Posição fora do texto é defeito, não é ignorada."""
    fontes = {_chave(s["url"]) for b in resp.buscas for s in b.sources}
    saida: list[Evidencia] = []
    defeitos: list[str] = []
    for parte in resp.partes:
        texto = parte["texto"]
        cits = [c for c in resp.citacoes
                if c.item_id == parte["item_id"] and c.content_index == parte["content_index"]]
        cits.sort(key=lambda c: (c.inicio if isinstance(c.inicio, int) else -1))
        cursor = 0
        for c in cits:
            if not (isinstance(c.inicio, int) and isinstance(c.fim, int)
                    and 0 <= c.inicio < c.fim <= len(texto)):
                defeitos.append(f"url_citation {c.annotation_index} com posição fora do texto "
                                f"({c.inicio}..{c.fim} em {len(texto)} caracteres)")
                continue
            trecho = _LINK_MD.sub(" ", texto[cursor:c.inicio])
            trecho = re.sub(r"\s+", " ", trecho).strip(" ;,\n")
            if not trecho and saida and saida[-1].fim == cursor:
                ev = saida[-1]                        # duas citações para a mesma frase
                ev.urls.append(c.url)
                ev.titulos.append(c.titulo or "")
                ev.na_source.append(_chave(c.url) in fontes)
            elif trecho:
                saida.append(Evidencia(id=f"e{len(saida) + 1}", trecho=trecho, urls=[c.url],
                                       titulos=[c.titulo or ""], inicio=cursor, fim=c.fim,
                                       na_source=[_chave(c.url) in fontes]))
            cursor = c.fim
    return saida, defeitos


# ---------------------------------------------------------------------------
# 4. conferência textual
# ---------------------------------------------------------------------------

_PALAVRAS_NUMERO = {"um": "1", "uma": "1", "dois": "2", "duas": "2", "tres": "3", "quatro": "4",
                    "cinco": "5", "seis": "6", "sete": "7", "oito": "8", "nove": "9", "dez": "10"}
_VAZIAS = frozenset("para pela pelo pelos pelas como mais menos entre sobre onde quando quem "
                    "esta este essa esse isso aqui cada todo toda todos todas seus suas deve "
                    "pode podem sera serao foram desde atraves tambem apenas ainda".split())


def _normal(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9,. ]+", " ", t)


def _termos(texto: str) -> set[str]:
    return {p[:6] for p in _normal(texto).replace(",", " ").replace(".", " ").split()
            if len(p) > 3 and p not in _VAZIAS}


_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")


def _numeros_de(texto: str) -> set[float]:
    from funnelforge.domain.dossie import numeros_do_texto
    return numeros_do_texto(texto)


def _valor_presente(valor: str, texto: str) -> bool:
    """O valor está no texto? Compara os NÚMEROS do valor pelo valor numérico —
    o canário real de 07/10 reprovou "até 2" contra "até 02 (dois) salários"
    por comparar a string inteira. Valor sem número: comparação textual."""
    if not valor.strip():
        return True
    numeros = _numeros_de(valor)
    if numeros:
        return numeros <= _numeros_de(texto)
    return _normal(valor).strip() in _normal(texto)


_MESES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro")


def data_no_trecho(iso: str, trecho: str) -> bool:
    """A data ISO inteira (dia, mês e ano) está no trecho? '2026-01-14' casa com
    '14/01/2026', '14.01.2026', '2026-01-14' ou '14 de janeiro de 2026'. Só o
    ano no trecho NÃO vale: o canário real recebeu '2026-01-01' para "em 2026"."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", (iso or "").strip()[:10])
    if not m:
        return False
    ano, mes, dia = m.groups()
    t = unicodedata.normalize("NFKD", trecho or "").encode("ascii", "ignore").decode().lower()
    d, mm = int(dia), int(mes)
    padroes = [rf"\b0?{d}[/.-]0?{mm}[/.-]{ano}\b", rf"\b{ano}-{mes}-{dia}\b",
               rf"\b0?{d}o? de {_MESES[mm - 1]} de {ano}\b"]
    return any(re.search(p, t) for p in padroes)


def sustentado(afirmacao: str, valor: str, trecho: str,
               minimo: float = SOBREPOSICAO_MINIMA) -> str:
    """'' quando o trecho sustenta a afirmação; senão, o motivo."""
    if not _valor_presente(valor, trecho):
        return f"valor '{valor}' não aparece no trecho citado"
    termos = _termos(afirmacao)
    if termos and len(termos & _termos(trecho)) / len(termos) < minimo:
        return "afirmação sem lastro suficiente no trecho citado"
    return ""


# ---------------------------------------------------------------------------
# 3. estruturação (schema estrito, sem URL)
# ---------------------------------------------------------------------------

def schema_da_estruturacao(tipos: list[str]) -> dict:
    texto = {"type": "string"}
    lista = {"type": "array", "items": {"type": "string"}}
    fato = {"type": "object", "additionalProperties": False,
            "properties": {"evidencia_id": texto, "afirmacao": texto,
                           "tipo": {"type": "string", "enum": list(tipos)}, "valor": texto,
                           "unidade": texto, "vigente_desde": texto, "dispositivo": texto,
                           "paginas": lista, "requisitos": lista}}
    fato["required"] = list(fato["properties"])
    return {"type": "object", "additionalProperties": False, "required": ["fatos"],
            "properties": {"fatos": {"type": "array", "items": fato}}}


def _prompt_da_pesquisa(assunto: str, paginas: list[dict], faltantes: list[dict] | None,
                        hoje: str) -> str:
    if faltantes:
        alvo = "\n".join(f"- [{f['duvida_id']}] {f['requisito']}: {f['descricao']}"
                         for f in faltantes)
        pedido = f"Pesquise SOMENTE estes requisitos, que ainda não têm fonte:\n{alvo}"
    else:
        alvo = "\n".join(f"- [{p['duvida_id']}] {r['id']}: {r['descricao']}"
                         for p in paginas for r in p.get("requisitos") or [])
        pedido = f"Requisitos a provar:\n{alvo}"
    return (f"Hoje é {hoje}. Pesquise na web, priorizando páginas oficiais, fatos atuais "
            f"sobre: {assunto}.\n{pedido}\n\n"
            "Responda com UMA frase curta por requisito, com palavras próprias (sem "
            "reproduzir trechos longos literalmente), começando por [id_do_requisito]. Cada "
            "frase traz o valor e a unidade quando houver número, e a data ou o ano de "
            "vigência/publicação que a fonte declara. Cite a fonte oficial em cada frase. "
            "Se não achar fonte para um requisito, diga isso em vez de supor.")


def _prompt_da_estruturacao(texto: str, evs: list[Evidencia], fontes: list[dict],
                            paginas: list[dict]) -> str:
    lista = "\n".join(f"- {e.id}: {e.trecho} (fonte: {', '.join(e.urls)})" for e in evs)
    reqs = "\n".join(f"- página {p['duvida_id']}: requisito {r['id']} — {r['descricao']} "
                     f"(tipos: {', '.join(r['tipos'])})"
                     for p in paginas for r in p.get("requisitos") or [])
    consultadas = "\n".join(f"- {s['url']}" for s in fontes[:40])
    return ("Transforme em fatos do dossiê SOMENTE as evidências abaixo, já pesquisadas e "
            "citadas. Regras: cada fato aponta para UM evidencia_id da lista; a afirmação "
            "parafraseia aquele trecho e não acrescenta nada; valor e unidade só se estiverem "
            "no trecho; vigente_desde só com a data que está no trecho, convertida para "
            "AAAA-MM-DD (ex.: '14/01/2026' -> '2026-01-14'; '19 de março de 2026' -> "
            "'2026-03-19'); trecho só com mês/ano ou sem data -> vazio; paginas e requisitos só dos ids listados. Não crie fato, número ou "
            "fonte. Evidência que não sustenta requisito nenhum fica de fora.\n\n"
            f"EVIDÊNCIAS:\n{lista}\n\nREQUISITOS:\n{reqs}\n\n"
            f"PÁGINAS CONSULTADAS (contexto; não são evidência):\n{consultadas}\n\n"
            f"TEXTO PESQUISADO:\n{texto}")


# ---------------------------------------------------------------------------
# leitura da página citada (conferência de conteúdo)
# ---------------------------------------------------------------------------

def ler_pagina(url: str, timeout_s: float = 20.0) -> tuple[str, str]:
    """(texto, motivo) — texto vazio + motivo quando não dá para conferir."""
    import httpx
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
    try:
        r = httpx.get(url, headers={"User-Agent": ua}, timeout=timeout_s, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        return "", f"página não lida ({type(exc).__name__})"
    if r.status_code != 200:
        return "", f"página respondeu HTTP {r.status_code}"
    tipo = r.headers.get("content-type", "").lower()
    if "pdf" in tipo or url.lower().split("?")[0].endswith(".pdf"):
        try:
            import io

            from pypdf import PdfReader
            leitor = PdfReader(io.BytesIO(r.content))
            return " ".join((p.extract_text() or "") for p in leitor.pages[:30]), ""
        except Exception as exc:  # noqa: BLE001
            return "", f"PDF não legível ({type(exc).__name__})"
    texto = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
    return _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", texto))), ""


# ---------------------------------------------------------------------------
# a rodada
# ---------------------------------------------------------------------------

def _plano(llm: Any):
    plano = getattr(llm, "plano", None)
    if plano is None:
        raise RuntimeError("chatgpt_plan_web_search sem sessão do plano: configure "
                           "openai.auth_mode=chatgpt_plan e faça o login")
    return plano


def _requisitar(plano: Any, body: dict, contar: Callable[[str], None] | None,
                modelo: str) -> tuple[RespostaMontada | None, dict, int]:
    """UM POST. Sem retentativa, sem renovação forçada com reenvio."""
    from funnelforge.adapters.openai_responses import RESPONSES_URL, _codigo
    if contar is not None:
        contar(modelo)
    inicio = time.perf_counter()
    resp = plano._enviar(RESPONSES_URL, plano._cabecalhos(), body, plano.timeout_s)
    if resp.status != 200:
        erro = resp.corpo.get("error") if isinstance(resp.corpo.get("error"), dict) else resp.corpo
        recusa = {"status": resp.status, "codigo": _codigo(resp.corpo),
                  "mensagem": str((erro or {}).get("message") or "")[:300]}
        return None, recusa, int((time.perf_counter() - inicio) * 1000)
    montada = montar_stream(resp.linhas)
    return montada, {}, int((time.perf_counter() - inicio) * 1000)


def _recibo(nome: str, m: RespostaMontada | None, recusa: dict, latencia: int) -> dict:
    if m is None:
        return {"chamada": nome, "auth_mode": AUTH_MODE, "recusa": recusa, "latencia_ms": latencia}
    return {"chamada": nome, "auth_mode": AUTH_MODE, "response_id": m.response_id,
            "status": m.status, "modelo_servido": m.modelo, "completed": m.completed,
            "falha": m.falha, "output_no_completed": m.output_no_completed,
            "eventos": m.eventos, "uso": m.uso, "latencia_ms": latencia,
            "web_search_calls": [b.__dict__ for b in m.buscas],
            "url_citations": [c.__dict__ for c in m.citacoes],
            "texto_devolvido": m.texto[:4000], "custo_retornado_pelo_servidor": None}


def _defeito_da_chamada(m: RespostaMontada | None, recusa: dict, slug: str,
                        exige_busca: bool) -> str:
    from funnelforge.adapters.openai_responses import _base
    if m is None:
        return (f"Responses API recusou ({recusa.get('status')} {recusa.get('codigo')}): "
                f"{recusa.get('mensagem', '')}").strip()
    if m.falha:
        return m.falha
    if not m.completed:
        return "stream terminou sem response.completed"
    if _base(m.modelo) != _base(slug):
        return f"modelo trocado pelo servidor: pedido {slug}, servido {m.modelo}"
    if exige_busca:
        if not m.buscas:
            return "nenhum web_search_call: a busca não foi feita"
        if any(b.status != "completed" for b in m.buscas):
            return "web_search_call sem status completed"
        if not m.citacoes:
            return "resposta sem url_citation: nada sustenta trecho algum"
    if not m.texto.strip():
        return "texto vazio"
    return ""


def pesquisar_dossie_plano(llm: Any, cfg: StepConfig, assunto: str, paginas: list[dict],
                           faltantes: list[dict] | None = None, *,
                           ler: Callable[[str], tuple[str, str]] = ler_pagina,
                           hoje: str | None = None):
    """Uma rodada do dossiê pelo `chatgpt_plan_web_search` -> `RespostaDaPesquisa`."""
    from datetime import date

    from funnelforge.adapters.research_perplexity import _VOCABULARIO_DE_TIPOS
    from funnelforge.pipeline.dossie import RespostaDaPesquisa

    plano = _plano(llm)
    contar = getattr(llm, "_contar", None)
    slug = cfg.model.removeprefix(PREFIXO_DO_PLANO)
    esforco = cfg.reasoning_effort or "low"
    hoje = hoje or date.today().strftime("%d/%m/%Y")
    ferramenta: dict = {"type": "web_search", "search_context_size": "low",
                        "external_web_access": True}
    if cfg.dominios_permitidos:
        ferramenta["filters"] = {"allowed_domains": list(cfg.dominios_permitidos)}
    body = {"model": slug, "store": False, "stream": True,
            "reasoning": {"effort": esforco}, "max_output_tokens": MAX_TOKENS_DA_PESQUISA,
            "tools": [ferramenta], "tool_choice": "required",
            "include": ["web_search_call.action.sources"],
            "input": [{"role": "user",
                       "content": _prompt_da_pesquisa(assunto, paginas, faltantes, hoje)}]}
    metas: list[dict] = []

    def resposta(defeito: str, dados: dict | None = None, citacoes: list[str] | None = None):
        uso = [m.get("uso") or {} for m in metas]
        return RespostaDaPesquisa(
            dados=dados or {"fatos": []}, citacoes=citacoes or [], modelo_pedido=cfg.model,
            modelo_servido=next((m.get("modelo_servido") for m in metas
                                 if m.get("modelo_servido")), ""),
            auth_mode=AUTH_MODE,
            prompt_tokens=sum(int(u.get("input_tokens") or 0) for u in uso),
            completion_tokens=sum(int(u.get("output_tokens") or 0) for u in uso),
            custo_usd=0.0, custo_informado=False,
            latencia_ms=sum(int(m.get("latencia_ms") or 0) for m in metas),
            consultas_de_busca=sum(len(b.get("queries") or []) for m in metas
                                   for b in m.get("web_search_calls") or []),
            finish_reason=str(metas[-1].get("status") or "") if metas else "",
            defeito=defeito, metadados=metas)

    m1, recusa, lat = _requisitar(plano, body, contar, cfg.model)
    metas.append(_recibo("pesquisa_com_web_search", m1, recusa, lat))
    defeito = _defeito_da_chamada(m1, recusa, slug, exige_busca=True)
    evs, defeitos = evidencias(m1) if m1 is not None and not defeito else ([], [])
    if not defeito and defeitos:
        defeito = defeitos[0]
    if not defeito and not evs:
        defeito = "nenhuma evidência ancorada por url_citation"
    metas[-1]["evidencias"] = [e.__dict__ for e in evs]
    if defeito:
        return resposta(defeito)

    fontes = [s for b in m1.buscas for s in b.sources]
    tipos = [t for t, _ in _VOCABULARIO_DE_TIPOS]
    body2 = {"model": slug, "store": False, "stream": True,
             "reasoning": {"effort": esforco}, "max_output_tokens": MAX_TOKENS_DA_ESTRUTURACAO,
             "text": {"format": {"type": "json_schema", "name": "fatos_do_dossie",
                                 "schema": schema_da_estruturacao(tipos), "strict": True}},
             "input": [{"role": "user",
                        "content": _prompt_da_estruturacao(m1.texto, evs, fontes, paginas)}]}
    m2, recusa2, lat2 = _requisitar(plano, body2, contar, cfg.model)
    metas.append(_recibo("estruturacao_sem_busca", m2, recusa2, lat2))
    defeito = _defeito_da_chamada(m2, recusa2, slug, exige_busca=False)
    if not defeito and m2 is not None and m2.buscas:
        defeito = "a estruturação fez busca, e não podia"
    if defeito:
        return resposta(defeito)
    try:
        estruturados = json.loads(m2.texto).get("fatos") or []
    except (ValueError, AttributeError):
        return resposta("estruturação fora do schema (JSON ilegível)")

    por_id = {e.id: e for e in evs}
    requisitos_validos = {r["id"] for p in paginas for r in p.get("requisitos") or []}
    paginas_validas = {p["duvida_id"] for p in paginas}
    paginas_lidas: dict[str, tuple[str, str]] = {}
    fatos, rejeitados = [], []
    for f in estruturados:
        ev = por_id.get(str(f.get("evidencia_id") or ""))
        if ev is None:
            rejeitados.append({"fato": f, "motivo": "evidencia_id inexistente"})
            continue
        motivo = sustentado(str(f.get("afirmacao") or ""), str(f.get("valor") or ""), ev.trecho)
        if motivo:
            rejeitados.append({"fato": f, "evidencia_id": ev.id, "motivo": motivo})
            continue
        vigencia = str(f.get("vigente_desde") or "")
        if vigencia and not data_no_trecho(vigencia, ev.trecho):
            vigencia = ""             # data que o trecho não traz não entra
        url = next((u for u, ok in zip(ev.urls, ev.na_source) if ok), ev.urls[0])
        fato = {"afirmacao": f.get("afirmacao"), "tipo": f.get("tipo"),
                "valor": f.get("valor") or "", "unidade": f.get("unidade") or "",
                "fonte": url, "vigente_desde": vigencia, "dispositivo": f.get("dispositivo") or "",
                "evidencia_resumida": ev.trecho[:300], "evidencia_id": ev.id,
                "paginas": [p for p in f.get("paginas") or [] if p in paginas_validas],
                "requisitos": [r for r in f.get("requisitos") or [] if r in requisitos_validos]}
        if url not in paginas_lidas:
            paginas_lidas[url] = ler(url)
        conteudo, falha_leitura = paginas_lidas[url]
        if falha_leitura:
            fato["motivo_nao_verificado"] = f"conteúdo da fonte não conferido: {falha_leitura}"
        else:
            conf = sustentado(str(fato["afirmacao"]), str(fato["valor"]), conteudo,
                              minimo=SOBREPOSICAO_NA_PAGINA)
            if conf:
                fato["motivo_nao_verificado"] = f"página citada não confirma: {conf}"
        fatos.append(fato)
    metas[-1]["rejeitados"] = rejeitados
    metas[-1]["conferencia_de_conteudo"] = {u: (m or "ok") for u, (_, m) in paginas_lidas.items()}
    citadas = list(dict.fromkeys(c.url for c in m1.citacoes))
    return resposta("", {"fatos": fatos}, citadas)
