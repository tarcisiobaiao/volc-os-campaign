"""Leitura da recomendação em sombra de uma campanha real (contrato v1).

A recomendação NÃO é calculada aqui. Ela sai de um experimento já executado e
versionado no Freedom Lab (`tools/freedom-lab/experimentos/<id>/`), cujo
método é a reconciliação custo × receita da v17_04 no grão campanha × dia,
replay sem API. Este módulo só lê o que o experimento gravou, confere o
sha256 de cada artefato contra o manifesto do próprio experimento e projeta
um contrato estável para a tela.

O que ele NUNCA faz: chamar Google Ads, Supabase ou n8n; recalcular a
direção; sugerir valor; oferecer execução. `executada` é sempre `False` e não
há campo que a tela possa transformar em botão.

⚠️ Artefato adulterado não vira "sem recomendação". Um sha256 que não bate é
`IntegridadeQuebrada`, e a rota responde 409 dizendo isso — mostrar a
recomendação seria exibir um número que ninguém consegue reproduzir, e
escondê-la faria a quebra parecer ausência.

Escolha entre experimentos da mesma campanha (ciclo corretivo 2, 15/10): vence
o `as_of` mais recente do `resultado.json`, e nunca a ordem do nome da pasta.
Dois experimentos com o mesmo `as_of` são `ExperimentosAmbiguos` (409): não há
critério para preferir um, e escolher pela ordem alfabética seria esconder a
contradição. Os perdedores aparecem em `origem.experimentos_substituidos`.

Ausência só pode ser afirmada sobre uma fonte que existe e foi lida inteira:
- `resultado.json` é conferido contra o sha256 do manifesto ANTES de ser
  interpretado, e JSON ilegível é `IntegridadeQuebrada`. Como um resultado
  corrompido não diz de que campanha é, ele impede afirmar ausência para
  QUALQUER campanha enquanto existir;
- pasta de experimentos inexistente, ou sem nenhum experimento, é
  `FonteIndisponivel` (503), nunca "nenhum experimento olhou esta campanha".

⚠️ Decisão de deploy: o `backend/vercel.json` empacota só `app/**`, e a pasta
`tools/freedom-lab/experimentos/` fica fora da raiz do projeto Vercel do
backend. Não alteramos o empacotamento porque não há como provar, fora do
painel, que a Vercel inclui arquivos de fora da raiz. Num backend publicado
sem a pasta, a rota responde 503 `fonte_indisponivel`. Para servir a
recomendação lá, aponte `VOLC_EXPERIMENTOS_SHADOW_DIR` para uma cópia
empacotada dos experimentos.

`origem.integridade` diz `coerente_com_manifesto`, e não "conferida": o sha256
é comparado com o manifesto da MESMA pasta, então quem edita os dois passa.
Isso detecta deriva acidental, não adulteração deliberada.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import pathlib
import re
from datetime import datetime, timezone
from typing import Any, Optional


_RAIZ = pathlib.Path(__file__).resolve().parents[3]
RAIZ_PADRAO = _RAIZ / "tools" / "freedom-lab" / "experimentos"
# Para um deploy que não leva `tools/` (o backend da Vercel só empacota `app/**`).
VARIAVEL_RAIZ = "VOLC_EXPERIMENTOS_SHADOW_DIR"

CONTRATO = "recomendacao_shadow.v1"

# O vocabulário fechado da decisão, o da spec da prova vertical (E §3). Uma
# leitura `insuficiente` de `intencao.avaliar_suficiencia` corresponde a
# `evidencia_insuficiente`. Qualquer outra palavra vinda do experimento cai
# nela — nunca é repassada como se fosse uma direção.
DIRECOES = ("manter", "reduzir", "aumentar", "pausar", "evidencia_insuficiente")

_ID_EXTERNO = re.compile(r"^[0-9]{6,20}$")

# Medido pelo Leitor E em 15/10/2026 (`E-navegador-vertical.md` §3): a conta
# registra `conversions_value` = 10 por conversão. É valor estático de
# configuração, não receita; o ROAS que o Google mostra a partir dele é proxy
# falso e não entra em decisão nenhuma.
MOTIVO_ROAS_NATIVO = (
    "O valor de conversão do Google é fixo em 10 por conversão, configurado na "
    "conta; não é receita. O ROAS nativo calculado sobre ele não é confiável e "
    "não entra na recomendação."
)


class IntegridadeQuebrada(Exception):
    """Um artefato do experimento não bate com o manifesto ou não é legível."""


class ExperimentosAmbiguos(Exception):
    """Mais de um experimento da campanha com o mesmo `as_of` mais recente."""


class FonteIndisponivel(Exception):
    """A pasta de experimentos não existe ou não tem nenhum experimento."""


def _sha256(caminho: pathlib.Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _numero(texto: Any) -> Optional[float]:
    """Célula vazia é ausência, e ausência continua `None` (nunca 0)."""
    if texto is None:
        return None
    s = str(texto).strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _raiz_configurada() -> pathlib.Path:
    """A variável de ambiente, se definida; senão a pasta do repositório.

    Lido na chamada, e não no import: o teste troca a raiz pelo módulo.
    """
    definida = os.environ.get(VARIAVEL_RAIZ, "").strip()
    return pathlib.Path(definida) if definida else RAIZ_PADRAO


def _manifestos(raiz: pathlib.Path) -> list[pathlib.Path]:
    if not raiz.is_dir():
        raise FonteIndisponivel("a pasta de experimentos em sombra não existe neste servidor.")
    encontrados = sorted(raiz.glob("*/experimento.json"))
    if not encontrados:
        raise FonteIndisponivel("a pasta de experimentos em sombra não tem nenhum experimento.")
    return encontrados


def _json(caminho: pathlib.Path, experimento_id: str) -> dict[str, Any]:
    try:
        lido = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IntegridadeQuebrada(
            f"{caminho.name} do experimento {experimento_id} não é JSON legível."
        ) from exc
    if not isinstance(lido, dict):
        raise IntegridadeQuebrada(f"{caminho.name} do experimento {experimento_id} não é um objeto.")
    return lido


def _declara(manifesto: dict[str, Any], nome: str) -> bool:
    return any(
        isinstance(a, dict) and str(a.get("path")) == nome
        for a in manifesto.get("artifacts", [])
    )


def _data(as_of: Any, experimento_id: str) -> datetime:
    """`as_of` é o critério de recência; sem ele não há como ordenar."""
    try:
        quando = datetime.fromisoformat(str(as_of))
    except ValueError as exc:
        raise IntegridadeQuebrada(
            f"resultado.json do experimento {experimento_id} não tem as_of legível ({as_of!r})."
        ) from exc
    if quando.tzinfo is not None:
        quando = quando.astimezone(timezone.utc).replace(tzinfo=None)
    return quando


def _conferir(pasta: pathlib.Path, manifesto: dict[str, Any], nomes: tuple[str, ...]) -> None:
    declarados = {
        str(a.get("path")): str(a.get("sha256"))
        for a in manifesto.get("artifacts", [])
        if isinstance(a, dict)
    }
    for nome in nomes:
        esperado = declarados.get(nome)
        arquivo = pasta / nome
        if not esperado:
            raise IntegridadeQuebrada(f"{nome} não está declarado no manifesto do experimento.")
        if not arquivo.is_file():
            raise IntegridadeQuebrada(f"{nome} está declarado e não existe na pasta do experimento.")
        if _sha256(arquivo) != esperado:
            raise IntegridadeQuebrada(f"{nome} não bate com o sha256 declarado no manifesto.")


def _dias(csv_path: pathlib.Path) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            custo = _numero(linha.get("custo_brl"))
            receita = _numero(linha.get("receita_brl"))
            cliques = _numero(linha.get("clicks"))
            linhas.append({
                "data": str(linha.get("date") or ""),
                "custo_brl": None if custo is None else round(custo, 2),
                "cliques": None if cliques is None else int(cliques),
                "receita_brl": None if receita is None else round(receita, 2),
                # Só existe contribuição quando os DOIS lados existem.
                "contribuicao_brl": (
                    None if custo is None or receita is None else round(receita - custo, 2)
                ),
                "maduro": str(linha.get("maduro") or "").strip().lower() == "true",
                "estado": str(linha.get("estado") or "") or None,
            })
    return linhas


def _janela(bruta: Any) -> Optional[dict[str, Any]]:
    if not isinstance(bruta, dict):
        return None
    campos = ("dias", "custo_brl", "receita_brl", "cliques", "roas", "cpc", "rpc", "contribuicao_bruta")
    return {c: bruta.get(c) for c in campos}


def ler(campaign_id: str, *, raiz: Optional[pathlib.Path] = None) -> Optional[dict[str, Any]]:
    """Projeta a recomendação em sombra da campanha, ou `None` se não houver.

    `campaign_id` é o id da campanha no Google (o experimento é indexado por
    ele). Levanta `ValueError` para id malformado, `IntegridadeQuebrada`
    quando um artefato não bate com o manifesto ou é ilegível,
    `ExperimentosAmbiguos` quando o mais recente empata e `FonteIndisponivel`
    quando a pasta de experimentos não existe ou está vazia.
    """
    cid = str(campaign_id or "").strip()
    if not _ID_EXTERNO.fullmatch(cid):
        raise ValueError("id de campanha malformado")

    candidatos: list[tuple[datetime, pathlib.Path, dict[str, Any], dict[str, Any]]] = []
    for caminho in _manifestos(raiz or _raiz_configurada()):
        pasta = caminho.parent
        manifesto = _json(caminho, pasta.name)
        resultado_path = pasta / "resultado.json"
        # Experimento que não é de sombra (nem declara nem tem resultado) não
        # entra. Declarou ou tem: confere o sha256 ANTES de interpretar.
        if not _declara(manifesto, "resultado.json") and not resultado_path.exists():
            continue
        _conferir(pasta, manifesto, ("resultado.json",))
        resultado = _json(resultado_path, pasta.name)
        if str(resultado.get("campanha")) != cid:
            continue
        candidatos.append((_data(resultado.get("as_of"), pasta.name), pasta, manifesto, resultado))

    if not candidatos:
        return None
    candidatos.sort(key=lambda c: c[0], reverse=True)
    if len(candidatos) > 1 and candidatos[0][0] == candidatos[1][0]:
        empatados = sorted(c[1].name for c in candidatos if c[0] == candidatos[0][0])
        raise ExperimentosAmbiguos(
            f"{len(empatados)} experimentos da campanha têm o mesmo as_of "
            f"({candidatos[0][3].get('as_of')}): {', '.join(empatados)}."
        )
    _, pasta, manifesto, resultado = candidatos[0]
    _conferir(pasta, manifesto, ("resultado.json", "transformacao.csv"))
    projecao = _projetar(cid, pasta.name, manifesto, resultado, _dias(pasta / "transformacao.csv"))
    projecao["origem"]["experimentos_substituidos"] = sorted(c[1].name for c in candidatos[1:])
    return projecao


def _projetar(
    cid: str,
    experimento_id: str,
    manifesto: dict[str, Any],
    resultado: dict[str, Any],
    dias: list[dict[str, Any]],
) -> dict[str, Any]:
    rec = resultado.get("recomendacao") or {}
    direcao_bruta = str(rec.get("direcao") or "")
    direcao = direcao_bruta if direcao_bruta in DIRECOES else "evidencia_insuficiente"
    motivos = [str(m) for m in rec.get("motivos") or []]
    if direcao != direcao_bruta:
        motivos.insert(0, f"o experimento devolveu uma direção fora do vocabulário ({direcao_bruta or 'vazia'})")

    snapshot = manifesto.get("input_snapshot") or {}
    metodo = manifesto.get("method") or {}
    estimado = (manifesto.get("result") or {}).get("estimated") or {}
    return {
        "contrato": CONTRATO,
        "campanha_externa": cid,
        "grao": "campanha_dia",
        "direcao": direcao,
        "motivos": motivos,
        "ressalvas": [str(r) for r in rec.get("lacunas") or []],
        # Valor nunca é sugerido por esta leitura, e nada aqui é executável.
        "valor_sugerido": None,
        "executada": False,
        "as_of": resultado.get("as_of"),
        "corte_maturidade": resultado.get("corte_maturidade"),
        "parametros": resultado.get("parametros") or {},
        "janela_madura": _janela(resultado.get("janela_madura")),
        "janela_madura_recente": _janela(resultado.get("janela_madura_recente")),
        "roas_sob_estresse": estimado.get("roas_sob_estresse"),
        "fracao_custo_maduro_sem_receita": resultado.get("fracao_custo_maduro_sem_receita"),
        "dias": dias,
        "roas_nativo_google": {
            "valor_conversao_total": resultado.get("valor_conversao_google_total"),
            "confiavel": False,
            "motivo": MOTIVO_ROAS_NATIVO,
        },
        "origem": {
            "experimento_id": experimento_id,
            "metodo": metodo.get("description"),
            "codigo_sha256": resultado.get("codigo_sha256"),
            "snapshot_sha256": snapshot.get("sha256"),
            "capturado_em": snapshot.get("captured_at"),
            "replay_sem_api": bool(metodo.get("replay_without_api")),
            "integridade": "coerente_com_manifesto",
        },
        "isolamento": {
            "chamadas_externas": 0,
            "mutacoes_executadas": 0,
            "oferece_aplicar": False,
        },
    }
