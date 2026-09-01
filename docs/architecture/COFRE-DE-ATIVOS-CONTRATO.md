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

## Fronteira privada — implementada em 01/09/2026

A persistência existe: `supabase/migrations/v13_01_cofre_de_ativos.sql`, nove tabelas com prefixo `cofre_` no Supabase oficial, atrás de API administrativa (`/api/cofre`) e `exigir_admin`. **Não aplicada em produção** — exige autorização separada.

O backend guarda uma referência opaca em `cofre_credencial_referencia.localizador`. Essa referência:

- não é retornada ao browser — nenhuma função de leitura do banco a projeta;
- não é escrita no grafo nem no Roadmap;
- não aparece em log, recibo, snapshot de revisão ou mensagem de erro;
- não permite buscar o segredo sem uma operação administrativa com o papel `postgres`.

O provedor foi decidido: **1Password**, conforme o ADR de 28/08. O enum aceita os cinco (`1password`, `bitwarden`, `vaultwarden`, `passbolt`, `infisical`) porque a gramática do localizador é por provider e a coluna precisa aceitar a forma de cada um.

### O que impede uma senha de entrar, na prática

Três mecanismos, e nenhum sozinho bastaria:

1. **Forma.** `localizador` tem CHECK de gramática por provider. `op://cofre/item/campo` entra; `Tr0ub4dor&3` não é uma referência mal formatada — é um texto que a gramática não gera.
2. **Chave.** Todo jsonb que entra passa por varredura recursiva que compara a chave *normalizada* (minúscula, sem separadores) contra lista fechada. `accessToken`, `ACCESS-TOKEN` e `access_token` colapsam em `accesstoken`.
3. **Superfície.** Nenhuma função devolve o localizador. A postura sai por `cofre_postura_credencial`, que projeta provider, nome lógico, finalidade, estado e frescor.

⚠️ **Query string é recusada de propósito.** `op://cofre/item/campo?attribute=otp` aponta para um TOTP, e o ADR é explícito: MFA não entra no Cofre nem por referência.

## Retrato editorial — e por que ele deixou de ser a fonte

`src/features/asset-vault/fixtures.ts` continua existindo, e **apenas para teste hermético do contrato público**. Desde 01/09/2026 a tela lê `/api/cofre`, e a fixture **não é fallback**.

O motivo é preciso: uma tela que sempre mostra os mesmos oito ativos não distingue "o Cofre está vazio" de "o Cofre não respondeu" — porque nunca esteve vazio nem deixou de responder. Há teste que percorre os oito nomes da fixture e exige que nenhum apareça quando a API falha.

Gavetas sem ativos continuam visíveis com contagem zero, agora vindas do servidor. Isso torna a estrutura compreensível sem inventar contas, páginas ou canais ainda não conferidos.

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

## Entregue em 01/09/2026 (branch `sprint/asset-vault-onepassword-production-v1`)

- banco e migrations (`v13_01` + rollback `v13_99`), com 75 provas no ciclo aplicar→operar→reverter→reaplicar em `postgres:15`;
- API administrativa com 13 rotas, idempotência e recibo;
- formulários de cadastro, revisão, relação, verificação, referência de acesso, aposentadoria e reativação;
- importação determinística dos 7 engines criativos a partir dos manifestos versionados;
- escolha do cofre externo (1Password) e o smoke local de viabilidade;
- rota de handoff para produção criativa e publicação.

## Ainda não entregue

- **aplicação da migration em produção** — exige autorização separada;
- **cadastro real da página Facebook monetizada** — não há um único dado real dela no repositório; o fluxo e o pedido ao operador estão prontos (`docs/closure/asset-vault-onepassword-production-v1/`);
- **prova do 1Password ao vivo** — o app e o CLI não estão instalados nesta máquina, e o smoke reporta `blocked/cli_ausente`, que é o resultado correto;
- **escrita no grafo** — esta missão produz um delta de curadoria, e só o integrador aplica;
- **rotação ou leitura de qualquer credencial** — nunca foi escopo, e o desenho impede.
