// Gera vetores-ouro de normalização de UTM executando o código JavaScript REAL
// do VOLC Sensor v3 e do WEBS Wrapper v2 (as funções são extraídas do HTML, não
// reescritas). Uso, sem rede:
//
//   git show wip/historico-measurement-20261015:measurement/gtm/volc-sensor-v3.html > /tmp/s.html
//   git show wip/historico-measurement-20261015:measurement/gtm/webs-wrapper-v2.html > /tmp/w.html
//   node gerar_vetores_sensor.mjs /tmp/s.html /tmp/w.html > vetores_utm_sensor_v3.json
//
// Os vetores alimentam tests/data-intelligence/fundacao/test_identidade_normalizacao.py,
// que exige igualdade byte a byte com a reimplementação Python.
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const [sensorPath, wrapperPath] = process.argv.slice(2);
const sensorSrc = readFileSync(sensorPath, 'utf8');
const wrapperSrc = readFileSync(wrapperPath, 'utf8');
const sha = (s) => createHash('sha256').update(s, 'utf8').digest('hex');

function extrair(src, inicio, fim) {
  const i = src.indexOf(inicio);
  if (i < 0) throw new Error('trecho não encontrado: ' + inicio);
  const j = src.indexOf(fim, i);
  if (j < 0) throw new Error('fim não encontrado: ' + fim);
  return src.slice(i, j + fim.length);
}

// Sensor: var PII = [...]; function clean(...){...}; function utmValue(...){...}
const sPII = extrair(sensorSrc, 'var PII = [', '];');
const sClean = extrair(sensorSrc, 'function clean(s, max) {', "return s.slice(0, max || 60);\n  }");
const sUtm = extrair(sensorSrc, 'function utmValue(v) {', ".slice(0, 40);\n  }");
const utmValue = new Function(`${sPII}\n${sClean}\n${sUtm}\nreturn utmValue;`)();
const sensorClean = new Function(`${sPII}\n${sClean}\nreturn clean;`)();

// Wrapper: var PII = [...]; function safeValue(...){...}
const wPII = extrair(wrapperSrc, 'var PII = [', '];');
const wSafe = extrair(wrapperSrc, 'function safeValue(v) {', ".slice(0, 40);\n  }");
const safeValue = new Function(`${wPII}\n${wSafe}\nreturn safeValue;`)();

// Sensor campaign(): mesmo corpo, com location/sessionStorage simulados.
const sCampaign = extrair(sensorSrc, 'function campaign() {', 'return o;\n  }');
function campaignCom(href, armazenado) {
  const store = new Map();
  if (armazenado !== null && armazenado !== undefined) store.set('volc_utm', armazenado);
  const sessionStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
  };
  const location = { href };
  const fn = new Function('location', 'sessionStorage',
    `${sPII}\n${sClean}\n${sUtm}\n${sCampaign}\nreturn campaign();`);
  const o = fn(location, sessionStorage);
  return { utm: o, armazenado_depois: store.has('volc_utm') ? store.get('volc_utm') : null };
}

const longo = (n, c = 'a') => c.repeat(n);
const entradas = [
  null, '', '   ', 'Google', '  CPC  ', 'Cursos Senac', 'Educação Técnica', 'ÁÉÍÓÚ ãõ ç',
  'black friday 2026', 'cursos-senac-2026', 'senac_sp', 'Promoção "Relâmpago"!', "o'reilly",
  'a=b', 'x+y', 'tag#1', 'a*b~c;d^e(f)g<h>i[j]k,l', 'multi   space\t\ttab', 'linha\nnova',
  '24278665189', '2427866518', '242786651', '123456789', '12345678901234567890',
  'c24278665189', 'gads_24278_665189', '2427-866-5189', '(11) 98765-4321', '+55 11 987654321',
  '123.456.789-01', '12.345.678/0001-90', '12345678901', 'fulano@example.com', 'contato@x.co',
  'curso 2025 - 2026', '2026-10-15', 'campanha 2026/10', '{campaignid}', '{{campaign.id}}',
  longo(40), longo(41), longo(60, 'b'), 'Ç'.repeat(45), longo(199), longo(200), longo(201),
  'x'.repeat(195) + ' y y', 'emoji 🎓 curso', '🎓'.repeat(30), 'ﬁ ligadura', 'İstanbul',
  'nbsp aqui', 'zwnbsp﻿aqui', 'sep linha', 'ctrl\u001cfs', 'nel\u0085x',
  'ΣΊΣΥΦΟΣ', 'Ⅻ roman', '١٢٣٤٥٦٧٨٩٠١ arabic digits', 'ＦＵＬＬ ｗｉｄｔｈ ２０２６', 'K kelvin',
  'ſ long s', 'naïve café', '  lead and trail  ', 'UPPER_lower-Mixed.123',
];

const vetores = entradas.map((v) => ({
  entrada: v,
  sensor_v3: utmValue(v),
  wrapper_v2: safeValue(v),
  sensor_clean_200: v === null ? null : sensorClean(String(v).trim().toLowerCase(), 200),
}));

// Vetores pseudoaleatórios determinísticos (mulberry32, semente fixa) sobre um alfabeto hostil.
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const ALFABETO = Array.from('0123456789012345678901234567890123456789abcXYZ   .-()+@_/,;!#*~^<>[]"\'=ÇçÁãéÍõüñ\t\n\u00a0\u2028\ufeff\u0085\u001c🎓ﬁİΣ١');
const rnd = mulberry32(20261016);
const aleatorios = [];
for (let i = 0; i < 3000; i++) {
  const n = Math.floor(rnd() * (i % 50 === 0 ? 260 : 28));
  let s = '';
  for (let k = 0; k < n; k++) s += ALFABETO[Math.floor(rnd() * ALFABETO.length)];
  aleatorios.push({ entrada: s, sensor_v3: utmValue(s), wrapper_v2: safeValue(s) });
}

const cenarios_campaign = [
  ['https://creditoup.com.br/r/guia-cursos-senac/?utm_source=google&utm_medium=cpc&utm_campaign=24278665189&utm_term=cursos%20senac&utm_content=165432109876&utm_device=m&gclid=TESTE_SINTETICO', null],
  ['https://creditoup.com.br/r/guia-cursos-senac/?utm_source=google&utm_medium=cpc&utm_campaign=Cursos+Senac&utm_term=bolsa+de+estudo&gbraid=X', null],
  ['https://creditoup.com.br/rec/por-onde-comecar-senac-pr/', JSON.stringify({ source: 'google', medium: 'cpc', term: 'cursos_senac', paid: 1 })],
  ['https://creditoup.com.br/rec/por-onde-comecar-senac-pr/', null],
  ['https://creditoup.com.br/r/x/?gclid=', null],
  ['https://creditoup.com.br/r/x/?utm_campaign=24278665189', JSON.stringify({ source: 'google', medium: 'cpc', term: 'antigo', paid: 1 })],
  ['https://creditoup.com.br/r/x/?utm_campaign=24278665189&gclid=Y', JSON.stringify({ source: 'google', medium: 'cpc', term: 'antigo', paid: 1 })],
  ['https://creditoup.com.br/r/x/?utm_source=Facebook&utm_medium=paid_social&utm_campaign=Meta+Cursos', null],
  ['https://creditoup.com.br/r/x/?utm_campaign=a&utm_campaign=b', null],
  ['https://creditoup.com.br/r/x/?utm_campaign=Promo%C3%A7%C3%A3o%20Rel%C3%A2mpago', null],
  ['https://creditoup.com.br/r/x/?utm_campaign=%E0%A4%A', null],
].map(([href, armazenado]) => ({ href, armazenado, ...campaignCom(href, armazenado) }));

process.stdout.write(JSON.stringify({
  esquema: 'volc-dil/vetores-utm-sensor-v3@1',
  gerado_por: 'docs/data-intelligence/fundacao-20261016/receipts/identidade/gerar_vetores_sensor.mjs',
  node: process.version,
  fontes: {
    sensor: { ref: 'wip/historico-measurement-20261015 (918e9571)', caminho: 'measurement/gtm/volc-sensor-v3.html', sha256: sha(sensorSrc) },
    wrapper: { ref: 'wip/historico-measurement-20261015 (918e9571)', caminho: 'measurement/gtm/webs-wrapper-v2.html', sha256: sha(wrapperSrc) },
  },
  vetores,
  vetores_aleatorios: { semente: 20261016, n: aleatorios.length, itens: aleatorios },
  cenarios_campaign,
}, null, 1) + '\n');
