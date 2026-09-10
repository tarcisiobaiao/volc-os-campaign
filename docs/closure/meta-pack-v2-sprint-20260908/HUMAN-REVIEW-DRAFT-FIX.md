# Revisão humana e recuperação de rascunhos

09/09/2026. Lane `execution/volc-os-operacao-80-20`, sem commit/push ou nova worktree.

## Correções

- O envio estava liberado no rascunho anterior. O usuário confirmou a URL atual; uma imagem selecionada recebeu grant específico por 24 horas, até 10/09/2026 04:42:34 America/Sao_Paulo. Trocar dono, conta, seleção ou bytes invalida o grant. Isso não concede criação nem ativação de campanha.
- Revisão padrão `HUMAN_ONLY` não instancia Gemini, OCR ou avaliação automática. Aprovação humana persistida, finalidade `meta_ads`, versão, propriedade, arquivo não arquivado e hash dos bytes são conferidos novamente no envio. O resultado declara `HUMAN_REVIEW`, nunca `CLEAR` ou aprovação da Meta. Rotina automatizada permanece apenas como opção interna explícita testada, não exposta nesta UI/rota.
- Ledger de mídia admite o grant restrito sem depender da flag global de criação. Novas reservas reconferem autorização; conclusão/falha/ambiguidade de uma reserva já admitida continuam registráveis caso haja revogação durante a resposta da Meta. Fencing e idempotência existentes preservados.
- Continuar recupera dados e recarrega catálogos da conta/Página/fonte de mensuração sem selecionar a primeira opção por engano. Rascunho explícito ausente não vira novo vazio. Falha de hidratação impede autosave de padrões. Etapa inferida pelas escolhas; link com etapa explícita respeitado, cursor exato não persistido.
- Excluir usa confirmação inline e comparação de versão. É arquivamento recuperável via suporte, não DELETE físico. Some da lista/leitura e revoga grants; atualização tardia de outra aba não o ressuscita. Packs, arquivos e recibos ficam intactos. Se a versão mudou antes da confirmação, atualizar a lista e confirmar novamente.

## Banco oficial

Migration `20260909073845_meta_draft_archive.sql` aplicada em `https://database.agenciavolc.com.br`.
SHA256: `7af4171e3a4b914c0b292492be6acf240a12bb676e0a046824eba6958973d667`.
RPC pública SECURITY INVOKER, execução restrita a service_role, implementação em schema privado. Gatilho impede alteração de rascunho arquivado e revoga envio. Nenhum rascunho do usuário foi excluído.

Roundtrip oficial save → archive → read/list com papel service_role passou em transação revertida. Quatro rascunhos originais, zero arquivados após ROLLBACK. A primeira tentativa usando apenas claim de JWT foi recusada pelo guarda de papel; refeita com SET ROLE efetivo, sem relaxar o guarda.

## Provas

- 91 testes backend/SQL na bateria integrada; mais um teste de contrato HTTP de exclusão depois, aprovado na bateria focal de 14.
- 94 testes frontend em seis arquivos, incluindo retomada renderizada, save concorrente, confirmação/cancelamento/exclusão e revisão/upload separados.
- Build passou. Typecheck dos arquivos da retomada sem novos diagnósticos; projeto tem baseline global conhecido.
- Chrome isolado com componentes reais e transporte simulado: revisão em 375/768/1440 claro/escuro, teclado, loading e botão de envio habilitado; exclusão em 375/1440, cancelar e confirmar por teclado. Zero erro JS/overflow. Não equivale a QA autenticado ponta a ponta.
- Backend/8080 HTTP200. RPC real: seleção atual permitida, outro proprietário/rascunho negados, flag geral da conta desligada. Arquivo real e aprovação humana vigente conferidos, detectores configurados para falhar se chamados: zero IA/geração paga/upload.

## Limites do fechamento

Upload à Meta permanece para o clique explícito do operador. Nenhuma campanha criada ou ativada nesta sessão. O destino da montagem ainda é uma URL de teste; precisa ser substituído antes da criação real. Fonte de mensuração está selecionada. Autorização de criação anterior não foi ampliada para o novo rascunho.

Roadmap P11-T07 atualizado e P11-T08 encerrado no escopo acima. P11-T02/P11-T05 continuam partial. Nós `cap_meta_ads` e `cap_bancada_criativa` reconciliados; reconstrução e frescor do grafo conferidos no handoff.
