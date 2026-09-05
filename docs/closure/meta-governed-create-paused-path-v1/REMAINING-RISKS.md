# Riscos remanescentes — meta-governed-create-paused-path-v1

Herdados e novos. Um risco declarado aqui não está resolvido; está registrado.

---

## Herdados, ainda abertos

1. **A migration nunca foi aplicada em lugar nenhum.** Nem no Supabase oficial,
   nem em staging. O único ambiente onde ela rodou é o PostgreSQL descartável de
   `scripts/provar-ciclo-meta-create-paused.sh`. Ver
   `RUNBOOK-MIGRATION-META-CREATE-PAUSED.md`, cujos hashes foram atualizados
   nesta missão.

2. **Nenhum canário PAUSED foi executado.** As rotas existem e estão provadas
   contra transporte hermético. A primeira criação real continua não autorizada,
   e ela é a única coisa que decide se o contrato de payload do **AdSet** e do
   **Ad** está certo.

3. **Cobertura da validação continua parcial por construção.** Só Campaign e
   AdCreatives podem ser validados sem um objeto pai real. `advantage_audience`,
   a ausência deliberada de `destination_type`, `optimization_goal`,
   `daily_budget`, `billing_event`, `bid_strategy`, `start_time` e `targeting`
   **nunca chegaram à Meta**. Um plano "validado" ainda pode falhar no conjunto,
   e a tela diz isso junto do botão que cria — não numa nota de rodapé.

4. **Criativo flexível bloqueado por um único campo**, e **criativo de vídeo
   bloqueado pela miniatura.** Inalterados nesta missão.

5. **Baseline de TypeScript desatualizado.** `gate_tsc_ratchet.py` guarda 76;
   HEAD produz 77. Medido antes desta missão e inalterado por ela. O baseline
   não foi mexido: alterá-lo esconderia a dívida em vez de declará-la.

---

## Novos, introduzidos por esta missão

6. **A reconciliação identifica objetos por nome + read-back + `created_time`.**
   O nome é só a busca; a conclusão exige o read-back completo e a prova de que
   o objeto nasceu **depois** de o passo ser preparado. Dois homônimos na conta
   tornam o passo indecidível e a rota devolve `PERMANECE_AMBIGUO` em vez de
   escolher um. **Consequência operacional:** uma conta com nomes repetidos pode
   ter um recibo que a reconciliação nunca fecha sozinha.

   ⚠️ **`AdCreative` nunca é fechado por leitura.** A Marketing API não expõe
   `created_time` para criativos, então não há como provar que o criativo
   encontrado nasceu deste despacho. Um criativo ambíguo permanece ambíguo e
   exige decisão humana fora desta rota. É a escolha certa e é uma lacuna real.

6b. **O piso temporal da reconciliação é um piso, não um lease.** `resolve_absent`
   recusa fechar um passo com menos de 120 s contra um cliente HTTP de 20 s.
   Isso cobre qualquer despacho realista, e **não** cobre uma requisição
   patologicamente lenta que sobreviva a dois minutos. Um lease com fencing
   token seria a solução completa; ela não foi construída nesta missão.

6c. **A adoção entre aprovações confia na identidade de payload.** Quando um
   passo idêntico — mesma conta, mesmo nome de passo, mesmo `payload_sha256` —
   já está `CREATED`, a saga nova o adota sem POST. Se o operador quiser
   deliberadamente duas campanhas byte a byte idênticas na mesma conta, ele não
   conseguirá pela bancada: a segunda adota a primeira. Julgado correto (duas
   campanhas indistinguíveis são quase certamente um engano), e é uma restrição
   nova que ninguém pediu explicitamente.

7. **A prova de ausência depende de a listagem terminar.** `MAXIMO_DE_PAGINAS =
   25` a 200 objetos por página cobre 5.000 objetos por aresta. Uma conta maior
   que isso faz a leitura bater no teto e devolver `PERMANECE_AMBIGUO` — que é o
   comportamento seguro, e é também uma reconciliação que não conclui. Nenhuma
   conta VOLC chega perto disso hoje; o dia em que chegar, o teto precisa virar
   uma busca com filtro por nome, não um número maior.

8. **`plan_request` no banco expande a superfície de dados persistidos.** São
   referências opacas e texto do operador — sem token, sem id da Meta, sem
   `image_hash`. Mas é conteúdo que antes não saía do processo, e num Supabase
   comprometido ele revelaria a estratégia de campanha (destino, copy,
   orçamento). Julgado aceitável: `account_ref` já era persistido, e sem o
   pedido gravado a criação teria que aceitar payload do navegador — troca pior.

9. **A janela de 15 minutos não foi exercitada por um operador real.** Ela é
   curta o bastante em teoria para ler o resumo, marcar, digitar e clicar.
   Ninguém cronometrou. Se na prática for apertada, encurtar ou alongar **dentro
   do teto de uma hora** não exige migration.

10. **Reaprovar exige revalidar.** Consequência direta do `UNIQUE(validation_id)`,
    e é deliberada. Custa uma chamada `validate_only` extra por reaprovação —
    barata e sem efeito externo, mas é atrito novo que o operador vai sentir.

11. **A reconciliação relê a saga inteira.** Para um plano de 4 operações são 4
    listagens de aresta. Para um lote de 10 variações são 22 operações e até 22
    listagens. Nenhum limite de taxa da Meta foi medido contra esse padrão.

12. **Sem verificação visual no navegador.** A extensão do Chrome não foi
    conectada nesta missão. A tela é exercitada por 13 testes novos em jsdom que
    renderizam a página inteira, e o servidor de desenvolvimento responde na
    rota — mas ninguém olhou os pixels.

13. **`RegistroSagaMetaSupabase._exigir_escrita` gateia também as leituras.**
    `recibo` e `manifesto` exigem `META_CREATE_LEDGER_WRITE_ENABLED`, apesar de
    não escreverem nada. É fail-closed e simples, e é levemente mais restritivo
    do que precisaria: com a flag fechada não dá para inspecionar um recibo
    antigo. Deliberado nesta missão; revisável quando houver caso de uso.
