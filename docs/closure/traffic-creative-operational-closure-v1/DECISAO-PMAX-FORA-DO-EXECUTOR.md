# Decisão: PMax planeja, mas não entra no executor nesta rodada

*Decisão do lead da missão, tomada em 01/09/2026 sobre proposta do worker
channel-builders. Registrada porque é estrutural e porque a alternativa parecia,
de fora, a escolha "mais completa".*

## O que foi decidido

`perfil.PERFORMANCE_MAX.construtor` permanece `None`. `POST /api/trafego/provar`
com `canal=PMAX` continua respondendo **422**. `pmax.planejar()` existe, é
chamável direto, monta o plano offline e não fala com o Google.

PMax fica, portanto: **planejável ✓ · validável ✗ · criável pausada ✗ · ativável ✗**.

## Por que não habilitamos

Promover o construtor mudaria `perfil.canais_que_provam()`. E `volc_ads/subir.py`
**levanta no import** quando a vista dele discorda do perfil — não em runtime, no
import. O efeito não seria "PMax meio pronto": seria a rota HTTP inteira caindo,
para os quatro canais, incluindo o Search que acabou de ser provado num canário
real.

Trocar um canal novo por uma regressão nos três que já funcionam é um mau negócio.
E o CLAUDE.md já dizia isto antes de a questão aparecer: não misture reorganização
estrutural ampla com mudança funcional ampla no mesmo lote, sob pena de perder a
capacidade de provar equivalência e reverter.

Habilitar exige mudança coordenada em `subir.py`, no backend e em `plataforma.py`.
Isso é um lote próprio, com prova própria.

## Por que isso ainda fecha o critério da missão

A Definição de Pronto pede, para PMax: contrato próprio, asset groups e assets
obrigatórios modelados, sinais e limites explícitos, mensuração inadequada
mantendo criação/ativação bloqueada, plano offline e objetos v25 provados, e
`validate_only` **"somente se todos os requisitos reais existirem"**.

Esse "somente se" é condicional por escrito. Nenhum item exige PMax no executor
HTTP. O que a decisão nos obriga a entregar no lugar é prova mais forte offline.

## As três condições impostas para o aceite

1. **O 422 é estado, não erro.** O corpo precisa dizer *por que* recusou, com
   código de bloqueio próprio em `plano.CODIGOS`. Quem opera precisa distinguir
   "PMax planeja offline mas não está habilitado no executor nesta versão" de
   "esse canal não existe" — são leituras opostas do mesmo 422.

2. **Prova offline com protos v25 reais**, instanciados via `client.get_type(...)`
   e serializados, sem rede. Mock não conta. Foi exatamente "ausência de prova com
   os protos v25 reais" que reprovou o builder Demand Gen na revisão anterior.
   Esta prova é o que substitui o `validate_only` que não vamos rodar.

3. **O portão de mensuração precisa ser testado por si.** Hoje PMax está bloqueado
   por dois motivos independentes empilhados: o construtor `None` e a mensuração
   inadequada. Só o segundo é o que a missão pede. Se a prova se apoiar no
   primeiro, no dia em que alguém habilitar o construtor o portão desaparece
   junto — e ninguém percebe, porque o teste continuaria verde pelo motivo errado.

A terceira condição é a que evita que esta decisão vire dívida escondida.

## Estado que a tela precisa mostrar

"Não habilitado nesta versão" não é falha, não é ausência e não é zero. É um
estado próprio — indisponível por decisão — e `/trafego` precisa dizê-lo com
essas palavras: nem vermelho de erro, nem verde de pronto.
