# Riscos remanescentes — meta-creation-engine-operator-experience-v1

1. **`validate_only` real nunca foi executado.** Todo o contrato foi provado
   contra a documentação oficial e contra transportes herméticos. A primeira
   conversa real com a Meta ainda vai acontecer, e é ela que decide questões
   que a documentação não fecha — em especial se `promoted_object` é exigido
   para OUTCOME_TRAFFIC com LANDING_PAGE_VIEWS.
2. **Cobertura da validação é parcial por construção.** Só campanha e criativos
   podem ser validados sem um objeto pai real; conjunto e anúncios continuam
   pendentes até a criação existir. A tela diz isso com todas as letras, mas um
   plano "validado" ainda pode falhar no conjunto.
3. **Passo AMBÍGUO é terminal.** A saga marca ambiguidade corretamente e se
   recusa a reenviar, mas não existe fluxo de reconciliação montado para
   localizar o objeto por leitura e fechar o recibo. Enquanto `create_paused`
   não for autorizado isso é teórico; no dia em que for, é a primeira coisa a
   construir.
4. **Criativo flexível bloqueado por um único campo.** Tudo do `asset_feed_spec`
   está provado menos como a Página viaja junto dele. É um bloqueio pequeno e
   preciso, não uma capacidade ausente.
5. **Criativo de vídeo bloqueado pela miniatura.** A leitura de vídeos funciona
   e a prévia é real, mas `video_data` exige uma miniatura que seja `image_hash`
   da biblioteca ou URL própria — e a doc proíbe a URL do CDN da Meta, que é a
   única que a leitura devolve. Sair disso exige autorizar upload de ativo.
6. **Manifesto liga passos, não orçamento.** A aprovação durável agora fixa
   quais passos existem e em que ordem. O `payload_sha256` de um passo
   dependente só é conhecido em tempo de execução, então o orçamento aprovado
   ainda não é confrontado com o payload do conjunto.
7. **Baseline de TypeScript desatualizado** (76 registrados, 77 reais em HEAD).
   Declarado, não corrigido nesta lane.
