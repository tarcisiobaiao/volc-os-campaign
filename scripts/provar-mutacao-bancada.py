#!/usr/bin/env python3
"""Prova que as provas da bancada matam o defeito, e nao so passam.

## Por que este arquivo existe

A rodada anterior "provou" uma mutacao apagando uma linha e obtendo `1 error`.
Isso nao e prova de nada: um `SyntaxError` derruba a suite por motivo errado, e
uma prova que so exige "vermelho" aceita vermelho de qualquer cor.

Aqui cada mutacao:
  1. produz codigo SINTATICAMENTE VALIDO — conferido por `ast.parse` antes de rodar;
  2. precisa fazer a suite falhar por ASSERCAO, nao por erro de coleta;
  3. e revertida byte a byte, com o arquivo original conferido por sha256.

Uma mutacao que sobrevive e um defeito que a suite deixaria passar.

Uso:  python3 scripts/provar-mutacao-bancada.py
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PY_BIN = str(RAIZ.parent.parent / "Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign/backend/.venv/bin/python")
if not Path(PY_BIN).exists():
    PY_BIN = sys.executable
SUITE = "backend/tests/test_criativo_bancada.py"

B = "backend/app/criativo/bancada"

# (rotulo, arquivo, de, para) — o `para` tem de manter o codigo valido.
MUTACOES: list[tuple[str, str, str, str]] = [
    (
        "confianca-no-motor: nao conferir se o arquivo existe",
        f"{B}/operario.py",
        "            if not caminho.is_file():",
        "            if False:",
    ),
    (
        "confianca-no-motor: nao conferir o hash",
        f"{B}/operario.py",
        "            if hash_medido != a.sha256:",
        "            if False:",
    ),
    (
        "confianca-no-motor: nao conferir os bytes",
        f"{B}/operario.py",
        "            if medido != a.bytes_:",
        "            if False:",
    ),
    (
        "despacho: voltar a pegar o mais antigo da fila",
        f"{B}/operario.py",
        "        reivindicado = self.operario.deposito.reivindicar_este(\n"
        "            trabalho_id, self.operario.nome, lease_s=self.operario.lease_s\n"
        "        )",
        "        reivindicado = self.operario.deposito.reivindicar(\n"
        "            self.operario.nome, lease_s=self.operario.lease_s\n"
        "        )",
    ),
    (
        # ⚠️ SOBREVIVE, e a razao esta medida: a maquina de estados ja barra o
        # caminho antes. Quem perdeu o lease chega em `validating` com o trabalho
        # em `claimed` (o novo dono acabou de reivindicar), e `claimed ->
        # validating` nao existe. O `exigir_operario` no `rendered` e defesa em
        # profundidade, nao a unica guarda — e mutacao equivalente nao mede
        # cobertura. Mantida na lista para que a redundancia fique visivel.
        "[redundante] posse: concluir sem exigir que ainda sejamos donos",
        f"{B}/operario.py",
        "                    trabalho.id, EstadoDoTrabalho.RENDERED, recibo=corpo,\n"
        "                    exigir_operario=self.nome,\n"
        "                )",
        "                    trabalho.id, EstadoDoTrabalho.RENDERED, recibo=corpo,\n"
        "                )",
    ),
    (
        "posse: transicionar sem conferir o dono",
        f"{B}/deposito.py",
        "            if exigir_operario is not None and linha[\"operario\"] != exigir_operario:",
        "            if False:",
    ),
    (
        "batimento: aceitar batida de quem nao e dono",
        f"{B}/deposito.py",
        '            + (" and operario=?" if operario else ""),',
        '            + "",',
    ),
    (
        "lease: nao soltar o lease ao sair de execucao",
        f"{B}/deposito.py",
        "            solta = para in TERMINAIS or para is EstadoDoTrabalho.QUEUED",
        "            solta = False",
    ),
    (
        # ⚠️ VIROU EQUIVALENTE com a correcao de 29/08. Agora `transicionar` para
        # VALIDATING leva `exigir_operario`, e `cancelled` e terminal: sem a
        # guarda, a transicao estoura, cai no `_falhar`, e o `rmtree` do ramo de
        # perda de posse limpa o diretorio do mesmo jeito. Mesmo desfecho: sem
        # recibo, sem arquivo. A guarda fica porque diz o motivo no log em vez de
        # registrar uma "falha inesperada" que nao foi inesperada.
        "[equivalente] cancelamento: concluir mesmo cancelado",
        f"{B}/operario.py",
        "                if self._foi_cancelado(trabalho.id):\n"
        "                    log.info(\"trabalho %s cancelado durante a producao\", trabalho.id)",
        "                if False:\n"
        "                    log.info(\"trabalho %s cancelado durante a producao\", trabalho.id)",
    ),
    (
        # A guarda em Python e REDUNDANTE com o `where estado not in (...)` do
        # UPDATE, que e o arbitro real. Mutar so a de Python e mutacao
        # equivalente. Esta muta o arbitro.
        "cancelamento: o UPDATE deixa cancelar o que ja terminou",
        f"{B}/deposito.py",
        '                " where id=? and estado not in (?,?,?)",',
        '                " where id=? and (? is not null or ? is not null or ? is not null)",',
    ),
    (
        "retomada: reabrir o trabalho terminal em vez de criar um novo",
        f"{B}/deposito.py",
        "        raiz = original.retoma_de or original.id\n        n = original.retomada_n + 1",
        "        raiz = original.retoma_de or original.id\n        n = 1",
    ),
    (
        "retomada: deixar retomar o que deu certo",
        f"{B}/deposito.py",
        "        if original.estado is EstadoDoTrabalho.RENDERED:",
        "        if False:",
    ),
    (
        "tenant: ignorar o tenant na chave de identidade",
        f"{B}/contrato.py",
        '            "tenant": self.tenant_id,',
        '            "tenant": "",',
    ),
    (
        "tenant: por_id sem filtrar por tenant",
        f"{B}/deposito.py",
        '                "select * from trabalho where id=? and tenant_id=?",\n'
        "                (trabalho_id, tenant_id),",
        '                "select * from trabalho where id=?",\n'
        "                (trabalho_id,),",
    ),
    (
        "tenant: listar sem filtrar",
        f"{B}/deposito.py",
        '            "select * from trabalho where tenant_id=? order by criado_em desc limit ?",\n'
        "            (tenant_id, limite),",
        '            "select * from trabalho where tenant_id=? or 1=1 order by criado_em desc limit ?",\n'
        "            (tenant_id, limite),",
    ),
    (
        "canonicalizacao: 1 e 1.0 voltam a ser pedidos diferentes",
        f"{B}/contrato.py",
        '            "parametros": canonizar(self.parametros),',
        '            "parametros": self.parametros,',
    ),
    (
        "canonicalizacao: colapsar None em vazio",
        f"{B}/contrato.py",
        "    if isinstance(valor, bool):\n        return valor",
        "    if valor is None:\n        return \"\"\n    if isinstance(valor, bool):\n        return valor",
    ),
    (
        "fonte: voltar a aceitar fonte de sistema achada por acaso",
        f"{B}/adaptadores/tipografico.py",
        '    raise FalhaDoMotor(\n'
        '        "nenhuma fonte empacotada e CRIATIVO_FONTES_DIR nao definida",\n'
        "        permanente=True,\n"
        "    )",
        '    for pista in ("/System/Library/Fonts/Supplemental",):\n'
        "        p = Path(pista)\n"
        "        if p.is_dir() and (f := _escolher_em(p)):\n"
        "            return f\n"
        '    raise FalhaDoMotor("sem fonte", permanente=True)',
    ),
    (
        # A versao anterior desta mutacao inseria `pass` antes do `set()`, o que
        # nao muda nada: mutacao EQUIVALENTE nao mede cobertura. Agora ela de
        # fato nao para a thread.
        "reaper: parar() nao sinaliza a thread",
        f"{B}/operario.py",
        "        self._parar.set()\n        if self._t:\n            self._t.join(timeout=prazo_s)",
        "        if self._t:\n            self._t.join(timeout=prazo_s)",
    ),
    (
        "fila: recursao de volta em vez de laco",
        f"{B}/deposito.py",
        "                    continue\n                agora = _agora()",
        "                    break\n                agora = _agora()",
    ),
    (
        "sanitizacao: voltar a mandar o caminho cru para a tela",
        f"{B}/operario.py",
        '    texto = _re.sub(r"(/|~/)[^\\s\'\\"]{2,}", "<caminho>", texto)',
        "    texto = texto",
    ),
]


def rodar_suite() -> tuple[bool, str]:
    r = subprocess.run(
        [PY_BIN, "-m", "pytest", SUITE, "-q", "-p", "no:cacheprovider", "--no-header"],
        cwd=RAIZ, capture_output=True, text=True,
    )
    return r.returncode == 0, (r.stdout + r.stderr)[-1200:]


def main() -> int:
    verde, saida = rodar_suite()
    if not verde:
        print("BASELINE VERMELHO — nao da para medir mutacao com a suite quebrada")
        print(saida[-500:])
        return 2
    print(f"baseline verde\n{'=' * 72}")

    mortas, vivas, invalidas = [], [], []
    for rotulo, rel, de, para in MUTACOES:
        alvo = RAIZ / rel
        original = alvo.read_text(encoding="utf-8")
        sha = hashlib.sha256(original.encode()).hexdigest()

        if original.count(de) != 1:
            invalidas.append((rotulo, f"padrao encontrado {original.count(de)}x"))
            print(f"  ?  {rotulo}\n     PADRAO NAO ENCONTRADO UMA UNICA VEZ")
            continue

        mutado = original.replace(de, para)
        try:
            ast.parse(mutado)
        except SyntaxError as e:
            invalidas.append((rotulo, f"mutacao invalida: {e}"))
            print(f"  ?  {rotulo}\n     MUTACAO PRODUZIU CODIGO INVALIDO — descartada")
            continue

        alvo.write_text(mutado, encoding="utf-8")
        try:
            passou, saida = rodar_suite()
        finally:
            alvo.write_text(original, encoding="utf-8")
            assert hashlib.sha256(alvo.read_text(encoding="utf-8").encode()).hexdigest() == sha

        # ⚠️ Vermelho por ERRO DE COLETA nao conta: a suite tem de falhar por
        # assercao, senao estariamos medindo "o import quebrou".
        por_erro = "error" in saida.lower() and "failed" not in saida.lower()
        if passou:
            vivas.append(rotulo)
            print(f"  VIVA  {rotulo}")
        elif por_erro:
            invalidas.append((rotulo, "suite quebrou por erro, nao por assercao"))
            print(f"  ?     {rotulo}  (vermelho pelo motivo errado)")
        else:
            mortas.append(rotulo)
            print(f"  morta {rotulo}")

    validas = len(mortas) + len(vivas)
    score = (len(mortas) / validas * 100) if validas else 0.0
    print(f"{'=' * 72}\nmortas {len(mortas)} · vivas {len(vivas)} · "
          f"descartadas {len(invalidas)}\nMUTATION SCORE: {score:.1f}%")
    if vivas:
        print("\nMUTACOES VIVAS (defeitos que a suite deixaria passar):")
        for v in vivas:
            print(f"  - {v}")
    for rotulo, motivo in invalidas:
        print(f"  descartada: {rotulo} — {motivo}")
    return 0 if not vivas else 1


if __name__ == "__main__":
    raise SystemExit(main())
