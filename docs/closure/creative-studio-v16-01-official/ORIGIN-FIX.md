# Correção da primeira tentativa de geração — 08/09/2026

O POST de geração chegou ao backend autenticado, mas falhou ao inserir
`criativo_projeto`: `origem=assistente_criativo_meta` viola o CHECK da v11_01.
Não era falta de chave OpenAI nem das colunas v16_01. As duas tentativas
observadas falharam antes de criar job, ponte ou chamar o motor; a consulta
oficial confirmou zero jobs, masters e pontes naquele checkpoint.

O adaptador passa a enviar `origem=trafego`, o domínio chamador aceito pelo
contrato. A identificação específica do Assistente continua nas referências
project/run/creative da ponte; nenhuma constraint foi relaxada e nenhuma
migration adicional foi aplicada.

A rota agora converte ErroDePersistencia em HTTP 503 com JSON sanitizado.
O tratamento normal preserva os cabeçalhos CORS e evita que este erro 500
sem tratamento seja apresentado pelo navegador como falha de conexão.
A mensagem não afirma ausência de efeitos: uma falha posterior pode ocorrer
depois de gravar ou produzir a primeira peça de um lote. Não há retry automático.

## Provas

- 71 testes passaram: adaptador, autorização de gasto e executor.
- Regressão lê os valores permitidos do CHECK SQL e confere origem e refs.
- Falha antes do primeiro job e depois da primeira peça testadas: JSON/CORS,
  sem detalhe SQL e sem falsa promessa de que nenhum trabalho existe.
- No Supabase oficial, INSERT sintético com `origem=trafego` sob service_role
  passou; ROLLBACK executado; contagem residual da fixture = 0.
- Sem chamada paga ou Meta nesta correção. Geração e leitura do arquivo real
  ainda não estão comprovadas. O operador pode repetir o teste de uma peça
  em um formato após conferir novamente o plano.

P11-T02/P11-T04 continuam partial. Esta correção fecha o erro observado,
não declara o restante da geração, download ou uso em campanha concluído.
