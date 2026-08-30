# Prompt — M-W1-04 · Revisão substituta + integração dos candidatos Gemini (Opus, integrador único)

> ⛓ Após M-W1-03. Os reviewers automáticos crasharam por defeito do harness
> (PermissionError de escopo), então a revisão que faltou é FEITA POR VOCÊ —
> não pule direto ao merge.

```text
Você é o integrador único. Dois candidatos de código Gemini ficaram órfãos de
revisão por crash do harness (não por mérito) e precisam de revisão humana
substituta antes de entrar na main (FACT-MATRIX F010/F012):

(a) 656d72d — cadeia gemini-ads-health-deadman (P10-T04): contrato canônico
    de heartbeat/deadman. Os gates da tentativa a3 PASSARAM (41 passed em
    test_google_inteligencia_saude.py; 518 em volc_ads). a3 ⊃ a2 ⊃ a1 — só o
    tip interessa.
(b) 5eb6b38 — gemini-ads-pmax-observabilidade (P04-T07): núcleo read-only de
    observabilidade PMax. NUNCA foi revisado nem teve gates além do writer.

Para CADA candidato, nesta ordem:
1. git diff main...<sha> — leia o diff INTEIRO.
2. Revisão contra o aceite do roadmap (P10-T04 e P04-T07 têm blocos
   acceptance no ROADMAP-VIVO.json — o delta não commitado da worktree os
   contém; use-os como checklist):
   - P10-T04: saudável/atrasado/falhou/nunca-executado/desabilitado/
     indeterminado distintos; última tentativa ≠ último sucesso; relógio
     injetável timezone-aware; sem consulta a n8n/Google/Supabase; sem alerta.
   - P04-T07: contratos read-only tipados; ausência/zero/não-aplicável/falha/
     não-coletado/leitura-antiga distintos; provas offline; zero mutate/rede.
3. Procure ativamente: ausência colapsada em zero, rede escondida, teste que
   aceita qualquer erro, mudança fora do escopo da frente.
4. Se aprovado: merge do candidato (merge normal, mensagem citando a origem e
   'revisão substituta por crash do reviewer'), depois gates:
   pytest volc_ads -q; pytest backend/tests -q; tsc (baseline 76); build.
5. Se reprovado: NÃO integre; escreva as objeções com caminho+linha e
   registre no INTEGRATION-LEDGER como 'changes_requested por revisão
   substituta' — vira missão corretiva de onda 2.

Proibições: nenhuma edição de código (revisão e merge apenas); nenhum push;
não misture os dois candidatos num commit só.

Handoff: por candidato — veredito, objeções (se houver), SHA do merge, gates
com contagens; e o delta de curadoria PROPOSTO (P10-T04/P04-T07: todo →
partial ou done? só se o aceite estiver provado).
```
