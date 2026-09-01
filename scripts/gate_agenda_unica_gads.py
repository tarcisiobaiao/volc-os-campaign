#!/usr/bin/env python3
"""Prova que só EXISTE uma autoridade de agenda para a família Google Ads — e que
ela ainda não está ligada.

## O que este gate alega, e o que ele mede

A alegação sustentada é estreita e verdadeira:

1. **nenhuma unit systemd da família está instalada, habilitada ou ativa nesta
   máquina** — medido em `systemctl`, e não deduzido dos arquivos do repositório;
2. **os dois workflows n8n nascem inativos** no artefato versionado;
3. **nenhum artefato rastreado agenda a família por um terceiro caminho** —
   cron, `scheduleTrigger` de outro fluxo, Vercel cron ou timer;
4. **nenhum artefato rastreado chama a API de ativação do n8n.**

## O que ele NÃO é, dito antes que alguém conclua sozinho

Não é inspeção do servidor Hetzner nem da instância n8n viva. Ele mede ESTA
máquina e ESTE repositório. O estado real da instância n8n permanece
`REAL_N8N_READ_NOT_PROVEN` — e é exatamente por isso que o pacote de autorização
começa por uma conferência humana no painel.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    RAIZ / "n8n" / "volc_gads_campanha_dia_d0.json",
    RAIZ / "n8n" / "volc_gads_campanha_dia_d1.json",
]
UNITS = [
    "volc-google-intelligence@frequente.service",
    "volc-google-intelligence@completa.service",
    "volc-google-intelligence-frequente.timer",
    "volc-google-intelligence-completa.timer",
    "volc-gads-dia-d0.timer",
    "volc-gads-dia-d1.timer",
]

ok = 0
falhas: list[str] = []
pulados: list[str] = []


def prova(nome: str, condicao: bool, detalhe: str = "") -> None:
    global ok
    if condicao:
        ok += 1
        print(f"  ok   {nome}")
    else:
        falhas.append(nome)
        print(f"  FALHOU  {nome}{(' — ' + detalhe) if detalhe else ''}")


def pula(nome: str, motivo: str) -> None:
    pulados.append(nome)
    print(f"  PULADO  {nome} — {motivo}")


def rastreados() -> list[Path]:
    saida = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True,
                           text=True, check=True).stdout
    return [RAIZ / linha for linha in saida.splitlines() if linha]


print("── 1. systemd desta máquina")
if shutil.which("systemctl") is None:
    pula("nenhuma unit da família instalada", "systemctl não está no PATH")
else:
    instaladas = []
    ativas = []
    for unit in UNITS:
        p = subprocess.run(["systemctl", "list-unit-files", unit],
                           capture_output=True, text=True)
        if unit in p.stdout:
            instaladas.append(unit)
        e = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
        if e.stdout.strip() == "active":
            ativas.append(unit)
    prova("nenhuma unit da família está INSTALADA", not instaladas, ", ".join(instaladas))
    prova("nenhuma unit da família está ATIVA", not ativas, ", ".join(ativas))

    t = subprocess.run(["systemctl", "list-timers", "--all", "--no-pager"],
                       capture_output=True, text=True)
    agendados = [ln for ln in t.stdout.splitlines()
                 if "volc-google-intelligence" in ln or "volc-gads" in ln]
    prova("nenhum timer da família aparece em list-timers", not agendados,
          "; ".join(agendados))

    presentes = [
        p.name for p in Path("/etc/systemd/system").glob("volc-*")
    ] if Path("/etc/systemd/system").exists() else []
    prova("nenhuma unit da família copiada para /etc/systemd/system",
          not presentes, ", ".join(presentes))

print("\n── 2. os workflows n8n versionados")
for caminho in WORKFLOWS:
    wf = json.loads(caminho.read_text(encoding="utf-8"))
    prova(f"{caminho.name} nasce inativo", wf.get("active") is False)
    prova(f"{caminho.name} declara o estado no meta",
          "INATIVO" in str(wf.get("meta", {}).get("volc", {}).get("estado", "")))

print("\n── 3. agendas capazes de rodar, no repositório rastreado")
#
# ⚠️ A primeira versão varria TODO arquivo que mencionasse "google ads" e
# acusava documentação, inventário e um SQL com uma linha parecida com crontab.
# Um gate que aponta um `.md` como "segunda agenda" ensina a ignorar o gate. A
# varredura agora é por artefato CAPAZ de agendar, não por menção.
CAPAZES = {
    ".timer": re.compile(r"OnCalendar="),
    ".service": re.compile(r"OnCalendar="),
    ".cron": re.compile(r"."),
}
GADS = re.compile(r"(?i)google[_ -]?ads|googleads|gads")

achados: list[str] = []
for arquivo in rastreados():
    if not arquivo.is_file():
        continue
    rel = str(arquivo.relative_to(RAIZ))
    padrao = None
    if arquivo.suffix in CAPAZES:
        padrao = CAPAZES[arquivo.suffix]
    elif rel.startswith("n8n/") and arquivo.suffix == ".json":
        padrao = re.compile(r"scheduleTrigger")
    elif arquivo.name in {"vercel.json", "railway.json"}:
        padrao = re.compile(r'"crons"\s*:')
    if padrao is None:
        continue
    try:
        texto = arquivo.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    if padrao.search(texto):
        achados.append(rel)

# Os dois workflows desta entrega são a autoridade escolhida (e nascem inativos);
# o pacote systemd está versionado como ALTERNATIVA declarada e não instalada.
ESPERADOS = {
    "n8n/volc_gads_campanha_dia_d0.json",
    "n8n/volc_gads_campanha_dia_d1.json",
    "n8n/joinads_report_day_before.json",
    "n8n/joinads_report_intraday.json",
    "n8n/joinads_day_before_simplificado.json",
    "deploy/google-intelligence/volc-google-intelligence-frequente.timer",
    "deploy/google-intelligence/volc-google-intelligence-completa.timer",
}
inesperados = sorted(set(achados) - ESPERADOS)
prova("nenhum artefato capaz de agendar apareceu fora do conjunto declarado",
      not inesperados, "; ".join(inesperados))
prova("a alternativa systemd continua versionada e não instalada",
      all(e in achados for e in ESPERADOS if e.startswith("deploy/")))

joinads = [a for a in achados if "joinads" in a]
prova("os fluxos JoinAds agendados são de RECEITA, não da família Google Ads",
      all(not GADS.search(Path(RAIZ / a).read_text(encoding="utf-8")) for a in joinads),
      ", ".join(joinads))

print("\n── 3-bis. a instância n8n viva — o que o repositório NÃO prova")
#
# ⚠️ AQUI MORA O RISCO REAL DE AGENDA DUPLA, e ele não é deste repositório.
# O inventário sanitizado (snapshot de 19/08/2026) registra workflows da família
# Google Ads com gatilho de agenda e `ativo: true` na instância viva. Este gate
# não fala com o n8n; ele NOMEIA os candidatos para que a ativação não aconteça
# antes de alguém conferir no painel.
INVENTARIO = RAIZ / "docs" / "volc-os-graph" / "inventario-n8n-sanitizado.json"
conflitos: list[str] = []
if INVENTARIO.exists():
    inv = json.loads(INVENTARIO.read_text(encoding="utf-8"))
    for w in inv.get("workflows", []):
        if "schedule" not in w.get("gatilhos_tipos", []):
            continue
        if not w.get("ativo"):
            continue
        if GADS.search(w.get("slug", "")) or GADS.search(w.get("nome", "")):
            conflitos.append(f"{w['slug']} (camada {w.get('camada')})")
    prova("o inventário versionado foi consultado, não presumido", True)
else:
    pula("inventário n8n sanitizado", "arquivo ausente")

if conflitos:
    pula("agenda única CONFIRMADA na instância viva",
         "REAL_N8N_READ_NOT_PROVEN — o inventário de 19/08 registra "
         f"{len(conflitos)} workflow(s) da família com agenda ATIVA: "
         + "; ".join(sorted(conflitos))
         + ". Conferir e desligar no painel é PRÉ-CONDIÇÃO de ativação "
           "(docs/closure/hermes-p10-t16-n8n-ledger-v12-v1/AUTORIZACAO-ATIVACAO.md)")
else:
    prova("nenhum workflow da família com agenda ativa no inventário versionado", True)

print("\n── 4. nenhuma chamada de ativação da API do n8n")
#
# ⚠️ A varredura é sobre artefato CAPAZ de fazer a chamada — código e
# configuração —, não sobre texto que a menciona. A primeira versão varria tudo e
# acusou a própria MATRIZ-CONTRAPROVAS.json, que descreve o padrão proibido. Um
# gate que aponta a documentação da proibição como violação da proibição ensina a
# ignorar o gate, e é a segunda vez que esse mesmo defeito aparece nesta lane.
ativacao = re.compile(r"/(?:api/v1|rest)/workflows/[^\"'\s]*/activate")
EXECUTAVEIS = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".sh", ".bash",
               ".yml", ".yaml", ".toml", ".env"}
achados_ativacao = []
for arquivo in rastreados():
    if not arquivo.is_file():
        continue
    rel = str(arquivo.relative_to(RAIZ))
    executavel = arquivo.suffix in EXECUTAVEIS or (
        arquivo.suffix == ".json" and not rel.startswith("docs/"))
    if not executavel:
        continue
    try:
        texto = arquivo.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    if ativacao.search(texto):
        achados_ativacao.append(rel)
prova("nenhum artefato executável ativa workflow por API", not achados_ativacao,
      ", ".join(achados_ativacao))

# E o nó `n8n` do próprio n8n (que fala com a API dele) não pode estar em fluxo
# nenhum desta família.
no_n8n = [str(w.relative_to(RAIZ)) for w in WORKFLOWS
          if "n8n-nodes-base.n8n" in w.read_text(encoding="utf-8")]
prova("nenhum workflow desta família usa o nó da API do n8n", not no_n8n,
      ", ".join(no_n8n))

print()
print("════════════════════════════════════════════════════════")
print(f"  passaram {ok} · falharam {len(falhas)} · pulados {len(pulados)}")
if falhas:
    for f in falhas:
        print(f"    ✗ {f}")
    sys.exit(1)
print("  UMA autoridade de agenda escolhida (n8n) e NENHUMA ligada")
