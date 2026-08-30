"""O sistema de design do widget: um CSS e um JavaScript, escritos UMA vez.

## O que muda em relação ao que havia

Cada widget chegava com o próprio CSS. O de p5 (run 9) trazia 4.098 caracteres
e 19 cores diferentes, inventadas naquela chamada. Duas páginas do mesmo funil
nunca se pareciam, e nenhuma delas herdava conserto feito na outra.

Aqui o CSS é constante. Ele é escrito uma vez, revisado uma vez, e as quatro
peças o compartilham — o que também significa que acessibilidade e CLS deixam
de depender de o modelo lembrar.

## ⚠️ A PEÇA PERTENCE AO ARTIGO, NÃO A ESTE ARQUIVO

A primeira versão deste CSS foi desenhada no vácuo: paleta petróleo, face
monoespaçada nos rótulos, corpo travado em 16px. Publicada, ficou visivelmente
estrangeira — e o operador descreveu como "totalmente fora do design do site".
Ele estava certo, e o desencontro era MEDÍVEL.

Medido em 19/08/2026 na página no ar (`creditoup.com.br/rec/...-p3/`), com
estilos computados pelo navegador e cores amostradas do pixel:

| | o artigo | o widget de antes |
|---|---|---|
| fonte | Source Sans Pro | herdada (certo) |
| corpo | **21px** / 36px | **16px** / 1,55 |
| título | `#000`, peso 600 | `#10222e` |
| acento | **`#077793`** | `#0b5f63` |
| rótulos | mesma face | **monoespaçada** |

Um bloco de 16px dentro de um artigo de 21px lê como um recorte de outro site.
Não era questão de gosto: era escala, cor e face erradas ao mesmo tempo.

## As decisões, e por que cada uma

**A escala é RELATIVA, nunca absoluta.** `font-size: .95em` em vez de `16px`:
a peça acompanha o artigo onde quer que seja injetada. Se amanhã o tema mudar o
corpo para 18px, o widget acompanha sozinho — travar em pixel foi exatamente o
que produziu o desencontro.

**A paleta é a do site, medida.** `--vw-marca: #077793` é a cor dos links do
artigo, amostrada do pixel (1.795 amostras). O texto é `#46494c` e os títulos
`#000`, que são os valores computados do próprio tema. A peça não traz cor
nova nenhuma para a página.

**Sem `@font-face` e sem face própria.** Tudo herda a família do artigo
(Source Sans Pro, já carregada). Os rótulos que antes eram monoespaçados agora
são a mesma face em caixa alta com entreletra — é o vocabulário do Material,
que é o que este site fala. Uma fonte remota, além disso, custaria uma
requisição, um FOIT e um layout shift num artigo cuja tese é viewability.

**Cor nunca é o único sinal.** Todo cenário imprime o rótulo do chip em texto ao
lado da cor, e `contrato.py` recusa cenário sem `chip`. Regra WCAG
`color-not-only`: quem não distingue verde de âmbar continua lendo o veredito.

**Os nomes de classe são CONGELADOS.** Mudar `.vw-caixa` para `.vw-card` seria
inofensivo aqui e quebraria toda página já publicada: o conserto de uma peça no
ar é a troca do `<style>` dentro do bloco, e ela só funciona enquanto o markup
antigo casar com o CSS novo.

**Sem `prefers-color-scheme`.** Deliberado. O widget mora dentro de um artigo de
tema claro; segui-lo pelo sistema operacional faria a peça virar a única caixa
escura numa página branca. O widget acompanha o ARTIGO, não o sistema.

**CLS zero por geometria.** `.vw-out` é um grid e todo cenário ocupa
`grid-area:1/1`. O container tem sempre a altura do MAIOR cenário; trocar de
resposta muda `visibility`, que não reflui. O anúncio abaixo não se move porque
não há para onde mover. `checks.py` exige `grid-area` e proíbe `.style.display`
justamente para garantir o par.

**Alvo de toque 48px.** O maior entre os 44pt da Apple e os 48dp do Material —
quem lê isto está no celular, muitas vezes com pressa.
"""
from __future__ import annotations

# ⚠️ O `&` é PROIBIDO no corpo do <script> (`checks.py::ampersand_in_script`):
# o WordPress escapa e o JavaScript quebra. Por isso não há `&&` nem `||` aqui
# embaixo — os testes encadeados viram `if` aninhado, e as alternativas viram
# dois `if` separados. Fica mais verboso e é a única forma que sobrevive.
#
# Também proibidos e ausentes: `innerHTML`/`createElement` (tudo é
# pré-renderizado), `localStorage` (nada é lembrado entre visitas),
# `document.addEventListener('click')` global e `.style.display`.

JS = """(function(){
var r=document.getElementById("__ID__");
if(!r){return;}
var ctl=r.querySelectorAll("[data-vw-ctl]");
var cen=r.querySelectorAll("[data-vw-cen]");
function chave(){
var p=[];
for(var i=0;i<ctl.length;i++){
p.push(ctl[i].getAttribute("data-vw-ctl")+"="+ctl[i].getAttribute("data-vw-valor"));
}
return p.join("|");
}
function alvo(){
var k=chave();
for(var i=0;i<cen.length;i++){
if(cen[i].getAttribute("data-vw-quando")===k){return cen[i];}
}
for(var j=0;j<cen.length;j++){
if(cen[j].getAttribute("data-vw-padrao")==="1"){return cen[j];}
}
return cen[0];
}
function pintar(){
var a=alvo();
for(var i=0;i<cen.length;i++){
cen[i].style.visibility=(cen[i]===a)?"visible":"hidden";
}
}
for(var i=0;i<ctl.length;i++){
(function(c){
var s=c.querySelector("select");
if(s){
s.addEventListener("change",function(){
c.setAttribute("data-vw-valor",s.value);
pintar();
});
}
var bs=c.querySelectorAll("button[data-vw-opt]");
for(var k=0;k<bs.length;k++){
(function(b){
b.addEventListener("click",function(){
c.setAttribute("data-vw-valor",b.getAttribute("data-vw-opt"));
for(var m=0;m<bs.length;m++){
bs[m].setAttribute("aria-pressed",(bs[m]===b)?"true":"false");
}
pintar();
});
})(bs[k]);
}
})(ctl[i]);
}
pintar();
})();"""


CSS = """.vw{--vw-tinta:#111;--vw-corpo:#46494c;--vw-fraca:#6b7074;--vw-linha:#e3e6e8;
--vw-papel:#f6f8f9;--vw-marca:#077793;--vw-marca-fraca:#e6f1f4;--vw-raio:12px;
box-sizing:border-box;margin:2em 0;padding:0;border:1px solid var(--vw-linha);
border-radius:var(--vw-raio);background:#fff;color:var(--vw-corpo);
font-family:inherit;font-size:.95em;line-height:1.6;overflow:hidden;
box-shadow:0 1px 2px rgba(17,17,17,.04),0 4px 16px rgba(17,17,17,.05)}
.vw *,.vw *::before,.vw *::after{box-sizing:border-box}
.vw h3,.vw h4{margin:0;color:var(--vw-tinta);font-family:inherit;font-weight:600;
letter-spacing:normal}
.vw ul{margin:0;padding:0;list-style:none}

/* cabeçalho — o sobrolho é a MESMA face em caixa alta, não uma face de fora */
.vw-top{padding:1.15em 1.15em 1em;border-bottom:1px solid var(--vw-linha)}
.vw-olho{display:block;margin:0 0 .5em;font-size:.66em;font-weight:700;line-height:1;
letter-spacing:.09em;text-transform:uppercase;color:var(--vw-marca)}
.vw-tit{font-size:1.14em;line-height:1.3}
.vw-sub{margin:.4em 0 0;font-size:.85em;color:var(--vw-fraca)}

/* controles */
.vw-ctls{padding:1.15em;display:grid;gap:.9em}
.vw-rot{display:block;margin:0 0 .4em;font-size:.8em;font-weight:600;color:var(--vw-corpo)}
.vw-sel{display:block;width:100%;min-height:48px;padding:0 2.4em 0 .85em;
border:1px solid var(--vw-linha);border-radius:8px;background:#fff;color:var(--vw-corpo);
font:inherit;font-size:.95em;-webkit-appearance:none;appearance:none;cursor:pointer;
background-image:linear-gradient(45deg,transparent 50%,var(--vw-fraca) 50%),
linear-gradient(135deg,var(--vw-fraca) 50%,transparent 50%);
background-position:calc(100% - 20px) 21px,calc(100% - 14px) 21px;
background-size:6px 6px,6px 6px;background-repeat:no-repeat}
.vw-sel:hover{border-color:var(--vw-marca)}
.vw-bts{display:flex;flex-wrap:wrap;gap:.5em}
.vw-bt{min-height:48px;padding:0 1em;border:1px solid var(--vw-linha);border-radius:8px;
background:#fff;color:var(--vw-corpo);font:inherit;font-size:.9em;font-weight:600;
cursor:pointer;transition:border-color .16s ease,background-color .16s ease}
.vw-bt:hover{border-color:var(--vw-marca)}
.vw-bt[aria-pressed="true"]{border-color:var(--vw-marca);background:var(--vw-marca-fraca);
color:var(--vw-marca)}
/* o anel de foco NUNCA sai — é o único caminho de quem navega por teclado */
.vw-sel:focus-visible,.vw-bt:focus-visible{outline:2px solid var(--vw-marca);outline-offset:2px}

/* resultado — todos os cenários na MESMA célula do grid: nada reflui */
.vw-out{display:grid;padding:0 1.15em 1.15em}
.vw-cen{grid-area:1/1;visibility:hidden;opacity:0;transition:opacity .16s ease}
.vw-cen[style*="visible"]{opacity:1}
.vw-caixa{padding:1em;border:1px solid var(--vw-linha);border-left:3px solid var(--vw-marca);
border-radius:8px;background:var(--vw-papel)}
.vw-chip{display:inline-block;margin:0 0 .6em;padding:.25em .6em;border-radius:999px;
font-size:.7em;font-weight:700;line-height:1.5;letter-spacing:.05em;text-transform:uppercase}
.vw-ctit{font-size:1em;line-height:1.35}
.vw-corpo{margin:.5em 0 0;font-size:.92em}

/* tons — chip tonal (Material), e o rótulo diz em TEXTO o que a cor diz em cor */
.vw-t-neutro .vw-caixa{border-left-color:var(--vw-marca)}
.vw-t-neutro .vw-chip{color:#0b5f75;background:var(--vw-marca-fraca)}
.vw-t-ok .vw-caixa{border-left-color:#12724a;background:#f0f8f4}
.vw-t-ok .vw-chip{color:#0f5c3c;background:#dff0e7}
.vw-t-atencao .vw-caixa{border-left-color:#8a5300;background:#fdf7ec}
.vw-t-atencao .vw-chip{color:#7a4a00;background:#f7e9cd}
.vw-t-risco .vw-caixa{border-left-color:#a32b2b;background:#fdf2f1}
.vw-t-risco .vw-chip{color:#8f2222;background:#f7dcda}

/* trilha de passos — numerada porque a ordem É informação aqui */
.vw-passos{margin:.9em 0 0;display:grid;gap:.5em;counter-reset:vwp}
.vw ul.vw-passos li.vw-passo{position:relative;padding-left:2em;font-size:.92em;margin:0}
/* ⚠️ SELETOR LONGO DE PROPÓSITO — o tema do site disputa este pseudo-elemento.
   Medido em 19/08/2026 na página no ar: `.content ul li::before{content:"•"}`,
   especificidade (0,1,2), vencia `.vw-passo::before` (0,1,1). O resultado era
   uma bolinha no lugar do número — a trilha "1, 2, 3" virava três marcadores
   iguais, e a ORDEM, que é a informação inteira de um passo a passo, sumia.
   `.vw ul.vw-passos li.vw-passo` dá (0,3,2) e ganha sem `!important`. */
.vw ul.vw-passos li.vw-passo::before{counter-increment:vwp;content:counter(vwp);
position:absolute;left:0;top:.15em;width:1.5em;height:1.5em;min-width:1.5em;
border-radius:50%;background:var(--vw-marca);color:#fff;padding:0;
font-size:.75em;font-weight:700;line-height:1.5em;text-align:center}

/* listas nomeadas — prós, contras, cuidados */
.vw-listas{margin:.9em 0 0;display:grid;gap:.8em}
.vw-lrot{margin:0 0 .35em;font-size:.68em;font-weight:700;letter-spacing:.08em;
text-transform:uppercase;color:var(--vw-fraca)}
.vw ul li.vw-litem{position:relative;padding-left:1em;font-size:.88em;margin:.25em 0 0}
/* mesma disputa do `.vw-passo`: sem esta especificidade o tema devolve "•" */
.vw ul li.vw-litem::before{content:"";position:absolute;left:0;top:.62em;
width:6px;min-width:6px;height:1.5px;padding:0;background:var(--vw-fraca)}

.vw-pe{padding:.8em 1.15em;border-top:1px solid var(--vw-linha);background:var(--vw-papel);
font-size:.78em;line-height:1.5;color:var(--vw-fraca)}

@media (min-width:640px){
.vw-ctls{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.vw-listas{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}
}
/* quem pediu menos movimento recebe menos movimento */
@media (prefers-reduced-motion:reduce){
.vw-cen,.vw-bt{transition:none}
}"""
