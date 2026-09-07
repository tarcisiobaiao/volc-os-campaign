#!/usr/bin/env python3
"""Publica (ou, por padrão, SIMULA a publicação de) o workflow n8n Meta Ads.

## O que este script existe para impedir

Importar um JSON no n8n parece trivial e tem três maneiras conhecidas de dar
errado em silêncio nesta instância — todas já observadas nesta base, nenhuma
hipotética:

1. **Sobrescrever o workflow de outra pessoa.** A instância tem 396 workflows e
   já carrega nomes vizinhos do nosso: `Meta Insights` e `VOLC - Meta Ads`
   (`docs/specs/meta-operator-go-live-v1/EVIDENCE.json:115`). Procurar o "nosso"
   por NOME acha um deles e o atualiza. Por isso a busca aqui é por IDENTIDADE —
   a trinca (gerador, dono, contrato_sha256) que vive em `meta.volc` do artefato
   — e **nunca** por nome sozinho. Nome só entra no relatório, como aviso.

2. **Publicar um fluxo que não consegue rodar.** Enquanto a credencial Meta não
   estiver provisionada, o nó da Graph aponta para um marcador que não resolve.
   O bloqueio é MECÂNICO: `--apply` recusa antes de abrir socket nenhum. Um
   aviso em sticky note não é bloqueio — é um aviso.

3. **Ligar a agenda sem querer.** O contrato público do POST/PUT da API do n8n
   aceita só `{name, nodes, connections, settings}`; `active` **não viaja**. O
   padrão do POST é inativo — mas "o padrão é inativo" é uma crença sobre o
   servidor, e crença não é prova. Depois de criar, este script faz um **GET de
   volta** e lê `active` **do servidor**. Se vier qualquer coisa diferente de
   `false`, ele grita.

## Credenciais deste script (a escolha, e por que ela)

`os.environ` primeiro; se a variável não estiver no ambiente, cai para uma
leitura literal do `.env` do repositório. Esta base tem os dois padrões vivos —
`n8n/patch_flows_joinads_vivos.py:5-6` usa só `os.environ`, e
`scripts/baixar-inventario-n8n.py:115-126` lê só o `.env` — e escolher um dos
dois sozinho quebra metade dos usos. A ordem é essa e não a inversa porque o
ambiente é o que um runner de CI ou um shell com credencial temporária
consegue controlar; o `.env` é a conveniência da máquina do operador, e
conveniência não pode ter precedência sobre o que foi passado de propósito.

O VALOR da chave nunca é impresso, nunca entra em recibo e nunca aparece em
mensagem de erro — nem truncado. O que o relatório mostra é a ORIGEM (`ambiente`
ou `.env`), que é o que ajuda a depurar.

Uso:
    python3 scripts/publicar_workflows_n8n_meta.py             # DRY-RUN (padrão)
    python3 scripts/publicar_workflows_n8n_meta.py --offline   # DRY-RUN sem rede
    python3 scripts/publicar_workflows_n8n_meta.py --recibo r.json
    python3 scripts/publicar_workflows_n8n_meta.py --apply     # cria de verdade
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
ARTEFATO = RAIZ / "n8n" / "volc_meta_insights_dia_d1.json"
#: O contrato público do import/export do n8n. `active` NÃO está aqui e isso é
#: deliberado: a API o trata como somente-leitura, e mandá-lo daria a falsa
#: impressão de que o estado de ativação viajou.
CAMPOS_PUBLICOS = ("name", "nodes", "connections", "settings")
TEMPO_LIMITE = 60


class Recusa(Exception):
    """Parada declarada, com código. Nunca carrega segredo na mensagem."""

    def __init__(self, codigo: str, detalhe: str) -> None:
        super().__init__(f"{codigo}: {detalhe}")
        self.codigo = codigo
        self.detalhe = detalhe


# ───────────────────────────────────────────────────────────── credenciais ──


def _do_env_arquivo(chave: str) -> str | None:
    caminho = RAIZ / ".env"
    if not caminho.exists():
        return None
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha.startswith(f"{chave}="):
            return linha.partition("=")[2].strip().strip('"').strip("'")
    return None


def credencial(chave: str) -> tuple[str, str]:
    """Devolve (valor, origem). A origem entra no relatório; o valor, nunca."""
    import os

    do_ambiente = os.environ.get(chave)
    if do_ambiente:
        return do_ambiente, "ambiente"
    do_arquivo = _do_env_arquivo(chave)
    if do_arquivo:
        return do_arquivo, ".env"
    raise Recusa("CREDENCIAL_N8N_AUSENTE",
                 f"{chave} não está no ambiente nem no .env do repositório")


# ────────────────────────────────────────────────────────────────── cliente ──


class ClienteN8n:
    def __init__(self, base: str, chave: str) -> None:
        self.base = base.rstrip("/")
        self._chave = chave

    def _pedir(self, metodo: str, caminho: str, corpo: dict | None = None) -> Any:
        req = urllib.request.Request(
            f"{self.base}/api/v1{caminho}", method=metodo,
            data=json.dumps(corpo).encode("utf-8") if corpo is not None else None)
        req.add_header("X-N8N-API-KEY", self._chave)
        req.add_header("Accept", "application/json")
        if corpo is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=TEMPO_LIMITE) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            # ⚠️ O CORPO DO ERRO NÃO É IMPRESSO. Uma resposta de erro da API pode
            # devolver o pedido inteiro — cabeçalhos inclusive — e é assim que
            # uma chave termina num log. Só o método, o caminho e o código.
            raise Recusa("N8N_HTTP", f"{metodo} {caminho} respondeu {e.code}") from None
        except urllib.error.URLError as e:
            raise Recusa("N8N_INALCANCAVEL",
                         f"{metodo} {caminho} não completou ({type(e.reason).__name__})") from None

    def listar(self) -> list[dict]:
        """Todas as páginas. A instância tem centenas de workflows."""
        saida: list[dict] = []
        cursor = None
        while True:
            caminho = "/workflows?limit=100" + (f"&cursor={cursor}" if cursor else "")
            pagina = self._pedir("GET", caminho)
            saida.extend(pagina.get("data", []))
            cursor = pagina.get("nextCursor")
            if not cursor:
                return saida

    def obter(self, wid: str) -> dict:
        return self._pedir("GET", f"/workflows/{wid}")

    def criar(self, payload: dict) -> dict:
        return self._pedir("POST", "/workflows", payload)


# ────────────────────────────────────────────────────────────── identidade ──


def identidade(wf: dict) -> tuple[str, str, str] | None:
    """A trinca origem/dono/hash. `None` quando o workflow não é nosso.

    ⚠️ TRÊS CAMPOS, NÃO UM. `gerador` sozinho casaria com qualquer artefato desta
    família; `contrato_sha256` sozinho é estável demais entre papéis; `dono`
    sozinho não distingue artefatos. Juntos eles respondem "é ESTE artefato?" sem
    nunca perguntar "tem ESTE nome?".
    """
    volc = (wf.get("meta") or {}).get("volc") or {}
    gerador, dono, sha = volc.get("gerador"), volc.get("dono"), volc.get("contrato_sha256")
    if not (gerador and dono and sha):
        return None
    return (str(gerador), str(dono), str(sha))


def payload_publico(wf: dict) -> dict:
    faltando = [c for c in CAMPOS_PUBLICOS if c not in wf]
    if faltando:
        raise Recusa("ARTEFATO_INCOMPLETO",
                     f"faltam campos do contrato público: {', '.join(faltando)}")
    return {c: wf[c] for c in CAMPOS_PUBLICOS}


def impressao(payload: dict) -> str:
    texto = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


# ──────────────────────────────────────────────────────────────── o portão ──


def exigir_credencial_provisionada(wf: dict) -> None:
    """⚠️ O BLOQUEIO. Mecânico, antes de qualquer socket.

    Enquanto `meta.volc.pronto_para_publicar` for falso, o nó da Graph aponta
    para um marcador de cofre que não resolve. Publicar assim cria, na instância,
    um workflow que parece pronto, aparece nas listagens e não roda — o pior dos
    dois mundos, porque o próximo a olhar vai supor que alguém já tratou disso.
    """
    volc = (wf.get("meta") or {}).get("volc") or {}
    cred = volc.get("credencial") or {}
    if volc.get("pronto_para_publicar") is not True:
        raise Recusa(
            "CREDENCIAL_NAO_PROVISIONADA",
            "o artefato declara pronto_para_publicar=False "
            f"(credencial.estado={cred.get('estado')!r}, "
            f"tipo={cred.get('tipo')!r}). Crie o item Header Auth no cofre do n8n, "
            "preencha CRED_META_ITEM_ID em n8n/gerar_flows_meta_ledger.py e regere.")


def conferir_inativo_no_servidor(devolvido: dict) -> None:
    """A prova de inatividade vem do SERVIDOR, não da nossa expectativa.

    `active` não viaja no POST, e o padrão da API é criar inativo. Mas isso é uma
    crença sobre o comportamento do servidor, e este fluxo lê dinheiro: a
    diferença entre "acho que nasceu inativo" e "o servidor me disse que está
    inativo" é a diferença entre um contrato e uma esperança.
    """
    if devolvido.get("active") is not False:
        raise Recusa(
            "WORKFLOW_NASCEU_ATIVO",
            f"o servidor devolveu active={devolvido.get('active')!r}; "
            "DESATIVE MANUALMENTE AGORA — a agenda só pode ser ligada pelo pacote "
            "de autorização")


def recibo_sanitizado(devolvido: dict, *, aplicado: bool, impressao_local: str) -> dict:
    """Só rótulos e contagens. Nunca token, nunca corpo cru, nunca nó."""
    return {
        "aplicado": aplicado,
        "id": devolvido.get("id"),
        "versionId": devolvido.get("versionId"),
        "nome": devolvido.get("name"),
        "active": devolvido.get("active"),
        "nos": len(devolvido.get("nodes") or []),
        "criado_em": devolvido.get("createdAt"),
        "atualizado_em": devolvido.get("updatedAt"),
        "impressao_do_payload_local": impressao_local,
    }


# ─────────────────────────────────────────────────────────────────── fluxo ──


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="cria de verdade. Sem esta flag NADA é escrito na instância.")
    p.add_argument("--offline", action="store_true",
                   help="dry-run sem tocar a rede: só confere o artefato e o portão.")
    p.add_argument("--recibo", type=Path, default=None,
                   help="grava o recibo sanitizado neste caminho (padrão: só imprime).")
    args = p.parse_args()

    if args.apply and args.offline:
        print("ERRO · --apply e --offline se contradizem", file=sys.stderr)
        return 2

    modo = "APLICAR" if args.apply else ("DRY-RUN (offline)" if args.offline else "DRY-RUN")
    print(f"── publicar_workflows_n8n_meta · modo {modo}")
    print(f"   artefato: {ARTEFATO.relative_to(RAIZ)}")

    try:
        wf = json.loads(ARTEFATO.read_text(encoding="utf-8"))
        payload = payload_publico(wf)
        ident = identidade(wf)
        if ident is None:
            raise Recusa("ARTEFATO_SEM_IDENTIDADE",
                         "meta.volc precisa de gerador, dono e contrato_sha256 para "
                         "que a busca não caia em nome")
        marca = impressao(payload)
        print(f"   identidade: gerador={ident[0]} · dono={ident[1]}")
        print(f"               contrato_sha256={ident[2][:16]}…")
        print(f"   payload público: {len(payload['nodes'])} nós · impressão {marca}")
        print(f"   active no arquivo: {wf.get('active')!r} (não viaja no POST)")

        # ── o portão ────────────────────────────────────────────────────────
        try:
            exigir_credencial_provisionada(wf)
            print("   portão da credencial: LIBERADO")
            bloqueado = None
        except Recusa as r:
            bloqueado = r
            print(f"   portão da credencial: BLOQUEADO · {r.codigo}")
            print(f"      {r.detalhe}")

        if args.apply and bloqueado is not None:
            # ⚠️ Antes de qualquer socket. Nada foi pedido à instância.
            print("\nRECUSADO · --apply não prossegue com credencial não provisionada.",
                  file=sys.stderr)
            return 1

        if args.offline:
            print("\n[offline] nenhuma chamada à instância. "
                  "O que o dry-run com rede faria: listar todos os workflows, "
                  "procurar a identidade acima e relatar criar/atualizar.")
            print(json.dumps({"aplicado": False, "modo": "offline",
                              "impressao_do_payload_local": marca}, ensure_ascii=False))
            return 0

        base, origem_base = credencial("N8N_BASE_URL")
        chave, origem_chave = credencial("N8N_API_KEY")
        print(f"   N8N_BASE_URL de {origem_base} · N8N_API_KEY de {origem_chave} "
              "(valor nunca impresso)")
        cliente = ClienteN8n(base, chave)

        # ── busca POR IDENTIDADE ────────────────────────────────────────────
        todos = cliente.listar()
        print(f"   instância: {len(todos)} workflows lidos")
        iguais = [w for w in todos if identidade(w) == ident]
        # ⚠️ O nome NÃO decide nada — mas o operador precisa VER a vizinhança,
        # porque é ela que torna a busca por nome perigosa.
        vizinhos = [w for w in todos
                    if identidade(w) != ident
                    and "meta" in str(w.get("name", "")).lower()]
        if vizinhos:
            print(f"   ⚠️ {len(vizinhos)} workflow(s) com 'meta' no nome que NÃO são este "
                  "artefato (a busca por nome pegaria um deles):")
            for w in vizinhos[:8]:
                print(f"      · {w.get('name')!r} · active={w.get('active')!r}")

        if len(iguais) > 1:
            raise Recusa("IDENTIDADE_DUPLICADA",
                         f"{len(iguais)} workflows carregam a MESMA identidade; "
                         "resolver à mão antes de publicar")

        if iguais:
            existente = iguais[0]
            print(f"   já existe: id={existente.get('id')} · "
                  f"active={existente.get('active')!r}")
            print("   → o dry-run PARA aqui. Atualizar workflow existente é PUT, e PUT "
                  "sobre um fluxo vivo é outra decisão; ela é de T11, não deste passo.")
            print(json.dumps(recibo_sanitizado(existente, aplicado=False,
                                               impressao_local=marca), ensure_ascii=False))
            return 0

        print("   não existe na instância → a ação seria CRIAR (POST /api/v1/workflows)")
        if not args.apply:
            print("\n   DRY-RUN: nenhum POST foi enviado. Para criar de verdade, "
                  "rode com --apply.")
            print(json.dumps({"aplicado": False, "acao_planejada": "criar",
                              "nome": payload["name"], "nos": len(payload["nodes"]),
                              "impressao_do_payload_local": marca}, ensure_ascii=False))
            return 0

        criado = cliente.criar(payload)
        wid = criado.get("id")
        if not wid:
            raise Recusa("POST_SEM_ID", "a criação não devolveu id; nada a conferir")
        # ⚠️ A leitura de volta é obrigatória: `criado` é o eco do POST, não o
        # estado do servidor.
        devolvido = cliente.obter(str(wid))
        conferir_inativo_no_servidor(devolvido)
        recibo = recibo_sanitizado(devolvido, aplicado=True, impressao_local=marca)
        print(f"   criado e conferido no servidor: active={recibo['active']!r}")
        print(json.dumps(recibo, ensure_ascii=False))
        if args.recibo:
            args.recibo.write_text(json.dumps(recibo, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
            print(f"   recibo em {args.recibo}")
        return 0

    except Recusa as r:
        print(f"\nRECUSADO · {r.codigo}: {r.detalhe}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
