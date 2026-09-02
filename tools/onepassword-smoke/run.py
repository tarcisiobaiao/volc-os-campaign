#!/usr/bin/env python3
"""Smoke seguro do 1Password local: prova a cadeia CLI -> app -> sessão -> injeção
sem nunca revelar, medir ou derivar o valor do segredo.

POR QUE ESTE ARQUIVO EXISTE (P03-T09): o cofre de segredos só é confiável se
alguém puder provar, num processo descartável, que a injeção acontece de fato.
Prova sem exposição exige uma disciplina explícita, medida nesta máquina em
01/09/2026:

  * `which op` -> "op not found"; `/Applications/1Password.app` -> inexistente;
    `which 1password-mcp` -> não encontrado; nenhuma variável OP_* no ambiente.
    Logo o estado honesto desta máquina hoje é `blocked/cli_ausente`, e o smoke
    precisa DIZER isso em vez de simular sucesso.
  * `which timeout` e `which gtimeout` -> ambos ausentes (macOS, Darwin 24.6.0).
    Por isso todo limite de tempo aqui é `subprocess.run(timeout=...)` do Python,
    nunca o binário `timeout`.

DISCIPLINA DE SEGREDO. O smoke jamais lê o valor. Nem comprimento, nem hash, nem
prefixo: comprimento vaza entropia (estreita o espaço de busca) e hash permite a
quem tem um palpite confirmá-lo offline. O único fato que sai do processo filho é
um booleano de presença.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Contrato de estados. Cada estado tem exit code próprio: um runner externo
# precisa distinguir "não deu para provar" de "provou e vazou" sem parsear texto.
# ---------------------------------------------------------------------------
ESTADOS: dict[str, int] = {
    "ok": 0,
    "blocked/cli_ausente": 10,
    "blocked/app_ausente": 11,
    "blocked/sem_sessao": 12,
    "blocked/aprovacao_negada": 13,
    # Estado ADICIONAL aos cinco pedidos: sem `--referencia` não existe ambiente
    # a testar. Emitir `ok` seria mentira e emitir um dos outros quatro seria
    # diagnóstico errado; então ele ganha nome e código próprios.
    "blocked/referencia_ausente": 14,
    "falha/vazamento": 20,
    # `op run` retornou 0 mas o filho não viu segredo algum (ou viu a própria
    # referência não resolvida). Injeção não aconteceu => `ok` é proibido.
    "falha/injecao_nao_ocorreu": 21,
    "falha/preflight": 30,
    "falha/interna": 40,
}

# Erros documentados em www.1password.dev para app bloqueado/headless.
PADROES_SEM_SESSAO = (
    "lostconnectiontoapp",
    "connectionreset",
    "connection reset",
    "no accounts configured",
)

# A documentação NÃO publica a string exata de uma aprovação negada por
# Environment. Estes termos são heurística declarada, não contrato: se nenhum
# casar, o estado cai em falha/interna — nunca em `ok`.
PADROES_APROVACAO = (
    "not authorized",
    "unauthorized",
    "authorization",
    "approval",
    "approve",
    "denied",
    "declined",
)

NOME_VAR_PADRAO = "VOLC_SMOKE_SEGREDO"
LIMITE_SEGUNDOS = 25
MAX_NOMES_IMPRESSOS = 20

# Identificador de item/vault do 1Password: 26 caracteres base32 minúsculos.
RE_ID_OP = re.compile(r"\b[a-z0-9]{26}\b")
RE_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
RE_CONTROLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Saídas TOTALMENTE previstas dos processos filhos. Ver `varrer_saida_filho`.
RE_PRESENCA = re.compile(r"^VARIAVEL_PRESENTE=(true|false)$")
RE_ECO = re.compile(r"^ECO_DETECTADO=(true|false|indeterminado)$")


# ---------------------------------------------------------------------------
# Sanitização
# ---------------------------------------------------------------------------
def sanitizar_texto(texto: str, limite: int = 400) -> str:
    """Tira controle, IDs de 26 chars e e-mails antes de qualquer impressão."""
    limpo = RE_CONTROLE.sub(" ", texto)
    limpo = RE_ID_OP.sub("<id-omitido>", limpo)
    limpo = RE_EMAIL.sub("<email-omitido>", limpo)
    limpo = " ".join(limpo.split())
    if len(limpo) > limite:
        limpo = limpo[:limite] + "…"
    return limpo


def sanitizar_nome(nome: str, limite: int = 48) -> str:
    return sanitizar_texto(str(nome), limite=limite)


def classificar_erro(texto: str) -> str:
    """Reduz stderr a uma etiqueta. Nunca devolve o texto cru para o recibo."""
    baixo = texto.lower()
    for padrao in PADROES_SEM_SESSAO:
        if padrao in baixo:
            return f"documentado:{padrao}"
    for padrao in PADROES_APROVACAO:
        if padrao in baixo:
            return f"heuristica_aprovacao:{padrao}"
    if not texto.strip():
        return "sem_stderr"
    return "nao_classificado"


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
def comando_op(caminho_op: str, *args: str) -> list[str]:
    """Monta uma invocacao do `op` com o CACHE DESLIGADO.

    ⚠️ MEDIDO EM 01/09/2026, com o 1Password TRANCADO:

        op vault list                 -> respondeu, sem pedir nada
        op --cache=false vault list   -> "authorization prompt dismissed"

    `--cache` vem ligado por padrao em sistemas UNIX (`op --help`). Uma prova de
    revogacao que um cache quente satisfaz nao e prova: ela mede o cache, nao o
    acesso. O segredo em si nunca veio do cache — `op run` falhou com e sem ele —
    mas o metadado vinha, e era o bastante para a prova dizer "listei os cofres"
    depois de o cofre ter sido trancado.

    Desligar o cache nao endurece o 1Password; endurece a MEDICAO.
    """
    return [caminho_op, "--cache=false", *args]


def executar(cmd: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    """Roda um comando com limite de tempo do Python (não existe `timeout` aqui)."""
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=LIMITE_SEGUNDOS,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", "executável não encontrado no PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"tempo esgotado após {LIMITE_SEGUNDOS}s"
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def montar_ambiente(duple: str | None) -> dict[str, str]:
    env = os.environ.copy()
    if duple:
        # O duplê SÓ entra no PATH quando pedido em `--duple`. Um smoke que
        # escolhe sozinho um `op` falso é um smoke que mente.
        env["PATH"] = f"{duple}{os.pathsep}{env.get('PATH', '')}"
    return env


# ---------------------------------------------------------------------------
# Processos filhos (modos internos deste mesmo arquivo)
# ---------------------------------------------------------------------------
def filho_presenca(nome_var: str) -> int:
    """Filho descartável: diz APENAS se a variável chegou preenchida.

    Não imprime comprimento (vaza entropia) nem hash (permite confirmar palpite).
    Valor ainda em forma de referência `op://` significa que `op run` não
    resolveu nada — presença falsa, e o pai trata como falha, não como ok.
    """
    valor = os.environ.get(nome_var)
    presente = bool(valor) and not valor.startswith("op://")
    sys.stdout.write(f"VARIAVEL_PRESENTE={'true' if presente else 'false'}\n")
    return 0


def filho_varredura(nome_var: str, arquivo: str) -> int:
    """Filho descartável que procura eco do valor SEM devolver o valor.

    Este é o único lugar do sistema que pode comparar contra o segredo: ele roda
    dentro do subprocesso de `op run`, que já o possui legitimamente, e exporta
    um único booleano. O processo pai nunca precisa conhecer o valor para
    conseguir a resposta.
    """
    valor = os.environ.get(nome_var, "")
    if not valor or valor.startswith("op://"):
        sys.stdout.write("ECO_DETECTADO=indeterminado\n")
        return 0
    if len(valor) < 8:
        # Valor curto casaria por acaso em qualquer log; a resposta honesta é
        # "não sei", não "não vazou".
        sys.stdout.write("ECO_DETECTADO=indeterminado\n")
        return 0
    try:
        conteudo = Path(arquivo).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        sys.stdout.write("ECO_DETECTADO=indeterminado\n")
        return 0
    sys.stdout.write(f"ECO_DETECTADO={'true' if valor in conteudo else 'false'}\n")
    return 0


def varrer_saida_filho(stdout: str, stderr: str, regex: re.Pattern[str]) -> tuple[bool, int]:
    """Lista-branca estrita: o filho só pode ter dito a linha canônica.

    O pai não conhece o valor, então não consegue procurar por ele — procurar
    exigiria possuí-lo, e possuí-lo já seria o vazamento. Invertemos o teste:
    QUALQUER byte fora da linha prevista conta como eco suspeito. É conservador
    de propósito: preferimos um falso `falha/vazamento` a um falso `ok`.
    """
    linhas = [l for l in stdout.splitlines() if l.strip()]
    ok_stdout = len(linhas) == 1 and bool(regex.match(linhas[0].strip()))
    bytes_inesperados = len(stderr.encode("utf-8"))
    if not ok_stdout:
        bytes_inesperados += len(stdout.encode("utf-8"))
    return (not ok_stdout or stderr.strip() != ""), bytes_inesperados


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
def preflight(argv: list[str], permitir_service_account: bool) -> list[str]:
    """Recusas que precisam acontecer ANTES de qualquer chamada ao `op`."""
    erros: list[str] = []
    if any("--no-masking" in arg for arg in argv):
        erros.append(
            "flag proibida: --no-masking. A documentação diz que segredos em "
            "stdout/stderr são ocultados por padrão e que essa é a única forma "
            "de desligar o mascaramento; um smoke que a usa deixa de ser seguro."
        )
    if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN") and not permitir_service_account:
        erros.append(
            "OP_SERVICE_ACCOUNT_TOKEN presente no ambiente. Service account é "
            "outro modelo de confiança (sem app, sem aprovação por Environment) "
            "e não é o que P03-T09 pede; use --permitir-service-account para "
            "assumir a troca conscientemente."
        )
    return erros


# ---------------------------------------------------------------------------
# Recibo
# ---------------------------------------------------------------------------
def calcular_run_id(argv: list[str]) -> str:
    """Determinístico a partir dos argumentos, e propositalmente irreversível.

    A referência `op://…` está em argv; por isso entra como digest e nunca em
    claro no recibo. Digest de LOCALIZADOR (não de segredo) é aceitável: ele não
    abre caminho para adivinhar um valor, só identifica a execução.
    """
    bruto = "\x1f".join(argv)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]


def forma_da_referencia(referencia: str | None) -> dict:
    """Só a FORMA da referência entra no recibo — nunca os segmentos."""
    if not referencia:
        return {"presente": False}
    corpo = referencia[len("op://"):] if referencia.startswith("op://") else referencia
    corpo, _, query = corpo.partition("?")
    segmentos = [s for s in corpo.split("/") if s]
    return {
        "presente": True,
        "esquema_op": referencia.startswith("op://"),
        "segmentos": len(segmentos),
        "tem_secao": len(segmentos) == 4,
        "query_param": sanitizar_nome(query) if query else None,
    }


def montar_recibo(**campos) -> dict:
    base = {
        "ferramenta": "onepassword-smoke",
        "tarefa": "P03-T09",
        "contrato_verificado_em": "2026-09-01 (www.1password.dev)",
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    base.update(campos)
    return base


# ---------------------------------------------------------------------------
# Fluxo principal do smoke
# ---------------------------------------------------------------------------
def rodar_smoke(args, argv: list[str]) -> tuple[dict, list[str]]:
    humano: list[str] = []
    verificado: list[str] = []
    nao_verificado: list[str] = []
    evidencia: dict = {}
    run_id = calcular_run_id(argv)

    # ⚠️ O LOCALIZADOR FORA DE argv. Este repositorio trata o `op://` como
    # sensivel em todo lugar: recusa ele em campo de prosa
    # (backend/app/asset_vault/dominio.py:163), descarta mensagem do banco que o
    # carregue (infraestrutura.py:94), e nenhuma rota de leitura o devolve. A
    # unica excecao era a linha de comando DESTE arquivo: passado por
    # `--referencia`, o endereco fica visivel em `ps` para qualquer processo
    # local enquanto a prova roda. `calcular_run_id` so protegia o recibo.
    #
    # `--referencia-arquivo` fecha essa fresta: argv passa a carregar um CAMINHO,
    # e o endereco entra por um arquivo que so o dono le. A flag antiga continua
    # valendo — quebrar quem ja a usa nao melhora nada — mas o recibo passa a
    # dizer por onde a referencia entrou, para que uma prova nao possa alegar
    # discricao que nao teve.
    origem_referencia = "argv" if args.referencia else "ausente"
    caminho_ref = getattr(args, "referencia_arquivo", None)
    if caminho_ref:
        alvo_ref = Path(caminho_ref)
        if not alvo_ref.is_file():
            humano.append(f"--referencia-arquivo: nao e um arquivo: {caminho_ref}")
            evidencia["referencia_arquivo_erro"] = "inexistente"
            return (
                montar_recibo(
                    run_id=run_id, estado="falha/preflight",
                    exit_code=ESTADOS["falha/preflight"], duple_em_uso=bool(args.duple),
                    duple_caminho=args.duple, plataforma=platform.system(),
                    referencia={"presente": False}, verificado=[],
                    nao_verificado=["nada foi executado"], evidencia=evidencia,
                    proximo_ato="aponte --referencia-arquivo para um arquivo existente",
                ),
                humano,
            )
        modo = alvo_ref.stat().st_mode & 0o077
        if modo:
            humano.append("--referencia-arquivo: o arquivo esta legivel por grupo/outros; use chmod 600")
            evidencia["referencia_arquivo_erro"] = "permissao_frouxa"
            return (
                montar_recibo(
                    run_id=run_id, estado="falha/preflight",
                    exit_code=ESTADOS["falha/preflight"], duple_em_uso=bool(args.duple),
                    duple_caminho=args.duple, plataforma=platform.system(),
                    referencia={"presente": False}, verificado=[],
                    nao_verificado=["nada foi executado"], evidencia=evidencia,
                    proximo_ato="chmod 600 no arquivo da referencia e rode de novo",
                ),
                humano,
            )
        args.referencia = alvo_ref.read_text(encoding="utf-8").strip()
        origem_referencia = "arquivo"
    evidencia["origem_da_referencia"] = origem_referencia

    def recibo(estado: str, proximo_ato: str) -> dict:
        return montar_recibo(
            run_id=run_id,
            estado=estado,
            exit_code=ESTADOS[estado],
            duple_em_uso=bool(args.duple),
            duple_caminho=args.duple,
            plataforma=platform.system(),
            referencia=forma_da_referencia(args.referencia),
            verificado=verificado,
            nao_verificado=nao_verificado,
            evidencia=evidencia,
            proximo_ato=proximo_ato,
        )

    erros = preflight(argv, args.permitir_service_account)
    if erros:
        evidencia["preflight_erros"] = erros
        nao_verificado.append("nada foi executado: o preflight recusou antes do `op`")
        humano.extend(f"preflight recusou: {e}" for e in erros)
        return recibo("falha/preflight", "corrija a invocação e rode de novo"), humano
    verificado.append("preflight: sem --no-masking e sem service account implícito")
    evidencia["variaveis_op_no_ambiente"] = sorted(
        k for k in os.environ if k.startswith("OP_")
    )  # NOMES apenas; valores nunca.

    env = montar_ambiente(args.duple)
    caminho_op = shutil.which("op", path=env["PATH"])
    if not caminho_op:
        nao_verificado.extend(
            [
                "app do 1Password",
                "sessão / conta",
                "listagem de nomes",
                "injeção em processo descartável",
            ]
        )
        evidencia["op_no_path"] = False
        humano.append("`op` não está no PATH.")
        return (
            recibo(
                "blocked/cli_ausente",
                "instale o app 1Password e o CLI, ligue Settings > Developer > "
                "'Integrate with 1Password CLI' e rode o smoke de novo",
            ),
            humano,
        )
    evidencia["op_no_path"] = True
    verificado.append("CLI `op` encontrado no PATH")

    rc, out, err = executar(comando_op(caminho_op, "--version"), env)
    evidencia["op_version_rc"] = rc
    evidencia["op_version"] = sanitizar_nome(out.strip()) if rc == 0 else None
    humano.append(f"op --version -> rc={rc} {sanitizar_nome(out.strip())}")

    # Presença do app: em macOS é um caminho no disco. Em outras plataformas a
    # documentação não define um caminho canônico, então dizemos "não verificado"
    # em vez de inventar um.
    if args.caminho_app:
        caminho_app = args.caminho_app
    elif platform.system() == "Darwin":
        caminho_app = "/Applications/1Password.app"
    else:
        caminho_app = None

    if caminho_app is None:
        nao_verificado.append(
            "presença do app: sem caminho canônico documentado fora do macOS; "
            "use --caminho-app"
        )
    else:
        evidencia["caminho_app_verificado"] = caminho_app
        if not Path(caminho_app).exists():
            nao_verificado.extend(
                ["sessão / conta", "listagem de nomes", "injeção em processo descartável"]
            )
            humano.append(f"app ausente em {caminho_app}")
            return (
                recibo(
                    "blocked/app_ausente",
                    "instale o app de desktop do 1Password; o CLI sozinho não "
                    "abre sessão neste modelo",
                ),
                humano,
            )
        verificado.append("app do 1Password presente no caminho verificado")

    rc, out, err = executar(comando_op(caminho_op, "account", "list", "--format=json"), env)
    # Varre stdout também: nem todo CLI manda erro só para stderr, e um erro
    # documentado lido no lugar errado viraria um falso "sessão viva".
    etiqueta = classificar_erro(err + "\n" + out)
    if rc == 0 and not etiqueta.startswith("documentado:"):
        etiqueta = "sem_erro"
    evidencia["account_list_rc"] = rc
    evidencia["account_list_classificacao"] = etiqueta
    if rc != 0 or etiqueta.startswith("documentado:"):
        nao_verificado.extend(["listagem de nomes", "injeção em processo descartável"])
        humano.append(f"op account list -> rc={rc} ({etiqueta})")
        return (
            recibo(
                "blocked/sem_sessao",
                "destranque o app, confirme Settings > Developer > 'Integrate "
                "with 1Password CLI' e refaça o login da conta",
            ),
            humano,
        )
    try:
        contas = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        contas = []
    evidencia["contas_encontradas"] = len(contas)
    if not contas:
        nao_verificado.extend(["listagem de nomes", "injeção em processo descartável"])
        humano.append("op account list devolveu zero contas")
        return (
            recibo("blocked/sem_sessao", "adicione a conta ao CLI e rode de novo"),
            humano,
        )
    verificado.append("sessão viva: `op account list` respondeu com pelo menos uma conta")

    rc, out, err = executar(comando_op(caminho_op, "vault", "list", "--format=json"), env)
    if rc != 0:
        evidencia["vault_list_classificacao"] = classificar_erro(err)
        nao_verificado.append("injeção em processo descartável")
        humano.append(f"op vault list -> rc={rc}")
        return (
            recibo("blocked/sem_sessao", "confira as permissões da conta no app"),
            humano,
        )
    try:
        cofres = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        cofres = []
    nomes_cofres = [sanitizar_nome(c.get("name", "")) for c in cofres if isinstance(c, dict)]
    evidencia["cofres_listados"] = len(nomes_cofres)
    verificado.append("nomes de cofres listados (só nomes, saída sanitizada)")
    if not args.json:
        humano.append("cofres: " + ", ".join(nomes_cofres[:MAX_NOMES_IMPRESSOS]))

    if not args.referencia:
        nao_verificado.append("injeção em processo descartável: nenhuma referência informada")
        humano.append("sem --referencia op://<vault>/<item>/<campo>: nada a injetar")
        return (
            recibo(
                "blocked/referencia_ausente",
                "crie o Environment e passe --referencia op://<vault>/<item>/<campo>",
            ),
            humano,
        )

    segmentos = args.referencia[len("op://"):].partition("?")[0].split("/")
    cofre_alvo = segmentos[0] if segmentos else ""
    achou_cofre = any(
        n == sanitizar_nome(cofre_alvo) for n in nomes_cofres
    ) or bool(RE_ID_OP.fullmatch(cofre_alvo))
    evidencia["cofre_da_referencia_na_lista"] = achou_cofre
    if not achou_cofre:
        nao_verificado.append("injeção em processo descartável")
        humano.append("o cofre da referência não apareceu na lista de nomes")
        return (
            recibo(
                "blocked/referencia_ausente",
                "confira o nome/UUID do cofre da referência contra `op vault list`",
            ),
            humano,
        )

    rc, out, err = executar(
        comando_op(caminho_op, "item", "list", "--vault", cofre_alvo, "--format=json"), env
    )
    if rc == 0:
        try:
            itens = json.loads(out) if out.strip() else []
        except json.JSONDecodeError:
            itens = []
        nomes_itens = [
            sanitizar_nome(i.get("title", "")) for i in itens if isinstance(i, dict)
        ]
        evidencia["itens_listados"] = len(nomes_itens)
        verificado.append("nomes de itens listados (só nomes, saída sanitizada)")
        if not args.json:
            humano.append("itens: " + ", ".join(nomes_itens[:MAX_NOMES_IMPRESSOS]))
    else:
        evidencia["item_list_rc"] = rc
        nao_verificado.append("listagem de itens do cofre alvo")

    # --- injeção em processo descartável -----------------------------------
    trabalho = tempfile.mkdtemp(prefix="volc-1p-smoke-")
    os.chmod(trabalho, 0o700)
    rc = rc_v = None
    suspeito_1 = suspeito_2 = False
    try:
        env_injecao = dict(env)
        env_injecao[args.nome_var] = args.referencia
        alvo = [
            *comando_op(caminho_op),
            "run",
            "--",
            sys.executable,
            os.path.abspath(__file__),
            "--filho-presenca",
            "--nome-var",
            args.nome_var,
        ]
        rc, out, err = executar(alvo, env_injecao)
        evidencia["op_run_rc"] = rc
        etiqueta = classificar_erro(err)
        evidencia["op_run_classificacao"] = etiqueta

        suspeito_1, bytes_1 = varrer_saida_filho(out, err, RE_PRESENCA)
        evidencia["bytes_inesperados_filho_presenca"] = bytes_1

        # A varredura por eco roda dentro de `op run`: só lá o valor existe.
        arquivo_varredura = Path(trabalho) / "capturado.txt"
        arquivo_varredura.write_text(
            "\n".join(
                [
                    out,
                    err,
                    json.dumps(evidencia, ensure_ascii=False),
                    "\n".join(humano),
                ]
            ),
            encoding="utf-8",
        )
        os.chmod(arquivo_varredura, 0o600)
        alvo_varredura = [
            *comando_op(caminho_op),
            "run",
            "--",
            sys.executable,
            os.path.abspath(__file__),
            "--filho-varredura",
            "--nome-var",
            args.nome_var,
            "--arquivo",
            str(arquivo_varredura),
        ]
        rc_v, out_v, err_v = executar(alvo_varredura, env_injecao)
        suspeito_2, bytes_2 = varrer_saida_filho(out_v, err_v, RE_ECO)
        evidencia["bytes_inesperados_filho_varredura"] = bytes_2
        veredito_eco = None
        m = RE_ECO.match(out_v.strip().splitlines()[0].strip()) if out_v.strip() else None
        if m:
            veredito_eco = m.group(1)
        evidencia["varredura_por_valor"] = veredito_eco
        evidencia["op_run_varredura_rc"] = rc_v
    finally:
        # O arquivo capturado pode conter o eco de um segredo. Ele morre aqui.
        shutil.rmtree(trabalho, ignore_errors=True)

    # ⚠️ A ORDEM AQUI E A CORRECAO. A versao anterior perguntava "houve eco
    # suspeito?" ANTES de "o `op run` sequer funcionou?" — e `varrer_saida_filho`
    # devolve suspeito para QUALQUER saida fora da linha canonica. Quando o
    # `op run` falha, o filho nem chega a rodar: stdout vem vazio e stderr traz o
    # erro do proprio `op`. Isso e sempre suspeito. Consequencias medidas:
    #
    #   * a classificacao por rc logo abaixo era CODIGO MORTO;
    #   * `blocked/sem_sessao` (12) e `blocked/aprovacao_negada` (13) eram
    #     inalcancaveis — e sao exatamente os dois estados que a prova de
    #     revogacao precisa ler;
    #   * TRAVAR o 1Password, que e o comportamento seguro esperado, era
    #     reportado como `falha/vazamento` — um alarme de vazamento onde nao
    #     houve vazamento nenhum, no unico sinal que ninguem pode aprender a
    #     ignorar.
    #
    # A postura conservadora do docstring de `varrer_saida_filho` ("preferimos um
    # falso vazamento a um falso ok") continua valendo onde ela informa: se a
    # injecao ACONTECEU (rc 0) e ainda assim a saida fugiu da linha canonica,
    # isso e eco. O veredito da varredura interna — a unica camada que de fato
    # procura o valor, porque roda dentro do `op run` onde ele existe — vale
    # sempre, com rc qualquer.
    eco_confirmado = veredito_eco == "true"
    eco_por_saida = (rc == 0 and suspeito_1) or (rc_v == 0 and suspeito_2)
    if eco_confirmado or eco_por_saida:
        motivos = []
        if eco_confirmado:
            motivos.append("valor encontrado na saída capturada (varredura interna)")
        if rc == 0 and suspeito_1:
            motivos.append("saída inesperada do filho de presença")
        if rc_v == 0 and suspeito_2:
            motivos.append("saída inesperada do filho de varredura")
        evidencia["motivos_vazamento"] = motivos
        nao_verificado.append("injeção NÃO pode ser declarada boa: houve eco suspeito")
        humano.append("VAZAMENTO: " + "; ".join(motivos))
        return (
            recibo(
                "falha/vazamento",
                "não use este ambiente para segredos reais até a origem do eco "
                "ser removida; confira se algum wrapper usa --no-masking",
            ),
            humano,
        )

    if rc != 0:
        if etiqueta.startswith("documentado:"):
            estado = "blocked/sem_sessao"
            ato = "destranque o app; a aprovação vale só até o 1Password travar"
        elif etiqueta.startswith("heuristica_aprovacao:"):
            estado = "blocked/aprovacao_negada"
            ato = "aprove o Environment no app do 1Password e rode de novo"
        else:
            estado = "falha/interna"
            ato = "rode o comando `op run` à mão para ler o erro completo"
        nao_verificado.append("injeção em processo descartável")
        humano.append(f"op run -> rc={rc} ({etiqueta})")
        return recibo(estado, ato), humano

    presente = out.strip() == "VARIAVEL_PRESENTE=true"
    evidencia["presenca_confirmada"] = presente
    if not presente:
        nao_verificado.append("injeção: `op run` saiu 0 mas o filho não viu segredo")
        humano.append("op run saiu 0 sem injetar nada")
        return (
            recibo(
                "falha/injecao_nao_ocorreu",
                "confira se a referência aponta para um campo existente",
            ),
            humano,
        )
    if veredito_eco != "false":
        nao_verificado.append(
            "varredura por valor ficou indeterminada; ausência de vazamento não provada"
        )
        humano.append("varredura por valor indeterminada")
        return (
            recibo(
                "falha/interna",
                "verifique se o campo alvo tem ao menos 8 caracteres para a "
                "varredura ser conclusiva",
            ),
            humano,
        )

    verificado.append("injeção confirmada por presença booleana em processo descartável")
    verificado.append("varredura interna não achou eco do valor na saída capturada")
    nao_verificado.extend(
        [
            "corretude do valor injetado (o smoke não lê o segredo, de propósito)",
            "comprimento e hash do valor (proibidos: vazam entropia e confirmam palpite)",
            "durabilidade da aprovação (a documentação diz que vale até o 1Password travar)",
        ]
    )
    humano.append("ok: variável injetada e presença confirmada sem revelar valor")
    return recibo("ok", "nenhum: a cadeia foi provada nesta execução"), humano


# ---------------------------------------------------------------------------
# Autoteste com duplê controlado
# ---------------------------------------------------------------------------
VALOR_DE_TESTE = "VALOR-DE-TESTE-DUPLE-8f3a91c2e7b45d60"


def preparar_duple(base: Path, modo: str) -> Path:
    """Materializa o duplê num diretório temporário próprio de cada prova."""
    origem = Path(__file__).resolve().parent / "duple_op.py"
    destino = base / modo
    (destino / "1Password.app").mkdir(parents=True, exist_ok=True)
    alvo = destino / "op"
    shutil.copyfile(origem, alvo)
    os.chmod(alvo, 0o700)
    return destino


def autoteste() -> int:
    base = Path(tempfile.mkdtemp(prefix="volc-1p-autoteste-"))
    logs = base / "logs"
    logs.mkdir()
    referencia = "op://duple-vault/duple-item/credencial"
    arquivo_referencia = base / "referencia.txt"
    arquivo_referencia.write_text(referencia, encoding="utf-8")
    os.chmod(arquivo_referencia, 0o600)
    # O último campo é a classificação EXIGIDA de `op account list`. Sem ele,
    # uma prova de teste-mutante mostrou que c e d passavam mesmo com os padrões
    # documentados quebrados: qualquer rc != 0 já cai em blocked/sem_sessao.
    # A prova precisa exigir que a string documentada tenha sido RECONHECIDA.
    provas: list[tuple[str, str, list[str], str, str, str | None]] = [
        ("a", "caminho feliz produz ok", ["--referencia", referencia], "feliz", "ok", None),
        ("b", "duplê que ecoa é pego", ["--referencia", referencia], "vazamento", "falha/vazamento", None),
        ("c", "app bloqueado (LostConnectionToApp)", ["--referencia", referencia], "app_bloqueado", "blocked/sem_sessao", "documentado:lostconnectiontoapp"),
        ("d", "No accounts configured", ["--referencia", referencia], "sem_contas", "blocked/sem_sessao", "documentado:no accounts configured"),
        ("e", "--no-masking recusado", ["--referencia", referencia, "--no-masking"], "feliz", "falha/preflight", None),
        # ⚠️ PROVA g — a regressao do defeito que tornava a revogacao ilegivel.
        # Antes da correcao, QUALQUER falha do `op run` casava a varredura de eco
        # (stdout vazio nao e a linha canonica) e voltava `falha/vazamento`/20,
        # tornando `blocked/aprovacao_negada`/13 codigo morto. Travar o
        # 1Password — o comportamento seguro — era reportado como vazamento.
        ("g", "aprovacao negada vira blocked/13, nao vazamento/20",
         ["--referencia", referencia], "aprovacao_negada", "blocked/aprovacao_negada",
         "heuristica_aprovacao:authorization"),
        # ⚠️ PROVA h — o localizador entra por arquivo 0600 e nao por argv.
        ("h", "referencia por arquivo 0600 (fora de argv)",
         ["--referencia-arquivo", str(arquivo_referencia)], "feliz", "ok", None),
    ]
    falhas = 0
    for chave, titulo, extra, modo, esperado, classificacao_esperada in provas:
        dir_duple = preparar_duple(base, modo)
        env = os.environ.copy()
        env["VOLC_DUPLE_MODO"] = modo
        env["VOLC_DUPLE_VALOR"] = VALOR_DE_TESTE
        cmd = [
            sys.executable,
            os.path.abspath(__file__),
            "--json",
            "--duple",
            str(dir_duple),
            "--caminho-app",
            str(dir_duple / "1Password.app"),
        ] + extra
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=120, check=False
        )
        (logs / f"prova-{chave}.stdout").write_text(proc.stdout, encoding="utf-8")
        (logs / f"prova-{chave}.stderr").write_text(proc.stderr, encoding="utf-8")
        try:
            rec = json.loads(proc.stdout)
            obtido = rec.get("estado")
            exit_esperado = ESTADOS[esperado]
        except json.JSONDecodeError:
            rec, obtido, exit_esperado = {}, "<recibo ilegível>", -1
        ok_estado = obtido == esperado
        ok_exit = proc.returncode == exit_esperado
        detalhe = ""
        if chave == "a":
            ok_extra = rec.get("evidencia", {}).get("presenca_confirmada") is True
            detalhe = f" presenca_confirmada={rec.get('evidencia', {}).get('presenca_confirmada')}"
        elif chave == "b":
            ok_extra = proc.returncode != 0 and rec.get("evidencia", {}).get(
                "varredura_por_valor"
            ) == "true"
            detalhe = f" varredura_por_valor={rec.get('evidencia', {}).get('varredura_por_valor')}"
        elif chave in ("c", "d"):
            obtida = rec.get("evidencia", {}).get("account_list_classificacao")
            ok_extra = obtido != "ok" and obtida == classificacao_esperada
            detalhe = f" classificacao={obtida} (exigida {classificacao_esperada})"
        elif chave == "g":
            # Nao basta o estado: a etiqueta tem de provar que a recusa foi
            # RECONHECIDA como aprovacao negada, e nao que qualquer rc!=0 caiu
            # aqui por acidente.
            obtida = rec.get("evidencia", {}).get("op_run_classificacao")
            ok_extra = obtido != "ok" and obtida == classificacao_esperada
            detalhe = f" classificacao={obtida} (exigida {classificacao_esperada})"
        elif chave == "h":
            origem = rec.get("evidencia", {}).get("origem_da_referencia")
            ok_extra = (
                origem == "arquivo"
                and rec.get("evidencia", {}).get("presenca_confirmada") is True
            )
            detalhe = f" origem_da_referencia={origem}"
        else:
            ok_extra = obtido != "ok"
        passou = ok_estado and ok_exit and ok_extra
        falhas += 0 if passou else 1
        print(
            f"[{'PASSOU' if passou else 'FALHOU'}] prova {chave}: {titulo} -> "
            f"estado={obtido} exit={proc.returncode} (esperado {esperado}/{exit_esperado}){detalhe}"
        )

    # Prova (f): o valor de teste não pode existir em recibo nenhum nem em log
    # nenhum produzido pelo smoke.
    achados = []
    for arquivo in sorted(logs.iterdir()):
        if VALOR_DE_TESTE in arquivo.read_text(encoding="utf-8", errors="replace"):
            achados.append(arquivo.name)
    passou_f = not achados
    falhas += 0 if passou_f else 1
    print(
        f"[{'PASSOU' if passou_f else 'FALHOU'}] prova f: recibos e logs não contêm "
        f"o valor de teste -> arquivos varridos={len(list(logs.iterdir()))} "
        f"contaminados={achados or 'nenhum'}"
    )
    print(f"logs do autoteste: {logs}")
    print(f"resultado: {'0 falhas' if falhas == 0 else f'{falhas} falha(s)'}")
    return 0 if falhas == 0 else 1


# ---------------------------------------------------------------------------
def principal(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description="Smoke seguro do 1Password local (P03-T09).",
        allow_abbrev=False,
    )
    p.add_argument("--referencia", help="op://<vault>/<item>/[secao/]<campo>")
    p.add_argument(
        "--referencia-arquivo",
        help="arquivo 0600 contendo SO a referencia op://; mantem o localizador fora de argv",
    )
    p.add_argument("--nome-var", default=NOME_VAR_PADRAO)
    p.add_argument("--duple", help="diretório do duplê; SEM esta flag o smoke usa o `op` real")
    p.add_argument("--caminho-app", help="caminho do 1Password.app (padrão /Applications no macOS)")
    p.add_argument("--permitir-service-account", action="store_true")
    p.add_argument("--json", action="store_true", help="imprime só o recibo")
    p.add_argument("--autoteste", action="store_true")
    p.add_argument("--filho-presenca", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--filho-varredura", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--arquivo", help=argparse.SUPPRESS)
    args, desconhecidos = p.parse_known_args(argv)

    if args.filho_presenca:
        return filho_presenca(args.nome_var)
    if args.filho_varredura:
        return filho_varredura(args.nome_var, args.arquivo or "")
    if args.autoteste:
        return autoteste()

    # `parse_known_args` existe para que `--no-masking` chegue VIVO ao preflight
    # em vez de morrer num "unrecognized arguments" do argparse: a recusa tem de
    # ser nossa, com estado e exit code próprios.
    del desconhecidos
    recibo, humano = rodar_smoke(args, argv)
    if args.json:
        print(json.dumps(recibo, ensure_ascii=False, indent=2))
    else:
        for linha in humano:
            print(linha)
        print(json.dumps(recibo, ensure_ascii=False, indent=2))
    return recibo["exit_code"]


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
