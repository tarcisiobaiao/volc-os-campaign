# Correção focal final do R0 — token revogado e evidência histórica

Implementação local sobre `833d40dad901156d6a48d967735157452507079e`, na branch
`execution/volc-os-operacao-80-20`. Escopo: R0-C01/A06 e esclarecimento R0-C02.
Não é aceite de produção, de schema oficial ou de canário real.

## Resultado

- Um token fornecido precisa estar vigente **mesmo quando o token no banco é NULL**.
- Sem token e sem dono, a recuperação governada continua disponível. Omitir
  token quando existe dono continua recusado; as RPCs permanecem restritas a
  `service_role`, sem mudança de grants, assinatura ou acesso do navegador.
- Evidência, erro e geração mais recentes não são alterados por um trabalhador
  antigo, seja sua resposta positiva ou divergente.
- Alterada somente a migration **candidata não aplicada** de fencing e seu
  checksum no perfil. O rollback existente remove a função inteira; não requer
  mudança, e seu ciclo foi reexecutado. Não usar este arquivo editado como
  upgrade silencioso de um banco já migrado: CP2 deve conferir o catálogo e o
  histórico/checksum antes de escolher a aplicação.

## Provas

Seis regressões Python nasceram vermelhas (`DID NOT RAISE`) e ficaram verdes.
Cobrem recuperação, token original do despacho e token girado do read-back,
cada um com resposta positiva e divergente. O teste de sigilo passou a usar
IDs sintéticos longos: `1001` havia coincidido com trecho de um SHA variável,
produzindo um falso positivo. A verificação do corpo inteiro foi preservada.

Comandos executados da raiz da worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:backend/tests backend/.venv/bin/python -B docs/closure/traffic-operational-closure-v2/r0-corrective-v1/evidence-recebida/run_focal.py backend/tests/test_meta*.py -q -p no:cacheprovider --tb=short
python3 scripts/verificar_perfil_schema_meta.py
bash docs/closure/traffic-operational-closure-v2/prova-sql-local.sh
```

- **223 testes Meta passaram**, com conexões TCP bloqueadas.
- **38 verificações SQL passaram** em PostgreSQL 17.9 descartável, incluindo
  seis recusas de token revogado, duas recuperações legítimas, concorrência,
  grants, apply/rollback/reapply e catálogo compatível com o perfil.
- Uma seleção anterior por `-k meta` também selecionou quatro testes AdsPower
  por conterem `metadados` no nome: falharam ao abrir servidor falso local no
  sandbox; 309 passaram. Não foi liberada a rede para fazê-los passar. A seleção
  final por arquivos Meta acima é explícita e não inclui esses testes.
- Frontend não mudou. Build/TypeScript/pixels não foram novamente medidos nesta
  correção SQL; a revisão anterior confirmou 42 testes UI, não inspeção visual.

## Efeitos da sessão anterior: esclarecimento, não certificação

O pacote anterior relata `1 failed / 40 passed / 3 skipped` depois de retirar
o bloqueio TCP dos arquivos `test_trafego.py`, `test_quadro.py` e
`test_reler_wordpress.py`. As fixtures em `backend/tests/conftest.py` restauram
a configuração real. `test_quadro.py` declara leitura real; o teste em
`test_reler_wordpress.py:64` chama `reler-wp`, cuja implementação termina em
`supa.patch` (`backend/app/routers/publicacao.py:1250`).

Os artefatos versionados não contêm os nomes daqueles skips, os comandos
completos com isolamento ou logs de transporte suficientes para determinar os
efeitos. Assim, **zero acesso oficial da rodada anterior não está comprovado**.
As afirmações correspondentes foram retratadas no recibo/handoff históricos.
Também não se afirma que houve escrita. Esta rodada não repetiu esses testes
nem consultou contas, tokens ou banco oficial para investigar.

## Memória operacional e próximo ato

Tarefa afetada: **P11-T05**, permanece `partial`; specs T03/T11. O delta é:
anexar estas provas à recuperação/fencing, sem promover nascimento real. Não
atribuir a P11-T04: o título atual dessa tarefa é engines de imagem e vídeo.

Roadmap, curadoria e grafo não foram editados, preservando a restrição da rodada
corretiva. `atualizar_grafo_volc_os.py --check` informa `current:false`, por
alteração material de código/SQL; o integrador precisa reconciliar essa memória
em ato autorizado. Esta entrega fecha a correção local, não a tarefa global.

Próxima etapa: inspeção breve do operador e preparação de CP2 (catálogo oficial,
perfil exato, backup/recuperação e aplicação), com autorização própria. Depois,
CP3 prova a conta/Page/Shop/LP/peça e roots do plano atual; CP4 autoriza um único
nascimento Meta PAUSED completo com recibo/read-back. Nenhuma dessas permissões
foi inferida desta correção.

Nesta execução: zero push, tokens, Meta/Google Ads, Supabase oficial, migration
oficial, deploy, n8n e WordPress. Apenas alterações locais e banco descartável;
as flags e processos do ambiente operacional não foram alterados.
