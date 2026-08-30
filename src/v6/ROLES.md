# Roles do sistema

O sistema tem **três papéis** distintos. Ponto.

---

## 1. Admin

O usuário com acesso global ao sistema. É quem entra em
`/settings/users`, cadastra outros usuários, define acessos,
configura comissões e opera o sistema de ponta a ponta.

- Vive no campo `users.role = 'ADMIN'`
- É um **role global**, não está preso a nenhuma campanha
- Tem acesso a todas as telas administrativas
- **Não é configurado via membership** (não aparece em
  `campaign_members`)
- Normalmente não recebe comissão — é quem gerencia o sistema,
  não quem toca campanhas

**Quando atribuir:** às poucas pessoas de confiança que
gerenciam usuários, acessos e comissões dentro da empresa.

---

## 2. Operador

O usuário que **toca uma ou mais campanhas** e **pode receber
comissão** sobre elas.

- Vive em duas camadas:
  - **Role global:** `users.role = 'OPERATOR'`
  - **Role por campanha:** uma linha em `campaign_members` com
    role `OPERATOR` para cada campanha à qual ele tem acesso
- Só vê as campanhas onde foi explicitamente vinculado
- **Pode** ter uma vigência de comissão (`campaign_commissions`)
  para cada campanha que opera
- Se não tiver linha em `campaign_commissions`, não ganha nada —
  mesmo sendo operador da campanha

**Quando atribuir:** à pessoa que vai mexer na campanha
(otimizar, ajustar, responder por resultado). Normalmente é
quem recebe a comissão daquela campanha.

**Exemplo:**
> Marlise é `users.role = 'OPERATOR'`. Nas campanhas onde ela
> atua, tem `campaign_members.role_id` apontando para
> `OPERATOR`, e tem uma linha correspondente em
> `campaign_commissions` com 15%.

---

## 3. Visualizador

O usuário que **pode estar vinculado a uma ou mais campanhas
apenas para visualização** — sem poder receber comissão.

- Vive em `campaign_members` com role `VIEWER`
- Tipicamente tem `users.role = 'OPERATOR'` no role global
  (ou seja, é um usuário comum do sistema, só não é admin)
- **Não deve** ter linha em `campaign_commissions` — por design,
  visualizador não ganha comissão
- Aparece na campanha só para acompanhar números, auditar,
  revisar ou observar

**Quando atribuir:** em três situações típicas:

1. **Supervisor/QA** que precisa acompanhar uma campanha sem
   ter responsabilidade operacional nem financeira sobre ela
2. **Treinamento** — operador novo que está aprendendo, olha
   sem mexer
3. **Stakeholder externo** — cliente, consultor, auditor que
   precisa ver números mas não faz parte da operação

**Exemplo:**
> João entrou no time esta semana. Está como Visualizador em
> 5 campanhas da Marlise por 30 dias, para aprender. Depois disso,
> ele será promovido para Operador em algumas delas e aí sim
> passará a ter comissão.

---

## Regra de ouro da comissão

| Papel | Pode receber comissão? |
|---|---|
| **Admin** | Geralmente não (não opera campanha) |
| **Operador** | Sim — é o caso normal |
| **Visualizador** | **Não** — por design |

A comissão **não é um campo do membership**. É uma tabela
separada (`campaign_commissions`) com sua própria vigência. Um
operador só recebe comissão de uma campanha se, e somente se,
existir uma linha vigente em `campaign_commissions` para o par
`(user, campaign)`. Não há pagamento automático por ser operador.

---

## Múltiplos papéis na mesma campanha

O sistema **permite e suporta** que uma mesma campanha tenha
vários usuários com papéis diferentes ao mesmo tempo:

| Usuário | Papel na campanha | Tem comissão? |
|---|---|---|
| Marlise | Operador | Sim, 15% |
| João | Operador | Sim, 10% |
| Ana | Visualizador | Não |

Isso é o cenário esperado e suportado. Campanha **nunca é
exclusiva** de um único operador.

---

## TL;DR

1. **Admin** = acesso total ao sistema. Global. Fora de `campaign_members`.
2. **Operador** = toca campanha e pode ter comissão. Aparece em
   `campaign_members` como `OPERATOR` + linha em
   `campaign_commissions`.
3. **Visualizador** = só olha. Aparece em `campaign_members`
   como `VIEWER`. **Não** aparece em `campaign_commissions`.

Campanha pode ter vários operadores e vários visualizadores
simultaneamente. Comissão é separada do vínculo.
