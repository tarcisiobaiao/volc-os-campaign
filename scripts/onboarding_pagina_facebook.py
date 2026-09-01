#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Onboarding da página Facebook monetizada no Cofre de Ativos (P03-T02 · P12-T02),
e do perfil AdsPower que a opera (P03-T07).

O FATO QUE MOTIVA ESTE ARQUIVO
------------------------------
Não existe nenhum dado real da página neste repositório. A única linha que fala
dela é a fixture editorial (`src/features/asset-vault/fixtures.ts:11-44`), e ela
diz literalmente `external: {}` — sem ID, sem URL, sem Business Portfolio, sem o
nome verdadeiro. A única evidência é a declaração do dono, datada de 26/08/2026
(`fixtures.ts:29-37`), e o próprio `nextAction` da fixture manda "conferir ID da
página, Business Portfolio, propriedade, monetização, administradores".

Logo, o entregável desta tarefa NÃO PODE ser o cadastro: é o CAMINHO até ele.
Este script é a metade automatizável desse caminho — ele lê uma FICHA preenchida
por quem tem acesso à página e emite os payloads que o Cofre aceita. A outra
metade é humana e está em
`docs/closure/asset-vault-onepassword-production-v1/PEDIDO-AO-OPERADOR.md`.

O QUE ELE FAZ, E O QUE ELE SE RECUSA A FAZER
--------------------------------------------
Faz:  lê a ficha, valida contra as CHECKs de `supabase/migrations/v13_01_cofre_de_ativos.sql`
      e contra `backend/app/asset_vault/dominio.py`, e emite seis operações em ordem.
Não faz:  rede, escrita em banco, chamada à Meta, chamada ao AdsPower, leitura de
      cofre. Nenhum segredo passa por aqui — nem para ser conferido.

    python3 scripts/onboarding_pagina_facebook.py --ficha <arquivo.json>
    python3 scripts/onboarding_pagina_facebook.py --ficha <arquivo.json> --sql
    python3 scripts/onboarding_pagina_facebook.py --modelo
    python3 scripts/onboarding_pagina_facebook.py --autoteste

AS SEIS OPERAÇÕES, E POR QUE NESTA ORDEM
-----------------------------------------
A ordem não é estilo: é dependência de chave estrangeira declarada na migration.

  1. PÁGINA como ativo            `cofre_ativo` é o alvo de todas as FKs abaixo.
  2. PERFIL ADSPOWER como ativo   só quando a ficha declara um (bloco opcional).
  3. RELAÇÃO página → perfil      `cofre_relacao.destino_id` tem FK para
                                  `cofre_ativo` (migration linha 615): a relação
                                  não pode nascer antes dos dois ativos.
  4. CREDENCIAL da página         `cofre_credencial_referencia.ativo_id` tem FK
                                  para `cofre_ativo` (linha 683).
  5. CREDENCIAL do perfil         idem, e só quando há perfil.
  6. VERIFICAÇÃO                  `cofre_verificacao.ativo_id` tem FK (linha 766),
                                  e um recibo de prova sobre um ativo que ainda
                                  não existe não é prova de nada.

A DIREÇÃO DA RELAÇÃO — página é a ORIGEM, perfil é o DESTINO
-------------------------------------------------------------
`authenticates_through`, com `origem_id` = página e `destino_id` = perfil.
Três fatos do contrato decidem isso, não gosto pessoal:

  a) `cofre_relacionar` (migration linha 1490) incrementa `revisao_atual` e grava
     `cofre_ativo_revisao` SOMENTE para a ORIGEM. Quem for origem carrega o fato
     na própria trilha de revisões. A tarefa sob governança é P03-T02/P12-T02 —
     a PÁGINA. Inverter a direção esconderia o vínculo do histórico do ativo que
     o roadmap cobra.
  b) A rota HTTP é `POST /api/cofre/ativos/{ativo_id}/relacoes` e
     `rotas.py:relacionar` faz `payload["origem_id"] = ativo_id` — a origem é o
     ativo do caminho. Página como origem mantém o onboarding inteiro pendurado
     no mesmo `ativo_id`.
  c) O ADR de distribuição orgânica diz que "AdsPower abre o perfil correto"
     para chegar à URL publicada: a sessão autenticada mora no perfil, e a
     página é alcançada ATRAVÉS dele. `authenticates_through` é literalmente
     essa frase; `depends_on` diria que a página deixa de existir sem o perfil,
     o que é falso — ela existe e publica por outros caminhos.

O ID DA PÁGINA: ENTRA MASCARADO, NUNCA INTEIRO
-----------------------------------------------
`cofre_ativo.display_id` tem COMMENT explícito na migration (linha 424):
"Identificador JA sanitizado para exibicao. Nunca segredo, nunca ID cru
sensivel." O ID numérico da página é dado de plataforma: quem o tem consegue
enumerar a página em ferramentas de terceiros e ligá-la ao portfólio. Ele serve
para o operador RECONHECER a linha, e para reconhecer bastam os quatro últimos
dígitos. Então este script:

  - recebe o ID completo na ficha (arquivo local, não versionado);
  - emite `display_id` na forma `•••-•••-<4 últimos>`, que é o próprio exemplo
    escrito na migration (linha 379);
  - RECUSA se o ID completo aparecer em qualquer campo emitido — inclusive numa
    `url_publica` do tipo `/profile.php?id=<id>`. Nesse caso o endereço público
    correto é o do nome de usuário, ou nenhum: `url_publica` é opcional.

DETERMINISMO
------------
Nenhum `now()`, nenhum uuid sorteado, nenhuma ordem de `set` na saída. As chaves
de idempotência são DERIVADAS do conteúdo do payload — rodar duas vezes com a
mesma ficha produz os mesmos bytes e, no banco, `cofre_idempotencia` devolve o
recibo guardado em vez de duplicar o ativo. O relógio é lido em UM lugar só: a
recusa de `observado_em` no futuro, que é decisão de aceitar/recusar e não sai
na saída.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FICHA_MODELO = "docs/closure/asset-vault-onepassword-production-v1/FICHA-PAGINA-MODELO.json"


# ==========================================================================
# 1. OS ESPELHOS — copiados de dois arquivos, e nenhum deles é a autoridade
# ==========================================================================
# `dominio.py` já explica por que uma regra existe duas vezes: as duas respondem
# perguntas diferentes em momentos diferentes. Aqui há uma TERCEIRA cópia, e a
# justificativa é a mesma um degrau antes — este script roda na máquina de quem
# preenche a ficha, ANTES de existir requisição HTTP. O operador descobre que
# faltou um campo enquanto ainda está com o Business Suite aberto, e não num 400
# do PostgREST meia hora depois.
#
# Onde estas listas divergirem da migration, a MIGRATION vence. O autoteste
# compara o que dá para comparar; o resto é disciplina de quem editar.

GAVETA_DO_TIPO: dict[str, str] = {
    # `cofre_tipo` (migration, seção 3). Só os tipos que este script usa —
    # copiar os 28 aqui seria criar um quarto catálogo para manter em dia.
    "facebook_page": "social_presence",
    "browser_profile": "automation",
}

ESTADOS_DE_ATIVO = ("declared", "verified", "ready", "active", "restricted", "inactive", "retired")
CRITICIDADES = ("low", "medium", "high", "critical")
CUSTODIAS = ("declared", "verified", "unassigned")
PROVIDERS = ("1password", "bitwarden", "vaultwarden", "passbolt", "infisical")
ESTADOS_DE_CREDENCIAL = ("not_required", "not_registered", "referenced", "review_due")
RESULTADOS_DE_VERIFICACAO = ("unverified", "partial", "verified", "expired", "failed", "blocked")
PROCEDENCIAS = ("owner_declaration", "live_observation", "repository_inventory", "provider_record")
ALVOS_DE_VERIFICACAO = ("ativo", "credencial", "relacao", "engine")
ESTADOS_DE_RELACAO = ("declared", "verified")

ID_DE_ATIVO = re.compile(r"^[a-z][a-z0-9:_-]{2,179}$")
CHAVE_DE_IDEMPOTENCIA = re.compile(r"^[A-Za-z0-9._:-]{8,120}$")
NOME_LOGICO = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# `cofre_ativo_url_http` (migration linha 445): a forma é `+` e o comprimento é
# medido por `length()`, porque `{3,2000}` estoura o teto de 255 repetições do
# regex do Postgres. Aqui a separação é copiada para que a recusa local aconteça
# pelo mesmo motivo que a do banco.
URL_PUBLICA = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
# `cofre_ativo_display_id_sanitizado`: nada de dois espaços seguidos.
DISPLAY_ID_ESPACOS = re.compile(r"[\s]{2,}")

# `cofre_localizador_valido` (migration linha 197) e `GRAMATICA_DO_LOCALIZADOR`
# de `dominio.py`, verbatim. A ausência de query string é deliberada nos dois:
# `?attribute=otp` endereça um TOTP, e o ADR proíbe MFA no Cofre até por
# referência.
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

# `CHAVES_PROIBIDAS` de `dominio.py:CHAVES_PROIBIDAS`, que por sua vez é a lista
# de `cofre_chave_sensivel` (migration seção 11). Copiada inteira e sem edição —
# a instrução desta missão é ESPELHAR, não inventar outra lista. `credential`
# no singular continua ausente de propósito: o contrato público usa esse nome
# para a POSTURA (provider, estado, nota), que não esconde segredo nenhum.
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

# `dominio.py:MATERIAL_DE_CREDENCIAL`, verbatim.
MATERIAL_DE_CREDENCIAL = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY"
    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"
    r"|\bop://[A-Za-z0-9._%~-]+/[A-Za-z0-9._%~-]+/"
    r"|\b(sk|pk|ghp|gho|xox[baprs])[-_][A-Za-z0-9]{16,}"
)

# `dominio.py:_TRECHOS_DE_DISCO`, usado por `sanitizar_localizacao`. O `@` está
# lá porque é o que distingue um caminho de Google Drive de um caminho comum: é
# o e-mail do operador dentro do caminho.
TRECHOS_DE_DISCO = ("/Users/", "/home/", "C:\\", "GoogleDrive-", "@")

# Guarda final sobre a SAÍDA INTEIRA. Note que `@` NÃO está aqui, e a diferença
# é proposital: `owner_nome` e `dono_nome` podem legitimamente ser um e-mail de
# pessoa responsável, enquanto `localizacao_rotulo` não pode conter `@` por
# regra de `dominio.sanitizar_localizacao`. Duas guardas, dois escopos.
TRECHOS_DE_DISCO_NA_SAIDA = ("/Users/", "/home/", "C:\\", "GoogleDrive-", "CloudStorage")

# Constantes estruturais. Não vão para a ficha porque não são decisão do
# operador: são o contrato.
PAGINA_ATIVO_ID = "asset:facebook-page:monetized-acquired"   # fixtures.ts:11
PAGINA_KIND = "facebook_page"
PAGINA_PLATAFORMA = "Meta"                                   # fixtures.ts:15
PERFIL_KIND = "browser_profile"
PERFIL_PLATAFORMA = "AdsPower"                               # ADR, seção "AdsPower MCP"
RELACAO_TIPO = "authenticates_through"
PREFIXO_CHAVE = "onb-fbpage"


class FichaRecusada(ValueError):
    """A ficha não pode virar operação. A mensagem é para quem preenche."""


# ==========================================================================
# 2. PENDÊNCIA — o marcador que impede um ID inventado de entrar no banco
# ==========================================================================
# Regra dura (a) da missão: campo com marcador ainda por preencher não vira
# aviso, vira saída != 0. O motivo é concreto — um payload emitido com
# `"nome": "PREENCHER"` passa em toda CHECK de comprimento do banco e cria um
# ativo real chamado PREENCHER, que ninguém consegue distinguir de um ativo de
# verdade depois. A recusa acontece antes de existir payload.

MARCADORES_DE_PENDENCIA = (
    "PREENCHER", "PREENCHA", "SUBSTITUIR", "TODO", "FIXME", "XXXX", "???", "…",
)
#: A forma de template `<algo>`. Ela é usada de propósito nos valores modelo do
#: localizador, para que o placeholder ENSINE a forma correta e ao mesmo tempo
#: seja detectado como pendência.
TEMPLATE_ANGULAR = re.compile(r"<[^>]{1,80}>")


def _e_pendencia(valor) -> bool:
    if not isinstance(valor, str):
        return False
    alto = valor.upper()
    if any(m in alto for m in MARCADORES_DE_PENDENCIA):
        return True
    return bool(TEMPLATE_ANGULAR.search(valor))


def coletar_pendencias(doc, caminho: str = "ficha") -> list[str]:
    """Percorre o documento inteiro e devolve os CAMINHOS ainda por preencher.

    Devolve o caminho e o marcador, nunca o valor por extenso: o valor de um
    campo pendente é inofensivo hoje, mas esta função é a mesma que roda numa
    ficha meio preenchida onde o campo ao lado já tem coisa séria.
    """
    achados: list[str] = []
    if isinstance(doc, dict):
        for chave, valor in doc.items():
            if str(chave).startswith("_") or str(chave).endswith("__onde_obter"):
                continue  # instrução para humano, não campo de dado
            achados.extend(coletar_pendencias(valor, f"{caminho}.{chave}"))
    elif isinstance(doc, list):
        for i, item in enumerate(doc):
            achados.extend(coletar_pendencias(item, f"{caminho}[{i}]"))
    elif _e_pendencia(doc):
        achados.append(caminho)
    return achados


# ==========================================================================
# 3. AS DUAS RECUSAS DE SEGREDO — chave proibida e material reconhecível
# ==========================================================================


def chave_normalizada(chave: str) -> str:
    """`dominio.chave_normalizada`, verbatim: minúscula, sem acento, sem separador."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", chave or "")
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-zA-Z0-9]", "", sem_acento).lower()


def recusar_chave_sensivel(doc, caminho: str = "ficha", isentos: tuple[str, ...] = ()) -> None:
    """Levanta citando a CHAVE e o CAMINHO — nunca o valor.

    `isentos` existe por uma razão que o banco também tem: `cofre_referenciar_credencial`
    roda a varredura em `p_payload - 'localizador'` (migration linha 1774), porque
    `localizador` está na lista de proibidas para não poder viajar dentro de
    nenhum outro documento, e mesmo assim é legítimo NAQUELA porta.

    ⚠️ A isenção é por CAMINHO COMPLETO, não por nome de chave. Isentar o nome em
    qualquer profundidade abriria de volta o buraco que a lista fecha: um
    `pagina.localizador` passaria calado, e é justamente esse tipo de campo que
    faz uma referência de cofre viajar dentro de um documento que não é o dela.
    """
    if isinstance(doc, dict):
        for chave, valor in doc.items():
            nome = str(chave)
            if f"{caminho}.{nome}" in isentos:
                continue
            if chave_normalizada(nome) in CHAVES_PROIBIDAS:
                raise FichaRecusada(
                    f"campo proibido na ficha: {caminho}.{nome} — o Cofre guarda "
                    "referência, nunca valor de credencial. Apague o campo."
                )
            recusar_chave_sensivel(valor, f"{caminho}.{nome}", isentos)
    elif isinstance(doc, list):
        for i, item in enumerate(doc):
            recusar_chave_sensivel(item, f"{caminho}[{i}]", isentos)


def recusar_material_de_credencial(doc, caminho: str = "ficha", isentos: tuple[str, ...] = ()) -> None:
    """Regra dura (b): valor que PARECE credencial derruba a ficha inteira.

    A mensagem cita o caminho e nunca o texto. Um erro que ecoa o segredo
    recusado o publica no terminal, no histórico do shell e no scrollback — que
    é exatamente o defeito medido no `DETAIL: Failing row contains (…)` do
    Postgres e documentado na migration (linhas 186-193).

    ⚠️ Isto NÃO é um detector de segredo, e `dominio.py` diz o mesmo com todas
    as letras: uma senha curta passa. A defesa real é a gramática do localizador
    somada à lista de chaves proibidas. Este regex pega o que é RECONHECÍVEL.
    """
    if isinstance(doc, dict):
        for chave, valor in doc.items():
            nome = str(chave)
            if f"{caminho}.{nome}" in isentos:
                continue  # o localizador é `op://…` por contrato, e só naquele caminho
            recusar_material_de_credencial(valor, f"{caminho}.{nome}", isentos)
    elif isinstance(doc, list):
        for i, item in enumerate(doc):
            recusar_material_de_credencial(item, f"{caminho}[{i}]", isentos)
    elif isinstance(doc, str) and MATERIAL_DE_CREDENCIAL.search(doc):
        raise FichaRecusada(
            f"o campo {caminho} contém material que parece credencial (chave PEM, JWT, "
            "token de provedor ou referência de cofre fora do campo próprio). "
            "O valor não é repetido aqui de propósito."
        )


#: Os DOIS únicos CAMINHOS onde uma secret reference é legítima. Fora deles, um
#: `op://…` é material de credencial num lugar errado — e o regex acima o pega.
ISENTOS = (
    "ficha.credencial_pagina.localizador",
    "ficha.credencial_perfil.localizador",
)


# ==========================================================================
# 4. OS VALIDADORES — as CHECKs do banco, avaliadas antes da rede
# ==========================================================================


def texto(valor, campo: str, minimo: int, maximo: int) -> str:
    """`cofre_texto_util` + os CHECKs `BETWEEN` de comprimento, com `btrim`."""
    if not isinstance(valor, str):
        raise FichaRecusada(f"o campo {campo} precisa ser texto.")
    limpo = valor.strip()
    if not (minimo <= len(limpo) <= maximo):
        raise FichaRecusada(
            f"o campo {campo} precisa ter entre {minimo} e {maximo} caracteres "
            f"depois de aparar espaços (tem {len(limpo)})."
        )
    return limpo


def texto_opcional(valor, campo: str, minimo: int, maximo: int) -> str | None:
    """Ausência é NULL, jamais string vazia.

    A migration escreve isso como CHECK (`cofre_ativo_projeto_nao_vazio` e irmãs)
    com o comentário: string vazia é "presente e inútil" — passa em NOT NULL,
    aparece na tela como espaço em branco e não distingue "não tem" de "não sei".
    """
    if valor is None:
        return None
    if isinstance(valor, str) and not valor.strip():
        return None
    return texto(valor, campo, minimo, maximo)


def escolha(valor, campo: str, permitidos: tuple[str, ...]) -> str:
    if valor not in permitidos:
        raise FichaRecusada(
            f"o campo {campo} precisa ser um de: {', '.join(permitidos)}."
        )
    return valor


def lista(valores, campo: str, minimo: int, maximo: int) -> list[str]:
    """`cofre_lista_util(valores, min, max)`: tamanho no intervalo, nenhum item em branco."""
    if not isinstance(valores, list):
        raise FichaRecusada(f"o campo {campo} precisa ser uma lista.")
    itens = [v.strip() if isinstance(v, str) else v for v in valores]
    if any(not isinstance(v, str) or not v for v in itens):
        raise FichaRecusada(f"a lista {campo} tem item vazio ou que não é texto.")
    if not (minimo <= len(itens) <= maximo):
        raise FichaRecusada(
            f"a lista {campo} precisa ter entre {minimo} e {maximo} itens (tem {len(itens)})."
        )
    return itens


def url_publica(valor, campo: str) -> str | None:
    """`cofre_ativo_url_http`: só HTTP(S), comprimento entre 11 e 2000.

    Regra dura (d) da missão. `file://`, `javascript:` e caminho de disco são
    recusados aqui e não só na tela — como diz a migration na linha 439.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if not isinstance(valor, str):
        raise FichaRecusada(f"o campo {campo} precisa ser texto ou null.")
    limpa = valor.strip()
    if not (11 <= len(limpa) <= 2000):
        raise FichaRecusada(
            f"o campo {campo} precisa ter entre 11 e 2000 caracteres (tem {len(limpa)}) — "
            "é o teto de `cofre_ativo_url_http`."
        )
    if not URL_PUBLICA.match(limpa):
        raise FichaRecusada(
            f"o campo {campo} precisa ser um endereço HTTP(S) sem espaços. "
            "Nada de file://, javascript: ou caminho de disco."
        )
    return limpa


def localizacao_rotulo(valor, campo: str) -> str | None:
    """`dominio.sanitizar_localizacao`: rótulo operacional, nunca caminho de disco.

    O `@` derruba porque o caminho do Drive do operador contém o e-mail dele, e
    `cofre_ativo.localizacao_rotulo` tem COMMENT dizendo que isso não entra na
    coluna nem em resposta HTTP nenhuma.
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    limpo = texto(valor, campo, 1, 240)
    if any(t in limpo for t in TRECHOS_DE_DISCO):
        raise FichaRecusada(
            f"o campo {campo} parece caminho de disco ou contém '@'. Use um rótulo "
            "operacional curto (ex.: 'Business Portfolio Meta · VOLC')."
        )
    return limpo


def data_iso(valor, campo: str) -> str | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if not isinstance(valor, str) or not DATA_ISO.match(valor.strip()):
        raise FichaRecusada(f"o campo {campo} precisa ser uma data AAAA-MM-DD.")
    bruto = valor.strip()
    try:
        datetime.strptime(bruto, "%Y-%m-%d")
    except ValueError:
        raise FichaRecusada(f"o campo {campo} não é uma data de calendário válida.") from None
    return bruto


def instante_observado(valor, campo: str, agora: datetime) -> str:
    """`cofre_verificacao.observado_em` — timestamptz, com fuso e nunca no futuro.

    Dois motivos para exigir o fuso explícito, e nenhum é preciosismo:

      · a coluna é `timestamptz`; um texto sem offset é interpretado no fuso do
        SERVIDOR, e o servidor é um container em Ashburn. "Conferi às 9h" vira
        outra hora sem ninguém perceber.
      · `cofre_verificacao_nao_futura` recusa `observado_em > now() + 1 minuto`.
        Sem offset, a mesma frase pode passar ou cair dependendo do fuso do
        container — um gate que decide por acidente não é gate.
    """
    if not isinstance(valor, str) or not valor.strip():
        raise FichaRecusada(f"o campo {campo} é obrigatório (instante ISO-8601 com fuso).")
    bruto = valor.strip()
    try:
        quando = datetime.fromisoformat(bruto)
    except ValueError:
        raise FichaRecusada(
            f"o campo {campo} não é um instante ISO-8601. Exemplo da forma aceita: "
            "2026-09-01T14:35:00-03:00"
        ) from None
    if quando.tzinfo is None:
        raise FichaRecusada(
            f"o campo {campo} precisa trazer o fuso (ex.: -03:00 ou Z). A coluna é "
            "timestamptz e sem fuso o instante seria lido no fuso do servidor."
        )
    if quando > agora + timedelta(minutes=1):
        raise FichaRecusada(
            f"o campo {campo} está no futuro. `cofre_verificacao_nao_futura` recusa: "
            "uma observação que ainda não aconteceu não é observação."
        )
    return bruto


def id_de_ativo(valor: str, campo: str) -> str:
    if not ID_DE_ATIVO.match(valor or ""):
        raise FichaRecusada(
            f"o campo {campo} não tem a forma de identificador de ativo: minúsculas, "
            "dígitos, ':', '_' ou '-', de 3 a 180 caracteres "
            "(ex.: asset:browser-profile:piloto)."
        )
    return valor


def localizador(provider: str, valor, campo: str) -> str:
    """A gramática da secret reference. Recusa SEM repetir o que recebeu.

    Regra dura (e) da missão vive aqui: a gramática do 1Password não aceita
    query string, e é por isso que `op://cofre/item/campo?attribute=otp` — a
    forma documentada de endereçar um TOTP — não passa. MFA não entra no Cofre
    nem por referência; a migration diz isso na linha 213 e este script é a
    primeira porta onde a frase vira recusa.
    """
    gramatica = GRAMATICA_DO_LOCALIZADOR.get(provider)
    if gramatica is None:
        raise FichaRecusada(f"provider de cofre desconhecido: {provider}")
    if not isinstance(valor, str) or not valor.strip():
        raise FichaRecusada(f"o campo {campo} é obrigatório.")
    bruto = valor.strip()
    if "?" in bruto or "#" in bruto:
        # Diagnóstico específico ANTES da mensagem genérica, porque este é o erro
        # que o operador comete de boa-fé: o 1Password oferece o botão que copia
        # a referência do campo de código de verificação.
        raise FichaRecusada(
            f"o campo {campo} tem query string ou fragmento. A gramática do Cofre não "
            "os aceita: `?attribute=otp` endereça um segundo fator, e MFA não entra "
            "aqui nem por referência. Aponte para o campo de senha ou de acesso."
        )
    if len(bruto) > 300 or not gramatica.match(bruto):
        raise FichaRecusada(
            f"referência inválida no campo {campo} para o provider {provider}: a forma "
            f"esperada é {FORMA_ESPERADA[provider]}. O valor recebido não é repetido "
            "aqui de propósito."
        )
    return bruto


def nome_logico(valor, campo: str) -> str:
    """`cofre_credencial_nome_logico_forma`: MAIÚSCULA_COM_UNDERSCORE, 2 a 64.

    A migration explica o efeito colateral útil (linha 690): um valor colado por
    engano quase nunca tem essa forma, então a CHECK filtra o acidente mais
    comum. E note que nomes como ADSPOWER_API_KEY são LEGÍTIMOS aqui — a própria
    migration os usa como exemplo. A lista de chaves proibidas vale para NOMES DE
    CAMPO do payload, não para o rótulo lógico do item de cofre.
    """
    if not isinstance(valor, str) or not NOME_LOGICO.match(valor.strip()):
        raise FichaRecusada(
            f"o campo {campo} precisa ser MAIUSCULA_COM_UNDERSCORE, de 2 a 64 caracteres, "
            "começando por letra (ex.: FACEBOOK_PAGE_ACESSO)."
        )
    return valor.strip()


def display_id_mascarado(id_completo: str, campo: str) -> str:
    """Regra dura (c): o ID de plataforma entra MASCARADO ou não entra.

    Quatro dígitos bastam para o operador reconhecer a linha certa; o ID inteiro
    permite enumerar a página em ferramentas de terceiros. `cofre_ativo.display_id`
    tem COMMENT dizendo "nunca o ID cru sensível", e esta função é essa frase.
    A forma `•••-•••-1692` é o exemplo escrito na própria migration (linha 379).

    A faixa de 8 a 25 dígitos é uma banda para pegar erro de digitação, não um
    limite documentado pela Meta — ela recusa "12" e recusa um parágrafo colado.
    """
    if not isinstance(id_completo, str) or not id_completo.strip().isdigit():
        raise FichaRecusada(
            f"o campo {campo} precisa ser só dígitos — é o ID numérico da página. "
            "Se você tem a URL e não o número, deixe o pedido ao operador aberto: "
            "o script não adivinha ID."
        )
    bruto = id_completo.strip()
    if not (8 <= len(bruto) <= 25):
        raise FichaRecusada(
            f"o campo {campo} tem {len(bruto)} dígitos; o esperado é entre 8 e 25. "
            "Confira se copiou o ID da página e não outro número da tela."
        )
    mascara = "•••-•••-" + bruto[-4:]
    if len(mascara) > 80 or DISPLAY_ID_ESPACOS.search(mascara):
        raise FichaRecusada("a máscara gerada não passa em `cofre_ativo_display_id_sanitizado`.")
    return mascara


def chave_de_idempotencia(sufixo: str, payload: dict) -> str:
    """Chave DERIVADA do conteúdo, não sorteada.

    Ela não é — e não tenta ser — o `entrada_hash` do banco. `cofre_entrada_hash`
    é derivado lá dentro justamente para que o chamador não possa mentir sobre
    ele (migration linha 1256), e o texto canônico do `jsonb` do Postgres não é o
    do `json.dumps` do Python. O que esta chave precisa ser é ESTÁVEL: mesma
    ficha, mesma chave, e o replay devolve o recibo guardado em vez de duplicar
    o ativo. Ficha diferente, chave diferente, e o replay não mascara outra
    operação com o recibo da anterior.
    """
    canonico = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonico.encode("utf-8")).hexdigest()[:12]
    chave = f"{PREFIXO_CHAVE}.{sufixo}.{digest}"
    if not CHAVE_DE_IDEMPOTENCIA.match(chave):
        raise FichaRecusada(
            f"chave de idempotência fora da forma de `cofre_operacao_chave_forma`: {chave}"
        )
    return chave


# ==========================================================================
# 5. A FICHA MODELO — cada campo com a instrução de ONDE achar o dado
# ==========================================================================
# Os caminhos de menu abaixo são referência de NAVEGAÇÃO, não contrato: telas de
# plataforma mudam. O que não muda é o VALOR pedido, e é ele que a instrução
# nomeia. Nenhum valor real aparece aqui — o repositório não tem nenhum, e essa
# ausência é o motivo desta ficha existir.
#
# Os campos com `__onde_obter` são instrução para humano e NÃO viram payload:
# `_campos_de_dado` os descarta antes de qualquer montagem.

FICHA_MODELO_DOC: dict = {
    "_o_que_e_isto": (
        "Ficha de onboarding da página Facebook monetizada no Cofre de Ativos "
        "(P03-T02 / P12-T02) e do perfil AdsPower que a opera (P03-T07). "
        "Preencha, salve como cópia FORA do repositório e rode "
        "`python3 scripts/onboarding_pagina_facebook.py --ficha <sua-copia.json>`."
    ),
    "_nunca_escreva_aqui": (
        "Nenhuma senha, token, cookie, chave de API, código de recuperação ou "
        "código de verificação. Só o ENDEREÇO do segredo dentro do 1Password. "
        "O script recusa a ficha inteira se encontrar qualquer um deles."
    ),
    "_marcador_de_pendencia": (
        "Todo campo ainda por preencher está com PREENCHER ou com <template>. "
        "Enquanto sobrar um, o script sai com código != 0 e lista o que falta."
    ),

    "pagina": {
        "id_plataforma": "PREENCHER",
        "id_plataforma__onde_obter": (
            "OBRIGATÓRIO. Só dígitos. Meta Business Suite > Configurações > "
            "Informações da Página > ID da Página. Alternativa: abra a Página > "
            "Sobre > Transparência da Página. USO: o script guarda apenas os 4 "
            "últimos dígitos, na forma •••-•••-1234; o número inteiro NÃO entra "
            "em nenhum payload e não deve ser versionado."
        ),
        "nome": "PREENCHER",
        "nome__onde_obter": (
            "OBRIGATÓRIO, 2 a 160 caracteres. O nome público da Página, exatamente "
            "como aparece nela. A fixture do repositório traz o rótulo provisório "
            "'Página monetizada adquirida', que NÃO é o nome real."
        ),
        "url_publica": None,
        "url_publica__onde_obter": (
            "OPCIONAL (null se não houver). Só HTTP(S), até 2000 caracteres. Use o "
            "endereço de nome de usuário (facebook.com/nomedapagina). NÃO use o "
            "formato profile.php?id=<número>: ele carrega o ID inteiro e o script "
            "recusa por isso."
        ),
        "business_portfolio_nome": "PREENCHER",
        "business_portfolio_nome__onde_obter": (
            "OBRIGATÓRIO. business.facebook.com > seletor de portfólio no topo, ou "
            "Configurações do Negócio > Informações do Negócio > Nome. Vai para "
            "`localizacao_rotulo` prefixado por 'Business Portfolio Meta · ', que é "
            "onde a Página operacionalmente mora. Não pode conter '@' nem caminho "
            "de disco."
        ),
        "estado": "PREENCHER",
        "estado__onde_obter": (
            "OBRIGATÓRIO. Um de: declared, verified, ready, active, restricted, "
            "inactive, retired. Use 'declared' enquanto a propriedade não foi "
            "conferida com prova; 'verified' só depois de existir recibo."
        ),
        "criticidade": "PREENCHER",
        "criticidade__onde_obter": "OBRIGATÓRIO. Um de: low, medium, high, critical.",
        "resumo": (
            "Página comprada para a operação orgânica e de vídeo, ainda sem identidade "
            "técnica e propriedade conferidas no VOLC."
        ),
        "resumo__onde_obter": (
            "OBRIGATÓRIO, 10 a 800 caracteres. O texto acima veio de "
            "src/features/asset-vault/fixtures.ts:18 — é o que o repositório já "
            "declara. Corrija se estiver errado."
        ),
        "dono_nome": "PREENCHER",
        "dono_nome__onde_obter": (
            "OBRIGATÓRIO, 1 a 240 caracteres. Quem responde pela Página no VOLC. "
            "A fixture registra 'Tarcisio' (fixtures.ts:19)."
        ),
        "dono_custodia": "PREENCHER",
        "dono_custodia__onde_obter": (
            "OBRIGATÓRIO. Um de: declared, verified, unassigned. 'declared' = o dono "
            "afirmou; 'verified' = alguém conferiu no painel da plataforma."
        ),
        "projeto": None,
        "projeto__onde_obter": "OPCIONAL (null). Nome do projeto VOLC ao qual a Página pertence.",
        "vertical": None,
        "vertical__onde_obter": "OPCIONAL (null). Vertical/nicho de conteúdo da Página.",
        "capacidades": [
            "Publicação orgânica",
            "Distribuição de vídeo",
            "Monetização declarada",
        ],
        "capacidades__onde_obter": (
            "OBRIGATÓRIO, 1 a 40 itens, nenhum vazio. A lista acima veio de "
            "fixtures.ts:21. Ajuste para o que a Página realmente faz hoje."
        ),
        "tags": ["primeiro lote", "meta", "orgânico"],
        "tags__onde_obter": "OPCIONAL, 0 a 30 itens. Veio de fixtures.ts:43.",
        "proxima_acao": (
            "Conferir ID da página, Business Portfolio, propriedade, monetização, "
            "administradores e método de recuperação."
        ),
        "proxima_acao__onde_obter": (
            "OBRIGATÓRIO, 10 a 800 caracteres. Veio de fixtures.ts:42."
        ),
    },

    "perfil_adspower": {
        "_opcional": (
            "BLOCO OPCIONAL. Se ainda não existe perfil AdsPower dedicado a esta "
            "Página, troque este objeto inteiro por null. O script então emite "
            "quatro operações em vez de seis, e não inventa perfil nenhum."
        ),
        "slug": "PREENCHER",
        "slug__onde_obter": (
            "OBRIGATÓRIO dentro deste bloco. Minúsculas, dígitos e hífen. Vira o "
            "identificador do ativo: asset:browser-profile:<slug>. Escolha algo "
            "estável (ex.: piloto-organico)."
        ),
        "id_referencia": "PREENCHER",
        "id_referencia__onde_obter": (
            "OBRIGATÓRIO. Cliente AdsPower > lista de perfis > coluna 'No.' ou o ID "
            "do perfil (user_id da Local API). Vai INTEIRO para `display_id`, e isso "
            "é intencional: P03-T07 exige que o perfil tenha ID de referência "
            "visível, e esse número é inútil sem a API key da Local API — que nunca "
            "entra no Cofre."
        ),
        "nome": "PREENCHER",
        "nome__onde_obter": "OBRIGATÓRIO, 2 a 160 caracteres. O nome do perfil no AdsPower.",
        "estado": "PREENCHER",
        "estado__onde_obter": (
            "OBRIGATÓRIO. Um de: declared, verified, ready, active, restricted, "
            "inactive, retired."
        ),
        "criticidade": "PREENCHER",
        "criticidade__onde_obter": "OBRIGATÓRIO. Um de: low, medium, high, critical.",
        "resumo": "PREENCHER",
        "resumo__onde_obter": (
            "OBRIGATÓRIO, 10 a 800 caracteres. Para que serve este perfil: qual "
            "sessão ele mantém e em qual etapa do fluxo ele abre."
        ),
        "dono_nome": "PREENCHER",
        "dono_nome__onde_obter": "OBRIGATÓRIO. Quem responde pelo perfil.",
        "dono_custodia": "PREENCHER",
        "dono_custodia__onde_obter": "OBRIGATÓRIO. Um de: declared, verified, unassigned.",
        "proxy_rotulo": None,
        "proxy_rotulo__onde_obter": (
            "OPCIONAL (null). Rótulo NÃO sensível do proxy usado pelo perfil "
            "(ex.: 'Proxy residencial BR-SP'). NUNCA host, porta, usuário ou senha "
            "do proxy. Vai para `localizacao_rotulo` prefixado por 'Proxy · '."
        ),
        "capacidades": ["PREENCHER"],
        "capacidades__onde_obter": (
            "OBRIGATÓRIO, 1 a 40 itens (ex.: 'Abertura de sessão isolada', "
            "'QA visual pós-publicação')."
        ),
        "tags": [],
        "tags__onde_obter": "OPCIONAL, 0 a 30 itens.",
        "proxima_acao": "PREENCHER",
        "proxima_acao__onde_obter": "OBRIGATÓRIO, 10 a 800 caracteres.",
    },

    "relacao": {
        "_direcao": (
            "A direção é fixa e está justificada no cabeçalho do script: origem = "
            "Página, tipo = authenticates_through, destino = perfil AdsPower. Só o "
            "estado é seu."
        ),
        "estado": "declared",
        "estado__onde_obter": (
            "OBRIGATÓRIO. 'declared' ou 'verified'. Use 'verified' apenas se alguém "
            "abriu o perfil e viu a sessão da Página logada."
        ),
    },

    "credencial_pagina": {
        "provider": "1password",
        "provider__onde_obter": (
            "OBRIGATÓRIO. Um de: 1password, bitwarden, vaultwarden, passbolt, infisical."
        ),
        "nome_logico": "PREENCHER",
        "nome_logico__onde_obter": (
            "OBRIGATÓRIO. MAIUSCULA_COM_UNDERSCORE, 2 a 64 caracteres "
            "(ex.: FACEBOOK_PAGE_ACESSO). É o rótulo lógico do item, não o valor dele."
        ),
        "localizador": "op://<cofre>/<item>/<campo>",
        "localizador__onde_obter": (
            "OBRIGATÓRIO. O ENDEREÇO no 1Password, nunca o valor. No app: clique com "
            "o botão direito no CAMPO desejado > 'Copiar referência de segredo'. "
            "Pela CLI: `op item get \"<item>\" --format json` e monte "
            "op://<cofre>/<item>/<campo>. Espaços viram %20. SEM query string: uma "
            "referência terminada em ?attribute=otp aponta para o segundo fator e "
            "o script recusa."
        ),
        "finalidade": "PREENCHER",
        "finalidade__onde_obter": (
            "OBRIGATÓRIO, 5 a 500 caracteres. Para que esse acesso é usado "
            "(ex.: 'Administração da Página e publicação orgânica')."
        ),
        "owner_nome": "PREENCHER",
        "owner_nome__onde_obter": "OBRIGATÓRIO. Quem é responsável por esse item no cofre.",
        "estado": "referenced",
        "estado__onde_obter": (
            "OBRIGATÓRIO. Um de: not_required, not_registered, referenced, review_due."
        ),
        "valido_ate": None,
        "valido_ate__onde_obter": "OPCIONAL (null). Data AAAA-MM-DD de expiração conhecida.",
    },

    "credencial_perfil": {
        "_opcional": (
            "Preencha só se `perfil_adspower` não for null. Se o perfil existir e "
            "este bloco for null, o script recusa: um perfil sem endereço de "
            "credencial é um ativo que ninguém consegue abrir."
        ),
        "provider": "1password",
        "provider__onde_obter": "OBRIGATÓRIO. Mesmos cinco valores do bloco acima.",
        "nome_logico": "PREENCHER",
        "nome_logico__onde_obter": (
            "OBRIGATÓRIO. Ex.: ADSPOWER_ACESSO ou ADSPOWER_API_KEY — a própria "
            "migration usa ADSPOWER_API_KEY como exemplo de nome lógico legítimo."
        ),
        "localizador": "op://<cofre>/<item>/<campo>",
        "localizador__onde_obter": "OBRIGATÓRIO. Mesma regra do bloco acima.",
        "finalidade": "PREENCHER",
        "finalidade__onde_obter": (
            "OBRIGATÓRIO, 5 a 500 caracteres (ex.: 'Abertura do perfil isolado para "
            "QA visual pós-publicação')."
        ),
        "owner_nome": "PREENCHER",
        "owner_nome__onde_obter": "OBRIGATÓRIO.",
        "estado": "referenced",
        "estado__onde_obter": "OBRIGATÓRIO. Mesmos quatro valores do bloco acima.",
        "valido_ate": None,
        "valido_ate__onde_obter": "OPCIONAL (null).",
    },

    "verificacao": {
        "_o_que_e": (
            "O primeiro recibo de prova sobre a Página. Ele é o que separa "
            "'achamos que a página é nossa' de 'conferimos em tal dia, por tal "
            "método'. Se a única base ainda for a palavra do dono, diga isso: "
            "resultado 'unverified' com procedência 'owner_declaration' é uma "
            "resposta honesta e aceita pelo contrato."
        ),
        "alvo": "ativo",
        "alvo__onde_obter": "OBRIGATÓRIO. Um de: ativo, credencial, relacao, engine.",
        "resultado": "PREENCHER",
        "resultado__onde_obter": (
            "OBRIGATÓRIO. Um de: unverified, partial, verified, expired, failed, "
            "blocked. Os seis não são sinônimos: 'failed' é uma tentativa que deu "
            "errado, 'blocked' é o cofre trancado, 'unverified' é 'nunca tentei'."
        ),
        "metodo": "PREENCHER",
        "metodo__onde_obter": (
            "OBRIGATÓRIO, 3 a 240 caracteres. COMO você conferiu (ex.: 'Leitura do "
            "Business Suite > Configurações da Página, com captura de tela')."
        ),
        "procedencia": "PREENCHER",
        "procedencia__onde_obter": (
            "OBRIGATÓRIO. Um de: owner_declaration, live_observation, "
            "repository_inventory, provider_record."
        ),
        "evidencia": "PREENCHER",
        "evidencia__onde_obter": (
            "OBRIGATÓRIO, 10 a 1000 caracteres. O QUE foi visto, em palavras. "
            "Sem colar token, cookie ou URL assinada — o script recusa. NÃO repita "
            "o ID completo da Página aqui."
        ),
        "observado_em": "PREENCHER",
        "observado_em__onde_obter": (
            "OBRIGATÓRIO. Instante ISO-8601 COM FUSO da OBSERVAÇÃO, não do "
            "preenchimento (ex.: 2026-09-01T14:35:00-03:00). O banco recusa data no "
            "futuro; sem fuso, o instante seria lido no fuso do servidor."
        ),
        "proximo_ato": None,
        "proximo_ato__onde_obter": "OPCIONAL (null), 5 a 800 caracteres.",
        "revisar_em": None,
        "revisar_em__onde_obter": "OPCIONAL (null). Data AAAA-MM-DD da próxima revisão.",
    },
}


def _campos_de_dado(bloco: dict) -> dict:
    """Descarta instrução para humano. Só o que sobra pode virar payload."""
    return {
        k: v for k, v in bloco.items()
        if not k.startswith("_") and not k.endswith("__onde_obter")
    }


# ==========================================================================
# 6. MONTAGEM DAS SEIS OPERAÇÕES
# ==========================================================================


def _bloco(ficha: dict, nome: str) -> dict:
    valor = ficha.get(nome)
    if valor is None:
        raise FichaRecusada(f"a ficha não tem o bloco obrigatório `{nome}`.")
    if not isinstance(valor, dict):
        raise FichaRecusada(f"o bloco `{nome}` precisa ser um objeto JSON.")
    return _campos_de_dado(valor)


def _operacao(passo: int, operacao: str, metodo: str, caminho: str, funcao: str,
              chave: str, corpo_http: dict, payload_sql: dict, motivo: str | None = None) -> dict:
    """Uma operação sai nas DUAS formas, e as duas são necessárias.

    `corpo_http` é o que `rotas.py` aceita: sem `ativo_id`/`origem_id`, porque
    eles vêm do caminho da URL. `payload_sql` é o que a função governada aceita:
    com eles dentro, porque não há caminho de URL num `SELECT`. Emitir só uma das
    duas obrigaria quem opera a reescrever a outra à mão — e é exatamente aí que
    um campo se perde.
    """
    return {
        # `passo` e o numero CANONICO da operacao nas seis do cabecalho; `ordem`
        # e a posicao na lista emitida. Sem perfil AdsPower a lista tem quatro
        # entradas e os passos 2 e 3 nao existem — manter os dois numeros e o que
        # deixa isso legivel em vez de parecer buraco.
        "passo": passo,
        "ordem": passo,
        "operacao": operacao,
        "http": {"metodo": metodo, "caminho": caminho, "corpo": corpo_http},
        "sql": {"funcao": funcao, "payload": payload_sql,
                **({"motivo": motivo} if motivo is not None else {})},
        "chave_idempotencia": chave,
    }


def montar(ficha: dict, agora: datetime) -> list[dict]:
    """Valida a ficha inteira e devolve as operações em ordem de dependência."""

    # -- Portão 1: segredo, e ele vem ANTES da pendência de propósito.
    # -- As duas regras recusam, mas respondem a perguntas diferentes: pendência
    # -- é "isto ainda não existe", segredo é "isto nunca pode existir aqui". Se
    # -- a ficha meio preenchida respondesse primeiro "faltam três campos", quem
    # -- opera corrigiria os três e rodaria de novo com a senha ainda no arquivo,
    # -- ouvindo só na terceira volta que ela nunca deveria ter sido digitada.
    # -- A isenção do `localizador` é a mesma que o banco faz em
    # -- `p_payload - 'localizador'` (migration linha 1774); fora dela, um
    # -- `op://…` é material de credencial num campo errado.
    recusar_chave_sensivel(ficha, "ficha", isentos=ISENTOS)
    recusar_material_de_credencial(ficha, "ficha", isentos=ISENTOS)

    # -- Portão 2: pendências. Antes de qualquer validação de forma, porque um
    # -- "PREENCHER" que passa em `BETWEEN 2 AND 160` é o defeito que a regra (a)
    # -- existe para impedir: ele vira um ativo real chamado PREENCHER.
    pendentes = coletar_pendencias(ficha)
    if pendentes:
        raise FichaRecusada(
            "a ficha ainda tem campo por preencher. Emitir payload com marcador é "
            "como um ID inventado entra no banco. Falta:\n  - "
            + "\n  - ".join(pendentes)
        )

    pagina = _bloco(ficha, "pagina")
    credencial_pagina = _bloco(ficha, "credencial_pagina")
    verificacao = _bloco(ficha, "verificacao")
    relacao_cfg = _campos_de_dado(ficha.get("relacao") or {})

    tem_perfil = ficha.get("perfil_adspower") is not None
    if tem_perfil and ficha.get("credencial_perfil") is None:
        raise FichaRecusada(
            "há bloco `perfil_adspower` mas `credencial_perfil` é null. Um perfil de "
            "navegador sem endereço de credencial é um ativo que ninguém consegue "
            "abrir — e o ADR exige que o perfil entre no Cofre COMO referência."
        )
    if not tem_perfil and ficha.get("credencial_perfil") is not None:
        raise FichaRecusada(
            "há `credencial_perfil` sem `perfil_adspower`. "
            "`cofre_credencial_referencia.ativo_id` tem FK para `cofre_ativo`: a "
            "referência não pode apontar para um ativo que não vai existir."
        )

    # ---------------------------------------------------------------- 1. PÁGINA
    id_completo = str(pagina.get("id_plataforma", "")).strip()
    display = display_id_mascarado(id_completo, "pagina.id_plataforma")
    portfolio = texto(pagina.get("business_portfolio_nome"),
                      "pagina.business_portfolio_nome", 1, 200)

    ativo_pagina = {
        "ativo_id": id_de_ativo(PAGINA_ATIVO_ID, "ativo_id da página"),
        "kind": PAGINA_KIND,
        "cluster": GAVETA_DO_TIPO[PAGINA_KIND],
        "nome": texto(pagina.get("nome"), "pagina.nome", 2, 160),
        "plataforma": PAGINA_PLATAFORMA,
        "estado": escolha(pagina.get("estado"), "pagina.estado", ESTADOS_DE_ATIVO),
        "criticidade": escolha(pagina.get("criticidade"), "pagina.criticidade", CRITICIDADES),
        "resumo": texto(pagina.get("resumo"), "pagina.resumo", 10, 800),
        "dono_nome": texto(pagina.get("dono_nome"), "pagina.dono_nome", 1, 240),
        "dono_custodia": escolha(pagina.get("dono_custodia"), "pagina.dono_custodia", CUSTODIAS),
        "display_id": display,
        # O Business Portfolio é onde a Página operacionalmente MORA, e
        # `localizacao_rotulo` é o campo de "onde mora" que não aceita segredo
        # nem caminho de disco. A alternativa seria cadastrar o portfólio como
        # ativo `meta_business_portfolio` e relacioná-lo — o que é uma tarefa
        # inteira (P03) e não cabe neste onboarding de seis passos.
        "localizacao_rotulo": localizacao_rotulo(
            f"Business Portfolio Meta · {portfolio}", "pagina.business_portfolio_nome"),
        "capacidades": lista(pagina.get("capacidades"), "pagina.capacidades", 1, 40),
        "tags": lista(pagina.get("tags") or [], "pagina.tags", 0, 30),
        "proxima_acao": texto(pagina.get("proxima_acao"), "pagina.proxima_acao", 10, 800),
    }
    url = url_publica(pagina.get("url_publica"), "pagina.url_publica")
    if url is not None:
        ativo_pagina["url_publica"] = url
    projeto = texto_opcional(pagina.get("projeto"), "pagina.projeto", 1, 240)
    if projeto is not None:
        ativo_pagina["projeto"] = projeto
    vertical = texto_opcional(pagina.get("vertical"), "pagina.vertical", 1, 240)
    if vertical is not None:
        ativo_pagina["vertical"] = vertical

    operacoes: list[dict] = []
    motivo_pagina = (
        "onboarding da pagina Facebook monetizada (P03-T02 / P12-T02) a partir de "
        "ficha preenchida pelo operador, por scripts/onboarding_pagina_facebook.py"
    )
    chave_pagina = chave_de_idempotencia("pagina", ativo_pagina)
    operacoes.append(_operacao(
        1, "cofre.cadastrar_ativo", "POST", "/api/cofre/ativos", "public.cofre_cadastrar_ativo",
        chave_pagina,
        {"chave_idempotencia": chave_pagina, "motivo": motivo_pagina, "ativo": ativo_pagina},
        ativo_pagina, motivo_pagina))

    # ---------------------------------------------------------------- 2. PERFIL
    perfil_id: str | None = None
    if tem_perfil:
        perfil = _bloco(ficha, "perfil_adspower")
        slug = texto(perfil.get("slug"), "perfil_adspower.slug", 1, 120)
        perfil_id = id_de_ativo(f"asset:browser-profile:{slug}", "perfil_adspower.slug")
        referencia = texto(perfil.get("id_referencia"), "perfil_adspower.id_referencia", 1, 80)
        if DISPLAY_ID_ESPACOS.search(referencia):
            raise FichaRecusada(
                "perfil_adspower.id_referencia tem dois ou mais espaços seguidos e "
                "`cofre_ativo_display_id_sanitizado` recusa isso."
            )
        ativo_perfil = {
            "ativo_id": perfil_id,
            "kind": PERFIL_KIND,
            "cluster": GAVETA_DO_TIPO[PERFIL_KIND],
            "nome": texto(perfil.get("nome"), "perfil_adspower.nome", 2, 160),
            "plataforma": PERFIL_PLATAFORMA,
            "estado": escolha(perfil.get("estado"), "perfil_adspower.estado", ESTADOS_DE_ATIVO),
            "criticidade": escolha(perfil.get("criticidade"), "perfil_adspower.criticidade", CRITICIDADES),
            "resumo": texto(perfil.get("resumo"), "perfil_adspower.resumo", 10, 800),
            "dono_nome": texto(perfil.get("dono_nome"), "perfil_adspower.dono_nome", 1, 240),
            "dono_custodia": escolha(perfil.get("dono_custodia"), "perfil_adspower.dono_custodia", CUSTODIAS),
            # ID INTEIRO, e a diferença para a Página é factual: P03-T07 pede que
            # "o perfil possua ID de referência", esse número é local do cliente
            # AdsPower e não endereça conta de plataforma nenhuma sem a API key da
            # Local API — que o ADR proíbe de entrar no Cofre.
            "display_id": referencia,
            "capacidades": lista(perfil.get("capacidades"), "perfil_adspower.capacidades", 1, 40),
            "tags": lista(perfil.get("tags") or [], "perfil_adspower.tags", 0, 30),
            "proxima_acao": texto(perfil.get("proxima_acao"), "perfil_adspower.proxima_acao", 10, 800),
        }
        proxy = texto_opcional(perfil.get("proxy_rotulo"), "perfil_adspower.proxy_rotulo", 1, 200)
        if proxy is not None:
            ativo_perfil["localizacao_rotulo"] = localizacao_rotulo(
                f"Proxy · {proxy}", "perfil_adspower.proxy_rotulo")

        motivo_perfil = (
            "inventario do perfil AdsPower que opera a pagina (P03-T07), sem segredo "
            "bruto, por scripts/onboarding_pagina_facebook.py"
        )
        chave_perfil = chave_de_idempotencia("perfil", ativo_perfil)
        operacoes.append(_operacao(
            2, "cofre.cadastrar_ativo", "POST", "/api/cofre/ativos",
            "public.cofre_cadastrar_ativo", chave_perfil,
            {"chave_idempotencia": chave_perfil, "motivo": motivo_perfil, "ativo": ativo_perfil},
            ativo_perfil, motivo_perfil))

        # ------------------------------------------------------------ 3. RELAÇÃO
        estado_relacao = escolha(relacao_cfg.get("estado", "declared"),
                                 "relacao.estado", ESTADOS_DE_RELACAO)
        if perfil_id == ativo_pagina["ativo_id"]:
            raise FichaRecusada(
                "o perfil e a página ficaram com o mesmo ativo_id; "
                "`cofre_relacao_sem_laco` recusa aresta de um nó só."
            )
        corpo_relacao = {
            "tipo": RELACAO_TIPO,
            "destino_id": perfil_id,
            "destino_rotulo": texto(ativo_perfil["nome"], "relacao.destino_rotulo", 1, 240),
            "estado": estado_relacao,
        }
        payload_relacao = {"origem_id": ativo_pagina["ativo_id"], **corpo_relacao}
        chave_relacao = chave_de_idempotencia("relacao", payload_relacao)
        operacoes.append(_operacao(
            3, "cofre.relacionar", "POST",
            f"/api/cofre/ativos/{ativo_pagina['ativo_id']}/relacoes",
            "public.cofre_relacionar", chave_relacao,
            {"chave_idempotencia": chave_relacao, **corpo_relacao},
            payload_relacao))

    # ------------------------------------------------------- 4 e 5. CREDENCIAIS
    def _credencial(bloco: dict, prefixo: str, ativo_id: str, ordem: int, sufixo: str) -> dict:
        provider = escolha(bloco.get("provider"), f"{prefixo}.provider", PROVIDERS)
        corpo = {
            "provider": provider,
            "nome_logico": nome_logico(bloco.get("nome_logico"), f"{prefixo}.nome_logico"),
            "localizador": localizador(provider, bloco.get("localizador"), f"{prefixo}.localizador"),
            "finalidade": texto(bloco.get("finalidade"), f"{prefixo}.finalidade", 5, 500),
            "owner_nome": texto(bloco.get("owner_nome"), f"{prefixo}.owner_nome", 1, 240),
            "estado": escolha(bloco.get("estado", "referenced"), f"{prefixo}.estado",
                              ESTADOS_DE_CREDENCIAL),
        }
        validade = data_iso(bloco.get("valido_ate"), f"{prefixo}.valido_ate")
        if validade is not None:
            corpo["valido_ate"] = validade
        payload = {"ativo_id": ativo_id, **corpo}
        chave = chave_de_idempotencia(sufixo, payload)
        return _operacao(
            ordem, "cofre.referenciar_credencial", "POST",
            f"/api/cofre/ativos/{ativo_id}/credencial",
            "public.cofre_referenciar_credencial", chave,
            {"chave_idempotencia": chave, **corpo}, payload)

    operacoes.append(_credencial(credencial_pagina, "credencial_pagina",
                                 ativo_pagina["ativo_id"], 4, "credpagina"))
    if tem_perfil:
        operacoes.append(_credencial(_bloco(ficha, "credencial_perfil"), "credencial_perfil",
                                     perfil_id, 5, "credperfil"))

    # ------------------------------------------------------------ 6. VERIFICAÇÃO
    corpo_verificacao = {
        "alvo": escolha(verificacao.get("alvo"), "verificacao.alvo", ALVOS_DE_VERIFICACAO),
        "resultado": escolha(verificacao.get("resultado"), "verificacao.resultado",
                             RESULTADOS_DE_VERIFICACAO),
        "metodo": texto(verificacao.get("metodo"), "verificacao.metodo", 3, 240),
        "procedencia": escolha(verificacao.get("procedencia"), "verificacao.procedencia",
                               PROCEDENCIAS),
        "evidencia": texto(verificacao.get("evidencia"), "verificacao.evidencia", 10, 1000),
        "observado_em": instante_observado(verificacao.get("observado_em"),
                                           "verificacao.observado_em", agora),
    }
    proximo = texto_opcional(verificacao.get("proximo_ato"), "verificacao.proximo_ato", 5, 800)
    if proximo is not None:
        corpo_verificacao["proximo_ato"] = proximo
    revisar = data_iso(verificacao.get("revisar_em"), "verificacao.revisar_em")
    if revisar is not None:
        corpo_verificacao["revisar_em"] = revisar

    payload_verificacao = {"ativo_id": ativo_pagina["ativo_id"], **corpo_verificacao}
    chave_verificacao = chave_de_idempotencia("verificacao", payload_verificacao)
    operacoes.append(_operacao(
        6, "cofre.registrar_verificacao", "POST",
        f"/api/cofre/ativos/{ativo_pagina['ativo_id']}/verificacoes",
        "public.cofre_registrar_verificacao", chave_verificacao,
        {"chave_idempotencia": chave_verificacao, **corpo_verificacao},
        payload_verificacao))

    # -- Portão 3, e o mais importante da regra (c): o ID completo não sobrevive.
    # -- Ele foi usado para derivar quatro dígitos e para nada mais. Se aparecer
    # -- em qualquer campo emitido — uma url `profile.php?id=…`, uma evidência
    # -- colada, uma tag — a emissão inteira cai.
    for posicao, op in enumerate(operacoes, start=1):
        op["ordem"] = posicao

    serializado = json.dumps(operacoes, ensure_ascii=False)
    if id_completo in serializado:
        raise FichaRecusada(
            "o ID completo da Página aparece em algum campo emitido (provavelmente "
            "`pagina.url_publica` no formato profile.php?id=… ou a evidência). O ID "
            "cru não entra no Cofre: use o endereço de nome de usuário, ou deixe "
            "`url_publica` como null, e descreva a evidência sem repetir o número."
        )
    for trecho in TRECHOS_DE_DISCO_NA_SAIDA:
        if trecho in serializado:
            raise FichaRecusada(
                f"a saída contém {trecho!r}, que é rastro de caminho de disco do "
                "operador. Use rótulos operacionais, não caminhos."
            )
    return operacoes


# ==========================================================================
# 7. EMISSÃO
# ==========================================================================


def emitir_json(operacoes: list[dict], ficha_sha: str) -> str:
    """A saída não carrega o caminho da ficha, e isso é decisão e não descuido.

    O caminho da ficha do operador é quase sempre `/Users/<pessoa>/…` — o mesmo
    problema que `dominio.sanitizar_localizacao` recusa. Em vez do caminho, sai o
    sha256 do conteúdo: identifica a ficha para quem a tem, e não diz nada sobre
    a máquina de ninguém.
    """
    documento = {
        "gerado_por": "scripts/onboarding_pagina_facebook.py",
        "ficha_sha256": ficha_sha,
        "aplicar_em_ordem": True,
        "por_que_a_ordem": (
            "cofre_relacao.destino_id, cofre_credencial_referencia.ativo_id e "
            "cofre_verificacao.ativo_id têm FK para cofre_ativo"
        ),
        "operacoes": operacoes,
    }
    return json.dumps(documento, ensure_ascii=False, indent=2) + "\n"


def emitir_sql(operacoes: list[dict], ficha_sha: str) -> str:
    """`SELECT public.cofre_*(…)` na ordem, com autor vindo por `psql -v`.

    Identidade de operador não é escrita num artefato: `autor_sub` e `autor_email`
    entram como variáveis, do mesmo jeito que `scripts/importar_engines_no_cofre.py`
    já faz.
    """
    linhas = [
        "-- Gerado por scripts/onboarding_pagina_facebook.py — NAO EDITAR A MAO.",
        f"-- Ficha (sha256, 12 primeiros): {ficha_sha}",
        "-- Autor e e-mail chegam por psql -v; identidade de operador nao pertence",
        "-- a um artefato versionado.",
        "--   psql -v autor_sub=<uuid> -v autor_email=<email> -f <este arquivo>",
        "--",
        "-- APLIQUE NA ORDEM. As FKs de cofre_relacao, cofre_credencial_referencia e",
        "-- cofre_verificacao apontam para cofre_ativo: fora de ordem, o banco recusa.",
        "BEGIN;",
        "",
    ]
    for op in operacoes:
        corpo = json.dumps(op["sql"]["payload"], ensure_ascii=False, indent=2)
        if "$cofre$" in corpo or "$motivo$" in corpo:
            raise FichaRecusada("o payload contém a tag de dollar-quoting; o SQL sairia quebrado.")
        linhas.append(f"-- {op['ordem']}. {op['operacao']} (passo canonico {op['passo']})")
        linhas.append(f"SELECT {op['sql']['funcao']}(")
        linhas.append(f"  $cofre${corpo}$cofre$::jsonb,")
        linhas.append(f"  '{op['chave_idempotencia']}',")
        linhas.append("  :'autor_sub'::uuid,")
        linhas.append("  :'autor_email'")
        if "motivo" in op["sql"]:
            motivo = op["sql"]["motivo"]
            if "$motivo$" in motivo:
                raise FichaRecusada("o motivo contém a tag de dollar-quoting.")
            linhas[-1] = linhas[-1] + ","
            linhas.append(f"  $motivo${motivo}$motivo$")
        linhas.append(");")
        linhas.append("")
    linhas.append("COMMIT;")
    linhas.append("")
    return "\n".join(linhas)


def ler_ficha(caminho: Path) -> tuple[dict, str]:
    try:
        bruto = caminho.read_text(encoding="utf-8")
    except OSError as erro:
        raise FichaRecusada(f"não consegui ler a ficha: {erro.strerror}") from None
    try:
        ficha = json.loads(bruto)
    except json.JSONDecodeError as erro:
        raise FichaRecusada(
            f"a ficha não é JSON válido (linha {erro.lineno}, coluna {erro.colno}): {erro.msg}"
        ) from None
    if not isinstance(ficha, dict):
        raise FichaRecusada("a ficha precisa ser um objeto JSON no topo.")
    sha = hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:12]
    return ficha, sha


# ==========================================================================
# 8. AUTOTESTE — as recusas do banco, provadas antes de chegar nele
# ==========================================================================
# A ficha VÁLIDA usada abaixo é FICTÍCIA e existe só dentro desta função. Ela não
# é escrita em disco, não é sugerida ao operador e nenhum valor dela descreve a
# página real — o repositório não sabe nada sobre a página real, e é por isso que
# este script existe.

_INSTANTE_FICTICIO = "2026-08-26T15:40:00-03:00"  # a data da declaração do dono, fixtures.ts:34


def _ficha_ficticia(com_perfil: bool = True) -> dict:
    ficha = {
        "pagina": {
            "id_plataforma": "100000000001692",
            "nome": "PAGINA FICTICIA DE TESTE",
            "url_publica": "https://www.facebook.com/pagina-ficticia-de-teste",
            "business_portfolio_nome": "PORTFOLIO FICTICIO DE TESTE",
            "estado": "declared",
            "criticidade": "high",
            "resumo": "Ficha FICTICIA usada apenas pelo autoteste deste script; nao descreve ativo real.",
            "dono_nome": "DONO FICTICIO",
            "dono_custodia": "declared",
            "projeto": None,
            "vertical": None,
            "capacidades": ["Publicação orgânica"],
            "tags": ["autoteste"],
            "proxima_acao": "Nada a fazer: linha ficticia do autoteste, descartada ao fim do processo.",
        },
        "perfil_adspower": {
            "slug": "ficticio-autoteste",
            "id_referencia": "kfic0001",
            "nome": "PERFIL FICTICIO DE TESTE",
            "estado": "declared",
            "criticidade": "medium",
            "resumo": "Perfil FICTICIO usado apenas pelo autoteste; nao existe no AdsPower.",
            "dono_nome": "DONO FICTICIO",
            "dono_custodia": "declared",
            "proxy_rotulo": None,
            "capacidades": ["Abertura de sessão isolada"],
            "tags": [],
            "proxima_acao": "Nada a fazer: perfil ficticio do autoteste, descartado ao fim do processo.",
        },
        "relacao": {"estado": "declared"},
        "credencial_pagina": {
            "provider": "1password",
            "nome_logico": "FACEBOOK_PAGE_ACESSO",
            "localizador": "op://CofreFicticio/ItemFicticio/campo",
            "finalidade": "Ficticia: administracao da pagina no autoteste.",
            "owner_nome": "DONO FICTICIO",
            "estado": "referenced",
            "valido_ate": None,
        },
        "credencial_perfil": {
            "provider": "1password",
            "nome_logico": "ADSPOWER_ACESSO",
            "localizador": "op://CofreFicticio/PerfilFicticio/campo",
            "finalidade": "Ficticia: abertura do perfil isolado no autoteste.",
            "owner_nome": "DONO FICTICIO",
            "estado": "referenced",
            "valido_ate": None,
        },
        "verificacao": {
            "alvo": "ativo",
            "resultado": "unverified",
            "metodo": "Autoteste do script, sem observacao de plataforma.",
            "procedencia": "owner_declaration",
            "evidencia": "Ficha ficticia do autoteste; nenhuma tela foi aberta e nada foi conferido.",
            "observado_em": _INSTANTE_FICTICIO,
            "proximo_ato": None,
            "revisar_em": None,
        },
    }
    if not com_perfil:
        ficha["perfil_adspower"] = None
        ficha["credencial_perfil"] = None
    return ficha


def autoteste() -> int:
    agora = datetime.now(timezone.utc)
    falhas: list[str] = []
    passos = 0

    def checar(nome: str, condicao: bool, detalhe: str = "") -> None:
        nonlocal passos
        passos += 1
        marca = "ok  " if condicao else "FALHA"
        print(f"  [{marca}] {nome}" + (f" — {detalhe}" if detalhe and not condicao else ""))
        if not condicao:
            falhas.append(nome)

    def recusa(nome: str, ficha: dict, trecho_esperado: str) -> None:
        try:
            montar(ficha, agora)
        except FichaRecusada as erro:
            checar(nome, trecho_esperado.lower() in str(erro).lower(),
                   f"mensagem foi: {erro}")
            return
        checar(nome, False, "a ficha passou quando deveria ter sido recusada")

    print("autoteste de scripts/onboarding_pagina_facebook.py")
    print("")
    print("A. A ficha modelo intocada é recusada, e a recusa lista o que falta")
    modelo = json.loads(json.dumps(FICHA_MODELO_DOC))
    try:
        montar(modelo, agora)
        checar("modelo intocado recusado", False, "o modelo passou")
    except FichaRecusada as erro:
        texto_erro = str(erro)
        checar("modelo intocado recusado", "campo por preencher" in texto_erro)
        checar("a recusa nomeia pagina.nome", "ficha.pagina.nome" in texto_erro)
        checar("a recusa nomeia o localizador template",
              "ficha.credencial_pagina.localizador" in texto_erro)
        checar("a recusa nomeia o instante de observação",
              "ficha.verificacao.observado_em" in texto_erro)
        checar("a recusa ignora campos de instrução",
              "__onde_obter" not in texto_erro)

    print("")
    print("B. Segredo em qualquer campo derruba a ficha")
    com_senha = _ficha_ficticia()
    com_senha["pagina"]["password"] = "qualquer-coisa"
    recusa("chave proibida `password` recusada", com_senha, "campo proibido na ficha")

    com_senha_aninhada = _ficha_ficticia()
    com_senha_aninhada["credencial_pagina"]["mfa"] = "irrelevante"
    recusa("chave proibida `mfa` recusada", com_senha_aninhada, "campo proibido na ficha")

    com_grafia = _ficha_ficticia()
    com_grafia["pagina"]["Access-Token"] = "irrelevante"
    recusa("grafia alternativa `Access-Token` recusada", com_grafia, "campo proibido na ficha")

    com_jwt = _ficha_ficticia()
    com_jwt["pagina"]["resumo"] = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0 colado por engano"
    )
    recusa("JWT dentro de texto livre recusado", com_jwt, "parece credencial")

    localizador_fora_de_lugar = _ficha_ficticia()
    localizador_fora_de_lugar["pagina"]["localizador"] = "op://Cofre/Item/campo"
    recusa("`localizador` fora do bloco de credencial recusado",
           localizador_fora_de_lugar, "campo proibido na ficha")

    com_op_fora = _ficha_ficticia()
    com_op_fora["verificacao"]["evidencia"] = "Vi o item em op://Cofre/Item/campo do 1Password."
    recusa("`op://` fora do campo de localizador recusado", com_op_fora, "parece credencial")

    print("")
    print("C. MFA não entra nem por referência")
    com_otp = _ficha_ficticia()
    com_otp["credencial_pagina"]["localizador"] = "op://CofreFicticio/ItemFicticio/campo?attribute=otp"
    recusa("localizador com ?attribute=otp recusado", com_otp, "segundo fator")

    com_fragmento = _ficha_ficticia()
    com_fragmento["credencial_perfil"]["localizador"] = "op://CofreFicticio/PerfilFicticio/campo#totp"
    recusa("localizador com fragmento recusado", com_fragmento, "query string ou fragmento")

    com_senha_no_localizador = _ficha_ficticia()
    com_senha_no_localizador["credencial_pagina"]["localizador"] = "Senha-Do-Facebook-2026"
    try:
        montar(com_senha_no_localizador, agora)
        checar("senha colada no localizador recusada", False, "passou")
    except FichaRecusada as erro:
        checar("senha colada no localizador recusada", "forma esperada" in str(erro))
        checar("a recusa NÃO ecoa o valor recusado",
              "Senha-Do-Facebook-2026" not in str(erro), f"mensagem: {erro}")

    print("")
    print("D. Ficha fictícia válida emite as seis operações na ordem certa")
    operacoes = montar(_ficha_ficticia(), agora)
    checar("seis operações", len(operacoes) == 6, f"vieram {len(operacoes)}")
    esperado = [
        "cofre.cadastrar_ativo", "cofre.cadastrar_ativo", "cofre.relacionar",
        "cofre.referenciar_credencial", "cofre.referenciar_credencial",
        "cofre.registrar_verificacao",
    ]
    checar("a ordem é página, perfil, relação, credencial, credencial, verificação",
          [o["operacao"] for o in operacoes] == esperado,
          str([o["operacao"] for o in operacoes]))
    checar("a página é o ativo 1", operacoes[0]["sql"]["payload"]["kind"] == "facebook_page")
    checar("o perfil é o ativo 2", operacoes[1]["sql"]["payload"]["kind"] == "browser_profile")
    checar("a relação sai da página para o perfil",
          operacoes[2]["sql"]["payload"]["origem_id"] == PAGINA_ATIVO_ID
          and operacoes[2]["sql"]["payload"]["destino_id"] == "asset:browser-profile:ficticio-autoteste"
          and operacoes[2]["sql"]["payload"]["tipo"] == "authenticates_through")
    checar("a credencial 4 é da página",
          operacoes[3]["sql"]["payload"]["ativo_id"] == PAGINA_ATIVO_ID)
    checar("a credencial 5 é do perfil",
          operacoes[4]["sql"]["payload"]["ativo_id"] == "asset:browser-profile:ficticio-autoteste")
    checar("a verificação carrega o instante OBSERVADO da ficha",
          operacoes[5]["sql"]["payload"]["observado_em"] == _INSTANTE_FICTICIO)
    checar("a verificação carrega método e procedência",
          operacoes[5]["sql"]["payload"]["procedencia"] == "owner_declaration"
          and len(operacoes[5]["sql"]["payload"]["metodo"]) >= 3)

    print("")
    print("E. Sem perfil AdsPower, três operações e nenhum perfil inventado")
    # Tres, e nao quatro: sem perfil nao ha relacao (passo 3) nem credencial de
    # perfil (passo 5). Sobram pagina, credencial da pagina e verificacao.
    sem_perfil = montar(_ficha_ficticia(com_perfil=False), agora)
    checar("três operações", len(sem_perfil) == 3, f"vieram {len(sem_perfil)}")
    checar("os passos canônicos são 1, 4 e 6",
          [o["passo"] for o in sem_perfil] == [1, 4, 6], str([o["passo"] for o in sem_perfil]))
    checar("a ordem de aplicação é 1, 2, 3 sem buraco",
          [o["ordem"] for o in sem_perfil] == [1, 2, 3], str([o["ordem"] for o in sem_perfil]))
    checar("nenhuma menciona browser_profile",
          "browser_profile" not in json.dumps(sem_perfil, ensure_ascii=False))
    recusa("perfil sem credencial é recusado",
           {**_ficha_ficticia(), "credencial_perfil": None}, "sem endereço de credencial")
    recusa("credencial de perfil sem perfil é recusada",
           {**_ficha_ficticia(), "perfil_adspower": None}, "não vai existir")

    print("")
    print("F. O ID completo da página não sobrevive à emissão")
    saida = json.dumps(operacoes, ensure_ascii=False)
    checar("o ID completo não aparece na saída", "100000000001692" not in saida)
    checar("o display_id é a máscara de 4 dígitos",
          operacoes[0]["sql"]["payload"]["display_id"] == "•••-•••-1692",
          operacoes[0]["sql"]["payload"]["display_id"])
    com_url_id = _ficha_ficticia()
    com_url_id["pagina"]["url_publica"] = "https://www.facebook.com/profile.php?id=100000000001692"
    recusa("url com o ID cru recusada", com_url_id, "ID completo da Página aparece")

    print("")
    print("G. Comprimentos e formas do banco, recusados aqui e não num 400")
    curto = _ficha_ficticia()
    curto["pagina"]["resumo"] = "curto"
    recusa("resumo abaixo de 10 caracteres", curto, "entre 10 e 800")

    url_ruim = _ficha_ficticia()
    url_ruim["pagina"]["url_publica"] = "file:///etc/passwd"
    recusa("url não-HTTP recusada", url_ruim, "HTTP(S)")

    url_longa = _ficha_ficticia()
    url_longa["pagina"]["url_publica"] = "https://exemplo.invalid/" + ("a" * 2000)
    recusa("url acima de 2000 caracteres", url_longa, "entre 11 e 2000")

    sem_capacidade = _ficha_ficticia()
    sem_capacidade["pagina"]["capacidades"] = []
    recusa("lista de capacidades vazia", sem_capacidade, "entre 1 e 40 itens")

    nome_ruim = _ficha_ficticia()
    nome_ruim["credencial_pagina"]["nome_logico"] = "acesso da pagina"
    recusa("nome lógico fora da forma MAIUSCULA_COM_UNDERSCORE", nome_ruim, "MAIUSCULA_COM_UNDERSCORE")

    futuro = _ficha_ficticia()
    futuro["verificacao"]["observado_em"] = "2099-01-01T00:00:00-03:00"
    recusa("observação no futuro recusada", futuro, "no futuro")

    sem_fuso = _ficha_ficticia()
    sem_fuso["verificacao"]["observado_em"] = "2026-08-26T15:40:00"
    recusa("observação sem fuso recusada", sem_fuso, "fuso")

    id_curto = _ficha_ficticia()
    id_curto["pagina"]["id_plataforma"] = "1692"
    recusa("ID de página com poucos dígitos", id_curto, "entre 8 e 25")

    id_texto = _ficha_ficticia()
    id_texto["pagina"]["id_plataforma"] = "minha-pagina"
    recusa("ID de página que não é número", id_texto, "só dígitos")

    portfolio_email = _ficha_ficticia()
    portfolio_email["pagina"]["business_portfolio_nome"] = "conta@exemplo.invalid"
    recusa("portfólio com '@' recusado", portfolio_email, "caminho de disco")

    estado_ruim = _ficha_ficticia()
    estado_ruim["pagina"]["estado"] = "publicado"
    recusa("estado fora do CHECK do banco", estado_ruim, "precisa ser um de")

    provider_ruim = _ficha_ficticia()
    provider_ruim["credencial_pagina"]["provider"] = "keepass"
    recusa("provider fora dos cinco", provider_ruim, "precisa ser um de")

    print("")
    print("H. Chaves de idempotência na forma que cofre_operacao aceita")
    chaves = [o["chave_idempotencia"] for o in operacoes]
    checar("todas passam em cofre_operacao_chave_forma",
          all(CHAVE_DE_IDEMPOTENCIA.match(c) for c in chaves), str(chaves))
    checar("todas distintas", len(set(chaves)) == len(chaves), str(chaves))
    checar("todas entre 8 e 120 caracteres", all(8 <= len(c) <= 120 for c in chaves))
    checar("a chave HTTP é a mesma da SQL",
          all(o["http"]["corpo"]["chave_idempotencia"] == o["chave_idempotencia"] for o in operacoes))

    print("")
    print("I. Determinismo: duas execuções, os mesmos bytes")
    a = emitir_json(montar(_ficha_ficticia(), agora), "0" * 12)
    b = emitir_json(montar(_ficha_ficticia(), agora), "0" * 12)
    checar("saída JSON idêntica", a == b)
    sa = emitir_sql(montar(_ficha_ficticia(), agora), "0" * 12)
    sb = emitir_sql(montar(_ficha_ficticia(), agora), "0" * 12)
    checar("saída SQL idêntica", sa == sb)
    outra = _ficha_ficticia()
    outra["pagina"]["nome"] = "OUTRA PAGINA FICTICIA"
    checar("ficha diferente muda a chave",
          montar(outra, agora)[0]["chave_idempotencia"] != operacoes[0]["chave_idempotencia"])

    print("")
    print("J. O SQL emitido usa as funções governadas e nada mais")
    checar("nenhum INSERT direto", "INSERT INTO" not in sa)
    checar("as quatro funções governadas aparecem",
          all(f in sa for f in ("public.cofre_cadastrar_ativo", "public.cofre_relacionar",
                                "public.cofre_referenciar_credencial",
                                "public.cofre_registrar_verificacao")))
    checar("autor entra por psql -v", ":'autor_sub'::uuid" in sa and ":'autor_email'" in sa)

    print("")
    print("K. A ficha modelo em disco é a mesma do script (sem deriva)")
    caminho_modelo = RAIZ / FICHA_MODELO
    if not caminho_modelo.exists():
        checar(f"{FICHA_MODELO} existe", False, "arquivo ausente; rode --modelo e salve nele")
    else:
        em_disco = caminho_modelo.read_text(encoding="utf-8")
        checar(f"{FICHA_MODELO} idêntica ao modelo do script",
              em_disco == modelo_em_texto(),
              "rode `--modelo > <arquivo>` para regenerar")

    print("")
    print(f"{passos - len(falhas)}/{passos} verificações passaram.")
    if falhas:
        print("FALHOU: " + "; ".join(falhas))
        return 1
    print("autoteste OK")
    return 0


def modelo_em_texto() -> str:
    return json.dumps(FICHA_MODELO_DOC, ensure_ascii=False, indent=2) + "\n"


# ==========================================================================
# 9. LINHA DE COMANDO
# ==========================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Emite os payloads do Cofre para a página Facebook monetizada a partir "
            "de uma ficha preenchida pelo operador. Não faz rede e não escreve no banco."
        ))
    parser.add_argument("--ficha", metavar="ARQUIVO",
                        help="ficha JSON preenchida (veja --modelo)")
    parser.add_argument("--sql", action="store_true",
                        help="emite SELECT public.cofre_*(...) em vez de JSON")
    parser.add_argument("--modelo", action="store_true",
                        help="imprime a ficha modelo, com instrução em cada campo")
    parser.add_argument("--autoteste", action="store_true",
                        help="roda as provas internas e sai 0/1")
    args = parser.parse_args()

    if args.autoteste:
        return autoteste()
    if args.modelo:
        sys.stdout.write(modelo_em_texto())
        return 0
    if not args.ficha:
        parser.print_help(sys.stderr)
        print("\nFalta --ficha. Comece por: --modelo > minha-ficha.json", file=sys.stderr)
        return 2

    try:
        ficha, sha = ler_ficha(Path(args.ficha))
        operacoes = montar(ficha, datetime.now(timezone.utc))
    except FichaRecusada as erro:
        print(f"FICHA RECUSADA — {erro}", file=sys.stderr)
        return 1

    sys.stdout.write(emitir_sql(operacoes, sha) if args.sql else emitir_json(operacoes, sha))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
