# Plano — mover e rotacionar o developer token do Google Ads (item 5, não executado)

Estado: **plano**. Nada executado. Cada passo que toca n8n ou a conta Google Ads exige autorização nominal.

## Onde o token está hoje (leitura dos exports de 17/10, valores não lidos nem copiados)

- Em texto puro no campo `DEVELOPER TOKEN` de nós **Set** dos três coletores canônicos (D0: `Edit Fields`,
  `Edit Fields2`; D-1: `Edit Fields`; termos: `Edit Fields2`) e enviado por expressão no cabeçalho `developer-token`
  dos nós HTTP. As chamadas já usam a credencial OAuth2 `googleAdsOAuth2Api` para o access token.
- Consequências: o token aparece (1) em qualquer leitura do workflow pela API ou pela interface; (2) em todo export,
  inclusive os exports de rollback do item 5 (0600, fora do Git, em `experiments/.../artifacts/item5-20261017/`);
  (3) **nos dados de cada execução**, porque os coletores salvam execuções de sucesso e erro (`saveData*Execution =
  all`) e a saída do nó Set inclui o campo.
- Os legados Google (`hN15…`, `tKUI…`, `33cQ…`, `fwMK…`) provavelmente seguem o mesmo padrão (não verificado).

## Plano

1. **Inventário (read-only):** listar todos os workflows cujo JSON contém o nome de campo `DEVELOPER TOKEN` ou o
   cabeçalho `developer-token` (só contagem e id, nunca o valor).
2. **Mover para credencial:** usar o campo *Developer Token* da credencial `googleAdsOAuth2Api` já referenciada, se
   o n8n desta instância o injeta nas chamadas HTTP com credencial predefinida; **provar** isso numa cópia canário
   temporária (como no item 5: só o gatilho trocado, ativa por segundos, arquivada) sem o cabeçalho manual. Se não
   injetar, criar uma credencial *Header Auth* dedicada (`developer-token`) e referenciá-la nos nós HTTP.
3. **Cutover por coletor** (D0, D-1, termos; depois legados), com o mesmo gate do item 5: remover o campo do Set e a
   expressão do cabeçalho, diff semântico pós-update, canário, releitura no ledger e rollback pelo export.
4. **Rotacionar:** gerar token novo no API Center (ação humana do dono na conta MCC), gravar só na credencial,
   confirmar uma execução de cada coletor com o token novo, e então revogar o antigo. Ordem importa: rotacionar antes
   de mover deixaria o token novo exposto nos mesmos lugares.
5. **Limpar a exposição antiga (exige autorização própria, é apagar dados):** podar execuções antigas que contêm o
   token antigo (ou aceitar que o antigo revogado fica inerte nelas) e apagar os exports de rollback do item 5 quando a
   janela de rollback terminar, com manifesto.
6. **Prova:** varredura pós-cutover de workflows e de uma execução recente de cada coletor procurando o campo
   (contagem 0), e `verificar_segredos.py` no repositório.

## Riscos

- Tempo de rotação: entre gerar o token novo e revogar o antigo, os dois valem; minimizar a janela.
- Quota: o developer token é compartilhado com MCP, scripts e sincronizador; trocar o token sem atualizar todos os
  consumidores quebra quem ficou com o antigo. O inventário do passo 1 precisa cobrir também consumidores fora do n8n.
- O nível do token (Basic/Explorer) não está confirmado; a rotação não muda o nível.
