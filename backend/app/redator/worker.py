"""O worker do redator — dispara o motor como PROCESSO e acompanha o andamento.

## Por que processo separado, e não uma thread

O funnelforge é 100% síncrono, depende do diretório atual (lê `config.yaml`,
`.env` e escreve em `runs/` por caminho relativo) e faz `os.environ.setdefault`
das chaves de LLM no import. Numa thread dentro do backend isso significa:

- as chaves do PRIMEIRO projeto que rodar ficam valendo para todos os seguintes;
- um `os.chdir` de um run atrapalha qualquer outro código do processo;
- não há como impor timeout nem cancelar — `run_pipeline` não aceita deadline
  nem token de cancelamento;
- um estouro de memória no motor derruba a API junto.

Processo separado resolve os quatro de uma vez, e de graça: o isolamento é o do
sistema operacional, não um que eu precise escrever.

## Como o andamento chega até a tela

O motor já grava `runs/<run_id>/state.json` a cada etapa, com escrita atômica
(write-then-rename). O worker não inventa protocolo nenhum: ele LÊ esse arquivo
e traduz para a linha de `pautador_funnel_runs`. Se o backend cair no meio, o
arquivo continua lá e o estado é recuperável.

⚠️ O `runs_dir` é `runs/` para TODOS os runs, de propósito: é onde vive o
`_phrase_registry.json`, que garante que duas páginas de funis diferentes não
abram com a mesma frase. Dar um diretório por run mataria essa garantia. Por
isso o worker FIXA o timestamp do run e descobre a pasta por ele
(`runs/*-<timestamp>`), em vez de tentar adivinhar o slug — que o `dedupe_slugs`
pode mudar.

## O que este módulo protege

1. **A senha.** O perfil vai para um arquivo temporário com permissão 0600, em
   diretório 0700, e é apagado no `finally` — inclusive quando o processo morre.
   Nada dele entra em log; o que se registra é `perfil_para_log`.
2. **O bolso.** Teto de execuções simultâneas: dois runs em paralelo custam o
   dobro e ninguém pediu isso. E um timeout duro mata processo travado.
3. **A fila.** Um run por (card, site) — o disparo já recusa duplicata, e aqui a
   reconciliação de startup fecha o que ficou órfão de um backend reiniciado.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("volc.redator.worker")

# Teto de runs simultâneos. Dois funis em paralelo custam o dobro e demoram o
# mesmo; o gargalo é a API do LLM, não a CPU. Um de cada vez é o padrão honesto.
MAX_SIMULTANEOS = 1

# Um funil de 5 páginas leva ~45 min. O teto é folgado de propósito: ele existe
# para matar processo TRAVADO (rede pendurada, browser que não fecha), não para
# interromper trabalho legítimo.
TIMEOUT_S = 3 * 60 * 60

_semaforo = asyncio.Semaphore(MAX_SIMULTANEOS)
# {id da linha em pautador_funnel_runs: processo}
_em_execucao: Dict[int, asyncio.subprocess.Process] = {}


def raiz_do_motor() -> Path:
    """Onde o motor mora. Ele PRECISA rodar com isto como diretório atual."""
    aqui = Path(__file__).resolve()
    # backend/app/redator/worker.py -> sobe 4 níveis até a raiz do repositório
    return aqui.parents[3] / "funnelforge-migracao" / "engine"


class MotorIndisponivel(RuntimeError):
    """O motor não está instalado onde deveria, ou o venv dele não existe."""


def _executavel() -> Path:
    """O SCRIPT DE CONSOLE do motor, não o interpretador.

    ⚠️ Não use `python -m funnelforge`: o pacote não tem `__main__.py` e o
    Python recusa com "'funnelforge' is a package and cannot be directly
    executed". O ponto de entrada é o console script que o `pip install -e`
    cria a partir do `[project.scripts]` do pyproject.
    """
    raiz = raiz_do_motor()
    exe = raiz / ".venv" / "bin" / "funnelforge"
    if not exe.exists():
        raise MotorIndisponivel(
            f"O comando do motor não existe em {exe}. Rode: cd {raiz} && "
            f"python3 -m venv .venv && .venv/bin/pip install -e '.[dev,screenshots]'"
        )
    if not (raiz / "config.yaml").exists():
        raise MotorIndisponivel(f"config.yaml não encontrado em {raiz}")
    return exe


def _carimbo() -> str:
    """O timestamp que vira sufixo do `run_id` do motor.

    Fixado por nós de propósito: é a única forma de achar a pasta do run sem
    depender do slug, que o `dedupe_slugs` do motor pode alterar.
    """
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _achar_run_dir(raiz: Path, carimbo: str) -> Optional[Path]:
    """A pasta cujo nome termina no nosso carimbo. `None` até o motor criá-la."""
    runs = raiz / "runs"
    if not runs.is_dir():
        return None
    candidatas = [d for d in runs.iterdir() if d.is_dir() and d.name.endswith(carimbo)]
    if not candidatas:
        return None
    # `_pending-<carimbo>` é o nome provisório; quando o plano existe, o motor
    # renomeia para `<slug>-<carimbo>`. Se as duas aparecerem, a definitiva vence.
    definitivas = [d for d in candidatas if not d.name.startswith("_pending")]
    return (definitivas or candidatas)[0]


def _ler_estado(run_dir: Path) -> Optional[dict]:
    """Lê o `state.json` tolerando leitura no meio de uma escrita.

    O motor grava com write-then-rename, então o arquivo nunca fica pela metade
    — mas ele pode não existir ainda entre o rename e a próxima leitura.
    """
    p = run_dir / "state.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def resumo_do_estado(estado: dict, flags: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Traduz o `state.json` do motor para o que a linha do run guarda.

    Aqui mora a única regra de negócio deste módulo: o que conta como etapa
    concluída, e o que conta como página pronta.
    """
    passos = estado.get("step_status") or {}
    concluidos = sum(1 for r in passos.values()
                     if (r or {}).get("status") in ("OK", "RETRIED", "FALLBACK"))
    falhados = [k for k, r in passos.items() if (r or {}).get("status") == "FAILED"]
    custo = sum(float((r or {}).get("cost_usd") or 0.0) for r in passos.values())

    plano = estado.get("plan") or {}
    paginas = plano.get("pages") or []
    # Página "pronta" é a que passou pelo build — antes disso não existe artefato.
    prontas = sum(1 for p in paginas
                  if (passos.get(f"build_p{p.get('page_number')}") or {}).get("status")
                  in ("OK", "RETRIED", "FALLBACK"))

    # ── a matriz ──────────────────────────────────────────────────────────
    #
    # O dicionário completo de etapas já estava sendo calculado aqui e
    # DESCARTADO pelo filtro `_COLUNAS`. Agora ele vai para a linha junto com a
    # máscara por página, porque ausência de chave é ambígua por construção e só
    # o servidor conhece papéis e flags para desambiguar. Ver `matriz.py`.
    from app.redator import matriz as mz

    grade = mz.montar(estado, flags=flags)

    # O que o WordPress devolveu — VERBATIM, e não remontado a partir do slug.
    # É por igualdade de string com `campaign_funnel_urls` que a receita do
    # AdSense é atribuída ao clique comprado; um `-2` acrescentado pelo WP e não
    # capturado aqui zera a atribuição em silêncio.
    publicadas = [p for p in (estado.get("published") or {}).values() if p]
    lp = next((p for p in publicadas
               if str(p.get("role", "")).upper() == "LP"), None)

    return {
        "run_id": estado.get("run_id"),
        "paginas_planejadas": len(paginas) or None,
        "paginas_geradas": prontas or None,
        "custo_usd": round(custo, 6) if custo else None,
        "etapas_concluidas": concluidos,
        "etapas_falhadas": falhados,
        "passos": passos,
        "paginas": grade["paginas"],
        "passos_hash": mz.impressao(passos),
        "paginas_publicadas": publicadas,
        # ⚠️ De um RASCUNHO o WP devolve `?post_type=r&p=2146`, não o permalink:
        # o `/r/<slug>/` só nasce quando o post vai ao ar. Guardamos o que ele
        # disse; quem consumir olha `status_wp` para saber que ainda vai mudar.
        "lp_url": (lp or {}).get("url_wp") or None,
    }


async def _atualizar(supa, run_row_id: int, valores: Dict[str, Any]) -> None:
    from datetime import datetime as _dt
    valores = {**valores, "atualizado_em": _dt.now(timezone.utc).isoformat()}
    try:
        await supa.patch("pautador_funnel_runs", {"id": f"eq.{run_row_id}"}, valores)
    except Exception as exc:  # noqa: BLE001 — telemetria nunca derruba o run
        log.warning("não gravei o andamento do run %s: %s", run_row_id, str(exc)[:160])


async def executar(
    *,
    supa,
    run_row_id: int,
    arquitetura: Dict[str, Any],
    perfil: Dict[str, Any],
    publicar: bool = True,
) -> None:
    """Roda um funil de ponta a ponta. Não levanta: o desfecho vai para a linha.

    Chamada em segundo plano. Quem dispara já validou credencial, arquitetura e
    duplicata — aqui é execução, não decisão.
    """
    from app.redator.perfil import perfil_para_log

    raiz = raiz_do_motor()
    carimbo = _carimbo()
    # Diretório temporário SÓ para o perfil, com a senha decifrada dentro.
    tmp = Path(tempfile.mkdtemp(prefix="volc-perfil-"))
    os.chmod(tmp, 0o700)
    caminho_perfil = tmp / "perfil.json"
    caminho_arq = tmp / "arquitetura.json"

    async with _semaforo:
        proc: Optional[asyncio.subprocess.Process] = None
        try:
            exe = _executavel()

            caminho_perfil.write_text(json.dumps(perfil, ensure_ascii=False), encoding="utf-8")
            os.chmod(caminho_perfil, 0o600)
            caminho_arq.write_text(json.dumps(arquitetura, ensure_ascii=False), encoding="utf-8")

            log.info("run %s: disparando o motor · perfil=%s",
                     run_row_id, json.dumps(perfil_para_log(perfil), ensure_ascii=False)[:400])

            await _atualizar(supa, run_row_id, {"status": "running"})

            cmd = [str(exe), "run-volc",
                   str(caminho_arq), "--perfil", str(caminho_perfil),
                   "--timestamp", carimbo]
            if publicar:
                cmd.append("--publish")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(raiz),                       # o motor depende do diretório atual
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            _em_execucao[run_row_id] = proc
            # O PID e o carimbo vão para a LINHA, não só para a memória deste
            # processo. É o que permite a um backend REINICIADO descobrir que o
            # motor continua vivo — ver `reconciliar`.
            await _atualizar(supa, run_row_id, {
                "artefatos": {"pid": proc.pid, "carimbo": carimbo}})

            acompanhar = asyncio.create_task(
                _acompanhar(supa, run_row_id, raiz, carimbo, proc, publicar))
            try:
                saida, _ = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_S)
            except asyncio.TimeoutError:
                proc.kill()
                await _atualizar(supa, run_row_id, {
                    "status": "failed",
                    "erro": f"O motor passou de {TIMEOUT_S // 3600}h e foi encerrado.",
                })
                return
            finally:
                acompanhar.cancel()

            texto = (saida or b"").decode("utf-8", "replace")
            run_dir = _achar_run_dir(raiz, carimbo)
            if run_dir:
                (run_dir / "worker.log").write_text(texto, encoding="utf-8")

            estado = _ler_estado(run_dir) if run_dir else None
            final = resumo_do_estado(estado, _flags(raiz, publicar)) if estado else {}

            if proc.returncode != 0:
                await _atualizar(supa, run_row_id, {
                    "status": "failed",
                    "erro": (texto[-800:] or f"o motor saiu com código {proc.returncode}"),
                    **{k: v for k, v in final.items() if k in _COLUNAS},
                })
                return

            await _atualizar(supa, run_row_id, {
                "status": "done",
                "artefatos": _artefatos(run_dir) if run_dir else {},
                **{k: v for k, v in final.items() if k in _COLUNAS},
            })
        except MotorIndisponivel as exc:
            await _atualizar(supa, run_row_id, {"status": "failed", "erro": str(exc)})
        except Exception as exc:  # noqa: BLE001 — o worker nunca derruba a API
            log.exception("run %s explodiu", run_row_id)
            await _atualizar(supa, run_row_id, {"status": "failed", "erro": str(exc)[:800]})
        finally:
            _em_execucao.pop(run_row_id, None)
            # A senha decifrada sai do disco AQUI, aconteça o que acontecer.
            shutil.rmtree(tmp, ignore_errors=True)


_COLUNAS = {"run_id", "paginas_planejadas", "paginas_geradas", "custo_usd",
            # A matriz. `passos` é a matéria-prima; `paginas` é a máscara que só
            # o servidor sabe montar; `passos_hash` é o que permite ao polling
            # de 3s responder 304 em vez de trafegar a grade inteira.
            "passos", "paginas", "passos_hash", "paginas_publicadas", "lp_url"}


def _artefatos(run_dir: Path) -> Dict[str, Any]:
    """O que saiu, para a tela poder abrir. Caminhos relativos à pasta do run."""
    if not run_dir.is_dir():
        return {}
    arquivos = sorted(p.name for p in run_dir.iterdir() if p.is_file())
    return {"pasta": run_dir.name, "arquivos": arquivos}


@lru_cache(maxsize=4)
def _flags(raiz: Path, publicar: bool) -> Dict[str, Any]:
    """Quais colunas da matriz existem NESTE run.

    Três vêm do `config.yaml` do motor; `publish` vem do argumento de linha de
    comando que este worker acabou de montar — que é a verdade de runtime,
    porque o `--publish` sobrepõe o `run.publish: false` do arquivo.

    Em cache: é leitura de um YAML que não muda no meio do run, e `_acompanhar`
    a pediria a cada 3 segundos.
    """
    from app.redator import matriz as mz

    return {**mz.flags_do_motor(raiz), "publish": bool(publicar)}


async def _acompanhar(supa, run_row_id: int, raiz: Path, carimbo: str,
                      proc: asyncio.subprocess.Process,
                      publicar: bool = True) -> None:
    """Enquanto o motor roda, traduz o `state.json` para a linha do run.

    Cadência de 3s: uma etapa do motor leva de 30s a 3 min, então isso é folga
    de sobra e não custa nada — é leitura de um arquivo local.
    """
    ultimo: Dict[str, Any] = {}
    while proc.returncode is None:
        await asyncio.sleep(3)
        run_dir = _achar_run_dir(raiz, carimbo)
        if run_dir is None:
            continue
        estado = _ler_estado(run_dir)
        if not estado:
            continue
        resumo = resumo_do_estado(estado, _flags(raiz, publicar))
        valores = {k: v for k, v in resumo.items() if k in _COLUNAS and v is not None}
        # Só grava quando MUDOU: um UPDATE a cada 3s por 45 min seriam 900
        # escritas por run, quase todas idênticas.
        if valores and valores != ultimo:
            ultimo = valores
            await _atualizar(supa, run_row_id, valores)


async def cancelar(run_row_id: int) -> bool:
    """Encerra um run em andamento. `False` se ele não estava rodando aqui."""
    proc = _em_execucao.get(run_row_id)
    if proc is None or proc.returncode is not None:
        return False
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=10)
    except asyncio.TimeoutError:
        proc.kill()
    return True


def _processo_vivo(pid: Any) -> bool:
    """O PID ainda existe? `os.kill(pid, 0)` não mata: só pergunta.

    ⚠️ ESTA CHECAGEM É O CORAÇÃO DA RECONCILIAÇÃO, e a primeira versão não a
    tinha. O motor roda como processo SEPARADO — ele NÃO morre quando o backend
    reinicia. Sem conferir, um `uvicorn --reload` (ou seja: salvar um arquivo)
    marcava como órfão um run que estava vivo e gastando. Aconteceu de verdade
    no primeiro run real, às 18:08 de 17/08/2026: a linha virou `failed`
    enquanto o PID 30389 seguia escrevendo em `runs/`.

    "Processo vivo" aqui é fraco de propósito: um PID reciclado pelo sistema
    daria falso positivo. O custo do falso positivo é uma linha que fica aberta
    até o timeout; o do falso negativo é declarar morto quem está gastando. O
    primeiro é barato, o segundo mente sobre dinheiro.
    """
    try:
        n = int(pid)
    except (TypeError, ValueError):
        return False
    # ⚠️ PID TEM QUE SER POSITIVO. Em POSIX, `os.kill(-1, sig)` significa "TODOS
    # os processos que eu posso sinalizar" e `os.kill(0, sig)` significa "todo o
    # meu grupo". Com sinal 0 os dois são inócuos, mas devolvem sucesso — e eu
    # concluiria "vivo" para um valor lixo. Se algum dia alguém trocar o 0 por
    # um sinal de verdade, essa mesma linha derrubaria a máquina.
    if n <= 0:
        return False
    try:
        os.kill(n, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # existe, e é de outro dono


async def reconciliar(supa) -> int:
    """No startup: fecha os runs que ficaram órfãos DE VERDADE.

    Sem isto, um reinício deixa linhas eternamente "escrevendo" — a tela mostra
    trabalho que não existe, e o disparo recusa um novo run por duplicata. Com
    isto mal feito, um reinício MATA a linha de um run que está vivo.
    """
    try:
        orfaos = await supa.select("pautador_funnel_runs",
                                   {"status": "in.(queued,running)", "limit": 100})
    except Exception as exc:  # noqa: BLE001
        log.warning("não consegui reconciliar runs órfãos: %s", str(exc)[:160])
        return 0
    n = 0
    for linha in orfaos:
        rid = int(linha["id"])
        if rid in _em_execucao:
            continue  # este está vivo e é deste processo
        pid = ((linha.get("artefatos") or {}) or {}).get("pid")
        if pid and _processo_vivo(pid):
            # Sobreviveu ao reinício. Não é órfão — é órfão de VIGIA: ninguém
            # está lendo o state.json dele. O desfecho será recuperado do disco
            # quando o operador abrir o run, e o timeout do próprio motor
            # continua valendo.
            log.info("run %s continua vivo no PID %s; não vou fechá-lo", rid, pid)
            continue
        await _atualizar(supa, rid, _desfecho_do_disco(linha))
        n += 1
    return n


def _desfecho_do_disco(linha: Dict[str, Any]) -> Dict[str, Any]:
    """O que REALMENTE aconteceu com um run cujo vigia morreu.

    ## O defeito que isto conserta, medido no run #6

    A reconciliação marcava `failed` e ia embora — sem nunca ler o `state.json`
    que o motor terminou de escrever. A linha ficou congelada no último polling:
    US$ 2,2838 e nenhuma publicação. O disco dizia US$ 2,4215, cinco páginas e
    **três rascunhos já criados no WordPress** (posts 2146, 2147 e 2150).

    Para o operador isso é o pior desfecho possível: a tela mostra um run
    fracassado sem nada publicado, ele redispara, e paga ~US$ 2 de novo para
    escrever páginas que já existem no site — agora em duplicata.

    ## `report.md` é o marcador de fim

    O motor o escreve como ÚLTIMA coisa (`pipeline.py:630`). Presente = ele
    chegou ao fim por conta própria, e o desfecho é `done` mesmo que ninguém
    estivesse olhando. Ausente = foi interrompido de verdade.

    Nos dois casos o estado é colhido: dinheiro gasto é dinheiro gasto, e página
    publicada é página publicada — independentemente de como o run terminou.
    """
    carimbo = ((linha.get("artefatos") or {}) or {}).get("carimbo")
    raiz = raiz_do_motor()
    run_dir = _achar_run_dir(raiz, carimbo) if carimbo else None
    estado = _ler_estado(run_dir) if run_dir else None

    if not estado:
        return {
            "status": "failed",
            "erro": "O backend foi reiniciado enquanto este run estava em andamento, "
                    "e não achei o estado dele no disco.",
        }

    terminou = (run_dir / "report.md").is_file()
    colhido = {k: v for k, v in
               resumo_do_estado(estado, _flags(raiz, True)).items()
               if k in _COLUNAS and v is not None}
    return {
        **colhido,
        "artefatos": {**(linha.get("artefatos") or {}), **_artefatos(run_dir)},
        "status": "done" if terminou else "failed",
        "erro": None if terminou else (
            "O backend reiniciou no meio deste run. O motor seguiu sozinho e o "
            "que ele alcançou está aqui — confira as páginas publicadas antes "
            "de redisparar, para não duplicá-las no site."),
    }


# ── PUBLICAR UMA PÁGINA JÁ ESCRITA ─────────────────────────────────────────
#
# ⚠️ POR QUE ISTO PRECISOU EXISTIR
#
# O motor publicava tudo ou nada: `run-volc --publish` no disparo, e ponto. Se
# uma página caísse num portão e fosse consertada depois, não havia caminho
# nenhum de volta ao WordPress — nem pela tela, nem pela API.
#
# Medido em 19/08/2026, run 9: p2, p3 e p4 ficaram escritas, aprovadas nos
# portões e paradas no disco (11.774, 21.638 e 25.275 caracteres). O funil
# tinha duas páginas no ar e três órfãs, e a única forma de completá-lo era
# alguém abrir um terminal. Um funil pela metade não é meio funil: os links
# internos apontam para páginas que não existem, e a sessão comprada morre no
# primeiro salto.
#
# `TEMPO_LIMITE_PUBLICACAO_S` é curto de propósito. Isto não é um run: o texto
# já está pronto e o que falta é uma chamada REST ao WordPress. O único trecho
# que pode demorar é um widget que ainda não foi gerado (~40 s medidos). Se
# passar de cinco minutos, algo está pendurado — e o operador está olhando a
# tela, esperando.
TEMPO_LIMITE_PUBLICACAO_S = 5 * 60


async def publicar_pagina(
    *,
    supa,
    run_row_id: int,
    run_id: str,
    page_number: int,
    perfil: Dict[str, Any],
) -> Dict[str, Any]:
    """Envia ao WordPress UMA página já escrita. Devolve o desfecho, não levanta.

    Diferente de `executar`, esta função é AGUARDADA pela requisição: uma
    página leva segundos, o operador está olhando, e devolver "comecei" para
    algo que termina antes da próxima piscada seria pior que esperar.

    A linha do run é atualizada com o estado inteiro relido do disco — é o mesmo
    `resumo_do_estado` do run completo, então `paginas_publicadas`, custo e
    matriz ficam coerentes com o que o motor gravou.
    """
    raiz = raiz_do_motor()
    tmp = Path(tempfile.mkdtemp(prefix="volc-perfil-"))
    os.chmod(tmp, 0o700)
    caminho_perfil = tmp / "perfil.json"

    try:
        exe = _executavel()
        caminho_perfil.write_text(json.dumps(perfil, ensure_ascii=False), encoding="utf-8")
        os.chmod(caminho_perfil, 0o600)

        cmd = [str(exe), "resume", run_id,
               "--only", f"p{page_number}",
               "--publish", "--perfil", str(caminho_perfil)]

        log.info("run %s: publicando a página %s de %s", run_row_id, page_number, run_id)
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(raiz),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        try:
            saida, _ = await asyncio.wait_for(
                proc.communicate(), timeout=TEMPO_LIMITE_PUBLICACAO_S)
        except asyncio.TimeoutError:
            proc.kill()
            return {"ok": False,
                    "erro": f"O motor passou de {TEMPO_LIMITE_PUBLICACAO_S // 60} min "
                            f"publicando a página {page_number} e foi encerrado."}

        texto = (saida or b"").decode("utf-8", "replace")
        run_dir = raiz / "runs" / run_id
        estado = _ler_estado(run_dir) if run_dir.exists() else None
        if estado is None:
            return {"ok": False,
                    "erro": f"Não achei o estado do run em {run_dir}."}

        # A linha inteira é reescrita a partir do disco — o motor é a verdade.
        final = resumo_do_estado(estado, _flags(raiz, True))
        await _atualizar(supa, run_row_id,
                         {k: v for k, v in final.items() if k in _COLUNAS})

        publicada = next(
            (p for p in (final.get("paginas_publicadas") or [])
             if int(p.get("page_number") or 0) == int(page_number)), None)

        if publicada:
            return {"ok": True, "publicada": publicada}

        # ⚠️ SAIR COM CÓDIGO 0 E NÃO PUBLICAR É UM DESFECHO REAL.
        #
        # O laço do motor engole a exceção da página e grava a falha sob
        # `page_N` — o comando sai 0 e não imprime nada. Foi assim que um 401 do
        # WordPress passou despercebido por três tentativas. Quem chama isto
        # precisa da diferença entre "publiquei" e "rodei sem publicar".
        passos = estado.get("step_status") or {}
        motivo = ""
        for chave in (f"publish_p{page_number}", f"page_{page_number}",
                      f"blocked_p{page_number}", f"content_gate_p{page_number}"):
            r = passos.get(chave) or {}
            if r.get("status") == "FAILED":
                issues = r.get("issues") or []
                motivo = (issues[0].get("message") if issues else "") or chave
                break
        return {"ok": False,
                "erro": motivo or ("O motor rodou e a página não apareceu como "
                                   "publicada. Fim da saída: " + texto[-300:])}
    except MotorIndisponivel as exc:
        return {"ok": False, "erro": str(exc)}
    except Exception as exc:  # noqa: BLE001 — o worker nunca derruba a API
        log.exception("run %s: falhei ao publicar a página %s", run_row_id, page_number)
        return {"ok": False, "erro": str(exc)[:400]}
    finally:
        # A senha decifrada sai do disco AQUI, aconteça o que acontecer.
        shutil.rmtree(tmp, ignore_errors=True)
