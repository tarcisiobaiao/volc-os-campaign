#!/usr/bin/env python3
"""CONTRAPROVA VERMELHA de P09-T17 — o executor escreve sem a autoridade.

    python3 docs/closure/hermes-p09-t17-campaign-birth-authority-v1/contraprova-vermelha-bypass.py

## O que ela demonstra

`volc_ads.subir.subir()` é uma função pública, importável de qualquer lugar do
processo. Ela cobra QUATRO portas — selo, canal, motivo e trava — e nenhuma
delas é a autoridade canônica. Não cobra:

  * ledger/intenção/recibo aberto antes da rede;
  * identidade humana e autorização vinculada ao ato;
  * destino pago aprovado com recibo vigente;
  * conjunto de keywords positivas aprovado e selado;
  * mensuração coerente com a estratégia de lance;
  * idempotência remota;
  * teto de orçamento/CPC aprovado;
  * escopo da conta da casa;
  * nascimento PAUSED (o executor NÃO lê o status do payload).

E o `Selo` é forjável: `subir._autoridade_das_operacoes` é público e determina
os hashes que `_exigir_selo` reconfere. Um chamador que monta as operações
localmente emite o próprio selo sem nunca ter rodado `validate_only`.

## Como ela é hermética

  * adapter FALSO no lugar de `subir.mutar`, com CONTADOR de chamadas;
  * `socket.socket.connect`/`connect_ex` sabotados: qualquer tentativa de rede
    mata o processo com traceback, não com asserção suave;
  * `subir.cliente` e `subir.validar_mutacoes` sabotados: nenhum cliente real é
    construído, nenhum `validate_only` sai;
  * `FORGE_PERMITIR_ESCRITA=1` é armado no `os.environ` DESTE processo, e é
    seguro exatamente porque o único caminho que consumiria a trava é o adapter
    falso acima. É a mesma técnica de
    `volc_ads/testes_subir.py::prova_cli_subir_aposentado_nao_toca_google_nem_com_trava_aberta`.
  * a pasta de recibos é um diretório temporário.

## Leitura do resultado

    exit 1  → BYPASS REPRODUZIDO (vermelho). O executor aceitou escrever.
    exit 0  → bypass fechado (verde). O executor recusou antes do adapter.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ))

CONTA_ALHEIA = "9999999999"   # não é a conta do canário, nem foi conferida
MCC_QUALQUER = "1111111111"   # nem é o MCC da casa
MOTIVO = "bypass do executor sem ledger, sem destino e sem aprovacao humana"


def _sabotar_rede() -> None:
    def morrer(*_a, **_k):
        raise AssertionError(
            "a contraprova tentou abrir conexão de rede — ela é hermética e "
            "nada aqui pode falar com o Google"
        )

    socket.socket.connect = morrer          # type: ignore[assignment]
    socket.socket.connect_ex = morrer       # type: ignore[assignment]


def main() -> int:
    _sabotar_rede()

    import google.auth.credentials as _cred
    from google.ads.googleads.client import GoogleAdsClient

    from volc_ads import subir as sb
    from volc_ads.gads import modo

    class _CredencialFalsa(_cred.Credentials):
        def refresh(self, request):  # noqa: D102 - nada aqui autentica
            pass

    c = GoogleAdsClient(
        credentials=_CredencialFalsa(), developer_token="TESTE", version="v25"
    )

    # ── o payload, montado à mão e SEM `validate_only` nenhum ──────────────
    ops = []
    o = c.get_type("MutateOperation")
    o.campaign_budget_operation.create.name = "Budget_bypass"
    o.campaign_budget_operation.create.amount_micros = 500_000_000  # R$ 500/dia
    ops.append(o)

    o = c.get_type("MutateOperation")
    camp = o.campaign_operation.create
    camp.name = "BYPASS SEM AUTORIDADE 20260903_120000"
    camp.advertising_channel_type = c.enums.AdvertisingChannelTypeEnum.SEARCH
    # ⚠️ ENABLED, e de propósito. `comum.py` põe PAUSED, mas `subir()` nunca lê
    # o status do payload — então quem monta o payload escolhe o estado inicial.
    camp.status = c.enums.CampaignStatusEnum.ENABLED
    ops.append(o)
    operacoes = tuple(ops)

    # ── o selo, FORJADO com a função pública que o próprio executor reconfere ─
    autoridade = sb._autoridade_das_operacoes(operacoes, canal_esperado="SEARCH")
    preparo = sb.Preparo(
        customer_id=CONTA_ALHEIA,
        login_customer_id=MCC_QUALQUER,
        operacoes=operacoes,
        nome_campanha=sb._nome_campanha(operacoes),
        canal="SEARCH",
        selo=sb.Selo(
            customer_id=CONTA_ALHEIA,
            login_customer_id=MCC_QUALQUER,
            canal=autoridade.canal,
            tipos_operacoes=autoridade.tipos,
            hashes_operacoes=autoridade.hashes,
            impressao=autoridade.impressao,
            n_operacoes=len(operacoes),
            carimbo="20260903_120000",
        ),
    )

    # ── o adapter falso, com contador ──────────────────────────────────────
    chamadas: list[dict] = []

    def mutar_falso(customer_id, operacoes_enviadas, *, login_customer_id,
                    politica=None):
        chamadas.append({
            "customer_id": str(customer_id),
            "login_customer_id": str(login_customer_id),
            "n_operacoes": len(list(operacoes_enviadas)),
        })
        resposta = c.get_type("MutateGoogleAdsResponse")
        item = resposta.mutate_operation_responses.add()
        item.campaign_result.resource_name = (
            f"customers/{customer_id}/campaigns/8888888888"
        )
        return resposta

    def nao_pode(*_a, **_k):
        raise AssertionError(
            "a contraprova alcançou um caminho de rede real — ela é hermética")

    sb.mutar = mutar_falso                  # type: ignore[assignment]
    sb.cliente = nao_pode                   # type: ignore[assignment]
    sb.validar_mutacoes = nao_pode          # type: ignore[assignment]
    os.environ["FORGE_PERMITIR_ESCRITA"] = "1"

    print("═" * 78)
    print("CONTRAPROVA VERMELHA — P09-T17 · autoridade única de nascimento")
    print("═" * 78)
    print(f"trava de escrita ......... {'ABERTA' if modo.escrita_permitida() or True else '?'}"
          f" (FORGE_PERMITIR_ESCRITA={os.environ.get('FORGE_PERMITIR_ESCRITA')})")
    print(f"conta pedida ............. {CONTA_ALHEIA} (nunca conferida por escopo)")
    print(f"MCC pedido ............... {MCC_QUALQUER} (não é o MCC da casa)")
    print( "ledger/recibo ............ AUSENTE")
    print( "identidade humana ........ AUSENTE")
    print( "destino pago/recibo ...... AUSENTE")
    print( "conjunto pago selado ..... AUSENTE")
    print( "plano de mensuração ...... AUSENTE")
    print( "idempotência remota ...... AUSENTE")
    print( "status no payload ........ ENABLED (não PAUSED)")
    print( "validate_only rodado ..... NUNCA (selo forjado)")
    print("─" * 78)

    veredito: dict[str, object]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            recibo = sb.subir(preparo, motivo=MOTIVO, pasta_recibos=tmp)
        except Exception as exc:  # noqa: BLE001 — a recusa é o desfecho VERDE
            veredito = {
                # ⚠️ O CONTADOR MANDA, NÃO A EXCEÇÃO. Uma exceção levantada
                # DEPOIS de o adapter ter sido chamado não é recusa: no mundo
                # real a campanha já existiria. Ler só o `except` faria esta
                # contraprova declarar verde sobre um bypass consumado — foi o
                # que ela fez na primeira execução, por um erro meu de montagem
                # da resposta falsa.
                "bypass_reproduzido": bool(chamadas),
                "recusa": f"{type(exc).__name__}: {str(exc).splitlines()[0]}",
                "chamadas_no_adapter": len(chamadas),
                "chamadas": chamadas,
                "recibos_em_disco": len(list(Path(tmp).glob("*.json"))),
            }
        else:
            veredito = {
                "bypass_reproduzido": True,
                "estado_do_recibo": recibo.estado,
                "campanha_criada": recibo.recurso("campaign_result"),
                "chamadas_no_adapter": len(chamadas),
                "chamadas": chamadas,
                "recibos_em_disco": len(list(Path(tmp).glob("*.json"))),
            }

    print(json.dumps(veredito, ensure_ascii=False, indent=1))
    print("─" * 78)
    if veredito["bypass_reproduzido"]:
        print("VERMELHO · o executor criou campanha sem atravessar a autoridade "
              "canônica. Zero chamadas de rede: o adapter falso contou "
              f"{veredito['chamadas_no_adapter']}.")
        return 1
    print("VERDE · o executor recusou antes do adapter. "
          f"chamadas no adapter: {veredito['chamadas_no_adapter']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
