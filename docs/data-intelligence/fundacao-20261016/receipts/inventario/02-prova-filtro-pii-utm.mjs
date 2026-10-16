// Recibo A-inv 02 — prova hermética: o filtro de PII do Sensor v3 e do WEBS Wrapper v2
// descarta utm_campaign numérico com >= 10 dígitos (formato do campaign.id do Google Ads).
// Uso (somente leitura, sem rede):
//   git -C <repo> show 918e9571:measurement/gtm/volc-sensor-v3.html > /tmp/s.html
//   git -C <repo> show 918e9571:measurement/gtm/webs-wrapper-v2.html > /tmp/w.html
//   node 02-prova-filtro-pii-utm.mjs /tmp/s.html /tmp/w.html
// O script extrai as funções do próprio arquivo versionado (não reescreve a lógica à mão).
import fs from 'node:fs';
import vm from 'node:vm';
const [sensorPath, wrapperPath] = process.argv.slice(2);
const sensor = fs.readFileSync(sensorPath, 'utf8').split('\n');
const wrapper = fs.readFileSync(wrapperPath, 'utf8').split('\n');
// Sensor v3: linhas 69-79 (PII + clean) e 107-112 (utmValue) — 1-based.
const sensorSrc = sensor.slice(68, 79).join('\n') + '\n' + sensor.slice(106, 112).join('\n');
// Wrapper v2: linhas 34-39 (PII) e 74-80 (safeValue).
const wrapperSrc = wrapper.slice(33, 39).join('\n') + '\n' + wrapper.slice(73, 80).join('\n');
const s = {}; vm.createContext(s); vm.runInContext(sensorSrc + '\nthis.utmValue = utmValue;', s);
const w = {}; vm.createContext(w); vm.runInContext(wrapperSrc + '\nthis.safeValue = safeValue;', w);
const casos = ['24278665189', '1234567890', '123456789', 'senac-caruaru', 'google', 'cpc', '{campaignid}'];
for (const v of casos) {
  console.log(JSON.stringify(v).padEnd(18), 'sensor.utmValue ->', JSON.stringify(s.utmValue(v)).padEnd(18),
              'wrapper.safeValue ->', JSON.stringify(w.safeValue(v)));
}
