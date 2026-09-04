# Meta Operator Preview v1

## Resultado

O Hub Meta deixou de ser um placeholder. Mesmo sem uma conta conectada, o
operador consegue navegar por inventários e páginas canônicas de campanha,
conjunto, anúncio e criativo, além de percorrer uma bancada de criação em oito
decisões. Todo valor não observado na Meta é marcado como demonstração.

## Rotas para inspeção

- `/trafego?rede=meta&nivel=campanhas`
- `/trafego?rede=meta&nivel=conjuntos`
- `/trafego?rede=meta&nivel=anuncios`
- `/trafego?rede=meta&nivel=criativos`
- `/trafego/meta/campanhas/campanha-descoberta-01?modo=demo`
- `/trafego/meta/conjuntos/conjunto-amplo-01?modo=demo`
- `/trafego/meta/anuncios/anuncio-estatico-01?modo=demo`
- `/trafego/meta/criativos/criativo-imagem-01?modo=demo`
- `/trafego/meta/nova?modo=demo&etapa=base`

## Configuração local provisória

O ícone de engrenagem abre uma configuração deliberadamente local:

1. exige sessão ADMIN já validada pelo backend;
2. só responde em loopback, no macOS;
3. recebe o token do usuário de sistema apenas no corpo autenticado;
4. valida identidade e contas acessíveis por `GET /me` e
   `GET /me/adaccounts` na Graph API v26.0;
5. só depois de uma resposta válida grava a credencial como senha genérica no
   Chaveiro do macOS, separada pelo `sub` autenticado;
6. nunca devolve o token e não usa Supabase, browser storage, URL, `.env`, log
   ou Git.

As rotas locais oferecem somente consultar estado seguro, salvar+testar,
testar novamente e remover. Não existe endpoint Meta de mutate nesta entrega.

## Gates

- testes backend Meta: 52 passaram;
- contraprovas focais da configuração local: 5 passaram;
- testes Hub/Meta frontend: 47 passaram;
- TypeScript: passou sem erro;
- build Vite: passou;
- scanner de segredos: nenhum padrão forte;
- `git diff --check`: limpo;
- `/health` local: saudável;
- rota de configuração sem sessão: HTTP 401.

## Estado honesto

- `P11-T03`: partial — a porta provisória existe, mas nenhum token real foi
  fornecido e nenhuma conta Meta foi lida.
- `P11-T05`: partial — a bancada representa o contrato, mas não persiste
  blueprint e não cria campanha.
- `P11-T06`: partial — as páginas por nível existem, mas recebem fixtures
  explícitas, não o read model real.

## Fora desta entrega

- aplicar migration no Supabase;
- importar segredo para o Cofre definitivo;
- ler inventário ou insights reais;
- persistir o formulário de criação;
- validar, criar, editar, pausar ou ativar objeto Meta;
- deploy.
