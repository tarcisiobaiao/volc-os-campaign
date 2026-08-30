# Cofre de Ativos — contrato de produto v1

## Decisão

O Cofre de Ativos é o inventário operacional do patrimônio digital da VOLC. Ele responde, em linguagem simples:

- o que existe;
- em qual gaveta o ativo está;
- quem cuida dele;
- o que já foi comprovado;
- como o acesso está protegido;
- a que outros ativos e projetos ele se conecta;
- qual é a próxima ação concreta.

O Cofre não é um gerenciador de senhas. Senhas, tokens, chaves privadas, MFA, códigos de recuperação e o endereço interno do item no cofre especializado nunca entram no contrato público nem chegam ao navegador.

## Como a pessoa encontra um ativo

A interface começa por sete gavetas operacionais. As relações do grafo continuam existindo, mas aparecem como contexto do ativo, não como porta de entrada.

| Gaveta | O que entra |
| --- | --- |
| Presenças sociais | perfil e página do Facebook, Instagram, YouTube, Pinterest, TikTok, LinkedIn e X |
| Mídia paga | Business Portfolio Meta, contas Meta Ads, MCC e contas Google Ads |
| Sites e domínios | domínio, site, WordPress, landing page e propriedade monetizada |
| Comunidades e mensagens | WhatsApp, comunidades, Telegram e hubs como ChatPion |
| Produção criativa | engines de imagem, vídeo, áudio e variação criativa |
| Automações e integrações | workflows, conectores e rotinas operacionais |
| Infraestrutura e dados | Supabase, servidores, repositórios e serviços-base |

Um tipo pertence a exatamente uma gaveta. Essa regra é validada em tempo de execução para impedir que a mesma conta apareça classificada de formas contraditórias.

## Contrato público

Cada ativo publicado para a interface contém:

1. identidade e tipo;
2. gaveta operacional;
3. plataforma;
4. estado e criticidade;
5. dono e estado da custódia;
6. projeto e vertical, quando conhecidos;
7. ID sanitizado ou URL pública HTTP(S);
8. capacidades;
9. postura de credencial, sem segredo e sem localizador;
10. verificação e data da prova;
11. evidências com procedência;
12. relações declaradas ou verificadas;
13. próxima ação;
14. tags de busca.

O schema executável está em `src/features/asset-vault/contract.ts`. Ele é estrito: campos desconhecidos falham, URLs fora de HTTP(S) falham e tipos colocados na gaveta errada falham.

## Fronteira privada da próxima etapa

A persistência será criada no Supabase oficial do VOLC O.S., `https://database.agenciavolc.com.br`, atrás de API administrativa e autorização por papel.

O backend privado poderá guardar uma referência opaca para um item em Bitwarden, Vaultwarden, Passbolt ou Infisical. Essa referência:

- não será retornada ao browser;
- não será escrita no grafo;
- não aparecerá em logs ou recibos públicos;
- não permitirá buscar o segredo sem uma operação administrativa auditada.

O provedor do cofre especializado ainda é uma decisão pendente. A interface atual não finge que essa escolha já foi feita.

## Retrato editorial inicial

`src/features/asset-vault/fixtures.ts` é um retrato temporário para validar contrato e experiência. Não é seed, cadastro nem prova adicional de propriedade. Cada linha carrega a evidência que sustenta o que está sendo mostrado.

Gavetas sem ativos continuam visíveis com contagem zero. Isso torna a estrutura compreensível sem inventar contas, páginas ou canais ainda não conferidos.

## Ordem de implementação

1. Contrato público e navegação por gavetas.
2. Schema privado no Supabase oficial, com RLS forçada.
3. API administrativa, auditoria e idempotência.
4. Cadastro, edição, revisão e aposentadoria pela interface.
5. Importadores somente leitura para plataformas conhecidas.
6. Correspondências com projetos, campanhas e o grafo.
7. Integração com um cofre externo, sem material sensível no VOLC O.S.

## Aceite desta etapa

- a rota `/settings/cofre-ativos` existe e é administrativa;
- o inventário abre por gavetas reconhecíveis;
- Facebook, Instagram, Business Portfolio, Google Ads, WordPress, Pinterest e YouTube têm tipos explícitos no catálogo;
- relações são uma lente secundária;
- nenhuma credencial é armazenada;
- payload com chave sensível é recusado;
- URL não HTTP(S) é recusada;
- build e testes do Cofre passam.

## Ainda não entregue

- banco e migrations;
- API;
- formulário de cadastro;
- importação automática;
- escrita no grafo;
- escolha e integração do cofre externo;
- rotação ou leitura de qualquer credencial.
