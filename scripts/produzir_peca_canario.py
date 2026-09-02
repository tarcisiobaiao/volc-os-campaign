"""Produz a peca canario pela espinha produtiva e escreve a evidencia tecnica.

Nao e um helper isolado: ele enfileira no MESMO deposito, roda o MESMO operario
com a MESMA loja e le o MESMO recibo que a producao le. Uma evidencia produzida
por um caminho paralelo nao seria evidencia da producao.

⚠️ O que este arquivo escreve NAO inclui o texto do briefing, nem sanitizado.
Ele e artefato de fechamento e vai para o repositorio; o texto do cliente nao vai.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "backend"), str(RAIZ)]

BRIEFING_IMAGEM = "Matriculas 2027 abertas. Bolsa por merito para quem entra agora."
BRIEFING_VIDEO = "Sua matricula 2027 comeca aqui. Turmas com vagas limitadas."


def _pedido(tenant, receita, motor, modo, seed, saidas, parametros):
    from app.criativo.bancada.contrato import Encomenda, SaidaPedida

    return Encomenda(
        receita_id=receita, tenant_id=tenant, motor_slug=motor, modo_slug=modo,
        finalidade_slug="captacao", seed=seed,
        saidas=tuple(SaidaPedida(**s) for s in saidas),
        parametros=parametros,
    )


def _resumo(trabalho, chave_do_storage_existe) -> dict:
    r = trabalho.recibo
    a = r["artefatos"][0]
    s = r["storage"][0]
    return {
        "trabalho_id": trabalho.id,
        "estado": trabalho.estado.value,
        "tentativa": r["tentativa"],
        "produzido_por": r["produzido_por"],
        "motor": f'{r["motor_slug"]}@{r["motor_versao"]}',
        "seed": r["seed"],
        "chave_de_idempotencia": r["chave_de_idempotencia"],
        "assinatura_determinista": r["assinatura_determinista"],
        "duracao_do_trabalho_s": r["duracao_do_trabalho_s"],
        "artefato": {
            "slot": a["slot"], "mime": a["mime"], "bytes": a["bytes_"],
            "sha256": a["sha256"], "largura": a["largura"], "altura": a["altura"],
            "duracao_s": a["duracao_s"], "video": a["video"],
            "enquadramento": a["enquadramento"],
        },
        "audio": r["audio"],
        "audio_ausente_porque": r["audio_ausente_porque"],
        "video_ausente_porque": r["video_ausente_porque"],
        "procedencia": r["procedencia"],
        "custo": r["custo"],
        # Do insumo sai o ESTADO e a impressao digital. O texto, nem sanitizado.
        "insumo": {
            "estado": r["insumo"]["estado"],
            "hash_do_completo": r["insumo"]["hash_do_completo"],
            "substituicoes": r["insumo"]["substituicoes"],
            "versao_do_sanitizador": r["insumo"]["versao_do_sanitizador"],
        },
        "hashes_de_entrada": r["hashes_de_entrada"],
        "storage": {
            "estado": s["estado"],
            "chave": s["chave"]["valor"],
            "sha256_relido": s["sha256_relido"]["valor"],
            "bytes_relidos": s["bytes_relidos"]["valor"],
            "lido_em": s["lido_em"],
            "objeto_existe_no_disco": chave_do_storage_existe,
            "hash_do_artefato_bate_com_o_relido":
                s["sha256_relido"]["valor"] == a["sha256"],
        },
        "destinos": r["destinos"],
        "aprovacao": r["aprovacao"],
        "gates": [
            {"gate": v["gate"], "resultado": v["resultado"], "bloqueante": v["bloqueante"]}
            for v in r["validacoes"]
        ],
    }


def principal() -> int:
    destino = Path(os.environ.get("CRIATIVO_CANARIO_SAIDA")
                   or (RAIZ / "docs/closure/creative-factory-production-last-mile-v1"
                       "/contraprovas/PECA-CANARIO.json"))
    trabalho_dir = Path(tempfile.mkdtemp(prefix="volc-canario-"))
    os.environ["CRIATIVO_BANCADA_DIR"] = str(trabalho_dir / "bancada")
    os.environ["CRIATIVO_STORAGE_DIR"] = str(trabalho_dir / "storage")
    os.environ["CRIATIVO_DEPOSITO"] = "sqlite"

    from app.criativo.bancada.servico import montar
    import volc_ads.criativo.destinos as D

    deposito, operario, _ = montar()
    pecas: dict[str, object] = {}

    encomendas = {
        "imagem": _pedido(
            "positivo", "display-matricula-2027", "tipografico-local", "estatica-1x1",
            20260902,
            [{"slot": D.envelope_de("google-display-191x1").slot, "largura": 1200,
              "altura": 628, "midia": "imagem", "mime": "image/png"}],
            # `titulo` e `apoio` sao o que o motor tipografico compoe; `insumo` e o
            # briefing que entra na identidade e na sanitizacao. Os tres viajam.
            {"insumo": BRIEFING_IMAGEM,
             "titulo": "Matriculas 2027 abertas",
             "apoio": "Bolsa por merito para quem entra agora.",
             "canal": "google", "brand_pack_id": "positivo-2027"},
        ),
    }
    if "remotion-local" in operario.motores:
        encomendas["video"] = _pedido(
            "positivo", "reels-matricula-2027", "remotion-local", "video-vertical",
            20260902,
            [{"slot": D.envelope_de("organico-reels-video-9x16").slot, "largura": 1080,
              "altura": 1920, "midia": "video", "mime": "video/mp4"}],
            {"insumo": BRIEFING_VIDEO, "apoio": "Turmas com vagas limitadas.",
             "assinatura": "COLEGIO POSITIVO", "duracao_s": 2.0, "fps": 24,
             "canal": "organico", "brand_pack_id": "positivo-2027"},
        )
    else:
        pecas["video"] = {"nao_produzida": "motor remotion-local nao registrado nesta maquina"}

    for rotulo, encomenda in encomendas.items():
        trabalho, _criado = deposito.enfileirar(encomenda)
        feito = operario.executar(deposito.reivindicar(operario.nome, lease_s=300))
        if feito.estado.value != "rendered":
            pecas[rotulo] = {"falhou": feito.falha, "estado": feito.estado.value}
            continue
        chave = feito.recibo["storage"][0]["chave"]["valor"]
        existe = bool(chave) and (trabalho_dir / "storage" / chave).is_file()
        pecas[rotulo] = _resumo(feito, existe)

    corpo = {
        "_leia": (
            "Peca canario produzida pela espinha produtiva inteira, em diretorio "
            "descartavel. Nenhum ato externo: armazenamento LOCAL, sem provider pago, "
            "sem Supabase, sem publicacao. O texto do briefing NAO esta aqui — so o "
            "estado e a impressao digital dele."
        ),
        "pecas": pecas,
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(corpo, indent=2, ensure_ascii=False) + "\n", "utf-8")
    shutil.rmtree(trabalho_dir, ignore_errors=True)
    print(f"evidencia escrita em {destino}")
    for rotulo, p in pecas.items():
        if isinstance(p, dict) and "artefato" in p:
            a = p["artefato"]
            print(f"  {rotulo}: {a['mime']} {a['largura']}x{a['altura']} "
                  f"{a['bytes']} bytes sha256 {a['sha256'][:16]}… "
                  f"storage={p['storage']['estado']}")
        else:
            print(f"  {rotulo}: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
