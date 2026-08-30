"""O funil ESCRITO — o que o motor produziu, não como ele se comportou.

## Por que este módulo existe separado da matriz

`matriz.py` responde "em qual etapa o motor está e quanto já custou". É
telemetria: útil enquanto o run corre, irrelevante depois. A pergunta que sobra
— e que é a razão de alguém ter gastado US$ 2 — é outra: **o que ficou escrito?**

O motor deixa isso tudo no disco e nada disso chegava à tela:

  state.json  → h1, slug, papel, engajamento, objetivo emocional, gancho para a
                próxima página, rotas, palavras-alvo, título e meta description
                de SEO, links oficiais decididos, prints capturados, e o TEXTO
                de cada página com a contagem de palavras
  p<N>.webp   → a imagem gerada
  p<N>.meta.json / p<N>.admanifest.json → canonical, robots e os slots de anúncio

Sem isso, revisar um funil significava abrir cinco rascunhos no WordPress.

## O que este módulo NÃO faz

Não reescreve, não valida e não julga. Ele lê o que está lá e devolve — inclusive
quando está feio. Uma página bloqueada continua tendo pesquisa e rascunho pagos,
e escondê-los faria o operador pagar de novo pelo que já tem.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# Só estes artefatos podem ser servidos. Lista branca por EXTENSÃO e por padrão
# de nome — o `run_dir` também guarda `state.json` (com o plano inteiro),
# `config_snapshot.json` e `worker.log`, que não têm por que trafegar para o
# browser. Ver `caminho_de_artefato`.
_ARQUIVO_SERVIVEL = re.compile(r"^p\d+[a-zA-Z0-9._\-]*\.(webp|png|jpg|jpeg)$")


def _num(d: Dict[str, Any], n: Any) -> Any:
    """As chaves de `RunState` viram string no JSON, mas nem sempre. Tenta as
    duas antes de desistir — errar aqui esvazia a tela sem nenhum erro visível."""
    if not isinstance(d, dict):
        return None
    return d.get(str(n), d.get(n))


def _texto_da_pagina(estado: Dict[str, Any], n: Any) -> Dict[str, Any]:
    """O que o redator escreveu.

    A LP é um caso à parte: ela não é prosa, é um JSON de slots que o tema do
    WordPress monta (hero, seções, FAQ, CTAs). Devolver os dois formatos com o
    campo `formato` declarado deixa a tela escolher como renderizar sem adivinhar
    pelo conteúdo.
    """
    d = _num(estado.get("drafts") or {}, n) or {}
    if not isinstance(d, dict):
        return {"formato": "", "conteudo": "", "palavras": 0}
    return {
        "formato": d.get("format") or "",
        "conteudo": d.get("content") or "",
        "palavras": d.get("word_count") or 0,
    }


def _json_do_disco(run_dir: Path, nome: str) -> Optional[Any]:
    try:
        return json.loads((run_dir / nome).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _artefatos_da_pagina(run_dir: Optional[Path], n: Any, slug: str) -> Dict[str, Any]:
    """Os arquivos que aquela página gerou. Nomes, não caminhos absolutos: a tela
    pede cada um pela rota de artefato, que valida antes de servir."""
    if run_dir is None or not run_dir.is_dir():
        return {"imagem": None, "meta": None, "anuncios": None, "arquivos": []}
    prefixo = f"p{n}"
    arquivos = sorted(p.name for p in run_dir.iterdir()
                      if p.is_file() and p.name.startswith(f"{prefixo}.")
                      or p.is_file() and p.name.startswith(f"{prefixo}-"))
    imagem = next((a for a in arquivos
                   if a == f"{prefixo}.webp"), None)
    return {
        "imagem": imagem,
        "meta": _json_do_disco(run_dir, f"{prefixo}.meta.json"),
        "anuncios": _json_do_disco(run_dir, f"{prefixo}.admanifest.json"),
        "arquivos": arquivos,
    }


def montar(estado: Dict[str, Any], *, run_dir: Optional[Path] = None,
           publicadas: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Uma entrada por página do plano, com tudo que se sabe sobre ela."""
    plano = estado.get("plan") or {}
    passos = estado.get("step_status") or {}
    por_post = {p.get("page_number"): p for p in (publicadas or [])}

    saida: List[Dict[str, Any]] = []
    for pg in (plano.get("pages") or []):
        n = pg.get("page_number")
        seo = _num(estado.get("seo") or {}, n) or {}
        prints = _num(estado.get("screenshots") or {}, n) or []
        saida.append({
            "page_number": n,
            "papel": (pg.get("role") or "").upper(),
            "slug": pg.get("slug") or "",
            "h1": pg.get("h1_title") or "",
            "engajamento": pg.get("engajamento") or "",
            # Por que ESTA página existe no funil e para onde ela empurra. É a
            # única informação que explica a ORDEM das páginas — sem ela, um
            # funil de 5 páginas parece 5 artigos soltos.
            "objetivo": pg.get("emotional_objective") or "",
            "gancho": pg.get("hook_to_next_page") or "",
            "proxima": pg.get("next_page_slug") or "",
            "estrutura": pg.get("main_content_structure") or [],
            "palavras_alvo": pg.get("target_keywords") or [],
            # ⚠️ LISTA de arestas, não dicionário: `[{placement, kind, target,
            # anchor}]`. É daqui que a tela monta o grafo do funil — uma página
            # aponta para várias ao mesmo tempo, e a POSIÇÃO do link (hero,
            # inline, footer) é o peso real daquele caminho.
            "rotas": pg.get("routes") or [],
            "seo": {
                "titulo": seo.get("seotitle") or "",
                "descricao": seo.get("metadescription") or "",
                "foco": seo.get("keywordfocus") or "",
                "slug": seo.get("slug") or "",
            },
            # As URLs externas que ESTA página pode citar, decididas uma vez logo
            # após a pesquisa — o redator, o portão e o print leem daqui, então
            # os três nunca discordam sobre qual é o canal oficial.
            "links_oficiais": _num(estado.get("official_links") or {}, n) or [],
            "prints": [{"url": s.get("url"), "arquivo": Path(str(s.get("path", ""))).name}
                       for s in prints if isinstance(s, dict)],
            "texto": _texto_da_pagina(estado, n),
            "publicada": por_post.get(n),
            "bloqueada": f"blocked_p{n}" in passos,
            # O dinheiro daquela página, somado das etapas dela. É o número que
            # decide se vale reescrever ou descartar.
            "custo_usd": round(sum(
                float((r or {}).get("cost_usd") or 0.0)
                for k, r in passos.items() if k.endswith(f"_p{n}")), 6),
            "issues": [
                {"etapa": k.rsplit(f"_p{n}", 1)[0], "code": i.get("code"),
                 "message": i.get("message")}
                for k, r in passos.items() if k.endswith(f"_p{n}")
                for i in ((r or {}).get("issues") or [])
            ],
            **_artefatos_da_pagina(run_dir, n, pg.get("slug") or ""),
        })
    return saida


def caminho_de_artefato(run_dir: Optional[Path], nome: str) -> Optional[Path]:
    """Resolve um artefato servível, ou `None`.

    ⚠️ Três travas, e as três importam:

    1. **Lista branca de nome.** Só `p<N>...webp|png|jpg`. A pasta do run também
       tem `state.json` (o plano inteiro, com o briefing), `config_snapshot.json`
       e `worker.log` — nenhum deles tem por que trafegar para o browser.
    2. **Nada de separador de caminho.** Sem isto, `../../../etc/passwd` sai
       daqui como um caminho válido.
    3. **Confirmação depois de resolver.** `resolve()` desfaz symlink e `..`; se
       o resultado não estiver mais DENTRO do `run_dir`, não é artefato do run.
    """
    if run_dir is None or not nome or "/" in nome or "\\" in nome:
        return None
    if not _ARQUIVO_SERVIVEL.match(nome):
        return None
    alvo = (run_dir / nome).resolve()
    try:
        alvo.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return alvo if alvo.is_file() else None
