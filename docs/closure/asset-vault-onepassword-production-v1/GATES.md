# Gates do candidato aceito

> **Registro CONGELADO.** Este arquivo já foi um relatório gerado a cada
> execução de `./scripts/medir-gates-cofre.sh`. Ao aceitar o candidato técnico
> ele virou outra coisa: o registro fixo dos números do SHA aceito. O gerador
> continua existindo e continua sendo o jeito certo de remedir — mas o que está
> aqui não se move mais, porque procedência que se move não é procedência.

## Procedência

| Campo | Valor |
|---|---|
| `code_sha` | `2971c8c5e47e7a89cd11650d09ca17c570bc589c` |
| `code_sha` curto | `2971c8c` |
| Estado | **aceito e validado** pelo dono da missão |
| Base | `36bec04` (`origin/volc-os-v2`) |
| Branch | `sprint/asset-vault-onepassword-production-v1` |
| Commits de produto até `2971c8c` | **9** |
| `closure_artifact_commit` | `self_unavailable` |
| HEAD final da branch | reportado externamente, após o commit documental |

### Por que `closure_artifact_commit = self_unavailable`

Este arquivo é versionado no mesmo commit que o descreve. Um arquivo gerado não
conhece o hash do commit que o contém — o SHA só existe depois que o conteúdo
está congelado. Registrar aqui um SHA "do commit documental" só seria possível
apontando para o commit **anterior**, e foi exatamente esse o defeito que a
revisão de contrato encontrou neste pacote. Então o campo diz o que é verdade:
indisponível para si mesmo. O SHA documental é reportado fora do artefato.

`code_sha` não tem esse problema: `2971c8c` é o commit **de produto**, anterior
e independente deste registro. É ele que os números abaixo descrevem.

## Números comprovados em `2971c8c`

| Gate | Comando | Resultado |
|---|---|---|
| Ciclo SQL | `./scripts/provar-ciclo-v13_01.sh` | **92 provas** · PostgreSQL **15.19** |
| Testes backend do Cofre | `pytest backend/tests/test_cofre_ativos.py` | **67 passed** |
| Testes frontend do Cofre | `vitest run src/features/asset-vault` | **24 passed (24)** |
| TypeScript | `tsc --noEmit -p tsconfig.app.json` | **76** erros do baseline · **0** no ownership |
| Build | `npm run build` | **verde** |
| Smoke 1Password (real) | `tools/onepassword-smoke/run.py` | **`blocked/cli_ausente`, exit 10** |
| Smoke 1Password (dublê) | `run.py --autoteste` | 6 provas, 0 falhas |
| Onboarding da página | `onboarding_pagina_facebook.py --autoteste` | **56/56** |
| Importador de engines | `importar_engines_no_cofre.py --autoteste` | 248 asserções, 7 engines |
| Rotas do Cofre | `len(rotas.router.routes)` | 13 |
| Espaço em branco | `git diff --check` | limpo |

`blocked/cli_ausente` com exit 10 **é o resultado correto**, e não uma falha: não
há app, CLI `op` nem `1password-mcp` nesta máquina. O smoke sair `ok` aqui seria
o defeito.

## Suíte backend inteira — o que foi e o que não foi medido

**Contagem final medida em `2971c8c`:**

```
2187 passed, 53 skipped
```

**`baseline_delta_not_remeasured`.**

O baseline foi levantado com `pytest backend/tests -q --collect-only`, que
devolveu `2173 tests collected` — uma contagem de **coleta**, não de execução. A
suíte nunca foi *rodada* em `36bec04`, então não existe um `passed`/`skipped` do
baseline com que comparar. Publicar "baseline + N" a partir de uma contagem de
coleta seria somar duas grandezas diferentes e chamar o resultado de prova.

O que se pode afirmar: a suíte inteira roda verde em `2971c8c`, com zero falhas.
O delta contra o baseline não está remedido.

## Vitest completo — comparação não provada em `2971c8c`

O gate focal está provado: **24/24** em `src/features/asset-vault`, e o build
está verde.

A suíte de frontend **inteira** foi comparada contra o baseline uma vez, num HEAD
intermediário desta missão — não em `2971c8c`. Como a comparação não foi
reexecutada no SHA aceito, ela **não é afirmada aqui**. Qualquer frase sobre "as
mesmas oito suítes falhas antes e depois" vale para aquele HEAD intermediário e
não para este.

Para provar: `npx vitest run` em `36bec04` e em `2971c8c`, e comparar. Não foi
feito, e por isso não está escrito como feito.

## Como remedir

```bash
./scripts/medir-gates-cofre.sh            # bloco markdown, todos os gates
./scripts/medir-gates-cofre.sh --rapido   # pula ciclo SQL e build
```

O gerador nunca reescreve este arquivo sozinho: quem quiser um retrato novo
redireciona a saída para outro lugar e compara. Congelar aqui é deliberado.
