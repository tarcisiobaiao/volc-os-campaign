// Executa o código de um Code node do n8n fora do n8n, com $() simulado. Uso:
//   node executar_code_node.mjs <arquivo.js> <fixture.json>
// fixture: {nodes: {"Nome": [ {json}, ... ]}, workflow_id, execution_id}. Nó ausente lança, como no n8n.
import { readFileSync } from 'node:fs';
const [codeFile, fixtureFile] = process.argv.slice(2);
const code = readFileSync(codeFile, 'utf8');
const fx = JSON.parse(readFileSync(fixtureFile, 'utf8'));
const $ = (name) => {
  if (!(name in fx.nodes)) throw new Error(`Referenced node is unexecuted: ${name}`);
  const items = fx.nodes[name];
  return { all: () => items, first: () => items[0], item: items[0] };
};
const entrada = fx.input || [{ json: {} }];
const $input = { first: () => entrada[0], all: () => entrada, item: entrada[0] };
const fn = new Function('$', '$input', '$json', '$workflow', '$execution', `return (async () => {\n${code}\n})();`);
const out = await fn($, $input, entrada[0].json, { id: fx.workflow_id || 'wf-teste' }, { id: fx.execution_id || 'exec-teste', mode: 'trigger' });
process.stdout.write(JSON.stringify(out));
