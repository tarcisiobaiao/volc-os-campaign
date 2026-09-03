"""A peca-canario do go-live: a mesma espinha, atravessada por um WORKER DE VERDADE.

## Por que existe uma segunda canario

`produzir_peca_canario.py` prova a espinha, e prova bem — mas chama
`operario.executar(deposito.reivindicar(...))` DENTRO do proprio processo. Ele
prova o contrato do operario; nao prova que o trabalho atravessa um processo
separado. Sao afirmacoes diferentes, e a que o go-live precisa e a segunda: em
producao quem produz e `python -m app.criativo.bancada.worker`, e um pedido que
so funciona quando o web o executa nao e um pedido durrvel.

Esta canario nao reimplementa nada. Ela enfileira pela MESMA porta, sobe o
worker como SUBPROCESSO real, e depois le o recibo DO DEPOSITO — nunca do valor
de retorno de uma chamada em memoria, porque um retorno em memoria nao prova
persistencia.

## O que ela afirma, e como cada afirmacao e conferida

  1. pedido persistido ............ o trabalho existe no deposito antes do worker subir
  2. idempotencia ................. o mesmo pedido, enfileirado duas vezes, devolve
                                    o MESMO id e `criado=False`
  3. worker separado .............. `produzido_por` = `worker-<pid>`, e esse pid
                                    NAO e o desta processo, e o processo existiu
  4. artefato material ............ o arquivo esta no disco e tem bytes
  5. medicao ...................... sha256/mime/dimensoes recalculados AQUI, a partir
                                    do arquivo, e conferidos contra o recibo
  6. storage verificado ........... o objeto existe na loja e o hash relido bate
  7. recibo ....................... completo, com procedencia e custo nomeado
  8. destino ...................... validado, com veredito
  9. aguardando aprovacao ......... a aprovacao NASCE `aguardando`; ninguem aprovou
 10. zero publicacao ............. nenhuma URL de plataforma no recibo

⚠️ Nenhum ato externo: armazenamento LOCAL em `mktemp`, deposito sqlite
descartavel, motor local sem provider pago, sem Supabase, sem rede de produto.
⚠️ O texto do briefing NAO entra no arquivo de evidencia — so estado e hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "backend"), str(RAIZ)]

BRIEFING_IMAGEM = "Matriculas 2027 abertas. Bolsa por merito para quem entra agora."
BRIEFING_VIDEO = "Sua matricula 2027 comeca aqui. Turmas com vagas limitadas."

# Plataformas cuja URL dentro de um recibo significaria publicacao.
_PLATAFORMAS = (
    "facebook.com", "instagram.com", "graph.facebook", "googleads",
    "googleapis.com/adwords", "youtube.com", "tiktok.com", "postiz",
    "linkedin.com", "x.com/", "twitter.com",
    # ⚠️ `ads.google.com` faltava, e a contraprova do revisor usou exatamente
    # essa: uma lista de dominios so pega o dominio que alguem lembrou.
    "ads.google.com", "business.facebook", "ads.tiktok", "shorts",
)

#: Qualquer URL http(s) dentro de um recibo desta canario e suspeita por
#: construcao: uma peca produzida localmente, guardada localmente e nao aprovada
#: nao tem por que carregar endereco de rede nenhum. Isto pega o destino que
#: ninguem colocou na lista acima.
_URL = re.compile(r"https?://[^\s\"\'<>]+", re.IGNORECASE)

# ⚠️ ACHADO ADVERSARIAL (Codex, 02/09/2026). Procurar so DOMINIO era procurar a
# evidencia mais facil de nao existir. Reproduzido: um recibo com
# `{"publicado": true, "publication_id": "customers/1/ads/99"}` passava com
# `zero_publicacao: true`, porque nao ha dominio nenhum ali. Publicacao deixa
# rastro em NOME de campo, nao so em URL.
_CAMPOS_DE_PUBLICACAO = (
    "publicado", "publicacao", "published", "publication", "publish",
    "ad_id", "adid", "creative_id", "asset_id_externo", "post_id",
    "permalink", "external_id", "id_externo", "remote_id", "veiculado",
)


def _pedido(receita, motor, modo, seed, saidas, parametros):
    from app.criativo.bancada.contrato import Encomenda, SaidaPedida

    return Encomenda(
        receita_id=receita, tenant_id="positivo", motor_slug=motor, modo_slug=modo,
        finalidade_slug="captacao", seed=seed,
        saidas=tuple(SaidaPedida(**s) for s in saidas),
        parametros=parametros,
    )


def _medir(caminho: Path) -> dict:
    """Mede o arquivo AQUI, sem perguntar ao recibo. Conferir o recibo contra ele
    mesmo nao confere nada."""
    dados = caminho.read_bytes()
    medida = {"bytes": len(dados), "sha256": hashlib.sha256(dados).hexdigest()}
    cabeca = dados[:16]
    if cabeca.startswith(b"\x89PNG\r\n\x1a\n"):
        medida["mime_por_magic"] = "image/png"
        medida["largura"] = int.from_bytes(dados[16:20], "big")
        medida["altura"] = int.from_bytes(dados[20:24], "big")
    elif cabeca[4:8] == b"ftyp":
        medida["mime_por_magic"] = "video/mp4"
        try:
            saida = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height,duration",
                 "-of", "json", str(caminho)],
                capture_output=True, text=True, timeout=60, check=True,
            ).stdout
            fluxo = json.loads(saida)["streams"][0]
            medida["largura"] = int(fluxo["width"])
            medida["altura"] = int(fluxo["height"])
            medida["duracao_s"] = round(float(fluxo.get("duration") or 0), 3) or None
        except Exception as e:  # noqa: BLE001
            # Ausencia nomeada, nunca zero.
            medida["dimensao_nao_medida_porque"] = f"ffprobe: {e}"
    else:
        medida["mime_por_magic"] = "desconhecido"
    return medida


def _confere(recibo: dict, medido: dict) -> dict:
    a = recibo["artefatos"][0]
    return {
        "sha256_do_recibo_bate_com_o_arquivo": a["sha256"] == medido["sha256"],
        "bytes_do_recibo_batem_com_o_arquivo": a["bytes_"] == medido["bytes"],
        "mime_do_recibo_bate_com_magic": a["mime"] == medido.get("mime_por_magic"),
        "largura_bate": a["largura"] == medido.get("largura"),
        "altura_bate": a["altura"] == medido.get("altura"),
    }


def _chaves(objeto, prefixo="") -> list[str]:
    """Todos os caminhos de chave do recibo, para procurar por NOME e nao so por valor."""
    saida: list[str] = []
    if isinstance(objeto, dict):
        for k, v in objeto.items():
            saida.append(f"{prefixo}{k}")
            saida.extend(_chaves(v, f"{prefixo}{k}."))
    elif isinstance(objeto, list):
        for item in objeto:
            saida.extend(_chaves(item, prefixo))
    return saida


def _sem_publicacao(recibo: dict) -> dict:
    """Duas perguntas, porque uma so ja falhou: ha URL de plataforma? ha CAMPO de publicacao?"""
    bruto = json.dumps(recibo, ensure_ascii=False)
    texto = bruto.lower()
    urls = sorted({p for p in _PLATAFORMAS if p in texto})
    campos = sorted({c for c in _chaves(recibo)
                     if any(p in c.lower() for p in _CAMPOS_DE_PUBLICACAO)})
    quaisquer = sorted(set(_URL.findall(bruto)))
    return {
        "urls_de_plataforma_no_recibo": urls,
        "campos_com_cheiro_de_publicacao": campos,
        "qualquer_url_no_recibo": quaisquer,
        "zero_publicacao": not urls and not campos and not quaisquer,
    }


def principal() -> int:
    destino = Path(os.environ.get("CRIATIVO_CANARIO_SAIDA")
                   or (RAIZ / "docs/closure/creative-factory-production-go-live-v1"
                       "/contraprovas/PECA-CANARIO-GO-LIVE.json"))
    caixa = Path(tempfile.mkdtemp(prefix="volc-canario-go-live-"))
    ambiente = dict(os.environ)
    ambiente["CRIATIVO_BANCADA_DIR"] = str(caixa / "bancada")
    ambiente["CRIATIVO_STORAGE_DIR"] = str(caixa / "storage")
    ambiente["CRIATIVO_DEPOSITO"] = "sqlite"
    ambiente["PYTHONPATH"] = f'{RAIZ / "backend"}{os.pathsep}{RAIZ}'
    os.environ.update({k: ambiente[k] for k in
                       ("CRIATIVO_BANCADA_DIR", "CRIATIVO_STORAGE_DIR", "CRIATIVO_DEPOSITO")})

    from app.criativo.bancada.servico import montar
    import volc_ads.criativo.destinos as D

    deposito, operario_local, _ = montar()
    motores_desta_maquina = sorted(operario_local.motores)

    encomendas = {
        "imagem": _pedido(
            "display-matricula-2027", "tipografico-local", "estatica-1x1", 20260902,
            [{"slot": D.envelope_de("google-display-191x1").slot, "largura": 1200,
              "altura": 628, "midia": "imagem", "mime": "image/png"}],
            {"insumo": BRIEFING_IMAGEM, "titulo": "Matriculas 2027 abertas",
             "apoio": "Bolsa por merito para quem entra agora.",
             "canal": "google", "brand_pack_id": "positivo-2027"},
        ),
    }
    if "remotion-local" in operario_local.motores:
        encomendas["video"] = _pedido(
            "reels-matricula-2027", "remotion-local", "video-vertical", 20260902,
            [{"slot": D.envelope_de("organico-reels-video-9x16").slot, "largura": 1080,
              "altura": 1920, "midia": "video", "mime": "video/mp4"}],
            {"insumo": BRIEFING_VIDEO, "apoio": "Turmas com vagas limitadas.",
             "assinatura": "COLEGIO POSITIVO", "duracao_s": 2.0, "fps": 24,
             "canal": "organico", "brand_pack_id": "positivo-2027"},
        )

    # ── 1 e 2. pedido persistido, e idempotencia ────────────────────────────
    enfileirados: dict[str, dict] = {}
    for rotulo, encomenda in encomendas.items():
        t1, criado1 = deposito.enfileirar(encomenda)
        t2, criado2 = deposito.enfileirar(encomenda)   # o MESMO pedido, de novo
        enfileirados[rotulo] = {
            "trabalho_id": t1.id,
            "estado_antes_do_worker": t1.estado.value,
            "primeiro_enfileiramento_criou": criado1,
            "segundo_enfileiramento_criou": criado2,
            "mesmo_id_nas_duas_vezes": t1.id == t2.id,
            "idempotente": bool(criado1) and not criado2 and t1.id == t2.id,
        }

    # ── 3. o worker, como PROCESSO ──────────────────────────────────────────
    processo = subprocess.run(
        [sys.executable, "-m", "app.criativo.bancada.worker",
         "--ate-esvaziar", "--lease", "300"],
        cwd=str(RAIZ / "backend"), env=ambiente,
        capture_output=True, text=True, timeout=900,
    )
    worker = {
        "comando": "python -m app.criativo.bancada.worker --ate-esvaziar --lease 300",
        "pid_deste_processo": os.getpid(),
        "codigo_de_saida": processo.returncode,
        "linhas_de_log": len([l for l in processo.stderr.splitlines() if l.strip()]),
    }

    # ── 4-10. o que o DEPOSITO guarda, lido depois que o worker ja saiu ─────
    pecas: dict[str, object] = {}
    for rotulo, info in enfileirados.items():
        trabalho = deposito.por_id(info["trabalho_id"])
        if trabalho is None or trabalho.estado.value != "rendered":
            pecas[rotulo] = {
                **info,
                "estado_depois_do_worker": getattr(trabalho, "estado", None)
                and trabalho.estado.value,
                "falha": getattr(trabalho, "falha", None),
                "nao_produzida": True,
            }
            continue
        r = trabalho.recibo
        a = r["artefatos"][0]
        s = r["storage"][0]
        arquivo = Path(a["caminho"]) if a.get("caminho") else None
        chave = s["chave"]["valor"]
        objeto = caixa / "storage" / chave if chave else None
        medido = _medir(objeto) if objeto and objeto.is_file() else {}
        produzido_por = r["produzido_por"]
        pid_do_worker = produzido_por.rsplit("-", 1)[-1]
        pecas[rotulo] = {
            **info,
            "estado_depois_do_worker": trabalho.estado.value,
            "tentativa": r["tentativa"],
            "produzido_por": produzido_por,
            "produzido_por_outro_processo":
                pid_do_worker.isdigit() and int(pid_do_worker) != os.getpid(),
            "motor": f'{r["motor_slug"]}@{r["motor_versao"]}',
            "seed": r["seed"],
            "chave_de_idempotencia": r["chave_de_idempotencia"],
            "assinatura_determinista": r["assinatura_determinista"],
            "artefato": {
                "slot": a["slot"], "mime": a["mime"], "bytes": a["bytes_"],
                "sha256": a["sha256"], "largura": a["largura"], "altura": a["altura"],
                "duracao_s": a["duracao_s"], "video": a["video"],
                "enquadramento": a["enquadramento"],
                "arquivo_do_worker_ainda_existe": bool(arquivo and arquivo.is_file()),
            },
            "medido_agora_a_partir_do_arquivo": medido,
            "recibo_bate_com_o_arquivo": _confere(r, medido) if medido else None,
            "audio": r["audio"],
            "audio_ausente_porque": r["audio_ausente_porque"],
            "video_ausente_porque": r["video_ausente_porque"],
            "procedencia": r["procedencia"],
            "custo": r["custo"],
            "insumo": {
                "estado": r["insumo"]["estado"],
                "hash_do_completo": r["insumo"]["hash_do_completo"],
                "substituicoes": r["insumo"]["substituicoes"],
                "versao_do_sanitizador": r["insumo"]["versao_do_sanitizador"],
                "texto_no_arquivo_de_evidencia": False,
            },
            "hashes_de_entrada": r["hashes_de_entrada"],
            "storage": {
                "estado": s["estado"], "chave": chave,
                "sha256_relido": s["sha256_relido"]["valor"],
                "bytes_relidos": s["bytes_relidos"]["valor"],
                "lido_em": s["lido_em"],
                "objeto_existe_na_loja": bool(objeto and objeto.is_file()),
                "hash_relido_bate_com_o_artefato":
                    s["sha256_relido"]["valor"] == a["sha256"],
                "hash_relido_bate_com_a_medicao_independente":
                    s["sha256_relido"]["valor"] == medido.get("sha256"),
            },
            "destinos": r["destinos"],
            "aprovacao": r["aprovacao"],
            "aguardando_aprovacao": (r["aprovacao"] or {}).get("estado") == "aguardando",
            "publicacao": _sem_publicacao(r),
            "gates": [
                {"gate": v["gate"], "resultado": v["resultado"],
                 "bloqueante": v["bloqueante"]}
                for v in r["validacoes"]
            ],
        }

    corpo = {
        "_leia": (
            "Peca canario do GO-LIVE. A diferenca para a canario do last-mile e o "
            "worker: aqui o trabalho atravessa um PROCESSO SEPARADO "
            "(python -m app.criativo.bancada.worker), e o recibo e lido do deposito "
            "depois que esse processo ja saiu. Nenhum ato externo: armazenamento "
            "LOCAL em mktemp, sqlite descartavel, motor local sem provider pago, sem "
            "Supabase, sem publicacao. O texto do briefing NAO esta aqui — so o "
            "estado e a impressao digital dele."
        ),
        "motores_desta_maquina": motores_desta_maquina,
        "worker": worker,
        "pecas": pecas,
    }
    shutil.rmtree(caixa, ignore_errors=True)

    print(f"worker: saida={processo.returncode} pid_do_teste={os.getpid()}")
    ok = True
    for rotulo, p in pecas.items():
        if isinstance(p, dict) and "artefato" in p:
            a, s = p["artefato"], p["storage"]
            bate = p["recibo_bate_com_o_arquivo"] or {}
            print(f"  {rotulo}: {a['mime']} {a['largura']}x{a['altura']} {a['bytes']}B "
                  f"sha256 {a['sha256'][:16]}… storage={s['estado']} "
                  f"por={p['produzido_por']} outro_processo={p['produzido_por_outro_processo']} "
                  f"idempotente={p['idempotente']} aguardando={p['aguardando_aprovacao']} "
                  f"recibo_bate={all(bate.values()) if bate else None}")
            # ⚠️ ACHADO ADVERSARIAL (Codex, 02/09/2026). A primeira versao deste
            # veredito ignorava cinco fatos que ele PRECISA afirmar, e por isso
            # podia sair "TODAS AS AFIRMACOES CONFERIDAS" com o arquivo do
            # worker ausente, os destinos vazios e um gate bloqueante em FAIL.
            # Um veredito que nao olha o que promete olhar e evidencia falsa —
            # e este arquivo existe justamente para ser evidencia.
            gates_bloqueantes_ok = all(
                g["resultado"] in ("PASS", "SKIPPED")
                for g in p["gates"] if g["bloqueante"]
            )
            afirmacoes = {
                "worker saiu limpo": worker["codigo_de_saida"] == 0,
                "produzido por outro processo": p["produzido_por_outro_processo"],
                "idempotente": p["idempotente"],
                "estado rendered": p["estado_depois_do_worker"] == "rendered",
                "arquivo do worker existe": p["artefato"]["arquivo_do_worker_ainda_existe"],
                "bytes positivos": a["bytes"] > 0,
                "objeto existe na loja": s["objeto_existe_na_loja"],
                "storage VERIFIED_OK": s["estado"] == "VERIFIED_OK",
                "hash relido == medicao independente":
                    s["hash_relido_bate_com_a_medicao_independente"],
                "recibo bate com o arquivo": bool(bate) and all(bate.values()),
                "destino avaliado": bool(p["destinos"]),
                "nenhum gate bloqueante reprovou": gates_bloqueantes_ok,
                "aguardando aprovacao": p["aguardando_aprovacao"],
                "zero publicacao": p["publicacao"]["zero_publicacao"],
            }
            p["afirmacoes_conferidas"] = afirmacoes
            falhas = [k for k, v in afirmacoes.items() if not v]
            if falhas:
                print(f"    NAO CONFERIDO: {falhas}")
            ok = ok and not falhas
        else:
            print(f"  {rotulo}: NAO PRODUZIDA — {p.get('falha')} "
                  f"estado={p.get('estado_depois_do_worker')}")
            ok = False
    # ⚠️ O arquivo e escrito DEPOIS do veredito, de proposito: as afirmacoes
    # conferidas fazem parte da evidencia, e uma evidencia que nao registra o
    # que foi conferido pede que se acredite nela.
    corpo["veredito"] = "TODAS AS AFIRMACOES CONFERIDAS" if ok else "HA AFIRMACAO NAO CONFERIDA"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(corpo, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"evidencia escrita em {destino}")
    print("VEREDITO:", corpo["veredito"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(principal())
