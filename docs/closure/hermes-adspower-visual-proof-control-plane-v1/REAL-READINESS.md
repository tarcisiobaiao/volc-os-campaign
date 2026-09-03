# Real Readiness — o que ainda falta fora do núcleo hermético

## Estado real atual

| Item | Estado |
|---|---|
| Página real cadastrada | não provado nesta missão |
| Perfil AdsPower real inventariado | não provado nesta missão |
| Referência 1Password real para AdsPower | não resolvida nesta missão |
| Broker real persistente em host AdsPower | não instalado/não iniciado |
| Chamada AdsPower real | proibida/não feita |
| Screenshot real | proibido/não feito |
| VisualProofJob persistente | não há migration oficial aplicada |
| Aprovação humana real | não executada |

## Prontidão local entregue

O repositório agora tem contratos, broker, fake HTTP e painel de prontidão que distinguem:

- pronto para receber peça;
- pronto para publicar;
- pronto para QA;
- QA não persistido;
- QA não executado;
- em execução/aguardando revisão;
- indeterminado;
- corrigir;
- aprovado por humano.

## Lacunas para produção

1. Definir e autorizar os dados mínimos da página real.
2. Registrar referência lógica da credencial no Cofre, sem valor secreto.
3. Inventariar perfil AdsPower real com nome lógico, owner e ativo relacionado.
4. Criar persistência governada para `VisualProofJob`/receipt se a operação exigir durabilidade.
5. Implementar driver real de captura em checkpoint separado.
6. Rodar primeira leitura real read-only somente após autorização literal.

Nenhuma dessas lacunas transforma o núcleo hermético em falha; elas impedem apenas declarar `REAL_*` ou `PRODUCTION_READY`.
