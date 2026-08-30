# Prompt — M-W1-02 · Lote documental dos untracked (Codex, sessão interativa)

> Serializa com as demais escritas na main (⛓): rode quando nenhum outro
> integrador estiver commitando.

```text
Você vai versionar o trabalho documental de 28-29/08 que hoje existe só como
arquivos untracked na worktree principal do VOLC O.S.
(/Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign). Missão de commit, não
de autoria: NÃO edite conteúdo, exceto se a varredura de segredo exigir.

Escopo EXATO (git status já os lista; confira antes):
- docs/architecture/ADR-1PASSWORD-ADSPOWER-E-RECUPERACAO-AGENTICA.md
- docs/architecture/GADS-REPORT-D0-D1-E-CONTRATO-DE-DADOS.md
- docs/architecture/contracts/  e  docs/architecture/evidence/
- scripts/adaptar_gads_reports_n8n.py
- tools/agent-harness/missions/*.json (os 9 untracked)
- tools/agentic-recovery-smoke/
FORA do lote: .claude/skills/ (decisão do dono), volc-os-workbook/ROADMAP-VIVO.json
(modificado, vai no M-W1-09 com a curadoria).

Passos:
1. Varredura de segredo em CADA arquivo do lote: rode
   python3 scripts/verificar_segredos.py se existir; senão, grep por padrões
   (chaves, tokens, senhas, service_role, JWT, URLs com credencial embutida).
   Um único achado → pare e reporte o caminho+classe (nunca o valor).
2. Confirme que nenhum arquivo do lote contém IDs de credencial n8n com valor
   (IDs de referência são aceitáveis; valores não).
3. git add SOMENTE os caminhos do escopo; git status para provar que nada
   além entrou.
4. Um único commit: "docs(closure): versiona ADRs, contratos, evidências e
   missões de 28-29/08" com a trailer Co-Authored-By padrão do repo.
5. NÃO faça push (o push é do M-W1-01/M-W1-09).

Handoff: lista dos arquivos commitados, SHA do commit, resultado da varredura
de segredo (zero achados ou lista de classes), e o que ficou de fora e por quê.
```
