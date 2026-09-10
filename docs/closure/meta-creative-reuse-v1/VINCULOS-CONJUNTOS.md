# Vínculo anúncio, conjunto e criativo

08/09/2026. Implementação local; sem publicação ou mutação Meta.

## Contrato

Campanha contém conjuntos; anúncio aponta para exatamente um conjunto por `adset_key` e referencia uma peça/copy. Reutilizar a peça em outro conjunto cria outra variação/anúncio, com nova chave e nomes únicos. Não move o original nem transfere aprovação. IDs e provas de publicação não são fabricados.

## Correções

- Distribuição visível por conjunto na etapa Criativos, com quantidade efetivamente emitida e aviso sobre anúncios guardados fora do modo atual.
- Adicionar neste conjunto transporta a chave escolhida; adicionar sem destino em múltiplos conjuntos não cai no primeiro conjunto.
- Reutilizar em outro conjunto exige selecionar o destino e confirmar a cópia. Imagem/copy são preservadas; aprovação é limpa. Mudar o pai de anúncio também limpa sua declaração de política e invalida o plano.
- Anúncio novo começa sem mídia escolhida: não herda silenciosamente a última imagem de outro conjunto.
- Remoção de conjunto recusa anúncios referenciadores, inclusive guardados no modo individual. Tanto botão quanto mutação local defendem a regra.
- Backend já recusa chave de conjunto inexistente, chave duplicada e conjunto vazio; testes verificam dependências do compilador e estabilidade ao reordenar. Não foi necessário reescrever o compilador.

## Provas

54 testes frontend (incluindo reutilização pelo formulário seguida de compilação JSON); 46 testes backend. Build passou. Chrome com componentes reais e fixture: seis capturas 375/768/1440, claro/escuro, zero erro JS e zero overflow. Fixture não equivale a QA autenticado nem validação remota.

Verificação adicional: 43 testes de compatibilidade da bancada e nascimento passaram (97 frontend + 46 backend no total). TypeScript global permanece com 77 erros; nenhum aponta para os arquivos desta mudança. Não se afirma gate TypeScript global limpo.

## Limites

Packs ainda aguardam registro governado de imagens na conta antes de integrar o plano publicável. Este trabalho não remove essa proteção. Não certifica lançamento em produção, ativação, conversões elegíveis ou gestão remota. P11-T02/P11-T03 permanecem partial.
