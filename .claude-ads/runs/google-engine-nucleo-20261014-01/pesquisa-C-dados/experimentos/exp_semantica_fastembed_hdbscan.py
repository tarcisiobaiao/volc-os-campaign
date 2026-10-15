"""Experimento C/semântica (sintético, rotulado, sem dado real nem rede além do
download do modelo público).

Pergunta: agrupar termos de busca por embedding + HDBSCAN e "negativar a
intenção inteira" (alegação C16) é seguro? Medimos:
  - ARI/NMI contra o rótulo de intenção;
  - fração de ruído (termos sem cluster);
  - clusters MISTOS (têm termo 'manter' e termo 'negativar');
  - termos 'manter' que seriam negativados se o cluster fosse negativado pela
    maioria (o dano da alegação).
Baseline barato sem modelo: TF-IDF de n-gramas de caractere + o mesmo HDBSCAN.

Rodar:
  HF_HOME=<scratch>/hf FASTEMBED_CACHE=<scratch>/fe \
  venv-sem/bin/python -I exp_semantica_fastembed_hdbscan.py
"""
from __future__ import annotations

import json
import os
import random
import time
import unicodedata

import numpy as np
from sklearn.cluster import HDBSCAN as SkHDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

SEED = 20261014
rng = random.Random(SEED)

# intenção -> (ação esperada, núcleos, modificadores)
INTENCOES = {
    "emprestimo_contratar": ("manter", ["empréstimo consignado", "empréstimo pessoal", "crédito consignado inss",
                                         "empréstimo para negativado", "simular empréstimo"],
                             ["online", "na hora", "taxa baixa", "aprovado rápido", "2026", "pelo celular", ""]),
    "fgts_saque": ("manter", ["saque aniversário fgts", "antecipação fgts", "antecipar saque aniversário",
                              "empréstimo fgts", "liberar fgts"],
                   ["como fazer", "valor", "simulação", "pelo app", "hoje", "", "calendário"]),
    "cartao_credito": ("manter", ["cartão de crédito", "cartão consignado", "cartão sem anuidade",
                                  "cartão para negativado", "cartão benefício inss"],
                       ["pedir", "aprovação fácil", "limite alto", "online", "", "melhor"]),
    "login_suporte": ("negativar", ["login app", "segunda via boleto", "telefone sac", "0800 central",
                                    "atendimento whatsapp"],
                      ["crédito up", "banco", "caixa", "inss", "fgts", ""]),
    "emprego": ("negativar", ["vagas de emprego", "trabalhe conosco", "salário de atendente",
                              "concurso", "estágio"],
                ["banco", "caixa econômica", "financeira", "inss", "2026", ""]),
    "reclamacao_golpe": ("negativar", ["reclame aqui", "golpe", "processo contra", "cancelar contrato",
                                       "é confiável"],
                         ["empréstimo consignado", "fgts", "cartão consignado", "crédito up", ""]),
    "informacional": ("revisar", ["o que é", "como funciona", "qual a diferença entre", "vale a pena",
                                  "significado de"],
                      ["consignado", "saque aniversário", "cartão consignado", "margem consignável", "juros"]),
    "concorrente_marca": ("revisar", ["nubank", "banco pan", "bmg", "c6 bank", "mercado pago"],
                          ["empréstimo", "fgts", "cartão", "consignado", "login", ""]),
}


def ruido(t: str) -> str:
    """Variações reais de termo: sem acento, erro de digitação, ordem."""
    r = rng.random()
    if r < 0.25:
        t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    elif r < 0.35 and len(t) > 6:
        i = rng.randrange(1, len(t) - 1)
        t = t[:i] + t[i + 1:]
    return " ".join(t.split()).lower()


def gerar(n_por=25):
    termos, rot, acao = [], [], []
    for nome, (ac, nucleos, mods) in INTENCOES.items():
        vistos = set()
        while len([x for x in rot if x == nome]) < n_por:
            n, m = rng.choice(nucleos), rng.choice(mods)
            t = ruido(f"{m} {n}" if rng.random() < 0.3 else f"{n} {m}")
            if t in vistos:
                continue
            vistos.add(t)
            termos.append(t)
            rot.append(nome)
            acao.append(ac)
    return termos, rot, acao


def avaliar(rotulos_cluster, rot, acao):
    lab = np.array(rotulos_cluster)
    out = {
        "ari": round(float(adjusted_rand_score(rot, lab)), 3),
        "nmi": round(float(normalized_mutual_info_score(rot, lab)), 3),
        "n_clusters": int(len(set(lab)) - (1 if -1 in lab else 0)),
        "ruido_frac": round(float(np.mean(lab == -1)), 3),
    }
    mistos, manter_negativados, exemplos = 0, 0, []
    for c in sorted(set(lab) - {-1}):
        idx = np.where(lab == c)[0]
        acoes = [acao[i] for i in idx]
        if "manter" in acoes and "negativar" in acoes:
            mistos += 1
        if acoes.count("negativar") > len(acoes) / 2:  # "negativa a intenção inteira"
            dano = [i for i in idx if acao[i] == "manter"]
            manter_negativados += len(dano)
            exemplos += [termos[i] for i in dano[:3]]
    out["clusters_mistos_manter_e_negativar"] = mistos
    out["termos_manter_negativados_pela_maioria"] = manter_negativados
    out["exemplos_dano"] = exemplos[:8]
    return out


if __name__ == "__main__":
    termos, rot, acao = gerar()
    res = {"n_termos": len(termos), "seed": SEED, "intencoes": {k: v[0] for k, v in INTENCOES.items()}}

    # baseline sem modelo
    t0 = time.perf_counter()
    X = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True).fit_transform(termos).toarray()
    lab_tfidf = SkHDBSCAN(min_cluster_size=5, metric="euclidean").fit_predict(X)
    res["tfidf_char_sklearn_hdbscan"] = {**avaliar(lab_tfidf, rot, acao), "segundos": round(time.perf_counter() - t0, 2)}

    # FastEmbed multilíngue
    from fastembed import TextEmbedding
    modelo = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    t0 = time.perf_counter()
    emb = TextEmbedding(model_name=modelo, cache_dir=os.environ.get("FASTEMBED_CACHE"))
    t_load = time.perf_counter() - t0
    t0 = time.perf_counter()
    E = np.array(list(emb.embed(termos)))
    E = E / np.linalg.norm(E, axis=1, keepdims=True)
    t_emb = time.perf_counter() - t0
    for nome, est in {
        "fastembed_sklearn_hdbscan": SkHDBSCAN(min_cluster_size=5, metric="euclidean"),
    }.items():
        t0 = time.perf_counter()
        lab = est.fit_predict(E)
        res[nome] = {**avaliar(lab, rot, acao), "segundos_cluster": round(time.perf_counter() - t0, 2)}
    try:
        import hdbscan  # pacote separado: só para comparar com o do sklearn
        t0 = time.perf_counter()
        lab = hdbscan.HDBSCAN(min_cluster_size=5).fit_predict(E)
        res["fastembed_pkg_hdbscan"] = {**avaliar(lab, rot, acao), "segundos_cluster": round(time.perf_counter() - t0, 2)}
    except Exception as ex:  # registrar, não esconder
        res["fastembed_pkg_hdbscan_erro"] = f"{type(ex).__name__}: {ex}"

    # Variantes (otimistas: o limiar é escolhido OLHANDO o rótulo; serve só de teto)
    from sklearn.cluster import AgglomerativeClustering
    melhor = None
    for thr in (0.2, 0.3, 0.4, 0.5, 0.6):
        lab = AgglomerativeClustering(n_clusters=None, distance_threshold=thr, metric="cosine",
                                      linkage="average").fit_predict(E)
        r = {**avaliar(lab, rot, acao), "limiar_cos": thr}
        res.setdefault("fastembed_aglomerativo_cos_sweep", []).append(r)
    # Semi-supervisionado realista: 3 termos rotulados pelo operador por intenção, 1-NN no resto
    sementes = {}
    for i, r_ in enumerate(rot):
        sementes.setdefault(r_, [])
        if len(sementes[r_]) < 3:
            sementes[r_].append(i)
    idx_sem = [i for v in sementes.values() for i in v]
    resto = [i for i in range(len(termos)) if i not in idx_sem]
    sims = E[resto] @ E[idx_sem].T
    pred = [rot[idx_sem[j]] for j in sims.argmax(axis=1)]
    acc = float(np.mean([p_ == rot[i] for p_, i in zip(pred, resto)]))
    erro_grave = sum(1 for p_, i in zip(pred, resto) if INTENCOES[p_][0] == "negativar" and acao[i] == "manter")
    res["fastembed_1nn_3_sementes_por_intencao"] = {"acuracia": round(acc, 3), "n_avaliados": len(resto),
        "manter_previstos_como_negativar": erro_grave}
    Xt = X
    sims_t = (Xt[resto] / (np.linalg.norm(Xt[resto], axis=1, keepdims=True) + 1e-9)) @ (Xt[idx_sem] / (np.linalg.norm(Xt[idx_sem], axis=1, keepdims=True) + 1e-9)).T
    pred_t = [rot[idx_sem[j]] for j in sims_t.argmax(axis=1)]
    res["tfidf_1nn_3_sementes_por_intencao"] = {"acuracia": round(float(np.mean([p_ == rot[i] for p_, i in zip(pred_t, resto)])), 3),
        "manter_previstos_como_negativar": sum(1 for p_, i in zip(pred_t, resto) if INTENCOES[p_][0] == "negativar" and acao[i] == "manter")}
    res["fastembed_modelo"] = modelo
    res["fastembed_carga_s"] = round(t_load, 2)
    res["fastembed_embed_200_s"] = round(t_emb, 2)
    res["dim"] = int(E.shape[1])
    print(json.dumps(res, ensure_ascii=False, indent=1))
