#!/usr/bin/env python3
"""Valida o pacote `deploy/postiz/` SEM subir nada e SEM tocar na rede.

## Por que este validador existe

O pacote do Postiz e a unica parte do VOLC-OS que nao pode ser provada rodando:
subir a pilha significa baixar imagem de terceiro, escrever em volume e abrir
porta. Entao o que da para provar sem instancia foi separado e transformado em
gate — e o que NAO da esta declarado como capacidade nao provada no README, em
vez de ficar subentendido.

## O que a versao anterior deixava passar (medido em 02/09/2026, nao suposto)

Esta e a segunda versao. A primeira tinha um parser proprio de YAML e lia UM
arquivo so. As duas decisoes foram derrubadas por prova, e ficam registradas
aqui porque quem vier depois vai ser tentado a refaze-las:

1. **O parser proprio era derrotado por YAML VALIDO.** Ele so reconhecia item de
   lista de portas com exatamente 6 espacos e so registrava `ports` quando a
   chave vinha sem valor na linha. Duas escritas legitimas escapavam:
   `        - "0.0.0.0:4007:5000"` (8 espacos) e `ports: ["0.0.0.0:4007:5000"]`
   (sequencia de fluxo). Nos dois casos o gate imprimia APROVADO com a instancia
   inteira publicada em toda interface da maquina.
   A auto-conferencia com PyYAML nao pegava porque so comparava nome de servico,
   imagem e EXISTENCIA de healthcheck — nunca portas.
2. **Ler `docker-compose.yml` sozinho nao e ler o que o Compose executa.**
   `docker compose up -d` MESCLA os arquivos de override por padrao. Medido com
   o proprio Compose (`docker compose config`) num pacote com um
   `docker-compose.override.yml` de 10 linhas ao lado: imagem virava `:latest`,
   surgia uma publicacao em `0.0.0.0`, `privileged: true` entrava e as DUAS
   variaveis PROIBIDAS ficavam ativas — e o gate antigo dizia APROVADO.
3. **Sem PyYAML o gate ficava mais fraco em silencio**, e o README mandava rodar
   com o `python3` do sistema, que nao tem PyYAML nesta maquina. Um gate que
   enfraquece justamente no interpretador que o runbook recomenda e pior do que
   nao ter gate: ele produz a assinatura sem produzir a conferencia.

Por isso, agora: PyYAML e OBRIGATORIO e a ausencia dele FALHA FECHADO (saida 2,
nomeando o interpretador certo); todos os arquivos que o Compose mesclaria sao
carregados; e a existencia de qualquer arquivo de compose nao declarado no
pacote e ERRO por si so, antes de qualquer conferencia de conteudo.

## O que ele confere

Estrutura do pacote
  0. arquivos obrigatorios presentes; nenhum arquivo de compose fora dos
     DECLARADOS (`ARQUIVOS_DECLARADOS`) — override e o caminho silencioso.

Sobre o compose MESCLADO (todos os arquivos, como o Compose faria)
  1. imagem: nada em `:latest` nem sem tag (aviso para tag flutuante).
  2. healthcheck: existe, nao esta `disable: true`, e nao e teste trivial
     (`true`, `/bin/true`, `exit 0`, `:`) — teste trivial e healthcheck
     desligado com aparencia de ligado.
  3. rede: toda porta publicada em loopback por padrao, nas duas sintaxes
     (curta `"HOST:PORTA:PORTA"` e longa `{host_ip, published, target}`).
  4. dependencia: todo `depends_on` com `condition: service_healthy` — a forma
     de lista so garante ORDEM DE PARTIDA, nao prontidao.
  5. postura anunciada (README §7), agora executavel: `cap_drop: [ALL]`,
     `no-new-privileges:true`, `internal: true` na rede interna, nenhum
     `privileged: true`, nenhum `network_mode: host`, e so os servicos de
     `SERVICOS_NA_BORDA` na rede com saida.
  6. variavel: toda variavel interpolada documentada no `.env.example`, nas tres
     formas que o Compose aceita: `${NOME}`, `${NOME:-padrao}` e `$NOME`.
  7. proibidas: `DISABLE_SSRF_PROTECTION` e `NOT_SECURED` so em comentario.

Sobre os arquivos do pacote
  8. segredo: nenhum valor de credencial versionado (mesma familia de padroes de
     backend/tests/test_publicacao_organica_segredos.py).

## Prova de mordida

⚠️ Conferencia sem prova de mordida e o defeito que esta versao esta
consertando. Por isso o proprio script sabe se auto-testar:

    <interpretador> scripts/validar_postiz_pacote.py --autoteste

Ele copia o pacote para um diretorio temporario, aplica UMA mutacao conhecida de
cada vez (as duas que derrubaram o parser antigo inclusive) e exige que o gate
REPROVE com o rotulo esperado. Uma mutacao que nao aplica e ERRO, nao passe:
mutacao que nao pega transforma o autoteste em teatro.

## Como rodar

⚠️ PRECISA de PyYAML. O `python3` do sistema desta maquina NAO tem (medido em
02/09/2026); o venv do backend tem:

    backend/.venv/bin/python scripts/validar_postiz_pacote.py
    backend/.venv/bin/python scripts/validar_postiz_pacote.py --autoteste
    backend/.venv/bin/python scripts/validar_postiz_pacote.py --avisos-como-erro
    backend/.venv/bin/python scripts/validar_postiz_pacote.py --pacote deploy/postiz

Saida: 0 aprovado (pode ter avisos), 1 reprovado, 2 erro de uso ou de ambiente
(inclui PyYAML ausente — o gate NAO roda enfraquecido).
"""

from __future__ import annotations

import argparse
import re
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterator

# =============================================================================
# ⚠️ TRAVA DE REDE — a promessa "este validador nunca chama rede" vira controle
# executavel aqui, e nao permanece frase de docstring. Se um dia alguem
# acrescentar uma conferencia que resolve DNS ou consulta um registry, o script
# QUEBRA com uma mensagem explicando por que, em vez de silenciosamente passar a
# depender de conectividade num gate que roda em CI sem saida.
# =============================================================================
class RedeProibida(RuntimeError):
    """Alguem tentou abrir soquete dentro de um validador declarado offline."""


def _sem_rede(*_args, **_kwargs):  # noqa: ANN002, ANN003
    raise RedeProibida(
        "validar_postiz_pacote.py e OFFLINE por construcao: nao resolve nome, "
        "nao consulta registry e nao sobe container. Se a conferencia nova "
        "precisa de rede, ela pertence a outro script."
    )


socket.socket = _sem_rede          # type: ignore[assignment]
socket.create_connection = _sem_rede  # type: ignore[assignment]


RAIZ = Path(__file__).resolve().parents[1]

#: Interpretador que tem PyYAML nesta casa. Aparece na mensagem de falha fechada
#: porque "instale PyYAML" sem dizer ONDE e um conselho que ninguem executa.
INTERPRETADOR_SUGERIDO = "backend/.venv/bin/python"


def exigir_pyyaml():
    """Importa PyYAML ou MATA o processo. Nunca degrada em silencio.

    ⚠️ Esta e a correcao central da v2. A v1 caia para um parser proprio quando
    PyYAML faltava, e o README mandava rodar com o `python3` do sistema — que
    nao tem PyYAML. Resultado medido: um servico em sintaxe de fluxo com
    `alpine:latest` publicando `0.0.0.0:9999` era APROVADO no interpretador que
    o proprio runbook recomendava. Falhar fechado e ruidoso; degradar e
    silencioso, e so o silencio e perigoso.
    """
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        print(
            "ERRO [ambiente] este gate exige PyYAML e NAO roda enfraquecido.\n"
            f"       Interpretador atual: {sys.executable}\n"
            f"       Use o venv do backend:  {INTERPRETADOR_SUGERIDO} "
            "scripts/validar_postiz_pacote.py\n"
            "       (ou `python3 -m pip install --user pyyaml`, se preferir o "
            "interpretador do sistema)\n"
            "\n"
            "       Por que nao ha modo degradado: a versao anterior tinha um "
            "parser proprio de\n"
            "       YAML e ele era derrotado por YAML VALIDO — item de lista com "
            "8 espacos e\n"
            "       sequencia de fluxo passavam com a porta publicada em "
            "0.0.0.0. Um gate mais\n"
            "       fraco em silencio produz assinatura sem conferencia.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return yaml


# --- constantes de politica --------------------------------------------------

#: Nomes que o Postiz reconhece e que este pacote proibe. Ver `.env.example`.
VARIAVEIS_PROIBIDAS = ("DISABLE_SSRF_PROTECTION", "NOT_SECURED")

#: Enderecos de bind aceitos como "so esta maquina".
BINDS_LOCAIS = ("127.0.0.1", "::1", "localhost")

#: Os arquivos de compose que ESTE pacote declara ter. Qualquer outro nome que o
#: Compose leria e reprovacao — inclusive um override legitimo. Se um dia o
#: pacote passar a ter dois arquivos de proposito, o nome novo entra AQUI, e
#: essa edicao e o registro da decisao.
ARQUIVOS_DECLARADOS = ("docker-compose.yml",)

#: Ordem de precedencia do Compose v2 (compose-go/cli: `DefaultFileNames`).
#: `compose.yaml` vence `docker-compose.yml` quando os dois existem — por isso
#: um `compose.yaml` largado no diretorio troca o arquivo executado inteiro.
NOMES_BASE_COMPOSE = (
    "compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml",
)

#: `DefaultOverrideFileNames`. Estes NAO substituem: sao MESCLADOS por cima.
NOMES_OVERRIDE_COMPOSE = (
    "compose.override.yaml", "compose.override.yml",
    "docker-compose.override.yml", "docker-compose.override.yaml",
)

#: Os unicos servicos que podem estar na rede com saida para a internet. O
#: README §7 afirma isso em prosa; aqui a afirmacao vira conferencia. `postiz`
#: fala com Meta/LinkedIn/X; `temporal-ui` esta na borda so porque porta
#: publicada nao funciona em rede `internal: true` (e por isso vive atras de um
#: profile). Qualquer terceiro nome aqui e uma decisao de superficie de ataque.
SERVICOS_NA_BORDA = ("postiz", "temporal-ui")

#: Nome da rede sem gateway. Todo servico tem de estar nela.
REDE_INTERNA = "interna"

#: Condicoes de `depends_on` que significam PRONTIDAO (e nao so partida).
CONDICOES_ACEITAS = ("service_healthy", "service_completed_successfully")

#: Testes de healthcheck que sempre passam. Aceitar isso e o mesmo que nao ter
#: healthcheck, com a agravante de o `docker ps` imprimir `healthy`.
TESTE_TRIVIAL = re.compile(
    r"^(?:/bin/|/usr/bin/)?(?:true|:)$|^exit\s+0$|^return\s+0$", re.IGNORECASE
)

#: Padroes de segredo. Deliberadamente conservadores: um gate que grita a toa e
#: um gate que as pessoas aprendem a ignorar.
#: ⚠️ Os prefixos vieram de backend/tests/test_publicacao_organica_segredos.py —
#: os dois detectores olham para os MESMOS artefatos (`deploy/postiz` esta na
#: lista de alvos daquele teste), e duas listas diferentes para o mesmo alvo
#: garantem que um dia uma delas passe a mentir.
PADROES_DE_SEGREDO: dict[str, re.Pattern[str]] = {
    "chave-privada": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}"),
    "chave-google": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "chave-openai": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}"),
    "token-oauth-postiz": re.compile(r"\bpos_[A-Za-z0-9]{20,}"),
    # ⚠️ O `\b` NAO E ENFEITE: sem ele, `pk_` casa dentro de palavra e `pos_`
    # casava em `500_apos_gravar` (medido no teste de segredos desta missao).
    "prefixo-conhecido": re.compile(r"\b(?:xox[baprs]|ghp_|gho_|pk_)[A-Za-z0-9_-]{16,}"),
    "referencia-1password": re.compile(
        r"op://[A-Za-z0-9._%~-]+/[A-Za-z0-9._%~-]+/"
    ),
    # URL de banco com senha literal. A forma interpolada
    # `postgresql://${VAR}:${VAR}@host` NAO casa, porque `$` e `{` estao fora
    # das classes — e e exatamente essa a forma que o compose usa.
    "url-com-senha": re.compile(r"postgres(?:ql)?://[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]{6,}@"),
    # Atribuicao de literal longo a nome que cheira a segredo. Tambem nao casa
    # com `${...}` nem com atribuicao vazia (`NOME=`), que e a convencao dos
    # arquivos .example desta casa.
    "atribuicao-literal": re.compile(
        r"(?i)\b[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|_PWD|API_KEY|APIKEY)\b"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9+/=_\-]{16,}[\"']?"
    ),
}

#: As tres formas de interpolacao que o Compose entende, na ordem que importa:
#: `$$` PRIMEIRO, porque e o escape (variavel do container, nao do host) e tem
#: de consumir os dois cifroes antes que a alternativa `$NOME` os veja.
#: ⚠️ A v1 so enxergava `${NOME}`. `$NOME` sem chaves e interpolado igual, e
#: escapava inteiro da conferencia "toda variavel documentada".
REFERENCIA_DE_VARIAVEL = re.compile(
    r"\$\$|\$\{([A-Za-z_][A-Za-z0-9_]*)[^}]*\}|\$([A-Za-z_][A-Za-z0-9_]*)"
)


# --- leitura do compose ------------------------------------------------------

class ErroDeCompose(RuntimeError):
    """Arquivo de compose ilegivel. Gate que nao entende nao aprova."""


def arquivos_de_compose(pacote: Path) -> tuple[list[Path], list[Path]]:
    """(declarados presentes, intrusos) — na ordem em que o Compose leria.

    ⚠️ O Compose v2 le UM arquivo base (o primeiro de `NOMES_BASE_COMPOSE` que
    existir) e MESCLA por cima todos os overrides. Por isso o gate faz as duas
    coisas: reprova qualquer nome nao declarado (a existencia do arquivo ja e o
    problema) e, mesmo assim, mescla tudo antes de conferir conteudo — assim as
    conferencias mordem o que o `up` executaria, e nao o que o pacote gostaria
    de ter.
    """
    declarados: list[Path] = []
    intrusos: list[Path] = []
    for nome in (*NOMES_BASE_COMPOSE, *NOMES_OVERRIDE_COMPOSE):
        caminho = pacote / nome
        if not caminho.is_file():
            continue
        (declarados if nome in ARQUIVOS_DECLARADOS else intrusos).append(caminho)
    return declarados, intrusos


def mesclar(base: Any, sobreposto: Any) -> Any:
    """Mescla dois documentos como um gate deve mesclar: sem perder perigo.

    Mapa entra em mapa, recursivamente. Lista vira UNIAO (sem repetir).

    ⚠️ Uniao NAO e exatamente a semantica do Compose (para `cap_drop`, por
    exemplo, o override SUBSTITUI). A escolha e deliberada e conservadora numa
    direcao so: uniao nunca esconde um item PERIGOSO acrescentado pelo override
    — e foi assim que `0.0.0.0:4007:5000` apareceu no `docker compose config`
    real desta pilha, ao lado da publicacao em loopback. O caso oposto (override
    APAGANDO endurecimento) nao depende desta funcao: a mera existencia de um
    arquivo de compose nao declarado ja e ERRO.
    """
    if isinstance(base, dict) and isinstance(sobreposto, dict):
        resultado = dict(base)
        for chave, valor in sobreposto.items():
            resultado[chave] = mesclar(resultado.get(chave), valor)
        return resultado
    if isinstance(base, list) and isinstance(sobreposto, list):
        resultado = list(base)
        for item in sobreposto:
            if item not in resultado:
                resultado.append(item)
        return resultado
    return sobreposto


def carregar_mesclado(caminhos: list[Path]) -> tuple[dict, dict[Path, str]]:
    """Le e mescla os arquivos na ordem do Compose. Erro de sintaxe sobe."""
    yaml = exigir_pyyaml()
    documento: dict = {}
    textos: dict[Path, str] = {}
    for caminho in caminhos:
        texto = caminho.read_text(encoding="utf-8")
        textos[caminho] = texto
        try:
            parcial = yaml.safe_load(texto)
        except yaml.YAMLError as erro:  # pragma: no cover - depende do arquivo
            raise ErroDeCompose(f"{caminho.name}: {erro}") from erro
        if parcial is None:
            continue
        if not isinstance(parcial, dict):
            raise ErroDeCompose(f"{caminho.name}: o topo nao e um mapa YAML")
        documento = mesclar(documento, parcial)
    return documento, textos


def textos_do_documento(dado: Any) -> Iterator[str]:
    """Toda string do documento — chaves e valores.

    E sobre ELAS que o Compose interpola variavel; comentario nao e interpolado.
    Percorrer o documento (e nao o texto cru) evita acusar um nome citado dentro
    de um `#` de comentario.
    """
    if isinstance(dado, dict):
        for chave, valor in dado.items():
            if isinstance(chave, str):
                yield chave
            yield from textos_do_documento(valor)
    elif isinstance(dado, list):
        for item in dado:
            yield from textos_do_documento(item)
    elif isinstance(dado, str):
        yield dado


def variaveis_interpoladas(documento: dict) -> set[str]:
    """Nomes que o Compose vai tentar interpolar, nas tres formas aceitas."""
    nomes: set[str] = set()
    for texto in textos_do_documento(documento):
        for achado in REFERENCIA_DE_VARIAVEL.finditer(texto):
            nome = achado.group(1) or achado.group(2)
            if nome:
                nomes.add(nome)
    return nomes


def localizar(textos: dict[Path, str], trecho: str) -> str:
    """"arquivo:linha" onde `trecho` aparece; "" quando nao aparece.

    ⚠️ Best-effort de proposito. PyYAML descarta numero de linha, e inventar um
    numero errado e pior do que nao ter numero: a mensagem sempre nomeia o
    SERVICO, que e o endereco que o humano usa para achar o bloco.
    """
    for caminho, texto in textos.items():
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if trecho and trecho in linha:
                return f"{caminho.name}:{numero}"
    return ""


# --- conferencias unitarias --------------------------------------------------

def tag_e_flutuante(tag: str) -> bool:
    """True para tag que anda sozinha (`17-alpine`, `7.2`, `16`).

    ⚠️ NAO e o mesmo problema que `:latest`. `:latest` e reprovacao; tag
    flutuante e AVISO, porque as tres vieram do compose oficial e trocar por um
    numero de patch inventado — sem rede para confirmar que ele existe — quebra
    a subida. O caminho certo esta no README: resolver para digest.
    """
    base = re.sub(r"-(?:alpine|slim|bookworm|bullseye|jammy).*$", "", tag)
    return bool(re.fullmatch(r"v?\d+(?:\.\d+)?", base))


def problema_de_healthcheck(bloco: Any) -> str | None:
    """None quando o healthcheck realmente confere alguma coisa.

    Tres formas de nao ter healthcheck tendo um:
      - ausente;
      - `disable: true` (ou `test: ["NONE"]`), que e a forma OFICIAL de
        desligar — e a v1 aprovava, porque so olhava se a chave existia;
      - teste trivial (`true`, `/bin/true`, `exit 0`), que sempre passa. Este e
        o pior dos tres: o `docker compose ps` imprime `healthy` e o
        `depends_on` libera o dependente contra um servico que nao respondeu
        nada.
    """
    if bloco is None:
        return "nao tem healthcheck"
    if not isinstance(bloco, dict):
        return f"healthcheck em formato nao reconhecido ({type(bloco).__name__})"
    if bloco.get("disable"):
        return "tem `healthcheck.disable: true` — desligado por configuracao"

    teste = bloco.get("test")
    if teste is None:
        return "tem bloco de healthcheck SEM `test`"

    if isinstance(teste, str):
        comando = teste.strip()
    elif isinstance(teste, list):
        partes = [str(parte) for parte in teste]
        if partes and partes[0].upper() == "NONE":
            return "tem `test: [\"NONE\"]` — e a forma de DESLIGAR o healthcheck"
        if partes and partes[0].upper() in ("CMD", "CMD-SHELL"):
            partes = partes[1:]
        comando = " ".join(parte.strip() for parte in partes).strip()
    else:
        return f"`test` em formato nao reconhecido ({type(teste).__name__})"

    if not comando:
        return "tem `test` vazio"
    if TESTE_TRIVIAL.match(comando):
        return (
            f"tem teste TRIVIAL ({comando!r}), que sempre passa. `docker "
            "compose ps` vai imprimir `healthy` sem nada ter sido conferido"
        )
    return None


def bind_da_porta(publicacao: str) -> str | None:
    """Extrai o endereco de host de `HOST:PORTA:PORTA`; None quando nao ha.

    Uma publicacao sem endereco (`4007:5000`) significa `0.0.0.0` no Docker —
    toda interface da maquina. E o caso que esta funcao existe para pegar.
    ⚠️ O endereco pode vir de variavel (`${VAR:-127.0.0.1}`); o que se confere
    entao e o PADRAO, porque e ele que vale quando ninguem decidiu nada.
    ⚠️ IPv6 literal vem entre colchetes (`[::1]:4007:5000`); sem o ramo dos
    colchetes o `split(":")` devolveria `"["` e o gate acusaria um bind valido.
    """
    entre_colchetes = re.match(r"^\[([^\]]+)\]:", publicacao)
    if entre_colchetes:
        return entre_colchetes.group(1).strip()
    padrao_variavel = re.match(r"^\$\{[A-Za-z_][A-Za-z0-9_]*:?-([^}]*)\}:", publicacao)
    if padrao_variavel:
        return padrao_variavel.group(1).strip() or None
    if re.match(r"^\$", publicacao):
        # Variavel sem padrao: nao da para saber onde vai ligar sem o .env.
        return "?"
    partes = publicacao.split(":")
    if len(partes) >= 3:
        return partes[0]
    return None


def publicacoes(servico: dict) -> list[tuple[str, str | None]]:
    """[(descricao, bind)] para cada porta publicada, nas duas sintaxes.

    ⚠️ A sintaxe longa (`- {target: 5000, published: 4007}`) e a que a v1 nunca
    veria: sem `host_ip`, ela publica em 0.0.0.0 exatamente como a curta sem
    endereco, e o parser antigo so conhecia item de string.
    """
    resultado: list[tuple[str, str | None]] = []
    for item in como_lista(servico.get("ports")):
        if isinstance(item, dict):
            descricao = (
                f"{{host_ip: {item.get('host_ip', '<ausente>')}, "
                f"published: {item.get('published')}, target: {item.get('target')}}}"
            )
            host = item.get("host_ip")
            resultado.append((descricao, str(host) if host is not None else None))
            continue
        texto = str(item).strip().strip("\"'")
        resultado.append((texto, bind_da_porta(texto)))
    return resultado


def como_lista(valor: Any) -> list[Any]:
    """Normaliza campo que o compose aceita em lista OU em escalar.

    ⚠️ Sem isto, `cap_drop: ALL` (escalar, aceito pelo Compose) seria iterado
    caractere a caractere — `['A','L','L']` — e a conferencia de `ALL` passaria
    por acidente. Falso NEGATIVO por detalhe de tipo e como o gate anterior
    morreu.
    """
    if valor is None:
        return []
    if isinstance(valor, (list, tuple)):
        return list(valor)
    return [valor]


def redes_do_servico(servico: dict) -> list[str]:
    """Nomes de rede, aceitando lista (`- interna`) e mapa (com aliases)."""
    redes = servico.get("networks")
    if redes is None:
        return []
    if isinstance(redes, dict):
        return [str(nome) for nome in redes]
    if isinstance(redes, list):
        return [str(nome) for nome in redes]
    return [str(redes)]


def nomes_documentados(texto: str) -> set[str]:
    """Nomes que o `.env.example` documenta.

    Duas formas contam, e so duas:

    - `NOME=` no inicio da linha — a entrada normal, vazia por convencao desta
      casa (documenta-se o NOME, nunca o valor);
    - `# NOME ...` no inicio de um comentario, para os nomes que existem DENTRO
      do container (`DATABASE_URL`, `JWT_SECRET`) ou do outro lado da fronteira
      (`POSTIZ_BASE_URL`), que o operador nao define aqui mas precisa conhecer.

    ⚠️ A segunda forma exige `_` no nome. Sem essa exigencia, qualquer comentario
    comecando em maiuscula ("TODAS as entradas...", "URL do Redis...") era lido
    como documentacao de variavel, e o conjunto de "documentados" inchava com
    palavras em portugues — um gate que aprova por acidente e pior do que gate
    nenhum. Medido: sem a regra, 8 dos 25 nomes eram lixo textual.
    """
    documentados: set[str] = set()
    for linha in texto.splitlines():
        atribuicao = re.match(r"^([A-Z][A-Z0-9_]*)=", linha)
        if atribuicao:
            documentados.add(atribuicao.group(1))
            continue
        comentario = re.match(r"^#\s*([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b", linha)
        if comentario:
            documentados.add(comentario.group(1))
    return documentados


def exibir(caminho: Path) -> str:
    """Caminho relativo a raiz quando possivel; absoluto quando nao.

    ⚠️ `Path.relative_to` levanta ValueError para caminho de fora da raiz, e
    `--pacote` aceita caminho absoluto de proposito (e assim que o `--autoteste`
    roda contra copias descartaveis, sem sujar o repositorio). Deixar o
    ValueError subir trocaria uma mensagem util por um traceback.
    """
    try:
        return str(caminho.relative_to(RAIZ))
    except ValueError:
        return str(caminho)


def parte_ativa(linha: str) -> str:
    """O pedaco da linha antes do comentario — o unico que configura algo."""
    return linha.split("#", 1)[0]


# --- avaliacao completa ------------------------------------------------------

class Resultado:
    """Erros, avisos e o resumo que o relatorio imprime."""

    def __init__(self) -> None:
        self.erros: list[str] = []
        self.avisos: list[str] = []
        self.resumo: dict[str, Any] = {}

    @property
    def aprovado(self) -> bool:
        return not self.erros


def avaliar(pacote: Path) -> Resultado:
    """Roda TODAS as conferencias e devolve o resultado, sem imprimir nada.

    Separado de `main` para que `--autoteste` possa exercitar as conferencias
    contra copias mutadas do pacote no mesmo processo.
    """
    resultado = Resultado()
    erros, avisos = resultado.erros, resultado.avisos

    # --- 0. estrutura do pacote --------------------------------------------
    exemplo = pacote / ".env.example"
    for obrigatorio in (pacote / "docker-compose.yml", exemplo,
                        pacote / "README.md", pacote / "LICENCA-E-FRONTEIRA.md"):
        if not obrigatorio.is_file():
            erros.append(f"[pacote] arquivo obrigatorio ausente: {exibir(obrigatorio)}")
    if erros:
        return resultado

    declarados, intrusos = arquivos_de_compose(pacote)
    for intruso in intrusos:
        erros.append(
            f"[compose] existe '{intruso.name}' no pacote, e ele NAO esta "
            f"declarado ({', '.join(ARQUIVOS_DECLARADOS)}). `docker compose "
            "up -d` mescla os overrides e prefere `compose.yaml` ao "
            "`docker-compose.yml` — ou seja, o que roda deixa de ser o que este "
            "pacote revisou. Medido com `docker compose config`: um override de "
            "10 linhas trocou a imagem por `:latest`, publicou em 0.0.0.0, ligou "
            "`privileged` e ativou as duas variaveis PROIBIDAS."
        )

    try:
        documento, textos = carregar_mesclado([*declarados, *intrusos])
    except ErroDeCompose as erro:
        erros.append(f"[compose] arquivo ilegivel — {erro}. Gate que nao entende nao aprova.")
        return resultado

    servicos = documento.get("services") or {}
    if not isinstance(servicos, dict) or not servicos:
        erros.append(
            "[compose] nenhum servico em `services:`. Ou o pacote esta vazio, ou "
            "o arquivo nao e o que se pensava — nos dois casos o gate reprova."
        )
        return resultado

    # --- 1. imagens ---------------------------------------------------------
    for nome, servico in sorted(servicos.items()):
        servico = servico or {}
        referencia = servico.get("image")
        onde = localizar(textos, f"image: {referencia}") if referencia else ""
        if not referencia:
            erros.append(
                f"[imagem] servico '{nome}' nao declara `image:`. Sem imagem "
                "declarada nao ha versao para pinar nem para voltar."
            )
            continue
        referencia = str(referencia)
        if "@sha256:" in referencia:
            continue
        caminho, _, tag = referencia.rpartition(":")
        if not caminho or "/" in tag:
            erros.append(
                f"[imagem] servico '{nome}' ({onde or 'sem linha'}): "
                f"'{referencia}' esta SEM tag. Sem tag o Docker usa `latest`, e a "
                "versao do control plane passa a mudar sozinha. Pine uma tag ou "
                "um digest."
            )
            continue
        if tag == "latest":
            erros.append(
                f"[imagem] servico '{nome}' ({onde or 'sem linha'}): "
                f"'{referencia}' usa `:latest`. Um `docker compose pull` de rotina "
                "trocaria a versao sem decisao humana; a migration do Prisma roda "
                "no boot e altera o schema; e o rollback deixa de existir. Pine a "
                "versao."
            )
            continue
        if tag_e_flutuante(tag):
            avisos.append(
                f"[imagem] servico '{nome}' ({onde or 'sem linha'}): "
                f"'{referencia}' tem tag FLUTUANTE (anda a cada patch). Herdada do "
                "compose oficial. Antes de producao: `docker buildx imagetools "
                f"inspect {referencia}` e troque pelo digest."
            )

    # --- 2. healthcheck -----------------------------------------------------
    for nome, servico in sorted(servicos.items()):
        problema = problema_de_healthcheck((servico or {}).get("healthcheck"))
        if problema:
            erros.append(
                f"[healthcheck] servico '{nome}' {problema}. Sem healthcheck de "
                "verdade, `depends_on` garante so ORDEM DE PARTIDA: o dependente "
                "sobe contra um servico que ainda esta inicializando."
            )

    # --- 3. fronteira de rede (portas publicadas) ---------------------------
    for nome, servico in sorted(servicos.items()):
        for descricao, bind in publicacoes(servico or {}):
            onde = localizar(textos, descricao)
            prefixo = f"[rede] servico '{nome}' ({onde or 'sintaxe longa'}): '{descricao}'"
            if bind is None:
                erros.append(
                    f"{prefixo} publica porta SEM endereco de host — no Docker "
                    "isso e 0.0.0.0, ou seja, toda interface da maquina, sem TLS. "
                    "Prefixe com 127.0.0.1."
                )
            elif bind == "?":
                erros.append(
                    f"{prefixo} liga num endereco vindo de variavel SEM padrao. O "
                    "padrao tem de ser loopback, para que esquecer de configurar "
                    "seja seguro."
                )
            elif bind not in BINDS_LOCAIS:
                erros.append(
                    f"{prefixo} liga por padrao em '{bind}', que nao e loopback. "
                    "Exposicao real se faz com reverse proxy e TLS, nao mudando o "
                    "bind."
                )

    # --- 4. dependencia por PRONTIDAO, nao por ordem ------------------------
    for nome, servico in sorted(servicos.items()):
        dependencias = (servico or {}).get("depends_on")
        if dependencias is None:
            continue
        if isinstance(dependencias, list):
            erros.append(
                f"[dependencia] servico '{nome}' usa `depends_on` em LISTA "
                f"({dependencias}). Essa forma garante so ordem de PARTIDA: o "
                "Postiz sobe e tenta migrar contra um Postgres ainda em initdb. "
                "Use a forma longa com `condition: service_healthy`."
            )
            continue
        if not isinstance(dependencias, dict):
            erros.append(f"[dependencia] servico '{nome}': `depends_on` irreconhecivel")
            continue
        for alvo, detalhe in dependencias.items():
            condicao = (detalhe or {}).get("condition") if isinstance(detalhe, dict) else None
            if condicao not in CONDICOES_ACEITAS:
                erros.append(
                    f"[dependencia] servico '{nome}' depende de '{alvo}' com "
                    f"condicao {condicao!r}. Aceitas: {', '.join(CONDICOES_ACEITAS)}."
                )

    # --- 5. postura anunciada no README §7, agora executavel ----------------
    # ⚠️ Ate a v1, apagar QUALQUER uma destas linhas do compose mantinha o gate
    # APROVADO — a postura estava so na prosa. Documento que ninguem confere
    # vira ficcao na terceira edicao.
    redes_declaradas = documento.get("networks") or {}
    interna = (redes_declaradas.get(REDE_INTERNA) or {}) if isinstance(redes_declaradas, dict) else {}
    if not isinstance(redes_declaradas, dict) or REDE_INTERNA not in redes_declaradas:
        erros.append(
            f"[postura] nao existe a rede '{REDE_INTERNA}'. E ela que segura a "
            "pilha inteira sem rota de saida."
        )
    elif not (interna or {}).get("internal"):
        erros.append(
            f"[postura] a rede '{REDE_INTERNA}' NAO tem `internal: true`. Sem "
            "isso o Docker cria gateway de saida, e banco, Redis, Temporal e "
            "Elasticsearch passam a ter para onde exfiltrar. Isso e mais forte "
            "que 'nao publicar porta', que so impede a entrada."
        )

    for nome, servico in sorted(servicos.items()):
        servico = servico or {}

        if servico.get("privileged"):
            erros.append(
                f"[postura] servico '{nome}' tem `privileged: true`. Isso devolve "
                "todas as capabilities, desliga o seccomp padrao e da acesso aos "
                "devices do host — anula, sozinho, todo o `cap_drop` do pacote."
            )

        if str(servico.get("network_mode") or "").lower() == "host":
            erros.append(
                f"[postura] servico '{nome}' usa `network_mode: host`. A pilha "
                "passa a usar a rede do host: a conferencia de porta em loopback "
                "deixa de significar qualquer coisa, e a rede `interna` some."
            )

        cap_drop = [str(item).upper() for item in como_lista(servico.get("cap_drop"))]
        if "ALL" not in cap_drop:
            erros.append(
                f"[postura] servico '{nome}' nao tem `cap_drop: [ALL]`. O conjunto "
                "padrao do Docker traz ~14 capabilities; o pacote promete o "
                "minimo, readicionado item a item onde o entrypoint precisa."
            )

        opcoes = [
            str(item).replace(" ", "").lower()
            for item in como_lista(servico.get("security_opt"))
        ]
        if "no-new-privileges:true" not in opcoes:
            erros.append(
                f"[postura] servico '{nome}' nao tem `no-new-privileges:true` em "
                "`security_opt`. Sem isso, um binario setuid dentro do container "
                "ganha privilegio que o processo pai nao tinha."
            )

        redes = redes_do_servico(servico)
        if not redes:
            erros.append(
                f"[postura] servico '{nome}' nao declara `networks`. Sem "
                "declaracao ele entra na rede `default`, que TEM gateway de "
                "saida — o oposto do desenho deste pacote."
            )
            continue
        if REDE_INTERNA not in redes:
            erros.append(
                f"[postura] servico '{nome}' nao esta na rede '{REDE_INTERNA}' "
                f"(esta em {redes}). Todo servico da pilha fala pela rede sem "
                "gateway; quem nao esta nela ou nao conversa, ou conversa por fora."
            )
        for rede in redes:
            if rede != REDE_INTERNA and nome not in SERVICOS_NA_BORDA:
                erros.append(
                    f"[postura] servico '{nome}' esta na rede '{rede}', que tem "
                    f"saida para a internet. So {', '.join(SERVICOS_NA_BORDA)} "
                    "podem estar la (README §7). Se este servico precisa mesmo de "
                    "saida, a decisao entra em SERVICOS_NA_BORDA — e fica no "
                    "historico."
                )

    # --- 6. variaveis documentadas ------------------------------------------
    texto_exemplo = exemplo.read_text(encoding="utf-8")
    usadas = variaveis_interpoladas(documento)
    documentadas = nomes_documentados(texto_exemplo)
    for nome in sorted(usadas - documentadas):
        erros.append(
            f"[variavel] '{nome}' e interpolada no compose e NAO aparece no "
            ".env.example. Quem for subir o pacote descobre esse nome quando o "
            "`up` falhar, e nao antes."
        )
    # Informativo, NUNCA reprovacao: o .env.example documenta de proposito nomes
    # que o compose nao interpola — os do CONTAINER (`DATABASE_URL`,
    # `JWT_SECRET`), os do lado do VOLC (`POSTIZ_BASE_URL`) e os PROIBIDOS.
    # Reprovar por isso obrigaria a apagar justamente a documentacao mais util.
    orfas = sorted(documentadas - usadas - set(VARIAVEIS_PROIBIDAS))

    # --- 7. variaveis proibidas ---------------------------------------------
    # Varre o texto CRU de todo arquivo de compose encontrado (inclusive os
    # intrusos) e do .env.example: a forma nao importa, o nome ativo importa.
    for arquivo, texto in [*textos.items(), (exemplo, texto_exemplo)]:
        for numero, linha in enumerate(texto.splitlines(), start=1):
            ativo = parte_ativa(linha)
            for proibida in VARIAVEIS_PROIBIDAS:
                if proibida in ativo:
                    erros.append(
                        f"[proibida] {exibir(arquivo)}:{numero} — "
                        f"'{proibida}' aparece como configuracao ATIVA. Ela so "
                        "pode existir aqui dentro de comentario, na secao "
                        "PROIBIDAS do .env.example, com o motivo escrito."
                    )

    # --- 8. segredos versionados --------------------------------------------
    for arquivo in sorted(pacote.rglob("*")):
        if not arquivo.is_file() or arquivo.name == ".env":
            continue
        conteudo = arquivo.read_text(encoding="utf-8", errors="replace")
        for rotulo, padrao in PADROES_DE_SEGREDO.items():
            for achado in padrao.finditer(conteudo):
                linha = conteudo[: achado.start()].count("\n") + 1
                # ⚠️ O valor NAO e impresso. Um gate que ecoa o segredo para
                # provar que o achou acabou de vaza-lo para o log do CI.
                erros.append(
                    f"[segredo] {exibir(arquivo)}:{linha} — padrao "
                    f"'{rotulo}'. Valor omitido de proposito. Este pacote "
                    "documenta NOME, nunca valor."
                )

    if (pacote / ".env").exists():
        avisos.append(
            "[segredo] existe um `.env` neste diretorio. Ele NAO foi lido nem "
            "conferido; confirme que o .gitignore o cobre e que o modo e 600."
        )

    resultado.resumo = {
        "arquivos": [caminho.name for caminho in textos],
        "servicos": sorted(servicos),
        "variaveis": len(usadas),
        "todas_documentadas": not (usadas - documentadas),
        "orfas": orfas,
    }
    return resultado


# --- autoteste ---------------------------------------------------------------

def _troca(caminho: Path, antes: str, depois: str) -> None:
    """Substitui a PRIMEIRA ocorrencia e EXPLODE se o trecho nao existir.

    ⚠️ E o coracao da honestidade do autoteste. Uma mutacao que nao aplica
    produziria um pacote intacto — que o gate aprova — e a linha viraria
    "ESCAPOU" por motivo errado, ou pior, um `replace` silencioso faria o
    autoteste testar o pacote limpo e cantar vitoria.
    """
    texto = caminho.read_text(encoding="utf-8")
    if antes not in texto:
        raise AssertionError(
            f"mutacao NAO aplicada: o trecho nao existe mais em {caminho.name}: "
            f"{antes[:70]!r}. O compose mudou — atualize a mutacao, nao o "
            "veredito."
        )
    caminho.write_text(texto.replace(antes, depois, 1), encoding="utf-8")


LINHA_DA_PORTA = '      - "${POSTIZ_BIND_ADDR:-127.0.0.1}:${POSTIZ_PORT:-4007}:5000"'


def _primeiro_ports_e_do_postiz(compose: Path) -> None:
    """Garante que 'a primeira ocorrencia de `ports:`' ainda e a do `postiz`."""
    texto = compose.read_text(encoding="utf-8")
    posicao = texto.index("    ports:")
    if not (texto.index("  postiz:") < posicao < texto.index("  temporal-ui:")):
        raise AssertionError(
            "a ordem dos servicos no compose mudou: a mutacao de portas passaria "
            "a mexer no servico errado."
        )


def _mut_porta_oito_espacos(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml", LINHA_DA_PORTA,
           '        - "0.0.0.0:4007:5000"')


def _mut_porta_fluxo(pacote: Path) -> None:
    compose = pacote / "docker-compose.yml"
    _primeiro_ports_e_do_postiz(compose)
    _troca(compose, LINHA_DA_PORTA + "\n", "")
    _troca(compose, "    ports:\n", '    ports: ["0.0.0.0:4007:5000"]\n')


def _mut_porta_sintaxe_longa(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml", LINHA_DA_PORTA,
           "      - target: 5000\n        published: \"4007\"")


def _mut_override(pacote: Path) -> None:
    (pacote / "docker-compose.override.yml").write_text(
        "services:\n"
        "  postiz:\n"
        "    image: ghcr.io/gitroomhq/postiz-app:latest\n"
        "    privileged: true\n"
        "    ports:\n"
        '      - "0.0.0.0:4007:5000"\n'
        "    environment:\n"
        '      DISABLE_SSRF_PROTECTION: "true"\n'
        '      NOT_SECURED: "true"\n',
        encoding="utf-8",
    )


def _mut_compose_yaml(pacote: Path) -> None:
    # `compose.yaml` VENCE `docker-compose.yml` na precedencia do Compose v2:
    # este arquivo sozinho troca a pilha inteira por outra.
    (pacote / "compose.yaml").write_text(
        "services:\n"
        "  postiz:\n"
        "    image: alpine:latest\n"
        '    command: ["sleep", "infinity"]\n',
        encoding="utf-8",
    )


def _mut_healthcheck_desligado(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml",
           "    healthcheck:\n      # `redis-cli ping`",
           "    healthcheck:\n      disable: true\n      # `redis-cli ping`")


def _mut_healthcheck_trivial(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml",
           'test: ["CMD-SHELL", "redis-cli ping | grep -q PONG"]',
           'test: ["CMD-SHELL", "true"]')


def _mut_servico_sem_healthcheck(pacote: Path) -> None:
    with (pacote / "docker-compose.yml").open("a", encoding="utf-8") as arquivo:
        arquivo.write(
            "\n  ajudante:\n"
            "    <<: *endurecimento\n"
            "    image: alpine:3.20\n"
            '    command: ["sleep", "infinity"]\n'
            "    networks:\n"
            "      - interna\n"
            "    cap_drop:\n"
            "      - ALL\n"
        )


def _mut_variavel_sem_chaves(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml",
           'API_LIMIT: "${POSTIZ_API_LIMIT:-30}"',
           'API_LIMIT: "$POSTIZ_LIMITE_NAO_DOCUMENTADO"')


def _mut_sem_no_new_privileges(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml",
           "  security_opt:\n    - no-new-privileges:true\n", "")


def _mut_sem_cap_drop(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml",
           "    cap_drop:\n      - ALL\n    cap_add:", "    cap_add:")


def _mut_privileged(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml",
           "  postiz:\n    <<: *endurecimento\n",
           "  postiz:\n    <<: *endurecimento\n    privileged: true\n")


def _mut_network_mode_host(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml",
           "  postiz:\n    <<: *endurecimento\n",
           "  postiz:\n    <<: *endurecimento\n    network_mode: host\n")


def _mut_rede_interna_com_saida(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml", "    internal: true", "    internal: false")


def _mut_servico_novo_na_borda(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml",
           "    networks:\n      - interna\n    # ⚠️ SEM `read_only: true`: o ES",
           "    networks:\n      - interna\n      - borda\n    # ⚠️ SEM `read_only: true`: o ES")


def _mut_depends_on_lista(pacote: Path) -> None:
    _troca(
        pacote / "docker-compose.yml",
        "    depends_on:\n"
        "      postiz-postgres:\n"
        "        condition: service_healthy\n"
        "      postiz-redis:\n"
        "        condition: service_healthy\n"
        "      temporal:\n"
        "        condition: service_healthy\n",
        "    depends_on:\n      - postiz-postgres\n      - postiz-redis\n      - temporal\n",
    )


def _mut_imagem_latest(pacote: Path) -> None:
    _troca(pacote / "docker-compose.yml",
           "image: ghcr.io/gitroomhq/postiz-app:v2.23.0",
           "image: ghcr.io/gitroomhq/postiz-app:latest")


def _mut_segredo_versionado(pacote: Path) -> None:
    # ⚠️ Token SINTETICO, montado por concatenacao: escrever a string inteira
    # aqui plantaria no repositorio exatamente o que o gate procura, e o
    # detector de segredos desta missao acusaria o proprio autoteste.
    falso = "xox" + "b-" + "0123456789abcdefghijklmno"
    with (pacote / ".env.example").open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"\nPOSTIZ_TOKEN_DE_TESTE={falso}\n")


#: (nome, rotulo que TEM de aparecer, mutacao). O rotulo importa: uma mutacao
#: que reprova pelo motivo errado nao prova a conferencia que se queria provar.
MUTACOES: tuple[tuple[str, str, Callable[[Path], None]], ...] = (
    ("porta-item-com-8-espacos",      "[rede]",        _mut_porta_oito_espacos),
    ("porta-em-sequencia-de-fluxo",   "[rede]",        _mut_porta_fluxo),
    ("porta-em-sintaxe-longa",        "[rede]",        _mut_porta_sintaxe_longa),
    ("override-nao-declarado",        "[compose]",     _mut_override),
    ("compose-yaml-com-precedencia",  "[compose]",     _mut_compose_yaml),
    ("healthcheck-disable-true",      "[healthcheck]", _mut_healthcheck_desligado),
    ("healthcheck-teste-trivial",     "[healthcheck]", _mut_healthcheck_trivial),
    ("servico-sem-healthcheck",       "[healthcheck]", _mut_servico_sem_healthcheck),
    ("variavel-sem-chaves",           "[variavel]",    _mut_variavel_sem_chaves),
    ("sem-no-new-privileges",         "[postura]",     _mut_sem_no_new_privileges),
    ("sem-cap-drop-all",              "[postura]",     _mut_sem_cap_drop),
    ("privileged-true",               "[postura]",     _mut_privileged),
    ("network-mode-host",             "[postura]",     _mut_network_mode_host),
    ("rede-interna-com-saida",        "[postura]",     _mut_rede_interna_com_saida),
    ("servico-novo-na-borda",         "[postura]",     _mut_servico_novo_na_borda),
    ("depends-on-em-lista",           "[dependencia]", _mut_depends_on_lista),
    ("imagem-latest",                 "[imagem]",      _mut_imagem_latest),
    ("segredo-versionado",            "[segredo]",     _mut_segredo_versionado),
)


def autoteste(pacote: Path) -> int:
    """Quebra copias do pacote e exige que o gate morda cada uma.

    ⚠️ O controle (copia INTACTA) e tao importante quanto as mutacoes: sem ele,
    um gate que reprovasse tudo — inclusive o pacote bom — passaria no autoteste
    com nota maxima.
    """
    print(f"autoteste: {len(MUTACOES)} mutacoes + 1 controle, sobre {exibir(pacote)}")
    print("(nada e escrito no pacote real; tudo acontece em copia temporaria)\n")

    falhas = 0
    with tempfile.TemporaryDirectory(prefix="postiz-autoteste-") as area:
        base = Path(area)

        controle = base / "controle"
        shutil.copytree(pacote, controle)
        resultado = avaliar(controle)
        if resultado.aprovado:
            print("  OK       controle (copia intacta)            APROVOU, como deve")
        else:
            falhas += 1
            print("  FALHA    controle (copia intacta)            REPROVOU sem mutacao:")
            for erro in resultado.erros:
                print(f"             {erro}")

        for indice, (nome, rotulo, mutar) in enumerate(MUTACOES, start=1):
            destino = base / f"m{indice:02d}"
            shutil.copytree(pacote, destino)
            mutar(destino)
            resultado = avaliar(destino)
            mordeu = [erro for erro in resultado.erros if erro.startswith(rotulo)]
            if mordeu:
                print(f"  OK       {nome:<34} {rotulo} mordeu ({len(mordeu)} erro(s))")
            else:
                falhas += 1
                print(f"  ESCAPOU  {nome:<34} esperava {rotulo}; gate disse:")
                if resultado.aprovado:
                    print("             APROVADO — o defeito passou inteiro")
                for erro in resultado.erros:
                    print(f"             {erro}")

    print()
    if falhas:
        print(f"AUTOTESTE REPROVADO: {falhas} caso(s) sem mordida. "
              "Conferencia sem prova de mordida nao vale como conferencia.")
        return 1
    print(f"AUTOTESTE APROVADO: {len(MUTACOES)} mutacoes reprovadas pelo rotulo "
          "esperado, e o pacote intacto aprovado.")
    return 0


# --- entrada -----------------------------------------------------------------

def main() -> int:
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "--pacote", default="deploy/postiz",
        help="diretorio do pacote (padrao: deploy/postiz)",
    )
    analisador.add_argument(
        "--avisos-como-erro", action="store_true",
        help="reprova tambem por aviso (util em CI antes de producao)",
    )
    analisador.add_argument(
        "--autoteste", action="store_true",
        help="quebra copias temporarias do pacote e exige que o gate reprove cada uma",
    )
    opcoes = analisador.parse_args()

    exigir_pyyaml()  # falha fechada ANTES de qualquer conferencia
    pacote = (RAIZ / opcoes.pacote).resolve()
    if not pacote.is_dir():
        print(f"ERRO [uso] pacote nao e diretorio: {pacote}", file=sys.stderr)
        return 2

    if opcoes.autoteste:
        return autoteste(pacote)

    resultado = avaliar(pacote)

    print(f"pacote:   {exibir(pacote)}")
    if resultado.resumo:
        print(f"compose:  {', '.join(resultado.resumo['arquivos'])} "
              f"(declarados: {', '.join(ARQUIVOS_DECLARADOS)})")
        print(f"servicos: {len(resultado.resumo['servicos'])} "
              f"({', '.join(resultado.resumo['servicos'])})")
        print(f"variaveis interpoladas: {resultado.resumo['variaveis']} — todas "
              f"documentadas: {'sim' if resultado.resumo['todas_documentadas'] else 'NAO'}")
        if resultado.resumo["orfas"]:
            print("documentadas sem uso direto no compose (esperado, "
                  f"{len(resultado.resumo['orfas'])}): "
                  f"{', '.join(resultado.resumo['orfas'])}")
    print()

    for aviso in resultado.avisos:
        print(f"AVISO {aviso}")
    for erro in resultado.erros:
        print(f"ERRO  {erro}")

    if resultado.erros:
        print(f"\nREPROVADO: {len(resultado.erros)} problema(s). "
              "Nada foi subido e nada foi corrigido automaticamente.")
        return 1
    if resultado.avisos and opcoes.avisos_como_erro:
        print(f"\nREPROVADO por --avisos-como-erro: {len(resultado.avisos)} aviso(s).")
        return 1
    if resultado.avisos:
        print(f"\nAPROVADO com {len(resultado.avisos)} aviso(s). "
              "⚠️ Aprovacao aqui NAO e prova de que a pilha sobe: ver "
              "'Capacidades nao provadas' no README.")
    else:
        print("\nAPROVADO. ⚠️ Nao e prova de que a pilha sobe: ver "
              "'Capacidades nao provadas' no README.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
