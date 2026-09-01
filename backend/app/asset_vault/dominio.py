"""As regras do Cofre, sem framework e sem I/O.

## Por que este arquivo repete o que o banco ja valida

Ele nao repete por desconfianca do banco: repete porque as duas validacoes
respondem a perguntas diferentes, em momentos diferentes.

O banco e a autoridade — e o ultimo a falar, e sua recusa vale mesmo se este
arquivo sumir. Mas a recusa dele chega como um erro de Postgres, ja depois de
uma ida a rede, e — como foi medido em 01/09/2026 — a violacao de CHECK anexa
`DETAIL: Failing row contains (…)` com o valor recusado. Recusar aqui e recusar
ANTES de o valor sair desta maquina, com uma frase escrita para quem opera.

Onde as duas listas tem de concordar, a concordancia e PROVADA por teste
(`backend/tests/test_cofre_ativos.py`, os tres testes do bloco 1: eles LEEM a
migration e comparam tipo a tipo), nao prometida por comentario.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

# ── as sete gavetas e os vinte e oito tipos ─────────────────────────────────
#
# Espelham `cofre_gaveta` e `cofre_tipo` da v13_01 e `ASSET_CLUSTERS`/
# `ASSET_KINDS` de `src/features/asset-vault/contract.ts`. Os tres tem de
# concordar, e `test_cofre_ativos.py` compara este arquivo com o SQL lendo a
# migration — se alguem adicionar um tipo so num lugar, o teste cai.

GAVETAS: tuple[str, ...] = (
    "social_presence",
    "paid_media",
    "web_properties",
    "communities",
    "creative_production",
    "automation",
    "infrastructure",
)

TIPO_DA_GAVETA: dict[str, str] = {
    "facebook_profile": "social_presence",
    "facebook_page": "social_presence",
    "instagram_profile": "social_presence",
    "youtube_channel": "social_presence",
    "pinterest_account": "social_presence",
    "tiktok_account": "social_presence",
    "linkedin_page": "social_presence",
    "x_account": "social_presence",
    "meta_business_portfolio": "paid_media",
    "meta_ad_account": "paid_media",
    "google_ads_manager": "paid_media",
    "google_ads_account": "paid_media",
    "domain": "web_properties",
    "website": "web_properties",
    "wordpress_site": "web_properties",
    "landing_page": "web_properties",
    "monetization_property": "web_properties",
    "whatsapp_account": "communities",
    "whatsapp_community": "communities",
    "telegram_channel": "communities",
    "messaging_hub": "communities",
    "creative_engine": "creative_production",
    "automation_workflow": "automation",
    "integration": "automation",
    "browser_profile": "automation",
    "database_service": "infrastructure",
    "server": "infrastructure",
    "repository": "infrastructure",
}

TIPOS: tuple[str, ...] = tuple(TIPO_DA_GAVETA)

ESTADOS: tuple[str, ...] = (
    "declared", "verified", "ready", "active", "restricted", "inactive", "retired",
)
CRITICIDADES: tuple[str, ...] = ("low", "medium", "high", "critical")
CUSTODIAS: tuple[str, ...] = ("declared", "verified", "unassigned")

#: Seis valores, e nenhum e sinonimo de outro. `failed` e uma tentativa que
#: aconteceu e deu errado; `blocked` e o cofre trancado, que nao e falha da
#: credencial; `unverified` e "nunca tentei". Achatar os tres num booleano e
#: como o painel passa a dizer "acesso ok" sobre um cofre que ninguem abriu.
VERIFICACOES: tuple[str, ...] = (
    "unverified", "partial", "verified", "expired", "failed", "blocked",
)
PROCEDENCIAS: tuple[str, ...] = (
    "owner_declaration", "live_observation", "repository_inventory", "provider_record",
)
ALVOS_DE_VERIFICACAO: tuple[str, ...] = ("ativo", "credencial", "relacao", "engine")
RELACOES: tuple[str, ...] = (
    "belongs_to", "managed_by", "publishes_to", "authenticates_through",
    "spends_from", "monetizes", "depends_on", "produces_for",
)
PROVIDERS: tuple[str, ...] = (
    "1password", "bitwarden", "vaultwarden", "passbolt", "infisical",
)
ESTADOS_DE_CREDENCIAL: tuple[str, ...] = (
    "not_required", "not_registered", "referenced", "review_due", "retired",
)
MODALIDADES: tuple[str, ...] = ("imagem", "video", "audio", "misto")
ESTADOS_DE_ENGINE: tuple[str, ...] = (
    "catalogado", "externo_parcial", "integrado", "somente_referencia", "aposentado",
)

ID_DE_ATIVO = re.compile(r"^[a-z][a-z0-9:_-]{2,179}$")
CHAVE_DE_IDEMPOTENCIA = re.compile(r"^[A-Za-z0-9._:-]{8,120}$")
NOME_LOGICO = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
URL_PUBLICA = re.compile(r"^https?://[^\s]{3,2000}$", re.IGNORECASE)


class PayloadRecusado(ValueError):
    """O pedido nao pode virar operacao. A mensagem e para quem opera."""


# ── a recusa de campo sensivel, igual a do banco ────────────────────────────


def chave_normalizada(chave: str) -> str:
    """Minuscula, sem acento e sem separador.

    `accessToken`, `ACCESS-TOKEN`, `Access Token` e `access_token` sao a MESMA
    intencao escrita de quatro jeitos; comparar a chave crua pegaria uma e
    deixaria tres passar. O `NFKD` cobre o quinto jeito, que o SQL nao precisa
    tratar porque JSON de banco raramente traz acento em nome de campo, mas um
    payload vindo do browser traz: `senha_mestrá` vira `senhamestra`.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", chave or "")
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-zA-Z0-9]", "", sem_acento).lower()


#: A MESMA lista da secao 11 da v13_01. `credential` (singular) esta AUSENTE de
#: proposito: o contrato publico usa `credential` para a POSTURA — provider,
#: estado, nota — e proibi-lo quebraria o retrato que ja existe sem esconder
#: segredo nenhum. `credentials` (plural) e `credentiallocator` seguem banidos.
CHAVES_PROIBIDAS: frozenset[str] = frozenset({
    "password", "senha", "passwd", "pwd", "passphrase", "senhamestra", "masterpassword",
    "secret", "segredo", "clientsecret", "secretkey", "chavesecreta", "appsecret",
    "token", "accesstoken", "refreshtoken", "idtoken", "bearertoken", "sessiontoken",
    "apikey", "chaveapi", "apisecret", "xapikey",
    "privatekey", "chaveprivada", "sshkey", "pem", "privatepem", "certificatekey",
    "totp", "otp", "otpsecret", "mfa", "mfasecret", "twofactor", "doisfatores",
    "recoverycode", "codigorecuperacao", "backupcode", "codigobackup",
    "seedphrase", "mnemonic", "frasesemente",
    "cookie", "cookies", "setcookie", "sessionid", "sessao",
    "credentials", "credenciais", "credentiallocator", "localizador", "locator",
    "vaultitemid", "secretreference", "referenciasecreta", "opuri", "opref",
    "dotenv", "envfile", "environmentfile", "authorization", "authheader",
})

#: Formatos RECONHECIVEIS de credencial. Reconhecer um formato nao e adivinhar
#: entropia: `-----BEGIN` abre chave PEM, `eyJ` seguido de base64url longo e
#: cabecalho de JWT, e nenhum dos dois aparece por acidente numa frase.
#:
#: ⚠️ Isto NAO e um detector de segredo. Uma senha curta passa — e por isso a
#: defesa real e a gramatica do localizador e a lista de chaves acima.
MATERIAL_DE_CREDENCIAL = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY"
    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"
    r"|\bop://[A-Za-z0-9._%~-]+/[A-Za-z0-9._%~-]+/"
    r"|\b(sk|pk|ghp|gho|xox[baprs])[-_][A-Za-z0-9]{16,}"
)


def recusar_chave_sensivel(valor: Any, caminho: str = "payload") -> None:
    """Percorre o documento INTEIRO — objeto, lista, aninhamento.

    Levanta citando a CHAVE e o CAMINHO, nunca o valor: um erro que ecoa o
    segredo recusado o publica no log de quem o recusou. Foi exatamente esse o
    defeito medido na CHECK do banco em 01/09/2026.
    """
    if isinstance(valor, dict):
        for chave, aninhado in valor.items():
            if chave_normalizada(str(chave)) in CHAVES_PROIBIDAS:
                raise PayloadRecusado(
                    f"campo proibido no Cofre: {caminho}.{chave} — "
                    "este control plane guarda referencia, nunca valor de credencial"
                )
            recusar_chave_sensivel(aninhado, f"{caminho}.{chave}")
        return
    if isinstance(valor, (list, tuple)):
        for indice, item in enumerate(valor):
            recusar_chave_sensivel(item, f"{caminho}[{indice}]")


def recusar_material_de_credencial(texto: str | None, campo: str) -> None:
    if texto and MATERIAL_DE_CREDENCIAL.search(texto):
        raise PayloadRecusado(
            f"o campo {campo} contem material que parece credencial (chave, token ou "
            "referencia de cofre). O valor nao e repetido aqui de proposito."
        )


# ── coerencia de gaveta, identidade e endereco ──────────────────────────────


def gaveta_do_tipo(kind: str) -> str:
    try:
        return TIPO_DA_GAVETA[kind]
    except KeyError:
        raise PayloadRecusado(f"tipo de ativo desconhecido: {kind}") from None


def exigir_gaveta_coerente(kind: str, cluster: str) -> None:
    esperada = gaveta_do_tipo(kind)
    if cluster != esperada:
        raise PayloadRecusado(
            f"o tipo {kind} pertence a gaveta {esperada}, nao a {cluster}"
        )


def exigir_id_de_ativo(valor: str) -> str:
    if not ID_DE_ATIVO.match(valor or ""):
        raise PayloadRecusado(
            "identificador de ativo invalido: use minusculas, digitos, ':', '_' ou '-' "
            "(ex.: asset:facebook-page:piloto)"
        )
    return valor


def exigir_chave_de_idempotencia(valor: str) -> str:
    if not CHAVE_DE_IDEMPOTENCIA.match(valor or ""):
        raise PayloadRecusado(
            "chave de idempotencia invalida: 8 a 120 caracteres entre letras, digitos, "
            "'.', '_', ':' e '-'"
        )
    return valor


#: A gramatica da secret reference, por provider. Igual a `cofre_localizador_valido`
#: da v13_01 — e a concordancia entre as duas e provada por teste.
#:
#: Query string NAO e aceita de proposito: `?attribute=otp` aponta para um TOTP,
#: e o ADR e explicito de que MFA nao entra no Cofre nem por referencia.
GRAMATICA_DO_LOCALIZADOR: dict[str, re.Pattern[str]] = {
    "1password": re.compile(
        r"^op://[A-Za-z0-9._%~-]{1,64}/[A-Za-z0-9._%~-]{1,128}(/[A-Za-z0-9._%~-]{1,64}){1,2}$"),
    "bitwarden": re.compile(r"^bw://[0-9a-fA-F-]{16,64}(/[A-Za-z0-9._-]{1,64})?$"),
    "vaultwarden": re.compile(r"^bwv://[0-9a-fA-F-]{16,64}(/[A-Za-z0-9._-]{1,64})?$"),
    "passbolt": re.compile(r"^passbolt://[0-9a-fA-F-]{16,64}$"),
    "infisical": re.compile(r"^infisical://[A-Za-z0-9._/-]{3,200}$"),
}

FORMA_ESPERADA: dict[str, str] = {
    "1password": "op://<cofre>/<item>/[secao/]<campo>, com espacos em %20 e sem query string",
    "bitwarden": "bw://<uuid-do-item>[/<campo>]",
    "vaultwarden": "bwv://<uuid-do-item>[/<campo>]",
    "passbolt": "passbolt://<uuid-do-recurso>",
    "infisical": "infisical://<caminho/do/segredo>",
}


def exigir_localizador(provider: str, localizador: str) -> str:
    """Recusa sem NUNCA repetir o que foi recebido.

    Uma senha colada aqui e um texto que a gramatica nao gera. Devolver esse
    texto na mensagem de erro seria publicar a senha no log de quem tentou.
    """
    gramatica = GRAMATICA_DO_LOCALIZADOR.get(provider)
    if gramatica is None:
        raise PayloadRecusado(f"provider de cofre desconhecido: {provider}")
    if not localizador or len(localizador) > 300 or not gramatica.match(localizador):
        raise PayloadRecusado(
            f"referencia invalida para o provider {provider}: a forma esperada e "
            f"{FORMA_ESPERADA[provider]}. O valor recebido nao e repetido aqui de proposito."
        )
    return localizador


#: Trechos que denunciam um caminho de disco do operador. `canonical_path` dos
#: manifestos de engine e literalmente
#: `/Users/mac/Library/CloudStorage/GoogleDrive-tarcisio@agenciavolc.com.br/...`
#: — o e-mail da pessoa esta no caminho, e um caminho desses nao vai para uma
#: resposta HTTP so porque tecnicamente nao e "segredo".
_TRECHOS_DE_DISCO = ("/Users/", "/home/", "C:\\", "GoogleDrive-", "@")


def sanitizar_localizacao(rotulo: str | None) -> str | None:
    if rotulo is None:
        return None
    limpo = rotulo.strip()
    if not limpo:
        return None
    if any(t in limpo for t in _TRECHOS_DE_DISCO):
        raise PayloadRecusado(
            "a localizacao parece um caminho absoluto de disco. Use um rotulo "
            "operacional (ex.: 'Drive compartilhado VOLC · motor-imagem')."
        )
    return limpo


def exigir_url_publica(url: str | None) -> str | None:
    if url is None:
        return None
    limpa = url.strip()
    if not limpa:
        return None
    if not URL_PUBLICA.match(limpa):
        raise PayloadRecusado("endereco publico invalido: somente URL HTTP(S).")
    return limpa


def texto_util(valor: str | None, campo: str, minimo: int, maximo: int) -> str:
    limpo = (valor or "").strip()
    if not (minimo <= len(limpo) <= maximo):
        raise PayloadRecusado(
            f"o campo {campo} precisa ter entre {minimo} e {maximo} caracteres."
        )
    recusar_material_de_credencial(limpo, campo)
    return limpo


def lista_util(valores: Iterable[str] | None, campo: str, minimo: int, maximo: int) -> list[str]:
    itens = [str(v).strip() for v in (valores or [])]
    if any(not i for i in itens):
        raise PayloadRecusado(f"a lista {campo} tem item em branco.")
    if not (minimo <= len(itens) <= maximo):
        raise PayloadRecusado(
            f"a lista {campo} precisa ter entre {minimo} e {maximo} itens."
        )
    return itens
