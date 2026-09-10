// Validate the actual API adapter against local and production base URLs, without network calls.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import ts from '../frontend/node_modules/typescript/lib/typescript.js';

const root = path.resolve(import.meta.dirname, '..');
const source = fs.readFileSync(path.join(root, 'frontend/src/api.ts'), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022}}).outputText;
const directory = path.join(root, '.cache');
fs.mkdirSync(directory, {recursive: true});
for (const [name, base, expected] of [['local', undefined, '/api'], ['render', 'https://aegis-test.example.invalid/', 'https://aegis-test.example.invalid']]) {
  const output = path.join(directory, 'intake-api-' + name + '.mjs');
  fs.writeFileSync(output, compiled.replaceAll('import.meta.env.VITE_API_BASE_URL', JSON.stringify(base) ?? 'undefined'));
  const api = await import(pathToFileURL(output).href);
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push({url, options}); return new Response(JSON.stringify({status:'OK', source:'CALL'}), {status:200, headers:{'Content-Type':'application/json'}}); };
  const controller = new AbortController();
  await api.parseIntake({source:'CALL', text:'Fire near ABC school', gps_verified:false}, controller.signal);
  assert.equal(calls[0].url, expected + '/intake/parse');
  assert.equal(JSON.parse(calls[0].options.body).text, 'Fire near ABC school');
  controller.abort();
  assert.equal(calls[0].options.signal.aborted, true);
  await api.submitReport({source:'SMS', raw_content:'Flood here', intake_unknown_fields:['injured']});
  assert.equal(calls[1].url, expected + '/reports');
  assert.equal(JSON.parse(calls[1].options.body).source, 'SMS');
  const audio = new Blob(['recorded-audio'], {type:'audio/webm;codecs=opus'});
  const voiceController = new AbortController();
  await api.transcribeVoice(audio, voiceController.signal);
  assert.equal(calls[2].url, expected + '/voice/transcribe');
  assert.equal(calls[2].options.body, audio);
  assert.equal(calls[2].options.headers['Content-Type'], 'audio/webm;codecs=opus');
  assert.equal(calls[2].options.headers.Authorization, undefined);
  voiceController.abort();
  assert.equal(calls[2].options.signal.aborted, true);
  globalThis.fetch = async () => new Response('{}', {status:503});
  await assert.rejects(api.parseIntake({source:'CALL', text:'Fire', gps_verified:false}, new AbortController().signal));
}
console.log('PASS: intake and voice API URLs, audio payloads, no frontend provider authentication, cancellation, shared submission and errors (22 assertions).');
