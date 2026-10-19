from __future__ import annotations

import json
from pathlib import Path
import subprocess
import textwrap


RAIZ = Path(__file__).resolve().parents[2]
SENSOR = RAIZ / "measurement" / "gtm" / "volc-sensor-v3.html"
WRAPPER = RAIZ / "measurement" / "gtm" / "webs-wrapper-v2.html"


def _node(programa: str) -> dict:
    resultado = subprocess.run(
        ["node", "--input-type=module", "-e", programa, str(SENSOR), str(WRAPPER)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(resultado.stdout)


def test_javascript_real_preserva_ids_so_nas_chaves_de_atribuicao() -> None:
    programa = textwrap.dedent(
        r"""
        import { readFileSync } from 'node:fs';
        const [sensorPath, wrapperPath] = process.argv.slice(1);
        const sensor = readFileSync(sensorPath, 'utf8');
        const wrapper = readFileSync(wrapperPath, 'utf8');
        function trecho(src, inicio, fim) {
          const i = src.indexOf(inicio), j = src.indexOf(fim, i);
          if (i < 0 || j < 0) throw new Error('trecho ausente: ' + inicio);
          return src.slice(i, j + fim.length);
        }
        const spii = trecho(sensor, 'var PII = [', '];');
        const clean = trecho(sensor, 'function clean(s, max) {', 'return s.slice(0, max || 60);\n  }');
        const sutm = trecho(sensor, 'function utmValue(key, v) {', '.slice(0, 40);\n  }');
        const utm = new Function(`${spii}\n${clean}\n${sutm}\nreturn utmValue;`)();
        const wpii = trecho(wrapper, 'var PII = [', '];');
        const wsafe = trecho(wrapper, 'function safeValue(key, v) {', '.slice(0, 40);\n  }');
        const safe = new Function(`${wpii}\n${wsafe}\nreturn safeValue;`)();
        console.log(JSON.stringify({
          sensor_campaign: utm('utm_campaign', '20000000011'),
          sensor_content: utm('utm_content', '165432109876'),
          sensor_source: utm('utm_source', '20000000011'),
          sensor_cpf: utm('utm_campaign', '123.456.789-01'),
          wrapper_campaign: safe('utm_campaign', '20000000011'),
          wrapper_term: safe('utm_term', '20000000011'),
          wrapper_email: safe('utm_campaign', 'pessoa@example.com'),
        }));
        """
    )
    assert _node(programa) == {
        "sensor_campaign": "20000000011",
        "sensor_content": "165432109876",
        "sensor_source": "",
        "sensor_cpf": "",
        "wrapper_campaign": "20000000011",
        "wrapper_term": "",
        "wrapper_email": "",
    }


def test_wrapper_nao_herda_campanha_antiga_quando_nova_utm_esta_presente() -> None:
    programa = textwrap.dedent(
        r"""
        import { readFileSync } from 'node:fs';
        const wrapper = readFileSync(process.argv[2], 'utf8');
        function trecho(src, inicio, fim) {
          const i = src.indexOf(inicio), j = src.indexOf(fim, i);
          if (i < 0 || j < 0) throw new Error('trecho ausente: ' + inicio);
          return src.slice(i, j + fim.length);
        }
        const codigo = trecho(
          wrapper,
          'var BLOCKED_KEY =',
          'targeting();\n})(window);'
        ).replace('targeting();\n})(window);', 'targeting();');
        function rodar(search) {
          let salvo = JSON.stringify({targeting:{utm_campaign:'campanha_antiga'}});
          const targeting = {};
          const sessionStorage = {
            getItem: () => salvo,
            setItem: (_k, v) => { salvo = String(v); },
            removeItem: () => { salvo = null; },
          };
          const pubads = {
            setTargeting:(k,v)=>{targeting[k]=v},
            clearTargeting:(k)=>{delete targeting[k]},
            addEventListener:()=>{},
          };
          const w = {
            location:{search, pathname:'/r/teste/'}, dataLayer:[],
            googletag:{cmd:{push:(fn)=>fn()}, pubads:()=>pubads},
          };
          const cfg = {targeting:['utm_source','utm_medium','utm_campaign'], page:'teste'};
          new Function('w','cfg','sessionStorage','URLSearchParams', codigo)(w,cfg,sessionStorage,URLSearchParams);
          return {targeting, salvo: JSON.parse(salvo)};
        }
        console.log(JSON.stringify({
          numerico: rodar('?utm_source=google&utm_medium=cpc&utm_campaign=20000000011'),
          invalido: rodar('?utm_source=google&utm_medium=cpc&utm_campaign=pessoa@example.com'),
        }));
        """
    )
    resultado = _node(programa)
    assert resultado["numerico"]["targeting"]["utm_campaign"] == "20000000011"
    assert resultado["numerico"]["salvo"]["targeting"]["utm_campaign"] == "20000000011"
    assert "utm_campaign" not in resultado["invalido"]["targeting"]
    assert "utm_campaign" not in resultado["invalido"]["salvo"]["targeting"]
