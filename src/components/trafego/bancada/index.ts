/**
 * O vocabulário visual da Bancada Guiada.
 *
 * Seis peças, puramente apresentacionais: sem estado global, sem `fetch`, sem
 * decisão. Elas projetam o que o servidor já adjudicou — e a razão de existirem
 * juntas é que a Bancada tinha quatro linguagens de superfície convivendo
 * (`VISUAL-DIRECTION.md §2`: `card-volc`, `rounded-md+border`, poço `bg-muted`
 * e ardósia crua), e o empate entre elas é o que fazia a tela parecer gerada.
 */
export { ChipDeEstado, type TomDoChip } from './ChipDeEstado';
export { MapaDeParadas } from './MapaDeParadas';
export { PainelDeBloqueio } from './PainelDeBloqueio';
export { BlocoDeEvidencia, LinhaDeFato } from './BlocoDeEvidencia';
export { AcaoDominante } from './AcaoDominante';
export { Pedido } from './Pedido';
