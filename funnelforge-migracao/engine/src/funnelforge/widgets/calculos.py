"""Calculadoras locais: operações fixas, casos conferidos por Decimal, sem LLM.

Entradas não negativas com até dois decimais. No browser, centésimos inteiros
BigInt reproduzem ROUND_HALF_UP do Python. Não há consulta, armazenamento,
elegibilidade automática, constantes de benefício ou código vindo do modelo.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP, localcontext
from html import escape

from funnelforge.domain.models import CalculoDoAtivo
from funnelforge.widgets.estilo import CSS


# Formato brasileiro: ponto de milhar só em grupos de três e vírgula decimal
# ("1.518,00"). O ponto decimal ("1518.5") vale quando não pode ser milhar.
# O JS do navegador (`cents`, abaixo) usa as mesmas duas expressões.
_COM_VIRGULA = re.compile(r"([0-9]{1,3}(?:\.[0-9]{3})+|[0-9]{1,13})(?:,([0-9]{1,2}))?")
_COM_PONTO = re.compile(r"([0-9]{1,13})\.([0-9]{1,2})")


def numero(valor: str) -> Decimal:
    texto = str(valor).strip()
    m = _COM_VIRGULA.fullmatch(texto) or _COM_PONTO.fullmatch(texto)
    inteiro = m.group(1).replace(".", "") if m else ""
    if not m or len(inteiro) > 13:
        raise ValueError("Use número não negativo com até dois decimais (ex.: 1.518,00)")
    n = Decimal(f"{inteiro}.{m.group(2) or '0'}")
    if n > Decimal("1000000000000"):
        raise ValueError("Entrada acima do limite da calculadora")
    return n


def calcular(operacao: str, a: str, b: str) -> Decimal:
    x, y = numero(a), numero(b)
    with localcontext() as ctx:
        ctx.prec = 50
        if operacao == "divisao":
            if not y:
                raise ValueError("O divisor deve ser maior que zero")
            resultado = x / y
        elif operacao == "multiplicacao":
            resultado = x * y
        elif operacao == "percentual":
            resultado = x * y / Decimal(100)
        else:
            raise ValueError("Operação não implementada")
        return resultado.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def inteiro_positivo(valor: str) -> None:
    n = numero(valor)
    if n != n.to_integral_value() or n <= 0:
        raise ValueError("Use um número inteiro maior que zero")


def validar(calculo: CalculoDoAtivo) -> list[dict]:
    recibos = []
    for caso in calculo.casos:
        for i in calculo.inteiros:
            inteiro_positivo(caso.entradas[i])
        resultado = calcular(calculo.operacao, *caso.entradas)
        esperado = numero(caso.resultado)
        if resultado != esperado:
            raise ValueError("Exemplo de cálculo não corresponde ao resultado calculado por código")
        recibos.append({"entradas": caso.entradas, "resultado": str(resultado), "ok": True})
    return recibos


_JS = r'''(function(){
var r=document.getElementById("__ID__");if(!r){return;}
var inputs=r.querySelectorAll("input");var out=r.querySelector("[data-vc-out]");
var semjs=r.querySelector("[data-vc-semjs]");if(semjs){semjs.hidden=true;}
function cents(text){
var s=text.trim();
var m=/^(\d{1,3}(?:\.\d{3})+|\d{1,13})(?:,(\d{1,2}))?$/.exec(s)||/^(\d{1,13})\.(\d{1,2})$/.exec(s);
var inteiro=m?m[1].replace(/\./g,""):"";
if(!m||inteiro.length>13){throw Error("Entrada inválida");}
var v=BigInt(inteiro)*100n+BigInt(((m[2]||"")+"00").slice(0,2));
if(v>100000000000000n){throw Error("Entrada acima do limite");}return v;
}
function update(){try{
var a=cents(inputs[0].value);var b=cents(inputs[1].value);var n;var d;
var ints=(r.getAttribute("data-vc-inteiros")||"").split(",").filter(Boolean);
for(var k=0;k<ints.length;k++){var v=[a,b][+ints[k]];if(v%100n!==0n||v<=0n){throw Error("Use um número inteiro maior que zero em: "+r.querySelectorAll("label")[+ints[k]].textContent);}}
var op=r.getAttribute("data-vc-operation");
if(op==="divisao"){if(b===0n){throw Error("O divisor deve ser maior que zero");}n=a*100n;d=b;}
else if(op==="percentual"){n=a*b;d=10000n;}
else if(op==="multiplicacao"){n=a*b;d=100n;}
else{throw Error("Operação não disponível");}
var q=n/d;if((n%d)*2n>=d){q=q+1n;}
out.textContent=(q/100n).toString()+","+(q%100n).toString().padStart(2,"0");
out.setAttribute("data-vc-status","ok");
}catch(e){out.textContent=e.message;out.setAttribute("data-vc-status","invalid");}}
for(var i=0;i<inputs.length;i++){inputs[i].addEventListener("input",update);}
})();'''


def renderizar_calculo(calculo: CalculoDoAtivo, *, titulo: str, identidade: str) -> str:
    validar(calculo)
    wid = "vc-" + hashlib.sha256((identidade + json.dumps(
        calculo.model_dump(), sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:12]
    controles = "".join(
        f'<div><label class="vw-rot" for="{wid}-{i}">{escape(rotulo)}</label>'
        f'<input class="vw-sel" type="text" id="{wid}-{i}" value="" '
        f'inputmode="{"numeric" if i in calculo.inteiros else "decimal"}" '
        'aria-describedby="' + wid + '-help"></div>'
        for i, rotulo in enumerate(calculo.rotulos))
    html = (f'<section class="vw" id="{wid}" data-vc-operation="{calculo.operacao}" '
            f'data-vc-inteiros="{",".join(str(i) for i in calculo.inteiros)}">'
            f'<div class="vw-top"><h3 class="vw-tit">{escape(titulo)}</h3>'
            f'<div class="vw-sub" id="{wid}-help">Pode usar ponto de milhar e vírgula: '
            '1.518,00. '
            'A conta não consulta cadastro nem confirma direito.</div></div>'
            f'<div class="vw-ctls">{controles}</div><div class="vw-caixa">'
            f'<strong>{escape(calculo.rotulo_resultado)}</strong>'
            '<div class="vw-out" style="min-height:3em;grid-area:1/1" aria-live="polite" '
            'data-vc-out="1" data-vc-status="empty">Preencha os dois valores.</div>'
            # Fallback: só fica visível se o script não rodar.
            '<div class="vw-sub" data-vc-semjs="1">Sem a calculadora, faça a conta '
            'descrita no texto.</div>'
            '</div></section>')
    return '<!-- wp:html -->\n<style>' + CSS + '</style>\n' + html + '\n<script>' + (
        _JS.replace("__ID__", wid)) + '</script>\n<!-- /wp:html -->'
