# Meta safe validation and PAUSED birth v1

## Veredito

- `META_P0_COMPILE_AND_VALIDATE_ONLY_READY`
- `META_CREATE_PAUSED_NOT_MOUNTED`
- `P11-T05_PARTIAL`

O Hub agora possui um caminho autenticado, local e administrado para montar a
primeira receita Meta v26 (`OUTCOME_TRAFFIC` → `WEBSITE` →
`LANDING_PAGE_VIEWS`), resolver conta/Page/imagem por referências opacas,
compilar um plano determinístico e, após clique explícito, enviar somente as
raízes independentes com `execution_options=["validate_only"]`.

Nenhuma rota de aprovação, criação ou ativação foi montada. O botão de criação
permanece visível e desabilitado, explicando o bloqueio.

## Receita P0

- conta ativa e BRL;
- campanha, conjunto e anúncio em `PAUSED`;
- criativo estático com imagem já existente na conta;
- orçamento diário no conjunto;
- `LOWEST_COST_WITHOUT_CAP`, cobrança por impressões;
- Brasil, 18–65+, posicionamentos automáticos;
- nenhuma categoria especial, Advantage Audience, `promoted_object`, pixel ou
  custom conversion nesta primeira receita.

## Segurança e autoridade

- token continua no Keychain e nunca entra no payload público;
- Page ID, account ID e image hash são resolvidos novamente no backend e nunca
  retornados ao navegador;
- a rota exige host local/macOS e identidade ADMIN;
- `validate_only` exige flag efêmera no boot e confirmação no corpo;
- criação real não tem endpoint;
- existe um adapter de saga Supabase e uma migration candidata, ambos fechados
  por flag e não aplicados;
- a saga exige aprovação presa a plano, conta, ator, orçamento e expiração;
- cada passo é registrado antes do POST; timeout vira estado ambíguo e impede
  retry cego; read-back confirma os objetos veiculáveis em `PAUSED`.

## Próximo ato

1. operador inspeciona a bancada em `/trafego/meta/nova?etapa=base`;
2. operador compila e, se quiser, clica em validar na Meta (zero criação);
3. somente depois de uma autorização separada: aplicar as migrations Meta no
   Supabase oficial, montar aprovação/criação e criar um único canário PAUSED;
4. ativação permanece fora desse ato.

## Limites honestos

- a validação remota Meta não foi chamada nesta implementação;
- as migrations não foram aplicadas no Supabase oficial;
- a criação PAUSED está compilada/testada, mas deliberadamente não alcançável
  por HTTP;
- categorias especiais, Sales/Leads, custom conversions, vídeo, catálogo e
  Advantage+ precisam de receitas separadas.
