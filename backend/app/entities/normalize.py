"""
Entity canonicalization — normalize_entity_slug + dedup helpers.

Turns a noisy query/title ("como actualizar el rut por internet dian") into a
canonical entity slug ("rut"), preserving important public-service acronyms
(RUT, DIAN, SISBEN, INSS, FGTS…) and stripping action stopwords. This is the
authoritative dedup used at persist time so variations of the same entity
collapse into ONE card.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Optional

# Action/intent stopwords (PT + ES) that are NOT part of the entity itself.
ACTION_STOPWORDS = {
    # ES
    "como", "consultar", "actualizar", "descargar", "sacar", "imprimir",
    "paso", "a", "por", "internet", "gratis", "online", "en", "el", "la",
    "los", "las", "de", "del", "para", "mi", "tu", "su", "que", "es",
    "tramite", "tramites", "pdf",
    # PT
    "atualizar", "baixar", "tirar", "fazer", "ver", "consulta", "passo",
    "no", "na", "do", "da", "dos", "das", "pelo", "pela", "meu", "minha",
    "o", "as", "e", "ou", "com", "sem",
    # EN (light)
    "how", "to", "the", "online", "free", "download", "update",
}

# Phrases (multi-word) removed before tokenization.
ACTION_PHRASES = ["paso a paso", "por internet", "passo a passo", "pela internet", "step by step"]

# Important public-service acronyms — preserved (uppercased) even if short.
IMPORTANT_ACRONYMS = {
    "RUT", "DIAN", "SISBEN", "ADRES", "FOSYGA", "RUNT", "CURP", "RFC",
    "SAT", "IMSS", "ANSES", "AFIP", "INSS", "FGTS", "CPF", "CNPJ", "NIS",
    "PIS", "PASEP", "SUS", "DETRAN", "INE", "SUNAT", "RENIEC", "AFP",
    "ISSS", "CCSS", "SRI", "MUISCA", "HMRC", "DWP", "DVLA", "NHS",
    "ELSTER", "GEZ", "SNS",
}
_ACRONYM_LOWER = {a.lower(): a for a in IMPORTANT_ACRONYMS}


def strip_accents(text: str) -> str:
    norm = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in norm if unicodedata.category(c) != "Mn")


def _entity_tokens(value: str) -> List[str]:
    """Tokens de conteúdo de um nome/query: sem acento, sem pontuação, sem
    stopword de ação, preservando siglas importantes. Base compartilhada por
    `normalize_entity_slug` (query -> sigla) e `entity_name_key` (nome -> identidade)."""
    text = (value or "").strip().lower()
    text = strip_accents(text)
    for phrase in ACTION_PHRASES:
        text = text.replace(strip_accents(phrase), " ")
    # punctuation -> space
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t]

    kept: List[str] = []
    for tok in tokens:
        if tok in _ACRONYM_LOWER:
            kept.append(tok)  # important acronym — always keep
            continue
        if tok in ACTION_STOPWORDS:
            continue
        if len(tok) <= 1:
            continue
        kept.append(tok)

    # If everything was stripped, fall back to the most "entity-like" token
    if not kept:
        for tok in tokens:
            if tok not in ACTION_STOPWORDS:
                kept.append(tok)
                break
    if not kept:
        kept = tokens[:1]
    return kept


def normalize_entity_slug(value: str) -> str:
    """
    Canonical slug for an entity name or a noisy query.

    Rules: lowercase, strip accents/punctuation, drop action stopwords/phrases,
    PRESERVE important acronyms. Returns a kebab-case slug.
    """
    kept = _entity_tokens(value)

    # If an important acronym is present, the slug is just that acronym
    # (e.g. "rut dian" -> "rut", because RUT is the entity and DIAN the source).
    # OBS: essa regra é pra QUERY suja. Pra identidade de entidade use
    # `entity_name_key` — aqui ela funde "Pagamento do INSS" com "Aposentadoria
    # pelo INSS", que são entidades diferentes.
    acronyms_present = [t for t in kept if t in _ACRONYM_LOWER]
    if acronyms_present:
        return acronyms_present[0]

    return "-".join(kept)[:80] or "entidade"


def entity_name_key(value: str) -> str:
    """Chave de IDENTIDADE para um NOME de entidade (≠ `normalize_entity_slug`).

    `normalize_entity_slug` existe pra canonicalizar QUERY suja: "como actualizar
    el rut por internet dian" -> 'rut'. Pra isso, ela colapsa o texto inteiro na
    sigla importante que ele contiver.

    Aplicada a NOMES de entidade, essa regra funde coisas distintas: "Pagamento do
    INSS", "Aposentadoria pelo INSS" e "Empréstimo Consignado" (alias INSS) viravam
    todas a chave 'inss' — e o dedup tratava as três como a MESMA entidade. Em BR,
    onde dezenas de entidades citam INSS/CPF/SUS/CNPJ/FGTS, isso engolia descobertas
    novas dentro de registros sem relação.

    Aqui a sigla só vence quando o nome É a sigla ("INSS", "meu INSS" -> 'inss');
    havendo outros tokens de conteúdo, todos entram na chave.
    """
    kept = _entity_tokens(value)
    if not kept:
        return ""
    if len(kept) == 1 and kept[0] in _ACRONYM_LOWER:
        return kept[0]
    return "-".join(kept)[:80]


def canonical_acronym(value: str) -> Optional[str]:
    """Return the uppercase canonical acronym if the slug IS one (else None)."""
    slug = normalize_entity_slug(value)
    return _ACRONYM_LOWER.get(slug)


def suggest_official_source(text: str, current: Optional[str] = None) -> Optional[str]:
    """If a second important acronym appears (e.g. DIAN in 'rut dian'), suggest
    it as the official source when none is set."""
    if current:
        return current
    cleaned = strip_accents((text or "").lower())
    found = [a for a in IMPORTANT_ACRONYMS if re.search(rf"\b{a.lower()}\b", cleaned)]
    entity_slug = normalize_entity_slug(text)
    # source = an important acronym that is NOT the entity slug itself
    for acro in found:
        if acro.lower() != entity_slug:
            return acro
    return current


def dedup_key(country_code: str, slug: str) -> str:
    return f"{(country_code or '').upper()}::{slug}"


def entity_keys(
    canonical_name: str,
    full_name: Optional[str] = None,
    aliases: Optional[Iterable[str]] = None,
) -> set:
    """Set of normalized keys for an entity (canonical_name + full_name + aliases).

    Lets synonyms WITHOUT shared tokens still merge — e.g. "Registro Único
    Tributario" (key 'registro-unico-tributario') and "RUT" (key 'rut') both
    belong to the same entity, so their key sets overlap via the alias list.
    """
    keys = set()
    for value in [canonical_name, full_name, *(list(aliases or []))]:
        if value:
            k = entity_name_key(value)
            if k:
                keys.add(k)
    return keys


def identity_keys(canonical_name: str, full_name: Optional[str] = None, slug: Optional[str] = None) -> set:
    """Keys que IDENTIFICAM a entidade: nome canônico, nome completo e slug.

    Separadas dos aliases de propósito — ver `find_matching_entity`.
    """
    keys = {entity_name_key(v) for v in [canonical_name, full_name] if v}
    if slug:
        keys.add(slug)
    keys.discard("")
    return keys


def find_matching_entity(
    candidate_keys: set,
    existing_entities: List[dict],
    candidate_identity_keys: Optional[set] = None,
) -> Optional[dict]:
    """Return the existing entity that is the SAME entity as the candidate, else None.

    Uma chave compartilhada só vale como prova de identidade se for identidade
    (canonical_name/full_name/slug) de PELO MENOS UM dos lados:

      identidade do existente ∩ qualquer chave do candidato  -> casa
      alias do existente      ∩ identidade do candidato      -> casa
      alias                   ∩ alias                        -> NÃO casa

    O caso legítimo continua funcionando: "RUT" (identidade) casa com "Registro
    Único Tributario" que traz "RUT" na lista de aliases.

    O que isso corta é o sequestro por alias: aliases guardados são poluídos com
    termos genéricos ('cpf', 'sus', 'cnpj', 'inss', 'detran') e com frases de
    busca, então um card NOVO que apenas mencionasse "cpf" num alias era fundido
    numa entidade sem relação — a descoberta nova se perdia e os aliases dela
    eram gravados na entidade errada, ampliando o problema a cada run.

    `candidate_identity_keys` omitido => todas as chaves do candidato contam como
    identidade (compatível com chamadas antigas).
    """
    cand_identity = candidate_identity_keys if candidate_identity_keys is not None else candidate_keys
    for ent in existing_entities or []:
        ent_identity = identity_keys(
            ent.get("canonical_name") or ent.get("slug") or "",
            ent.get("full_name"),
            ent.get("slug"),
        )
        ent_aliases = {entity_name_key(a) for a in (ent.get("aliases") or []) if a}
        ent_aliases.discard("")
        if (ent_identity & candidate_keys) or (ent_aliases & cand_identity):
            return ent
    return None
