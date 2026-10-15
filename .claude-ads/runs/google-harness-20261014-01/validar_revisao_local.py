"""Revisão localizada explícita do output real, sem outra chamada ao Gemini.

Não é corretor automático do engine nem autorização para subir a campanha.
Somente validate_only, via cliente e construtor já usados pelo harness.
"""
import json
import time
from dataclasses import asdict
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from volc_ads.gads import client as gads
from volc_ads.harness.capture import snapshot
from volc_ads.harness.search import Entrada, Proposta, _gravar, preparar, sha

BASE = Path(__file__).resolve().parent


def main():
    entrada = Entrada.model_validate_json((BASE / "canary/input.json").read_text())
    resposta = json.loads((BASE / "canary/proof/gemini-2.json").read_text())
    bruto = json.loads(resposta["text"])
    mudancas = []
    ajustes = {
        "Confira as regras de renda familiar e os critérios gerais para concorrer a vagas gratuitas.":
            "Confira as regras de renda familiar e os critérios para concorrer a vagas gratuitas.",
        "Senac nos 27 Estados": "Senac do Seu Estado",
        "Lista dos 27 Estados": "Senac por Estado",
        "Links para 27 Estados": "Links Oficiais por Estado",
    }
    # Só essas quatro strings de copy. Não toca em keywords, grupos ou dinheiro.
    def revisar(valor, caminho=""):
        if isinstance(valor, dict):
            return {k: revisar(v, caminho + "/" + k) for k, v in valor.items()}
        if isinstance(valor, list):
            return [revisar(v, caminho + "/" + str(i)) for i, v in enumerate(valor)]
        if isinstance(valor, str) and valor in ajustes:
            mudancas.append({"path": caminho, "before": valor, "after": ajustes[valor]})
            return ajustes[valor]
        return valor

    revisada = revisar(bruto)
    assert len(mudancas) == 4, "a resposta mudou; não aplique o roteiro a outro run"
    p = Proposta.model_validate(revisada)
    ops, r = preparar(entrada, p)
    assert r.ok, r.resumo()
    payload = [MessageToDict(o._pb, preserving_proto_field_name=True) for o in ops]
    pasta = BASE / "canary/reviewed"
    pasta.mkdir(exist_ok=True)
    if (pasta / "receipt.json").exists():
        raise ValueError("validação já registrada; não repetir a RPC")
    _gravar(pasta / "proposta.json", revisada)
    _gravar(pasta / "payload.json", payload)
    _gravar(pasta / "revisao.json", {
        "source_response_sha256": sha(resposta), "source_proposal_sha256": sha(bruto),
        "changes": mudancas, "reason": "limite real de 90 caracteres e 26 estados + DF, não 27 estados",
        "reviewer": "Codex lead; revisão local explícita, não chamada LLM",
        "new_llm_calls": 0,
    })
    ids = []
    inicio = time.monotonic()
    falha = gads.validar_mutacoes(entrada.customer_id, ops,
                                  login_customer_id=entrada.login_customer_id, request_ids=ids)
    depois = snapshot(entrada.customer_id, entrada.login_customer_id)
    antes = json.loads((BASE / "canary/snapshot-before.json").read_text())
    _gravar(BASE / "canary/snapshot-after.json", depois)
    receipt = {
        "status": "validate_only_passed" if falha is None else "validate_only_failed",
        "api_version": gads.VERSAO_API, "google_request_ids": ids,
        "google_error": asdict(falha) if falha else None,
        "seconds_validation_and_readback": round(time.monotonic() - inicio, 3),
        "operations": len(ops), "groups": len(p.grupos), "keywords": len(entrada.keywords),
        "payload_sha256": sha(payload), "input_sha256": sha(entrada.model_dump()),
        "local_copy_adjustments": len(mudancas), "new_llm_calls": 0,
        "budget_diario": entrada.budget_diario, "cpc_inicial": entrada.cpc_inicial,
        "finance_origin": "explicit_technical_canary_input_not_serp",
        "persistent_mutations": 0, "validate_only": True, "campaign_status": "PAUSED",
        "snapshot_campaigns_ads_budget_strategy_unchanged": sha(antes) == sha(depois),
        "policy_approval_proven": False, "roi_proven": False,
        "http_authenticated_creation_proven": False,
        "builder_findings": asdict(r),
    }
    _gravar(pasta / "receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
