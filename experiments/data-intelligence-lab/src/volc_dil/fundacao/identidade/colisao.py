"""Detector de colisão e de identidade trocada.

Quatro famílias, todas observadas ou previstas por código no VOLC:
- mesma UTM para duas campanhas (nome igual após normalização; id em duas contas);
- campanha renomeada (quebra só chaves textuais; com template de id é informativa);
- custom_key substituída pela JoinAds (`n8n/gerar_flows_joinads.py:219-226` em `main`);
- truncamento ambíguo (dois nomes distintos viram a mesma chave de 40 unidades).
"""
from __future__ import annotations

import enum
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping, Optional

from .normalizacao import chave_sem_corte_sensor_v3, normalizar_utm_sensor_v3
from .resolvedor import CampanhaRegistrada, TemplateCampanha


class TipoColisao(str, enum.Enum):
    MESMA_UTM_DUAS_CAMPANHAS = "mesma_utm_duas_campanhas"
    ID_EM_DUAS_CONTAS = "id_em_duas_contas"
    CAMPANHA_RENOMEADA = "campanha_renomeada"
    CUSTOM_KEY_SUBSTITUIDA = "custom_key_substituida"
    TRUNCAMENTO_AMBIGUO = "truncamento_ambiguo"


class Gravidade(str, enum.Enum):
    BLOQUEIA = "bloqueia"  # a chave não identifica uma campanha só: junção recusada
    INFORMA = "informa"  # não quebra a chave em uso, mas fica registrado


@dataclass(frozen=True)
class Colisao:
    tipo: TipoColisao
    gravidade: Gravidade
    chave: str
    envolvidos: tuple[str, ...]
    detalhe: str = ""


def _sobrepoe(a: CampanhaRegistrada, b: CampanhaRegistrada) -> bool:
    fim_a = a.valido_ate or date.max
    fim_b = b.valido_ate or date.max
    return a.valido_de <= fim_b and b.valido_de <= fim_a


def detectar_colisoes_registro(campanhas: Iterable[CampanhaRegistrada]) -> list[Colisao]:
    campanhas = list(campanhas)
    out: list[Colisao] = []

    # id em duas contas (com sobreposição de validade)
    por_id: dict[str, list[CampanhaRegistrada]] = defaultdict(list)
    for c in campanhas:
        por_id[c.campaign_id].append(c)
    for cid, cs in sorted(por_id.items()):
        contas = sorted({c.customer_id for c in cs})
        if len(contas) > 1 and any(_sobrepoe(a, b) for a in cs for b in cs if a.customer_id != b.customer_id):
            out.append(Colisao(TipoColisao.ID_EM_DUAS_CONTAS, Gravidade.BLOQUEIA, cid, tuple(contas)))

    # renomeação: mesmo (conta, id) com nomes diferentes ao longo do tempo
    por_ident: dict[tuple[str, str], list[CampanhaRegistrada]] = defaultdict(list)
    for c in campanhas:
        por_ident[(c.customer_id, c.campaign_id)].append(c)
    for (conta, cid), cs in sorted(por_ident.items()):
        nomes = sorted({c.nome for c in cs})
        if len(nomes) > 1:
            textual = any(c.template is TemplateCampanha.NOME for c in cs)
            chaves = {c.chave_textual for c in cs}
            grav = Gravidade.BLOQUEIA if textual and len(chaves) > 1 else Gravidade.INFORMA
            out.append(Colisao(TipoColisao.CAMPANHA_RENOMEADA, grav, f"{conta}/{cid}", tuple(nomes),
                               "chave textual muda com o nome" if grav is Gravidade.BLOQUEIA
                               else "template por id: a chave de junção não muda"))

    # mesma chave textual para campanhas distintas com validade sobreposta
    textuais = [c for c in campanhas if c.template is TemplateCampanha.NOME]
    por_chave: dict[str, list[CampanhaRegistrada]] = defaultdict(list)
    for c in textuais:
        por_chave[c.chave_textual].append(c)
    for chave, cs in sorted(por_chave.items()):
        idents = sorted({f"{c.customer_id}/{c.campaign_id}" for c in cs})
        if len(idents) > 1 and any(_sobrepoe(a, b) for a in cs for b in cs
                                   if (a.customer_id, a.campaign_id) != (b.customer_id, b.campaign_id)):
            nomes = sorted({c.nome for c in cs})
            truncou = len({chave_sem_corte_sensor_v3(n) for n in nomes}) > 1
            tipo = TipoColisao.TRUNCAMENTO_AMBIGUO if truncou else TipoColisao.MESMA_UTM_DUAS_CAMPANHAS
            out.append(Colisao(tipo, Gravidade.BLOQUEIA, chave, tuple(idents),
                               "nomes distintos: " + " | ".join(nomes)))
    return out


def detectar_custom_key_substituida(linhas: Iterable[Mapping], esperada: str = "utm_campaign") -> list[Colisao]:
    """Linhas da JoinAds cuja `custom_key` (ou a grafia `custon_key`) difere da pedida."""
    out = []
    for i, r in enumerate(linhas):
        # Semântica do `??` do JS (`r.custom_key ?? r.custon_key`): null/ausente cai para a grafia
        # `custon_key` da documentação da JoinAds (R1-F23); depois `.trim()` (R1-M13).
        veio: Optional[object] = r.get("custom_key")
        if veio is None:
            veio = r.get("custon_key")
        veio = (str(veio).strip() if veio is not None else "")
        if veio and veio != esperada:
            out.append(Colisao(TipoColisao.CUSTOM_KEY_SUBSTITUIDA, Gravidade.BLOQUEIA, esperada,
                               (veio,), f"linha {i}: pedida {esperada}, veio {veio}"))
    return out


def colisoes_de_normalizacao(valores: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Valores crus distintos que o sensor transforma na mesma chave (caixa, acento, pontuação, 40)."""
    grupos: dict[str, set[str]] = defaultdict(set)
    for v in valores:
        n = normalizar_utm_sensor_v3(v)
        if n:
            grupos[n].add(v)
    return {k: tuple(sorted(vs)) for k, vs in sorted(grupos.items()) if len(vs) > 1}
