#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Importador determinístico dos engines criativos para o Cofre de Ativos.

O que este script faz: lê os DOIS manifestos versionados dos motores criativos e
emite, em stdout, a lista de payloads prontos para `public.cofre_cadastrar_ativo`
(supabase/migrations/v13_01_cofre_de_ativos.sql, seção 15).

O que ele NÃO faz, de propósito:
  - não escreve no banco (quem escreve é a função governada, chamada pelo operador);
  - não faz rede, não lê o disco fora deste repositório;
  - não inventa valor: ausência sai como CHAVE OMITIDA e como linha AUSENTE no
    relatório de stderr, nunca como zero, string vazia ou null.

Determinismo: nenhuma data de execução, nenhum uuid sorteado, nenhuma ordem de
`set`. Rodar duas vezes produz os mesmos bytes — e `--autoteste` prova isso.

    python3 scripts/importar_engines_no_cofre.py              # payloads em stdout, relatório em stderr
    python3 scripts/importar_engines_no_cofre.py --autoteste   # asserções internas, sai 0/1
    python3 scripts/importar_engines_no_cofre.py --sql         # SELECT ... por engine, chave derivada

AS TRÊS ORIGENS DE CADA CAMPO — e por que a distinção é o entregável
--------------------------------------------------------------------
  FONTE      o manifesto declara o valor; ele é copiado verbatim.
  DERIVADO   o valor é composto a partir de campos medidos do manifesto
             (números, flags, listas). Nenhuma cláusula sem origem.
  DECLARADO  o Cofre exige a coluna e NENHUM manifesto tem o campo. O valor é
             uma constante deste arquivo, justificada linha a linha, e o
             relatório de stderr o marca como DECLARADO — não como observado.
  AUSENTE    o manifesto não declara e o contrato permite omitir. A chave não
             entra no payload.

A quarta possibilidade — inventar um valor e chamá-lo de observado — é a que
este arquivo existe para tornar impossível.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Endereços — sempre RELATIVOS ao repositório.
# --------------------------------------------------------------------------
# `manifesto_fonte` vai para dentro do payload e o payload vira resposta HTTP.
# Caminho absoluto do operador contém o e-mail dele (veja `sanitizar_caminho`),
# então a procedência é escrita como caminho de repositório e nada mais.
RAIZ = Path(__file__).resolve().parents[1]
MANIFESTO_IMAGEM = "docs/creative-engines/motores-de-imagem.json"
MANIFESTO_VIDEO = "docs/creative-engines/motores-de-video.json"

# Fixos pelo contrato: `cofre_ativo` referencia o PAR (kind, cluster) em
# `cofre_tipo`, e o único par de engine criativo declarado na migration é este.
# Trocar qualquer um dos dois faz a FK composta recusar a linha.
KIND = "creative_engine"
CLUSTER = "creative_production"

# Allowlists espelhadas de `cofre_recusa_campo_desconhecido` (seção 15 da
# migration). Estão aqui para que o autoteste recuse um campo novo ANTES do
# banco — o erro do banco chega tarde e num ambiente onde ninguém está olhando.
CAMPOS_TOPO = (
    "ativo_id", "kind", "cluster", "nome", "plataforma", "estado", "criticidade",
    "resumo", "dono_nome", "dono_custodia", "projeto", "vertical", "display_id",
    "url_publica", "localizacao_rotulo", "capacidades", "tags", "proxima_acao",
    "engine",
)
CAMPOS_ENGINE = (
    "modalidade", "estado_operacional", "versao_contrato", "formatos", "skins",
    "nichos", "vozes", "manifesto_fonte", "manifesto_sha256", "fonte_fingerprint",
    "capacidades_observadas", "limitacoes", "requisitos", "destinos_compativeis",
    "verificado_em",
)

ATIVO_ID_RE = re.compile(r"^[a-z][a-z0-9:_-]{2,179}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CHAVE_IDEMPOTENCIA_RE = re.compile(r"^[A-Za-z0-9._:-]{8,120}$")
DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ESTADOS_ATIVO = ("declared", "verified", "ready", "active", "restricted", "inactive", "retired")
CRITICIDADES = ("low", "medium", "high", "critical")
CUSTODIAS = ("declared", "verified", "unassigned")
MODALIDADES = ("imagem", "video", "audio", "misto")
ESTADOS_OPERACIONAIS = ("catalogado", "externo_parcial", "integrado", "somente_referencia", "aposentado")


# ==========================================================================
# 1. SANITIZAÇÃO DE CAMINHO — a regra que motiva metade deste arquivo
# ==========================================================================
# Os manifestos guardam `canonical_path` absoluto, e o do Drive é literalmente
#   /Users/mac/Library/CloudStorage/GoogleDrive-tarcisio@agenciavolc.com.br/...
# ou seja: o e-mail do operador dentro do caminho. `cofre_ativo.localizacao_rotulo`
# tem COMMENT dizendo que "o caminho absoluto do operador contem o e-mail dele;
# ele nao entra aqui e nao entra em resposta HTTP nenhuma". Esta função é como
# essa frase vira código — e `_sem_vestigio_de_disco` é o que impede que ela
# falhe em silêncio num caminho de formato novo.

_HOME_RE = re.compile(r"^/Users/[^/]+/")

# Rastros que NUNCA podem sobreviver à sanitização. `@` está aqui porque é o que
# distingue um caminho de Drive de um caminho comum: é o e-mail.
_VESTIGIOS = ("/Users/", "CloudStorage", "GoogleDrive", "Drives compartilhados", "@")


def _sem_vestigio_de_disco(texto: str, contexto: str) -> str:
    """Levanta se um rastro de disco/e-mail sobreviveu. Sanitização que falha
    calada é pior do que nenhuma: ela publica o segredo com ar de segurança."""
    for vestigio in _VESTIGIOS:
        if vestigio in texto:
            raise ValueError(
                f"sanitizacao falhou em {contexto}: o resultado ainda contem {vestigio!r}"
            )
    return texto


def sanitizar_caminho(caminho: str) -> tuple[str, str]:
    """Devolve (família, caminho relativo não sensível).

    As três famílias saem dos três formatos MEDIDOS nos manifestos:
      - relativo            -> vive dentro deste repositório (ex.: volc_ads/criativo)
      - .../Drives compartilhados/...  -> Google Drive compartilhado da VOLC
      - /Users/<alguem>/...            -> disco da máquina do operador
    """
    if not caminho.startswith("/"):
        return ("Repositório VOLC O.S.", _sem_vestigio_de_disco(caminho.strip("/"), caminho))

    if "/Drives compartilhados/" in caminho:
        # Corta no /CLIENTES/ quando ele existe: é o ponto a partir do qual o
        # caminho passa a falar de negócio (cliente, ano, projeto) em vez de
        # falar da conta de quem sincronizou a pasta.
        if "/CLIENTES/" in caminho:
            relativo = caminho.split("/CLIENTES/", 1)[1]
        else:
            relativo = caminho.split("/Drives compartilhados/", 1)[1]
        return ("Drive compartilhado VOLC", _sem_vestigio_de_disco(relativo, caminho))

    achado = _HOME_RE.match(caminho)
    relativo = caminho[achado.end():] if achado else caminho.lstrip("/")
    # `Desktop/` não informa nada sobre o ativo; informa sobre a máquina.
    if relativo.startswith("Desktop/"):
        relativo = relativo[len("Desktop/"):]
    return ("Disco local", _sem_vestigio_de_disco(relativo, caminho))


# A família vira tag por MAPA e não por slug automático: `slug("Repositório
# VOLC O.S.")` devolvia `reposit-rio-volc-o-s` — o acento virava hífen e a tag
# ficava ilegível. Três famílias, três tags escritas à mão, zero surpresa.
TAG_DA_FAMILIA = {
    "Repositório VOLC O.S.": "no-repositorio",
    "Drive compartilhado VOLC": "drive-compartilhado",
    "Disco local": "disco-local",
}


def projeto_do_caminho(caminho: str) -> str | None:
    """Projeto/cliente derivado do caminho — e SOMENTE quando o caminho o declara.

    `/.../CLIENTES/IESDE/2026/...` declara IESDE; `/.../Volc Mídia Global/...`
    não declara cliente nenhum, e aí a resposta é ausência, não 'VOLC'.
    """
    for marcador in ("/CLIENTES/", "/SISTEMAS/"):
        if marcador in caminho:
            resto = caminho.split(marcador, 1)[1]
            candidato = resto.split("/", 1)[0].strip()
            if candidato:
                return _sem_vestigio_de_disco(candidato, caminho)
    return None


# ==========================================================================
# 2. CURADORIA DECLARADA — o que o Cofre exige e nenhum manifesto tem
# ==========================================================================
# `cofre_ativo` tem NOT NULL em plataforma, estado, criticidade, dono_nome e
# dono_custodia. NENHUM dos dois manifestos declara qualquer um desses cinco
# campos. Há duas saídas honestas: (a) não importar, ou (b) declarar o valor
# aqui, com justificativa, e marcá-lo como DECLARADO no relatório. Escolhi (b)
# porque (a) apenas transfere a invenção para quem digitar à mão depois.
#
# Cada entrada abaixo é uma AFIRMAÇÃO DO IMPORTADOR, não uma observação. O
# relatório de stderr diz isso em voz alta, campo por campo.
CURADORIA: dict[str, dict[str, str]] = {
    "volc_os_creative_port": {
        # plataforma: o próprio manifesto dá `canonical_path: volc_ads/criativo`,
        # um caminho DENTRO deste repositório — é o único engine assim.
        "plataforma": "VOLC O.S. · volc_ads/criativo",
        # estado: `verified` porque há prova executável citada no manifesto
        # (tests_observed=80). Não é `active`: nada em produção o chama.
        "estado": "verified",
        # criticidade: `high` — é a porta pela qual TODOS os outros engines
        # entrarão; um defeito aqui contamina os seis.
        "criticidade": "high",
        # modalidade: `misto`. O manifesto de imagem declara
        # `funnelforge_image_adapter` (imagem) e o de vídeo declara
        # `integration.port = volc_ads.criativo.MotorDeCriativo` com
        # `media_kind: VIDEO`. A porta atravessa as duas modalidades.
        "modalidade": "misto",
        # estado_operacional: `catalogado`, e NÃO `integrado`. O código vive no
        # repo e tem 80 testes, mas `integration_state.registered_in_volc_os_runtime`
        # é false e os três adapters (aprova/positivo/prensa) estão como false.
        # `integrado` exigiria adapter + job + prova; nenhum existe.
        # `externo_parcial` também estaria errado: o runtime dele NÃO roda fora.
        "estado_operacional": "catalogado",
    },
    "aprova_ad_studio_official": {
        # plataforma: composta do `stack` declarado, e só dele.
        "plataforma": "Vite · React · FastAPI · Python · SSE",
        # estado: `verified` — `validation.tests_observed` lista quatro suítes e
        # o git head foi observado.
        "estado": "verified",
        "criticidade": "high",
        "modalidade": "imagem",
        # estado_operacional: `externo_parcial` — `maturity` do próprio manifesto
        # é `external_working_product_not_integrated`: roda FORA do VOLC O.S. e
        # não foi provado integralmente daqui.
        "estado_operacional": "externo_parcial",
    },
    "aprova_ad_studio_desktop_divergent": {
        # plataforma: o manifesto não declara stack; declara que esta cópia não
        # tem backend canônico observado. É isso que a plataforma diz.
        "plataforma": "Cópia divergente sem backend canônico observado",
        # estado: `inactive`, não `retired`. `disposition` manda PRESERVAR como
        # fonte de ideias de intake — aposentar apagaria a instrução.
        "estado": "inactive",
        # criticidade: `low` — `authority: false`. Nada deve depender dela.
        "criticidade": "low",
        "modalidade": "imagem",
        # estado_operacional: `somente_referencia` — é a tradução exata de
        # `maturity: reference_only` + `authority: false` + a `disposition`.
        "estado_operacional": "somente_referencia",
    },
    "positivo_ad_studio": {
        "plataforma": "Vite · React · FastAPI · Python · Pillow · SSE",
        # estado: `verified` — sete suítes em `validation.tests_observed`.
        "estado": "verified",
        "criticidade": "high",
        "modalidade": "imagem",
        # estado_operacional: mesmo motivo do Aprova — `maturity` é
        # `external_working_product_not_integrated`.
        "estado_operacional": "externo_parcial",
    },
    "volc_motor_imagem": {
        # plataforma: o manifesto não declara stack; declara `kind`.
        "plataforma": "Parque de engenharia e contrato (kind: engineering_park_and_contract)",
        # estado: `verified` — o snapshot hasheado é a prova (856 arquivos
        # varridos, 443 fontes hasheadas, fingerprint sha256 declarado).
        "estado": "verified",
        "criticidade": "high",
        "modalidade": "imagem",
        # estado_operacional: `externo_parcial`. Roda fora (Disco local), tem 64
        # renders executados, e `maturity` é `validated_components_not_integrated`.
        "estado_operacional": "externo_parcial",
    },
    "prensa": {
        "plataforma": "Renderizador determinístico e pipeline de qualidade (kind: deterministic_renderer_and_quality_pipeline)",
        # estado: `verified` — `executed_inventory` traz 64 renders, 47 aprovados
        # no gate de pixel e 65 vereditos DOM ok.
        "estado": "verified",
        "criticidade": "high",
        "modalidade": "imagem",
        # estado_operacional: `externo_parcial`. `maturity: poc_proven_library_not_productized`
        # e `integration_state.prensa_adapter_implemented: false`.
        "estado_operacional": "externo_parcial",
    },
    "motor-video-volc": {
        # plataforma: o manifesto de vídeo não tem `stack` nem `kind`; declara
        # `integration.media_kind: VIDEO` e uma fábrica externa de execução.
        "plataforma": "Fábrica de vídeo externa (integration.media_kind: VIDEO)",
        # estado: `verified` — 38 MP4 finais observados, 20 com QA técnico.
        "estado": "verified",
        "criticidade": "high",
        "modalidade": "video",
        # estado_operacional: `externo_parcial` é tradução DIRETA do campo
        # `state: "external_partial"` do manifesto. Não é escolha minha.
        "estado_operacional": "externo_parcial",
    },
}

# dono_nome / dono_custodia: idênticos para os sete, e por isso ficam fora da
# tabela acima — repeti-los sete vezes esconderia que são a MESMA declaração.
#
# `dono_custodia = 'declared'` e não 'verified': `verified` significaria que
# alguém comprovou a custódia, e nenhum dos dois manifestos tem campo de dono,
# de custódia ou de prova de custódia. Marcar 'verified' aqui seria exatamente
# o tipo de confiança inventada que a seção A da migration existe para impedir.
DONO_NOME = "VOLC"
DONO_CUSTODIA = "declared"


# ==========================================================================
# 3. EVIDÊNCIA NUMÉRICA — preservar o número com o NOME que ele tem na fonte
# ==========================================================================
# `cofre_engine_perfil` só tem quatro colunas de contagem: formatos, skins,
# nichos e vozes. O manifesto de vídeo declara exatamente esses quatro nomes; o
# de imagem não declara NENHUM deles — declara `ui_presets_observed`,
# `backend_ratio_mappings_observed`, `rendered_outputs`, `pixel_gate_passed`…
#
# Chamar `backend_ratio_mappings_observed=12` de "12 formatos" seria inventar
# semântica. Perder o 12 seria perder patrimônio. A saída é preservá-lo em
# `capacidades_observadas` como token `campo=valor`, com o nome original.

# Sub-objetos varridos, na ordem em que a varredura acontece (determinismo).
PREFIXOS_EVIDENCIA = (
    "git", "inventory_snapshot", "executed_inventory", "format_strategy",
    "validation", "observed_evidence", "hook_modes",
)
# Escalares de topo que são evidência, não capacidade.
TOPO_ESCALAR = ("tests_observed", "observed_aspect_ratio_count")
# Listas de topo cujo TAMANHO é a evidência (os itens já viajam em outro campo).
TOPO_LISTA_CONTAGEM = ("observed_aspect_ratios", "components", "specialized_components")
# Já viaja em `fonte_fingerprint`; repeti-lo como capacidade seria ruído.
EVIDENCIA_IGNORADA = ("source_fingerprint_sha256",)

# Prosa não é evidência: um `native_generation` de duas linhas dentro de uma
# lista de capacidades vira lixo na tela. Só passam escalares curtos e sem
# espaço — hashes, contagens, enums, resoluções como 1080x1920.
_TOKEN_ESCALAR_RE = re.compile(r"^[A-Za-z0-9_.:x-]{1,64}$")


def _formatar_escalar(valor) -> str | None:
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        return repr(valor)
    if isinstance(valor, str) and _TOKEN_ESCALAR_RE.match(valor):
        return valor
    return None


def tokens_de_evidencia(engine: dict) -> list[str]:
    tokens: list[str] = []
    for prefixo in PREFIXOS_EVIDENCIA:
        sub = engine.get(prefixo)
        if not isinstance(sub, dict):
            continue  # ausente, ou null (o `git` do Motor de Imagem VOLC é null)
        for chave, valor in sub.items():
            if chave in EVIDENCIA_IGNORADA:
                continue
            if isinstance(valor, list) and all(not isinstance(i, (dict, list)) for i in valor):
                tokens.append(f"{prefixo}.{chave}_count={len(valor)}")
                continue
            escalar = _formatar_escalar(valor)
            if escalar is not None:
                tokens.append(f"{prefixo}.{chave}={escalar}")
    for chave in TOPO_ESCALAR:
        if chave in engine:
            escalar = _formatar_escalar(engine[chave])
            if escalar is not None:
                tokens.append(f"{chave}={escalar}")
    for chave in TOPO_LISTA_CONTAGEM:
        valor = engine.get(chave)
        if isinstance(valor, list):
            tokens.append(f"{chave}_count={len(valor)}")
    for tipo in engine.get("content_types", []) or []:
        tokens.append(f"content_type:{tipo}")
    return tokens


# ==========================================================================
# 4. FRASES DERIVADAS — resumo e proxima_acao, compostas só de fatos da fonte
# ==========================================================================
# `resumo` (10..800) e `proxima_acao` (10..800) são NOT NULL. Não dá para omitir
# e não dá para inventar. A saída é compor a frase interpolando SOMENTE valores
# que existem no manifesto — cada cláusula abaixo cita o campo de onde saiu.

def _primeira_maiuscula(frase: str) -> str:
    """`str.capitalize()` está PROIBIDO aqui, e o motivo foi medido: ele
    maiusculiza a primeira letra e MINUSCULIZA o resto — "38 MP4 finais … QA
    técnico" virava "38 mp4 finais … qa técnico". Corromper a grafia de um fato
    para arrumar a primeira letra é perder o fato."""
    return frase[:1].upper() + frase[1:]


# A evidência de execução de cada engine, em uma frase, feita dos números dele.
# A chave é o id do engine; o valor é uma função do dicionário do engine, para
# que o número NUNCA seja digitado à mão (digitar é onde a transcrição erra).
def _evidencia_em_frase(eid: str, e: dict) -> str:
    if eid == "volc_os_creative_port":
        return f"{e['tests_observed']} testes observados no pacote"
    if eid == "aprova_ad_studio_official":
        v = e["validation"]
        return (f"validação {v['level']} com {len(v['tests_observed'])} suítes observadas e "
                f"{len(e['observed_aspect_ratios'])} proporções observadas")
    if eid == "aprova_ad_studio_desktop_divergent":
        # Ausência de evidência dita como ausência: o manifesto não traz git,
        # nem validation, nem snapshot para esta cópia.
        return "sem git, validação ou snapshot observados nesta cópia"
    if eid == "positivo_ad_studio":
        v = e["validation"]
        return (f"validação {v['level']} com {len(v['tests_observed'])} suítes observadas e "
                f"{e['observed_aspect_ratio_count']} proporções observadas")
    if eid == "volc_motor_imagem":
        s = e["inventory_snapshot"]
        return (f"snapshot hasheado de {s['extracted_at']}: {s['files_scanned']} arquivos varridos, "
                f"{s['source_files_hashed']} fontes hasheadas, {s['specs']} specs, {s['skins']} skins, "
                f"{s['rendered_outputs']} renders")
    if eid == "prensa":
        x = e["executed_inventory"]
        return (f"{x['rendered_outputs']} renders executados, {x['pixel_gate_passed']} aprovados no gate "
                f"de pixel e {x['dom_verdict_ok']} vereditos DOM ok")
    if eid == "motor-video-volc":
        o = e["observed_evidence"]
        return (f"{o['final_mp4']} MP4 finais em {o['resolution']}, {o['technical_qa']} com QA técnico, "
                f"{o['visual_qa']} com QA visual e {o['publication_snapshots']} snapshots de publicação")
    raise KeyError(f"engine sem frase de evidência: {eid}")


# `proxima_acao` sai das LACUNAS declaradas — flags false de `integration_state`
# (imagem) e campos "todo" de `integration` (vídeo). Nenhuma delas é opinião.
def _proxima_acao(eid: str, e: dict, integracao: dict) -> str:
    if eid == "volc_os_creative_port":
        faltando = [k for k, v in integracao.items() if v is False]
        return ("Fechar as lacunas que o próprio manifesto marca como false em integration_state: "
                + ", ".join(faltando) + ".")
    if eid == "aprova_ad_studio_official":
        return ("Escrever o adapter e o envelope de CreativeJob: integration_state."
                "aprova_adapter_implemented=false e o manifesto marca not_registered_as_volc_os_service.")
    if eid == "aprova_ad_studio_desktop_divergent":
        return ("Preservar como fonte de ideias de intake e nunca como autoridade de engine — é a "
                "disposition declarada no manifesto, com authority=false.")
    if eid == "positivo_ad_studio":
        return ("Escrever o adapter e a governança de foto: integration_state."
                "positivo_adapter_implemented=false e o manifesto marca not_registered_as_volc_os_service.")
    if eid == "volc_motor_imagem":
        return ("Confirmar requisitos de plataforma contra a documentação oficial antes de extrair: o "
                "manifesto marca platform_requirements_need_current_official_verification e "
                "some_contracts_exist_without_materialized_png.")
    if eid == "prensa":
        return ("Empacotar a biblioteca atrás de um adapter: o manifesto marca library_cli_not_http_gateway, "
                "browser_per_call e no_batch_api, e integration_state.prensa_adapter_implemented=false.")
    if eid == "motor-video-volc":
        i = e["integration"]
        return (f"Implementar adapter e runtime: integration.adapter={i['adapter']} e "
                f"integration.runtime={i['runtime']}; o manifesto ainda registra "
                f"'nenhuma prova integral a partir da raiz organizada'.")
    raise KeyError(f"engine sem próxima ação: {eid}")


# ==========================================================================
# 5. MONTAGEM
# ==========================================================================

def sha256_arquivo(caminho_relativo: str) -> str:
    """sha256 do ARQUIVO de manifesto — a procedência da linha.

    É do arquivo, e não do sub-objeto do engine, porque é o arquivo que está
    versionado no git: é ele que alguém consegue conferir depois.
    """
    dados = (RAIZ / caminho_relativo).read_bytes()
    return hashlib.sha256(dados).hexdigest()


def _lista_texto(valores) -> list[str]:
    """Lista de texto sem elemento vazio — `cofre_lista_util` recusa branco."""
    return [str(v).strip() for v in (valores or []) if str(v).strip()]


def _slug(texto: str) -> str:
    bruto = re.sub(r"[^a-z0-9]+", "-", texto.strip().lower())
    return re.sub(r"-{2,}", "-", bruto).strip("-")


class Relatorio:
    """Acumula, por engine, a origem de CADA campo. Rule 10: ausência explícita
    é entregável — então ela ocupa uma linha, com o motivo, e não some."""

    def __init__(self) -> None:
        self.blocos: list[tuple[str, str, str, str, list[tuple[str, str, str]]]] = []

    def abrir(self, ativo_id: str, nome: str, fonte: str, sha: str) -> list:
        linhas: list[tuple[str, str, str]] = []
        self.blocos.append((ativo_id, nome, fonte, sha, linhas))
        return linhas

    def escrever(self, saida) -> None:
        for ativo_id, nome, fonte, sha, linhas in self.blocos:
            saida.write("=" * 100 + "\n")
            saida.write(f"{ativo_id}  ·  {nome}\n")
            saida.write(f"fonte: {fonte}  sha256 {sha}\n")
            saida.write("-" * 100 + "\n")
            # 32/16 medidos no maior rótulo real: `engine.capacidades_observadas`
            # (29) e `FONTE+DERIVADO` (14). Com 24/12 as colunas colavam.
            saida.write(f"{'campo':<32}{'origem':<16}detalhe\n")
            for campo, origem, detalhe in linhas:
                saida.write(f"{campo:<32}{origem:<16}{detalhe}\n")
            ausentes = [c for c, o, _ in linhas if o == "AUSENTE"]
            declarados = [c for c, o, _ in linhas if o == "DECLARADO"]
            saida.write("-" * 100 + "\n")
            saida.write(f"AUSENTES ({len(ausentes)}): {', '.join(ausentes) if ausentes else '—'}\n")
            saida.write(f"DECLARADOS pelo importador ({len(declarados)}): "
                        f"{', '.join(declarados) if declarados else '—'}\n\n")


def _bloco_engine(
    eid: str,
    e: dict,
    *,
    fonte: str,
    sha: str,
    updated_at: str,
    integracao: dict,
    linhas: list,
) -> dict:
    """Monta o sub-objeto `engine` do payload. Chave ausente = chave OMITIDA."""
    curado = CURADORIA[eid]
    engine: dict = {
        "modalidade": curado["modalidade"],
        "estado_operacional": curado["estado_operacional"],
    }
    linhas.append(("engine.modalidade", "DECLARADO", curado["modalidade"] + " — nenhum manifesto declara modalidade"))
    linhas.append(("engine.estado_operacional", "DECLARADO" if eid != "motor-video-volc" else "FONTE",
                   curado["estado_operacional"] + (
                       " — tradução direta de state=external_partial" if eid == "motor-video-volc"
                       else " — 'integrado' exigiria adapter, job e prova; nenhum engine os tem")))

    # versao_contrato: só o manifesto de vídeo declara.
    if e.get("contract_version"):
        engine["versao_contrato"] = e["contract_version"]
        linhas.append(("engine.versao_contrato", "FONTE", f"contract_version={e['contract_version']}"))
    else:
        linhas.append(("engine.versao_contrato", "AUSENTE", "o manifesto não declara versão de contrato"))

    # AS QUATRO CONTAGENS. Só entram quando algum manifesto declara o número COM
    # ESSE NOME, e o relatório sempre diz de qual caminho ele veio.
    # Zero não existe aqui: o CHECK do banco é `> 0`, e um manifesto que não
    # declara formato não observou zero formatos — não observou nada.
    for destino, caminhos, quase_chaves in (
        # `formats` só existe no manifesto de vídeo.
        ("formatos", ("formats",), ("presets", "ratio", "aspect")),
        # `skins` existe no topo do vídeo E dentro do snapshot do Motor de
        # Imagem VOLC (`inventory_snapshot.skins: 7`). São a mesma grandeza com
        # o mesmo nome, contada de duas formas; perder a segunda seria perder
        # patrimônio por causa da profundidade da chave.
        ("skins", ("skins", "inventory_snapshot.skins"), ("skins",)),
        ("nichos", ("niches",), ("niche",)),
        ("vozes", ("voices",), ("voice",)),
    ):
        origem_usada, valor = None, None
        for caminho_chave in caminhos:
            alvo = e
            for parte in caminho_chave.split("."):
                alvo = alvo.get(parte) if isinstance(alvo, dict) else None
            if isinstance(alvo, int) and not isinstance(alvo, bool) and alvo > 0:
                origem_usada, valor = caminho_chave, alvo
                break
        if origem_usada:
            engine[destino] = valor
            linhas.append((f"engine.{destino}", "FONTE", f"{origem_usada}={valor}"))
        else:
            # A quase-coincidência é dita em voz alta para que ninguém conclua
            # que o número se perdeu: ele existe, com OUTRO nome, e por isso não
            # ocupa esta coluna.
            quase = [t for t in tokens_de_evidencia(e) if any(q in t for q in quase_chaves)]
            detalhe = "nenhum manifesto declara " + " nem ".join(f"'{c}'" for c in caminhos)
            if quase:
                detalhe += f"; declara com OUTRO nome: {', '.join(quase)}"
            linhas.append((f"engine.{destino}", "AUSENTE", detalhe))

    engine["manifesto_fonte"] = fonte
    engine["manifesto_sha256"] = sha
    linhas.append(("engine.manifesto_fonte", "FONTE", fonte))
    linhas.append(("engine.manifesto_sha256", "DERIVADO", f"sha256 do arquivo: {sha}"))

    impressao = (e.get("inventory_snapshot") or {}).get("source_fingerprint_sha256")
    if impressao:
        engine["fonte_fingerprint"] = impressao
        linhas.append(("engine.fonte_fingerprint", "FONTE", f"inventory_snapshot.source_fingerprint_sha256={impressao}"))
    else:
        linhas.append(("engine.fonte_fingerprint", "AUSENTE", "o manifesto não declara fingerprint da fonte"))

    capacidades = _lista_texto(e.get("capabilities") or e.get("strengths"))
    evidencias = _lista_texto(tokens_de_evidencia(e))
    engine["capacidades_observadas"] = capacidades + evidencias
    linhas.append(("engine.capacidades_observadas", "FONTE+DERIVADO",
                   f"{len(capacidades)} de capabilities/strengths + {len(evidencias)} tokens campo=valor"))

    limitacoes = _lista_texto(e.get("limitations") or e.get("limits"))
    engine["limitacoes"] = limitacoes
    if limitacoes:
        linhas.append(("engine.limitacoes", "FONTE", f"{len(limitacoes)} itens de limitations/limits"))
    else:
        linhas.append(("engine.limitacoes", "AUSENTE", "o manifesto não declara limitações (lista vazia)"))

    # requisitos: o que o manifesto declara como necessário para RODAR.
    requisitos = [f"stack:{s}" for s in _lista_texto(e.get("stack"))]
    requisitos += [f"provider:{p}" for p in _lista_texto(e.get("providers"))]
    integracao_engine = e.get("integration") or {}
    if integracao_engine.get("human_approval_required") is True:
        requisitos.append("aprovacao_humana_obrigatoria")
    if integracao_engine.get("browser_secrets") is False:
        requisitos.append("segredo_nunca_no_navegador")
    engine["requisitos"] = requisitos
    if requisitos:
        linhas.append(("engine.requisitos", "FONTE", f"{len(requisitos)} de stack/providers/integration"))
    else:
        linhas.append(("engine.requisitos", "AUSENTE",
                       "o manifesto não declara stack, providers nem integration para este engine"))

    destinos = _lista_texto(e.get("documented_destinations"))
    engine["destinos_compativeis"] = destinos
    if destinos:
        linhas.append(("engine.destinos_compativeis", "FONTE",
                       f"{len(destinos)} de documented_destinations — DOCUMENTADOS, não provados"))
    else:
        linhas.append(("engine.destinos_compativeis", "AUSENTE",
                       "o manifesto não declara destinos; PACOTE-REUSO fala em later_destinations, "
                       "que é plano e não compatibilidade"))

    engine["verificado_em"] = updated_at
    linhas.append(("engine.verificado_em", "FONTE", f"updated_at do manifesto = {updated_at}"))
    return engine


def montar_payloads() -> tuple[list[dict], Relatorio]:
    imagem = json.loads((RAIZ / MANIFESTO_IMAGEM).read_text(encoding="utf-8"))
    video = json.loads((RAIZ / MANIFESTO_VIDEO).read_text(encoding="utf-8"))
    sha_imagem = sha256_arquivo(MANIFESTO_IMAGEM)
    sha_video = sha256_arquivo(MANIFESTO_VIDEO)
    integracao_imagem = imagem.get("integration_state", {})

    lotes = (
        [(e, MANIFESTO_IMAGEM, sha_imagem, imagem["updated_at"], integracao_imagem) for e in imagem["engines"]]
        + [(e, MANIFESTO_VIDEO, sha_video, video["updated_at"], {}) for e in video["engines"]]
    )

    relatorio = Relatorio()
    payloads: list[dict] = []

    for e, fonte, sha, updated_at, integracao in lotes:
        eid = e["id"]
        if eid not in CURADORIA:
            # Falhar alto. Um engine novo no manifesto sem curadoria seria
            # importado com campos inventados — exatamente o que não pode.
            raise KeyError(
                f"engine '{eid}' existe em {fonte} e não tem entrada em CURADORIA; "
                "declare plataforma, estado, criticidade, modalidade e estado_operacional com justificativa"
            )
        curado = CURADORIA[eid]
        nome = e.get("label") or e["name"]
        ativo_id = f"asset:engine:{_slug(eid)}"
        linhas = relatorio.abrir(ativo_id, nome, fonte, sha)

        linhas.append(("ativo_id", "DERIVADO", f"asset:engine:<slug(id)> a partir de id={eid}"))
        linhas.append(("kind / cluster", "DECLARADO", f"{KIND} / {CLUSTER} — o par declarado em cofre_tipo"))
        linhas.append(("nome", "FONTE", f"{'label' if e.get('label') else 'name'}={nome}"))
        linhas.append(("plataforma", "DECLARADO", curado["plataforma"]))
        linhas.append(("estado", "DECLARADO", f"{curado['estado']} — ver justificativa em CURADORIA"))
        linhas.append(("criticidade", "DECLARADO", curado["criticidade"]))
        linhas.append(("dono_nome / dono_custodia", "DECLARADO",
                       f"{DONO_NOME} / {DONO_CUSTODIA} — nenhum manifesto tem campo de dono ou custódia"))

        # O nome do port termina em "O.S." — concatenar "." cegamente produzia
        # "VOLC O.S..". A frase se fecha uma vez só.
        resumo_partes = [nome if nome.endswith(".") else nome + "."]
        # `maturity` só existe no manifesto de imagem; `state` só no de vídeo.
        # O ponto-e-vírgula só cabe quando há uma segunda cláusula depois dele.
        classificacao = []
        if e.get("kind"):
            classificacao.append(f"tipo declarado: {e['kind']}")
        if e.get("state"):
            classificacao.append(f"estado declarado: {e['state']}")
        if e.get("maturity"):
            classificacao.append(f"maturidade: {e['maturity']}")
        if classificacao:
            resumo_partes.append(_primeira_maiuscula("; ".join(classificacao)) + ".")
        resumo_partes.append(_primeira_maiuscula(_evidencia_em_frase(eid, e)) + ".")
        if integracao:
            resumo_partes.append(
                "Não registrado no runtime do VOLC O.S. "
                f"(integration_state.registered_in_volc_os_runtime={str(integracao.get('registered_in_volc_os_runtime')).lower()}).")
        elif e.get("integration"):
            # O manifesto de vídeo não tem `integration_state`; a mesma lacuna é
            # declarada nele como `adapter`/`runtime` = "todo". Omitir a frase
            # faria o vídeo parecer o único engine sem ressalva de integração.
            i = e["integration"]
            resumo_partes.append(
                f"Sem adapter e sem runtime no VOLC O.S. (integration.adapter={i['adapter']}, "
                f"integration.runtime={i['runtime']}).")
        resumo = " ".join(resumo_partes)
        linhas.append(("resumo", "DERIVADO", f"{len(resumo)} chars compostos de label/kind/maturity/evidência"))

        proxima_acao = _proxima_acao(eid, e, integracao)
        linhas.append(("proxima_acao", "DERIVADO", f"{len(proxima_acao)} chars compostos das lacunas declaradas"))

        caminho = e.get("canonical_path") or e["organized_root"]
        familia, relativo = sanitizar_caminho(caminho)
        rotulo = f"{familia} · {relativo}"
        if e.get("poc_path"):
            rotulo += f" (POC em {sanitizar_caminho(e['poc_path'])[1]})"
        if e.get("execution_root"):
            rotulo += f" (execução em {sanitizar_caminho(e['execution_root'])[1]})"
        linhas.append(("localizacao_rotulo", "DERIVADO",
                       f"{rotulo}  ← sanitizado de canonical_path/organized_root"))

        capacidades = _lista_texto(e.get("capabilities") or e.get("strengths"))
        if not capacidades:
            raise ValueError(f"engine {eid} sem capabilities/strengths; cofre_ativo exige 1..40 capacidades")
        linhas.append(("capacidades", "FONTE", f"{len(capacidades)} itens de "
                       f"{'capabilities' if e.get('capabilities') else 'strengths'}"))

        tags = [curado["modalidade"], "creative-engine", TAG_DA_FAMILIA[familia]]
        if "authority" in e:
            tags.append("autoridade" if e["authority"] else "sem-autoridade")
            linhas.append(("tags", "DERIVADO", ", ".join(tags) + "  ← modalidade + família de local + authority"))
        else:
            linhas.append(("tags", "DERIVADO", ", ".join(tags)
                           + "  ← modalidade + família de local (o manifesto de vídeo não declara authority)"))

        payload: dict = {
            "ativo_id": ativo_id,
            "kind": KIND,
            "cluster": CLUSTER,
            "nome": nome,
            "plataforma": curado["plataforma"],
            "estado": curado["estado"],
            "criticidade": curado["criticidade"],
            "resumo": resumo,
            "dono_nome": DONO_NOME,
            "dono_custodia": DONO_CUSTODIA,
        }

        projeto = projeto_do_caminho(caminho)
        if projeto:
            payload["projeto"] = projeto
            linhas.append(("projeto", "DERIVADO", f"{projeto}  ← segmento após /CLIENTES/ ou /SISTEMAS/ no caminho"))
        else:
            linhas.append(("projeto", "AUSENTE", "o caminho do manifesto não nomeia cliente ou projeto"))

        # vertical e display_id: nenhum manifesto tem o conceito. Omitidos.
        linhas.append(("vertical", "AUSENTE", "nenhum manifesto declara vertical"))
        linhas.append(("display_id", "AUSENTE", "engine não tem identificador de plataforma para exibir"))

        # ⚠️ BLOQUEIO MEDIDO EM 01/09/2026, e o único engine que esbarra nele é
        # este: `cofre_ativo_url_http` (v13_01, linha 432) usa
        # `~* '^https?://[^[:space:]]{3,2000}$'`, e o limite de contagem de
        # repetição do regex do Postgres é 255 — `{3,2000}` levanta
        # `invalid regular expression: invalid repetition count(s)` em QUALQUER
        # `url_publica` não nula. Medido num postgres:15.19 descartável: com
        # `{3,255}` a mesma URL passa; com `{3,256}` já levanta.
        #
        # A CHECK curto-circuita em NULL, então a migration aplica, o harness
        # `provar-ciclo-v13_01.sh` passa (ele nunca insere `url_publica`) e o
        # defeito só aparece no primeiro ativo com endereço público — que neste
        # importador é o Aprova, e no Cofre inteiro seria todo site e toda
        # página. O importador NÃO contorna: emitir o campo é o que torna o
        # defeito visível. Enquanto a migration não corrigir o limite, o
        # `--sql` deste engine falha, e falhar alto é o comportamento correto.
        remoto = (e.get("git") or {}).get("remote_observed")
        if remoto and remoto.startswith(("http://", "https://")):
            payload["url_publica"] = remoto
            linhas.append(("url_publica", "FONTE", f"git.remote_observed={remoto}"))
        else:
            linhas.append(("url_publica", "AUSENTE", "o manifesto não declara remote https observado"))

        payload["localizacao_rotulo"] = rotulo
        payload["capacidades"] = capacidades
        payload["tags"] = tags
        payload["proxima_acao"] = proxima_acao
        payload["engine"] = _bloco_engine(
            eid, e, fonte=fonte, sha=sha, updated_at=updated_at,
            integracao=integracao, linhas=linhas,
        )
        payloads.append(payload)

    return payloads, relatorio


def chave_de_idempotencia(payload: dict) -> str:
    """Chave DERIVADA do conteúdo, não sorteada.

    Rodar o importador duas vezes com o mesmo manifesto produz a mesma chave, e
    `cofre_idempotencia` devolve o recibo guardado em vez de duplicar o ativo.
    Se o manifesto mudar, o sha256 muda, a chave muda — e o replay não mascara
    uma importação diferente com o recibo da anterior.
    """
    engine = payload["engine"]
    slug = payload["ativo_id"].split(":")[-1]
    chave = f"engine-import.{slug}.{engine['manifesto_sha256'][:12]}"
    if not CHAVE_IDEMPOTENCIA_RE.match(chave):
        raise ValueError(f"chave de idempotência fora da forma exigida por cofre_operacao: {chave}")
    return chave


def motivo_da_revisao(payload: dict) -> str:
    e = payload["engine"]
    return (f"importacao determinista de {e['manifesto_fonte']} "
            f"(sha256 {e['manifesto_sha256'][:12]}) por scripts/importar_engines_no_cofre.py")


def emitir_json(payloads: list[dict]) -> str:
    # `ensure_ascii=False` preserva os acentos como acento; `indent=2` e a ordem
    # de inserção fazem o diff entre duas execuções ser vazio, não reordenado.
    return json.dumps(payloads, ensure_ascii=False, indent=2) + "\n"


def emitir_sql(payloads: list[dict]) -> str:
    linhas = [
        "-- Gerado por scripts/importar_engines_no_cofre.py — NAO EDITAR A MAO.",
        "-- Autor e e-mail chegam por psql -v; nenhum dos dois e escrito neste arquivo,",
        "-- porque identidade de operador nao pertence a um artefato versionado.",
        "--   psql -v autor_sub=<uuid> -v autor_email=<email> -f <este arquivo>",
        "",
    ]
    for payload in payloads:
        corpo = json.dumps(payload, ensure_ascii=False, indent=2)
        if "$cofre$" in corpo or "$motivo$" in corpo:
            raise ValueError("o payload contem a tag de dollar-quoting; o SQL sairia quebrado")
        linhas.append(f"-- {payload['ativo_id']} · {payload['nome']}")
        linhas.append("SELECT public.cofre_cadastrar_ativo(")
        linhas.append(f"  $cofre${corpo}$cofre$::jsonb,")
        linhas.append(f"  '{chave_de_idempotencia(payload)}',")
        linhas.append("  :'autor_sub'::uuid,")
        linhas.append("  :'autor_email',")
        linhas.append(f"  $motivo${motivo_da_revisao(payload)}$motivo$")
        linhas.append(");")
        linhas.append("")
    return "\n".join(linhas)


# ==========================================================================
# 6. AUTOTESTE — as asserções que o banco faria, feitas antes de chegar nele
# ==========================================================================
# Espelhos das CHECKs da migration. Espelho não é a fonte: se a migration mudar,
# isto tem de mudar junto. O ganho é que a recusa acontece aqui, com mensagem
# que cita o campo, em vez de num INSERT remoto às 3h da manhã.

# `cofre_chave_sensivel` (seção 11), verbatim.
_BLOCKLIST = (
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
)
# `cofre_sem_material_de_credencial` (seção 11), verbatim.
_MATERIAL_CREDENCIAL = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bop://[A-Za-z0-9._%~-]+/[A-Za-z0-9._%~-]+/"),
    re.compile(r"\b(sk|pk|ghp|gho|xox[baprs])[-_][A-Za-z0-9]{16,}"),
)


def _normalizar_chave(chave: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", chave).lower()


def _percorrer_chaves(doc, caminho="payload"):
    if isinstance(doc, dict):
        for k, v in doc.items():
            yield (f"{caminho}.{k}", k)
            yield from _percorrer_chaves(v, f"{caminho}.{k}")
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            yield from _percorrer_chaves(v, f"{caminho}[{i}]")


def autoteste() -> int:
    falhas: list[str] = []
    ok: list[str] = []

    def checar(nome: str, condicao: bool, detalhe: str = "") -> None:
        (ok if condicao else falhas).append(f"{nome}{(' — ' + detalhe) if detalhe else ''}")

    # -- 1. sanitização: os quatro formatos MEDIDOS nos manifestos ------------
    casos = [
        ("/Users/mac/Library/CloudStorage/GoogleDrive-tarcisio@agenciavolc.com.br/Drives compartilhados/"
         "VOLC/VOLC/CLIENTES/IESDE/2026/Aprova-Ad-Sstudio",
         ("Drive compartilhado VOLC", "IESDE/2026/Aprova-Ad-Sstudio")),
        ("/Users/mac/Desktop/SISTEMAS/IESDE/Aprova-Ad-Sstudio",
         ("Disco local", "SISTEMAS/IESDE/Aprova-Ad-Sstudio")),
        ("/Users/mac/Desktop/Volc Mídia Global/motor-imagem",
         ("Disco local", "Volc Mídia Global/motor-imagem")),
        ("/Users/mac/volc-factory", ("Disco local", "volc-factory")),
        ("volc_ads/criativo", ("Repositório VOLC O.S.", "volc_ads/criativo")),
    ]
    for entrada, esperado in casos:
        obtido = sanitizar_caminho(entrada)
        checar("sanitizar_caminho", obtido == esperado, f"{entrada[:44]}… -> {obtido}")

    # A sanitização tem de FALHAR ALTO, não devolver silenciosamente sujo.
    try:
        _sem_vestigio_de_disco("/Users/mac/x", "teste")
        checar("sanitizacao levanta em vestigio", False, "não levantou")
    except ValueError:
        checar("sanitizacao levanta em vestigio", True)

    payloads, _ = montar_payloads()
    texto = emitir_json(payloads)

    # -- 2. determinismo ------------------------------------------------------
    segundo, _ = montar_payloads()
    checar("determinismo do JSON", emitir_json(segundo) == texto)
    checar("determinismo do SQL", emitir_sql(segundo) == emitir_sql(payloads))

    # -- 3. nada de disco, e-mail ou Drive no output --------------------------
    for vestigio in _VESTIGIOS:
        checar(f"output sem {vestigio!r}", vestigio not in texto)

    # -- 4. cobertura: sete engines, nenhum perdido ---------------------------
    checar("sete engines importados", len(payloads) == 7, f"{len(payloads)}")
    ids = [p["ativo_id"] for p in payloads]
    checar("ativo_id unico", len(set(ids)) == len(ids))
    chaves = [chave_de_idempotencia(p) for p in payloads]
    checar("chave de idempotencia unica", len(set(chaves)) == len(chaves))

    # -- 4b. REGRESSÕES de defeitos que EU cometi e medi nesta missão --------
    por_id = {p["ativo_id"]: p for p in payloads}
    # `str.capitalize()` minusculizava o resto da frase: "38 MP4" virava "38 mp4",
    # "QA técnico" virava "qa técnico", "vereditos DOM ok" virava "dom ok".
    video = por_id["asset:engine:motor-video-volc"]["resumo"]
    checar("resumo do video preserva 'MP4' e 'QA' (regressao de capitalize)",
           "38 MP4 finais em 1080x1920" in video and "QA técnico" in video, video[:120])
    checar("resumo da prensa preserva 'DOM' (regressao de capitalize)",
           "vereditos DOM ok" in por_id["asset:engine:prensa"]["resumo"])
    # O nome do port termina em "O.S." e o concatenador produzia "O.S..".
    checar("nenhum resumo com ponto duplo", all(".." not in p["resumo"] for p in payloads))
    # `slug("Repositório VOLC O.S.")` produzia a tag ilegivel `reposit-rio-volc-o-s`.
    tags_ruins = [t for p in payloads for t in p["tags"] if not re.match(r"^[a-z][a-z0-9-]*$", t)]
    checar("toda tag em minuscula sem acento", not tags_ruins, str(tags_ruins))
    # O Motor de Imagem VOLC declara `inventory_snapshot.skins: 7`; perder esse 7
    # por ele estar aninhado seria perder patrimonio.
    checar("skins do Motor de Imagem VOLC vem de inventory_snapshot.skins",
           por_id["asset:engine:volc-motor-imagem"]["engine"].get("skins") == 7,
           str(por_id["asset:engine:volc-motor-imagem"]["engine"].get("skins")))

    sha_esperado = {MANIFESTO_IMAGEM: sha256_arquivo(MANIFESTO_IMAGEM),
                    MANIFESTO_VIDEO: sha256_arquivo(MANIFESTO_VIDEO)}

    for p in payloads:
        aid = p["ativo_id"]
        e = p["engine"]

        checar(f"[{aid}] ativo_id na forma do CHECK", bool(ATIVO_ID_RE.match(aid)))
        checar(f"[{aid}] kind/cluster do par de cofre_tipo",
               p["kind"] == KIND and p["cluster"] == CLUSTER)
        checar(f"[{aid}] campo desconhecido no topo",
               all(k in CAMPOS_TOPO for k in p), f"{[k for k in p if k not in CAMPOS_TOPO]}")
        checar(f"[{aid}] campo desconhecido em engine",
               all(k in CAMPOS_ENGINE for k in e), f"{[k for k in e if k not in CAMPOS_ENGINE]}")

        checar(f"[{aid}] nome 2..160", 2 <= len(p["nome"].strip()) <= 160, str(len(p["nome"])))
        checar(f"[{aid}] plataforma 1..240", 1 <= len(p["plataforma"].strip()) <= 240)
        checar(f"[{aid}] resumo 10..800", 10 <= len(p["resumo"].strip()) <= 800, str(len(p["resumo"])))
        checar(f"[{aid}] proxima_acao 10..800",
               10 <= len(p["proxima_acao"].strip()) <= 800, str(len(p["proxima_acao"])))
        checar(f"[{aid}] dono_nome 1..240", 1 <= len(p["dono_nome"].strip()) <= 240)
        checar(f"[{aid}] estado conhecido", p["estado"] in ESTADOS_ATIVO, p["estado"])
        checar(f"[{aid}] criticidade conhecida", p["criticidade"] in CRITICIDADES)
        checar(f"[{aid}] custodia conhecida", p["dono_custodia"] in CUSTODIAS)
        checar(f"[{aid}] capacidades 1..40 sem branco",
               1 <= len(p["capacidades"]) <= 40 and all(v.strip() for v in p["capacidades"]),
               str(len(p["capacidades"])))
        checar(f"[{aid}] tags 0..30 sem branco",
               len(p["tags"]) <= 30 and all(v.strip() for v in p["tags"]))
        checar(f"[{aid}] localizacao_rotulo 1..240",
               1 <= len(p["localizacao_rotulo"].strip()) <= 240, str(len(p["localizacao_rotulo"])))
        if "url_publica" in p:
            checar(f"[{aid}] url_publica http(s)",
                   bool(re.match(r"^https?://[^\s]{3,2000}$", p["url_publica"])))
        if "projeto" in p:
            checar(f"[{aid}] projeto nao vazio", bool(p["projeto"].strip()))

        checar(f"[{aid}] modalidade conhecida", e["modalidade"] in MODALIDADES)
        checar(f"[{aid}] estado_operacional conhecido", e["estado_operacional"] in ESTADOS_OPERACIONAIS)
        checar(f"[{aid}] estado_operacional NUNCA 'integrado'",
               e["estado_operacional"] != "integrado", e["estado_operacional"])
        checar(f"[{aid}] manifesto_sha256 confere com o arquivo",
               e["manifesto_sha256"] == sha_esperado[e["manifesto_fonte"]])
        checar(f"[{aid}] sha256 na forma [0-9a-f]{{64}}", bool(SHA256_RE.match(e["manifesto_sha256"])))
        if "fonte_fingerprint" in e:
            checar(f"[{aid}] fingerprint na forma [0-9a-f]{{64}}",
                   bool(SHA256_RE.match(e["fonte_fingerprint"])))
        checar(f"[{aid}] manifesto_fonte relativo ao repo",
               not e["manifesto_fonte"].startswith("/") and (RAIZ / e["manifesto_fonte"]).exists())
        checar(f"[{aid}] verificado_em AAAA-MM-DD", bool(DATA_RE.match(e["verificado_em"])))

        # A regra que o banco escreve como CHECK `> 0`: ausência é omissão.
        for contador in ("formatos", "skins", "nichos", "vozes"):
            if contador in e:
                checar(f"[{aid}] {contador} positivo e inteiro",
                       isinstance(e[contador], int) and not isinstance(e[contador], bool) and e[contador] > 0,
                       str(e[contador]))
        checar(f"[{aid}] nenhuma chave com valor null ou zero",
               all(v is not None and v != 0 for v in e.values()))

        checar(f"[{aid}] capacidades_observadas 0..80 sem branco",
               len(e["capacidades_observadas"]) <= 80
               and all(v.strip() for v in e["capacidades_observadas"]),
               str(len(e["capacidades_observadas"])))
        checar(f"[{aid}] limitacoes 0..80", len(e["limitacoes"]) <= 80)
        checar(f"[{aid}] requisitos 0..40", len(e["requisitos"]) <= 40)
        checar(f"[{aid}] destinos 0..60", len(e["destinos_compativeis"]) <= 60)

        # Espelho de cofre_recusa_chave_sensivel.
        sensiveis = [c for c, k in _percorrer_chaves(p) if _normalizar_chave(k) in _BLOCKLIST]
        checar(f"[{aid}] nenhuma chave da blocklist", not sensiveis, str(sensiveis))
        # Espelho de cofre_sem_material_de_credencial nos quatro campos de prosa.
        prosa = [p["resumo"], p["proxima_acao"], p.get("display_id"), p.get("localizacao_rotulo")]
        sujo = [t for t in prosa if t and any(r.search(t) for r in _MATERIAL_CREDENCIAL)]
        checar(f"[{aid}] prosa sem material de credencial", not sujo)

        checar(f"[{aid}] chave de idempotencia na forma de cofre_operacao",
               bool(CHAVE_IDEMPOTENCIA_RE.match(chave_de_idempotencia(p))))
        checar(f"[{aid}] motivo da revisao 5..800", 5 <= len(motivo_da_revisao(p)) <= 800)

    for linha in ok:
        print(f"ok    {linha}")
    for linha in falhas:
        print(f"FALHA {linha}")
    print(f"\n{len(ok)} asserções ok, {len(falhas)} falhas")
    return 1 if falhas else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emite os payloads dos engines criativos para public.cofre_cadastrar_ativo.")
    parser.add_argument("--autoteste", action="store_true", help="roda as asserções internas e sai 0/1")
    parser.add_argument("--sql", action="store_true",
                        help="emite SELECT public.cofre_cadastrar_ativo(...) por engine")
    args = parser.parse_args()

    if args.autoteste:
        return autoteste()

    payloads, relatorio = montar_payloads()
    relatorio.escrever(sys.stderr)
    sys.stderr.write(f"{len(payloads)} engines emitidos para public.cofre_cadastrar_ativo "
                     f"(kind={KIND}, cluster={CLUSTER}).\n")
    sys.stdout.write(emitir_sql(payloads) if args.sql else emitir_json(payloads))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
