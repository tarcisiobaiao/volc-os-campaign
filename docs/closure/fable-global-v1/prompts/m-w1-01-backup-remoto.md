# Prompt — M-W1-01 · Backup remoto da main (Opus, sessão interativa + dono)

> Pré-condição humana: o dono escolheu o remoto (decisão D9). NUNCA usar o
> remote `upstream` (webgo) nem o `origin` atual sem confirmar que é o destino
> desejado.

```text
Você é o operador de backup do VOLC O.S. Missão única e cirúrgica: colocar a
main local em segurança remota. Não replaneje, não refatore, não toque em
nenhum arquivo.

Contexto factual (não redescubra): repo /Users/mac/Desktop/VOLC-OS-CAMPAIGN/volc-os-campaign,
main local = e858651 (ou mais novo), origin/main contém SÓ o Initial commit
8bffa0e com história divergente; a main local está ~411 commits à frente
(evidência: docs/closure/fable-global-v1/FACT-MATRIX.json, F002).

Passos:
1. git remote -v — confirme os remotes existentes e mostre ao dono.
2. Com a URL fornecida pelo dono: git remote add backup <URL> (ou reutilize
   origin se o dono disser explicitamente que é o destino).
3. git push backup main --force-with-lease (justifique: história divergente
   do Initial commit; --force-with-lease, nunca --force).
4. Prova: git ls-remote backup refs/heads/main deve devolver o SHA local.
5. Empurre também as branches não integradas listadas na seção 1 do
   INTEGRATION-LEDGER.md (integration/autonomous-closure-20260829,
   feat/harness-gemini-37-flash-v1, feat/supervisor-continuo-v0) —
   são as únicas com trabalho exclusivo.

Proibições: nenhum merge/rebase/reset; nenhum push para upstream; nenhuma
alteração de arquivo; se qualquer push falhar, reporte o erro literal e pare.

Handoff (obrigatório, compacto): remote usado, SHAs empurrados, saída do
ls-remote, e a frase 'backup remoto verificado em <data>'. Depois do M-W1-09,
repita o push final e atualize o handoff.
```
