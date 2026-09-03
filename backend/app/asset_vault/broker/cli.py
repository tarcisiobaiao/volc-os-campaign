#!/usr/bin/env python3
"""O sidecar: a linha de comando do broker, e o autoteste que a prova.

    # do diretorio `backend/`
    python3 -m app.asset_vault.broker.cli --autoteste
    python3 -m app.asset_vault.broker.cli --preflight --perfis-permitidos k11abc

    # com o 1Password destrancado, no host do AdsPower:
    op run -- python3 -m app.asset_vault.broker.cli \\
        --acao inventario_perfis --perfis-permitidos k11abc \\
        --chave-idempotencia inventario-2026-09-02-01

⚠️ `--acao` faz rede. `--preflight` e `--autoteste` nao fazem: os dois so
exercitam as recusas, e por isso rodam em qualquer maquina, inclusive numa sem
AdsPower e sem 1Password — que e o caso desta.

## O que sai no stdout

Um recibo JSON sanitizado, e o codigo de saida do estado (`dominio.ESTADOS`).
Um runner externo distingue "nao deu para tentar" (10-19) de "tentou e vazou"
(20-29) sem parsear texto.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Mapping

# Permite `python3 backend/app/asset_vault/broker/cli.py` alem de `-m`.
if __package__ in (None, ""):  # pragma: no cover - so no modo caminho-direto
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.asset_vault.broker import dominio as dom  # noqa: E402
from app.asset_vault.broker.aplicacao import (  # noqa: E402
    FERRAMENTA,
    TAREFA,
    Broker,
    Pedido,
    Registro,
)
from app.asset_vault.broker.infraestrutura import (  # noqa: E402
    VARIAVEL_DA_REFERENCIA,
    VARIAVEL_DO_BEARER,
    ClienteLocalApi,
    SegredoDoAmbiente,
)

ENDERECO_PADRAO = f"http://127.0.0.1:{dom.PORTA_PADRAO_ADSPOWER}"


def _recibo_de_recusa(estado: str, mensagem: str, **extra: Any) -> dict[str, Any]:
    """Uma recusa tambem e um recibo: ela tem estado, motivo e hora.

    Sair com um `print` no stderr faria a recusa ser o unico ato do broker sem
    trilha — justamente o ato que mais interessa a quem audita.
    """
    recibo = {
        "ferramenta": FERRAMENTA,
        "tarefa": TAREFA,
        "estado": estado,
        "codigo_de_saida": dom.ESTADOS.get(estado, dom.ESTADOS["falha/interna"]),
        "motivo": mensagem,
        "observado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **extra,
    }
    try:
        dom.recusar_vazamento(recibo)
    except dom.BrokerRecusado:
        # A frase inteira cai, e nao so o trecho suspeito: recortar exigiria
        # saber onde o valor comeca, e quem sabe isso ja o possui.
        recibo["motivo"] = ("a mensagem foi descartada por conter material que parece "
                            "credencial. O valor nao e repetido aqui de proposito.")
        recibo["estado"] = "falha/vazamento"
        recibo["codigo_de_saida"] = dom.ESTADOS["falha/vazamento"]
    return recibo


def _parametros(pares: list[str] | None) -> dict[str, str]:
    saida: dict[str, str] = {}
    for par in pares or []:
        chave, sep, valor = str(par).partition("=")
        if not sep or not chave.strip():
            raise dom.BrokerRecusado("parametro mal formado: use --parametro chave=valor")
        saida[chave.strip()] = valor.strip()
    return saida


def _emitir(recibo: Mapping[str, Any]) -> int:
    sys.stdout.write(json.dumps(recibo, ensure_ascii=False, indent=2, default=str) + "\n")
    codigo = recibo.get("codigo_de_saida")
    return int(codigo) if isinstance(codigo, int) else dom.ESTADOS["falha/interna"]


def executar(args, argv: list[str], ambiente: Mapping[str, str]) -> int:
    # 1. Verificacao ligada — antes de tudo, inclusive antes de ler a acao.
    try:
        dom.exigir_verificacao_ligada(argv, ambiente)
        endereco = dom.exigir_endereco_de_loopback(args.endereco)
        perfis = tuple(p.strip() for p in (args.perfis_permitidos or []) if p.strip())
    except dom.BrokerRecusado as exc:
        return _emitir(_recibo_de_recusa(exc.estado, str(exc)))

    if args.preflight:
        return _emitir({
            "ferramenta": FERRAMENTA, "tarefa": TAREFA, "estado": "ok",
            "codigo_de_saida": 0,
            "preflight": {
                "endereco_aceito": endereco,
                "perfis_na_allowlist": len(perfis),
                "acoes_permitidas": sorted(dom.ACOES),
                "acoes_que_exigem_checkpoint": sorted(dom.ACOES_QUE_EXIGEM_CHECKPOINT),
                "variavel_do_bearer": VARIAVEL_DO_BEARER,
                "variavel_da_referencia": VARIAVEL_DA_REFERENCIA,
                # Presenca, nunca valor: booleano nao vaza nem entropia.
                "bearer_presente_no_ambiente": bool(
                    (ambiente.get(VARIAVEL_DO_BEARER) or "").strip()),
                "faz_rede": False,
            },
            "observado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    if not args.acao:
        return _emitir(_recibo_de_recusa(
            "falha/preflight",
            "informe --acao, --preflight ou --autoteste. Acoes: "
            + ", ".join(sorted(dom.ACOES))))

    fonte = SegredoDoAmbiente(ambiente)
    broker = Broker(endereco=endereco, perfis_permitidos=perfis,
                    fonte=fonte, porta=ClienteLocalApi(endereco),
                    registro=Registro())
    try:
        pedido = Pedido(
            acao=args.acao,
            chave_idempotencia=args.chave_idempotencia or "",
            perfil=args.perfil,
            parametros=_parametros(args.parametro),
            timeout_s=args.timeout,
        )
        recibo = asyncio.run(broker.executar(pedido))
    except dom.BrokerRecusado as exc:
        return _emitir(_recibo_de_recusa(exc.estado, str(exc), acao=args.acao))
    except dom.AcessoIndisponivel as exc:
        # Fail closed: sem Bearer ativo nao ha modo degradado, e a saida diz
        # exatamente qual dos bloqueios aconteceu.
        return _emitir(_recibo_de_recusa(exc.estado, str(exc), acao=args.acao))
    return _emitir(recibo)


# ═══════════════════════════════════════════════════════════════════════════
# Autoteste — as recusas, provadas sem rede, sem AdsPower e sem 1Password
# ═══════════════════════════════════════════════════════════════════════════


class _PortaFalsa:
    """Uma Local API de mentira. Registra o que recebeu e devolve o combinado."""

    def __init__(self, resposta: Any = None, erro: Exception | None = None):
        self.chamadas: list[tuple[str, dict[str, str]]] = []
        self.viu_bearer_como_texto: list[str] = []
        self._resposta = resposta if resposta is not None else {"code": 0, "msg": "success"}
        self._erro = erro

    async def chamar(self, acao, parametros, bearer, timeout_s):
        self.chamadas.append((acao.nome, dict(parametros)))
        # O duble NAO chama `.revelar()`: ele registra o que sairia se alguem
        # tratasse o Segredo como texto. Se `__str__` algum dia devolver o
        # valor, a prova de nao-impressao cai aqui.
        self.viu_bearer_como_texto.append(f"{bearer}")
        if self._erro is not None:
            raise self._erro
        return self._resposta


class _FonteFalsa:
    def __init__(self, valor: str | None, referencia: str | None = None):
        self._valor = valor
        self._referencia = referencia

    nome_da_variavel = "VOLC_ADSPOWER_API_KEY"
    origem = "autoteste"

    def bearer(self):
        return dom.exigir_bearer(self._valor, nome_da_variavel=self.nome_da_variavel)

    def referencia_declarada(self):
        return self._referencia


def _broker(porta, *, valor="chave-de-teste-nao-e-real", perfis=("k11abc",),
            registro=None, referencia=None) -> Broker:
    return Broker(endereco=ENDERECO_PADRAO, perfis_permitidos=perfis,
                  fonte=_FonteFalsa(valor, referencia), porta=porta,
                  registro=registro if registro is not None else Registro())


def _recusa(falhas: list[str], nome: str, fn, esperado: str | None = None) -> None:
    """Roda `fn` e exige que ela recuse. `esperado` confere o ESTADO, nao a frase."""
    try:
        fn()
    except (dom.BrokerRecusado, dom.AcessoIndisponivel) as exc:
        if esperado and getattr(exc, "estado", None) != esperado:
            falhas.append(f"{nome}: recusou com estado {getattr(exc, 'estado', '?')}, "
                          f"esperado {esperado}")
        return
    except Exception as exc:  # noqa: BLE001
        falhas.append(f"{nome}: levantou {type(exc).__name__} em vez de recusar")
        return
    falhas.append(f"{nome}: NAO recusou")


def autoteste() -> int:  # noqa: C901 - uma prova por bloco, lida de cima a baixo
    f: list[str] = []
    SEGREDO = "NAO-E-UMA-CHAVE-REAL-mas-serve-de-canario"

    # ── 1. Endereco: so loopback literal ────────────────────────────────────
    _recusa(f, "endereco/dns", lambda: dom.exigir_endereco_de_loopback(
        "http://local.adspower.net:50325"))
    _recusa(f, "endereco/externo", lambda: dom.exigir_endereco_de_loopback(
        "http://10.0.0.5:50325"))
    _recusa(f, "endereco/https", lambda: dom.exigir_endereco_de_loopback(
        "https://127.0.0.1:50325"))
    _recusa(f, "endereco/userinfo", lambda: dom.exigir_endereco_de_loopback(
        "http://user:senha@127.0.0.1:50325"))
    _recusa(f, "endereco/sem-porta", lambda: dom.exigir_endereco_de_loopback(
        "http://127.0.0.1"))
    _recusa(f, "endereco/com-caminho", lambda: dom.exigir_endereco_de_loopback(
        "http://127.0.0.1:50325/api"))
    if dom.exigir_endereco_de_loopback("http://127.0.0.1:50325/") != ENDERECO_PADRAO:
        f.append("endereco/canonico: nao normalizou a barra final")
    if dom.exigir_endereco_de_loopback("http://[::1]:50325") != "http://[::1]:50325":
        f.append("endereco/ipv6: a forma canonica perdeu os colchetes e deixou de ser URL")

    # ── 2. Modo sem verificacao falha no preflight ──────────────────────────
    for flag in ("--no-verify", "--insecure", "--sem-verificacao", "--no-masking"):
        _recusa(f, f"verificacao/{flag}",
                lambda flag=flag: dom.exigir_verificacao_ligada([flag], {}))
    _recusa(f, "verificacao/env", lambda: dom.exigir_verificacao_ligada(
        [], {"ADSPOWER_NO_AUTH": "1"}))
    try:
        dom.exigir_verificacao_ligada(["--acao", "status"], {"ADSPOWER_NO_AUTH": "0"})
    except Exception as exc:  # noqa: BLE001
        f.append(f"verificacao/desligado-explicito: recusou indevidamente ({exc})")

    # ── 3. Acao: allowlist, e o checkpoint com NOME ─────────────────────────
    for mutante in dom.ACOES_QUE_EXIGEM_CHECKPOINT:
        _recusa(f, f"acao/{mutante}", lambda m=mutante: dom.exigir_acao(m),
                esperado="blocked/exige_checkpoint")
    _recusa(f, "acao/inexistente", lambda: dom.exigir_acao("voar"))
    if any(a.muta for a in dom.ACOES.values()):
        f.append("acao/catalogo: ha acao MUTANTE publicada nesta versao")

    # ── 4. Perfil e parametros ──────────────────────────────────────────────
    _recusa(f, "perfil/allowlist-vazia", lambda: dom.exigir_perfil("k11abc", []))
    _recusa(f, "perfil/fora-da-allowlist", lambda: dom.exigir_perfil("k99zzz", ["k11abc"]))
    _recusa(f, "perfil/forma", lambda: dom.exigir_perfil("k11 abc/../etc", ["k11 abc/../etc"]))
    _recusa(f, "parametro/desconhecido", lambda: dom.exigir_parametros(
        dom.ACOES["inventario_perfis"], {"cookie": "x"}))
    _recusa(f, "parametro/valor-estranho", lambda: dom.exigir_parametros(
        dom.ACOES["inventario_perfis"], {"page": "1 OR 1=1"}))

    # ── 5. Timeout e chave ──────────────────────────────────────────────────
    _recusa(f, "timeout/zero", lambda: dom.exigir_timeout(0))
    _recusa(f, "timeout/enorme", lambda: dom.exigir_timeout(3600))
    if dom.exigir_timeout(None) != dom.TIMEOUT_PADRAO_S:
        f.append("timeout/padrao: valor inesperado")
    _recusa(f, "chave/curta", lambda: dom.exigir_chave_de_idempotencia("abc"))

    # ── 6. O Segredo nao se imprime ─────────────────────────────────────────
    s = dom.Segredo(SEGREDO)
    for rotulo, texto in (("repr", repr(s)), ("str", str(s)), ("format", f"{s}"),
                          ("interpolacao", "%s" % (s,))):
        if SEGREDO in texto:
            f.append(f"segredo/{rotulo}: o valor apareceu")
    for rotulo, ato in (("len", lambda: len(s)),
                        ("json", lambda: json.dumps({"x": s})),
                        ("deepcopy", lambda: __import__("copy").deepcopy(s)),
                        ("pickle", lambda: __import__("pickle").dumps(s))):
        try:
            ato()
        except TypeError:
            continue
        except Exception as exc:  # noqa: BLE001
            f.append(f"segredo/{rotulo}: levantou {type(exc).__name__}, esperado TypeError")
            continue
        f.append(f"segredo/{rotulo}: passou, e deveria ter sido recusado")
    if s.revelar() != SEGREDO:
        f.append("segredo/revelar: nao devolveu o valor")

    # ── 7. Fail closed: sem chave ativa nao ha modo degradado ───────────────
    _recusa(f, "bearer/ausente", lambda: dom.exigir_bearer(None, nome_da_variavel="X"),
            esperado="blocked/segredo_ausente")
    _recusa(f, "bearer/vazio", lambda: dom.exigir_bearer("   ", nome_da_variavel="X"),
            esperado="blocked/segredo_ausente")
    _recusa(f, "bearer/nao-resolvido",
            lambda: dom.exigir_bearer("op://VOLC/AdsPower/credential", nome_da_variavel="X"),
            esperado="blocked/segredo_nao_resolvido")
    _recusa(f, "bearer/placeholder",
            lambda: dom.exigir_bearer("changeme", nome_da_variavel="X"))

    porta = _PortaFalsa()
    _recusa(f, "broker/revogado",
            lambda: asyncio.run(_broker(porta, valor=None).executar(
                Pedido(acao="status", chave_idempotencia="revogacao-0001"))),
            esperado="blocked/segredo_ausente")
    if porta.chamadas:
        f.append("broker/revogado: chamou a Local API sem Bearer ativo")

    # ── 8. Projecao: a senha do perfil nao entra no recibo ──────────────────
    BRUTO = {
        "code": 0, "msg": "success",
        "data": {"list": [{
            "user_id": "k11abc", "serial_number": 7, "name": "Piloto organico",
            "group_id": "g1", "group_name": "VOLC", "domain_name": "facebook.com",
            "created_time": 1756800000,
            # Tudo o que segue NAO pode sobreviver a projecao.
            "username": "conta@exemplo.com", "password": "Tr0ub4dor&3",
            "fakey": "JBSWY3DPEHPK3PXP", "cookie": "[{\"name\":\"c_user\"}]",
            "remark": "senha antiga: Tr0ub4dor&3",
            "user_proxy_config": {"proxy_soft": "luminati", "proxy_user": "u",
                                  "proxy_password": "p", "proxy_host": "1.2.3.4"},
        }]},
    }
    projetado = dom.projetar_resposta(dom.ACOES["inventario_perfis"], BRUTO)
    serializado = json.dumps(projetado, ensure_ascii=False)
    for proibido in ("Tr0ub4dor&3", "JBSWY3DPEHPK3PXP", "c_user", "conta@exemplo.com",
                     "1.2.3.4", "luminati", "proxy_password"):
        if proibido in serializado:
            f.append(f"projecao: {proibido!r} sobreviveu")
    perfil = projetado["perfis"][0]
    if perfil.get("user_id") != "k11abc" or perfil.get("name") != "Piloto organico":
        f.append("projecao: perdeu a identidade do perfil")
    if perfil.get("tem_proxy") is not True:
        f.append("projecao: nao registrou a presenca do proxy")
    if set(perfil) - set(dom.CAMPOS_DE_PERFIL) - {"tem_proxy"}:
        f.append("projecao: apareceu campo fora da allowlist")

    # `status` desconhecido NAO e "fechado".
    aberto = dom.projetar_resposta(dom.ACOES["estado_do_perfil"],
                                   {"code": 0, "data": {"status": "Active"}})["aberto"]
    fechado = dom.projetar_resposta(dom.ACOES["estado_do_perfil"],
                                    {"code": 0, "data": {"status": "Inactive"}})["aberto"]
    ignoto = dom.projetar_resposta(dom.ACOES["estado_do_perfil"],
                                   {"code": 0, "data": {}})["aberto"]
    if (aberto, fechado, ignoto) != (True, False, None):
        f.append(f"projecao/estado: ({aberto}, {fechado}, {ignoto}) em vez de (True, False, None)")

    # ── 9. A peneira final do recibo ────────────────────────────────────────
    _recusa(f, "peneira/chave-sensivel",
            lambda: dom.recusar_vazamento({"ok": True, "cookie": "x"}))
    _recusa(f, "peneira/material",
            lambda: dom.recusar_vazamento({"nota": "op://VOLC/Item/campo"}),
            esperado="falha/vazamento")

    # ── 10. O recibo real: sem segredo, com postura ─────────────────────────
    porta = _PortaFalsa(BRUTO)
    recibo = asyncio.run(_broker(porta, valor=SEGREDO,
                                 referencia="op://VOLC/AdsPower/credential").executar(
        Pedido(acao="inventario_perfis", chave_idempotencia="inventario-0001")))
    texto = json.dumps(recibo, ensure_ascii=False, default=str)
    for proibido in (SEGREDO, "op://", "Tr0ub4dor&3", "JBSWY3DPEHPK3PXP"):
        if proibido in texto:
            f.append(f"recibo: {proibido!r} apareceu")
    if any(SEGREDO in v for v in porta.viu_bearer_como_texto):
        f.append("recibo: o Segredo virou texto no caminho ate a porta")
    if recibo["bearer"] != {"presente": True, "origem": "autoteste",
                            "nome_da_variavel": "VOLC_ADSPOWER_API_KEY"}:
        f.append("recibo: a postura do bearer mudou de forma")
    if recibo["referencia"].get("digest") is None or recibo["referencia"]["segmentos"] != 3:
        f.append("recibo: a forma da referencia nao foi registrada")
    if recibo["muta"] is not False or recibo["idempotente"] is not False:
        f.append("recibo: muta/idempotente com valor inesperado")

    # ── 11. Idempotencia: replay e conflito ─────────────────────────────────
    registro = Registro()
    b = _broker(_PortaFalsa(BRUTO), valor=SEGREDO, registro=registro)
    primeiro = asyncio.run(b.executar(Pedido(acao="status", chave_idempotencia="ritmo-0001")))
    segundo = asyncio.run(b.executar(Pedido(acao="status", chave_idempotencia="ritmo-0001")))
    if primeiro["idempotente"] is not False or segundo["idempotente"] is not True:
        f.append("idempotencia: replay nao foi marcado")
    if primeiro["run_id"] != segundo["run_id"]:
        f.append("idempotencia: o replay mudou de run_id")
    _recusa(f, "idempotencia/conflito",
            lambda: asyncio.run(b.executar(Pedido(
                acao="inventario_perfis", chave_idempotencia="ritmo-0001"))),
            esperado="falha/conflito_de_idempotencia")

    # ── 12. Indisponibilidade nao vira inventario vazio ─────────────────────
    caido = _PortaFalsa(erro=dom.AcessoIndisponivel(
        "sem Local API", estado="blocked/local_api_ausente"))
    recibo = asyncio.run(_broker(caido, valor=SEGREDO).executar(
        Pedido(acao="inventario_perfis", chave_idempotencia="caido-0001")))
    if recibo["estado"] != "blocked/local_api_ausente":
        f.append("indisponivel: estado inesperado")
    if recibo["resultado"].get("perfis") == [] or "perfis" in recibo["resultado"]:
        f.append("indisponivel: virou lista vazia de perfis")
    if recibo["codigo_de_saida"] != dom.ESTADOS["blocked/local_api_ausente"]:
        f.append("indisponivel: codigo de saida inesperado")

    # ── 13. O transporte tambem recusa acao mutante ─────────────────────────
    #
    # Cinto e suspensorio: o catalogo ja nao publica acao mutante. Esta prova
    # constroi uma a mao e verifica que a camada que abre o socket recusa
    # sozinha — porque um catalogo e uma lista, e listas ganham linha nova.
    inventada = dom.Acao(nome="abrir_perfil", metodo="GET", caminho="/api/v1/browser/start",
                         muta=True, exige_perfil=True, parametros=("user_id",),
                         descricao="nao deveria passar")
    _recusa(f, "transporte/mutante",
            lambda: asyncio.run(ClienteLocalApi(ENDERECO_PADRAO).chamar(
                inventada, {"user_id": "k11abc"}, dom.Segredo("x"), 1.0)),
            esperado="blocked/exige_checkpoint")

    if f:
        print("FALHOU:")
        for falha in f:
            print(f"  - {falha}")
        return 1
    print("autoteste OK — as recusas do broker, sem rede, sem AdsPower e sem 1Password")
    return 0


def principal(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="broker-adspower",
        description=("Broker de acesso do Cofre (P03-T11). Loopback, Bearer injetado por "
                     "`op run`, allowlist de perfil e acao. Esta versao SO pergunta."))
    # Sem `choices`: com ele, `--acao abrir_perfil` morreria no argparse com
    # "invalid choice", e a pessoa concluiria que o nome esta errado. O catalogo
    # responde melhor — "esta acao exige checkpoint" diz o que falta e a quem pedir.
    parser.add_argument("--acao", help="acao de leitura a executar (faz rede). "
                                       "Permitidas: " + ", ".join(sorted(dom.ACOES)))
    parser.add_argument("--perfil", help="user_id do perfil, quando a acao exigir")
    parser.add_argument("--perfis-permitidos", nargs="*", default=[],
                        help="allowlist de perfis deste broker")
    parser.add_argument("--parametro", action="append", metavar="CHAVE=VALOR",
                        help="parametro da acao (so os nomes que ela declara)")
    parser.add_argument("--endereco", default=ENDERECO_PADRAO,
                        help=f"endereco da Local API (padrao: {ENDERECO_PADRAO})")
    parser.add_argument("--chave-idempotencia", help="8 a 120 caracteres; derive do ato")
    parser.add_argument("--timeout", type=float, help="segundos (0.5 a 60)")
    parser.add_argument("--preflight", action="store_true",
                        help="so confere a configuracao; nao faz rede")
    parser.add_argument("--autoteste", action="store_true",
                        help="roda as provas internas e sai 0/1; nao faz rede")
    args = parser.parse_args(argv)

    if args.autoteste:
        return autoteste()
    try:
        return executar(args, argv, os.environ)
    except dom.BrokerRecusado as exc:
        return _emitir(_recibo_de_recusa(exc.estado, str(exc)))


if __name__ == "__main__":
    raise SystemExit(principal())
