/**
 * ADAPTADOR — o antigo `/trafego` visto como conteúdo da aba Oportunidades.
 *
 * ## O que este arquivo é hoje
 *
 * Uma casca de compatibilidade, e nada mais. O conteúdo operacional mudou-se
 * para `components/trafego/oportunidades/QuadroDeOportunidades`, que é um
 * COMPONENTE EMBUTÍVEL: sem `<Layout>`, sem cabeçalho de página e sem recuo
 * próprio. Este arquivo continua existindo só porque `src/App.tsx` ainda
 * escreve `oportunidades={<TrafegoPage />}` na rota, e trocar a rota é a
 * mudança do integrador, não desta frente.
 *
 * ## Por que a página inteira saiu de dentro da aba
 *
 * Uma página dentro de outra desenha duas molduras: dois recuos somados, e —
 * enquanto o cabeçalho ainda morava aqui — dois `<h1>Tráfego</h1>` empilhados.
 * Redundância visual é o menor dos danos: dois títulos de documento numa página
 * só fazem a estrutura parar de dizer, a quem navega por leitor de tela, onde
 * ele está. A moldura passou a ser uma só, a do Hub.
 *
 * ## Condição de aposentadoria
 *
 * Quando a rota passar a montar `<QuadroDeOportunidades />` diretamente, este
 * arquivo sai e nada mais precisa mudar. Ele não tem lógica, não tem estado e
 * não tem estilo: qualquer outra coisa aqui dentro é um sinal de que a mudança
 * foi para o lugar errado.
 */
import React from 'react';

import QuadroDeOportunidades from '@/components/trafego/oportunidades/QuadroDeOportunidades';

const TrafegoPage: React.FC = () => <QuadroDeOportunidades />;

export default TrafegoPage;
