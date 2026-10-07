# Refino visual e responsabilidade pelo aviso editorial

## Estado

P10-T17 / cap_funnel permanece **partial**. Nenhum funil foi publicado.
780 testes Python e 13 testes PHP isolados passaram. Nenhuma API paga foi chamada.
As mudancas de engine estao locais; os dois MU-plugins de aviso foram implantados
no Credito Up. Imagens existentes nao foram substituidas nesta rodada.

## Causa confirmada

A LP SENAC usa `runs/guia-cursos-senac-20260917-220001/p1.webp`, SHA-256
`8289e5970cb929e2b7c446f2b840c787eba769aa917c13622cb22c3b4822de5b`.
Inspecao direta confirma anatomia impossivel: mao no rosto, braco sobre a mesa
e outra mao segurando o tablet. **Esta imagem esta rejeitada para publicacao.**

O recibo anterior dizia accepted=true, mas seu schema so perguntava sobre marcas,
documentos/interfaces oficiais, dados pessoais, promessa de resultado e incerteza.
Nao havia criterio de anatomia nem contexto da pauta enviado ao revisor.
O SHA-256 provava identidade do arquivo, nao qualidade visual. A conferencia
manual anterior tambem nao identificou o defeito; nao e uma aprovacao valida.

Os dois prompts de geracao exigiam pessoa lendo, caderno/dispositivo generico e
luz quente/golden hour. Isso explica a repeticao de cenarios e paleta: era
direcionamento do motor, nao apenas acaso do gerador.

## Engine

- `editorial_safety.py`: politica `editorial-visual-v2`; campos obrigatorios de
  erro anatomico/fisico, incompatibilidade tematica e evidencias de ambos.
  Recibos antigos nao aprovam uma imagem sob a nova politica.
- `image_review.jinja`: rastrear membros visiveis, apoio dos objetos e pertinencia
  ao titulo. Nao inventar anatomia oculta, nem exigir logos para provar relevancia.
- `image_prompt*.jinja`: remover pessoa/caderno/luz dourada como cena obrigatoria;
  sugerir atividade, ambiente e materiais pertinentes, sem simular instalacoes
  oficiais ou comprovar disponibilidade de cursos. Pessoas sao opcionais.
- `steps.py`: passar titulo/palavras-chave ao revisor e descricoes de cenas ja
  aceitas no mesmo run ao planejador, para variar ambiente, atividade e enquadramento.

Mantidas as mesmas chamadas de planejamento e revisao: nenhum novo agente,
nenhum loop de regeneracao. O prompt cresceu; nao se promete custo/token identico.
Descricoes anteriores ajudam dentro do run, mas nao sao detector visual de
duplicatas entre funis. As referencias visuais do operador ainda serao incorporadas.

Os testes provam comportamento do codigo quando o revisor sinaliza defeitos;
nao medem sensibilidade real do modelo a imagens com anatomia ruim. Falta benchmark
visual e revisao das novas imagens. Nao publicar os runs historicos sem conciliar
com as edicoes atuais do WordPress e sem revisar seus assets.

## Aviso global e fallback

Novo adaptador versionado em
`funnelforge-migracao/referencia/hardening-wordpress/volc-editorial-notice-owner.php`.
O aviso do engine permanece nos dados salvos. So e omitido na resposta quando o
aviso global ja emitiu `volc_editorial_disclosure_rendered` apos seu HTML.
Reconhecimento por DOM e texto canonico, nao por palavras soltas ou CSS de ocultacao.
Container misto, texto editado, editor e AJAX sao preservados.

O cache do Elementor inicialmente contornou o hook de renderizacao. O adaptador
marca somente o container canonico como dinamico. Foi invalidado apenas
`_elementor_element_cache` dos posts 2306, 2321 e 2336. Nao houve purge global.
A geracao normal do renderer pode recompor caches/CSS derivados; nao e uma
declaracao de zero escrita no banco. Conteudo e `_elementor_data` foram comparados.

No MU-plugin `creditoup-compliance-hardening.php`, o aviso agora abrange guias,
ausencia de vinculo, inscricao e contratacao, alem de nao coleta de credenciais.
Foi acrescentada a chamada do hook apos a emissao do aviso global.

## Provas

- Tres LPs: global presente => 1 aviso global, 0 avisos internos renderizados.
- Tres LPs com cache aquecido e sem global => 1 aviso interno renderizado.
- Doze internas: 0 avisos canonicos redundantes com global presente.
- 15/15 continuam draft; content, `_elementor_data` e modified_gmt identicos.
- Homepage: HTTP 200, sem mensagem de erro critico no HTML coletado.
- PHP lint e 13 testes isolados: aprovados. Ruff nos arquivos de seguranca/testes:
  aprovado. Suite completa: 780 testes aprovados.
- Medicao: `REFINO-VISUAL-AVISOS-2026-09-18.json`.

Teste de Elementor feito pelo renderer no servidor, nao por screenshot de
preview autenticado. Nao equivale a validacao visual desktop/mobile completa.
Cache de pagina/CDN nao foi limpo globalmente; uma pagina publica em cache pode
manter a copy anterior ate sua expiracao. Os funis continuam em rascunho.

## Implantacao e rollback

Backup privado do MU-plugin global:
`/root/volc-notice-review-20260918/creditoup-compliance-hardening.before.php`.

Hashes do global antes/depois:
- antes: `de7c845d104714613c1033f70c368e51e20e948d018dd51f41eb821f38719fe3`
- depois: `31cb79cecf873b9fd54927d167ca84e76ae6659b85c9b4d45a5e1e04758e7b9e`
- adaptador: `c2917e78f28ed2340883f34bcccd109dc38e6f396487cecff62aeeb9fe7d635d`

Rollback: restaurar somente o MU-plugin global a partir do backup e retirar o
novo adaptador para storage privado; invalidar somente os caches Elementor dos
tres IDs. Nao restaurar posts antigos, temas ou conteudo. Nao foi alterada
configuracao de Nginx, anuncios, GTM, DNS, usuarios ou credenciais.

## Pendencias

1. Receber referencias de estilo e substituir a imagem anatomicamente errada.
2. Revisar visualmente o conjunto de imagens, variacao entre funis e pertinencia.
3. Conferir previews autenticados em desktop/mobile: dobra, quebras, aviso e CTA.
4. Grafo: reconstrucao oficial tentada e bloqueada pelo detector preexistente
   `.env_webgo: jwt` (valor nao exibido nem arquivo alterado). `--check` confirmou
   `current=false`, snapshot de 2026-08-29. P10-T17 e cap_funnel foram atualizados
   nas fontes humanas e permanecem partial. Nao contornar o detector.

Nada aqui garante aprovacao do Google Ads ou elimina a necessidade de revisao humana.
