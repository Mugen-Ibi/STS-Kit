const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {decodePcm16} = require('../static/pcm.js');

test('PCM16 decoder preserves channel samples and rejects incomplete WAV', () => {
  const wav = new ArrayBuffer(48), v = new DataView(wav);
  const tag = (offset, text) => [...text].forEach((c, i) => v.setUint8(offset + i, c.charCodeAt(0)));
  tag(0, 'RIFF'); v.setUint32(4, 40, true); tag(8, 'WAVE'); tag(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, 44100, true); v.setUint16(34, 16, true); tag(36, 'data');
  v.setUint32(40, 4, true); v.setInt16(44, -32768, true); v.setInt16(46, 16384, true);
  const context = {createBuffer(channels, frames, rate) {
    assert.equal(channels, 1); assert.equal(rate, 44100);
    const samples = new Float32Array(frames);
    return {samples, getChannelData() {return samples;}};
  }};
  assert.deepEqual([...decodePcm16(context, wav).samples], [-1, .5]);
  assert.equal(decodePcm16(context, wav.slice(0, 45)), null);
});

test('recorder batches frames and flushes the last partial frame in order', () => {
  let Recorder;
  const events = [];
  vm.runInNewContext(fs.readFileSync('static/recorder.js', 'utf8'), {
    AudioWorkletProcessor: class {constructor() {this.port = {postMessage: (data) => events.push(data)};}},
    registerProcessor: (_, cls) => Recorder = cls,
    Float32Array,
  });
  const recorder = new Recorder();
  for (let i = 0; i < 9; i++) recorder.process([[new Float32Array(128).fill(i)]], []);
  assert.equal(events.length, 1);
  recorder.port.onmessage({data: 'flush'});
  assert.equal(events.length, 3);
  assert.equal(new Float32Array(events[0]).length, 1024);
  assert.deepEqual([...new Float32Array(events[1])], Array(128).fill(8));
  assert.equal(events[2], 'flushed');
});

test('cancelled WebSocket packets cannot restart audio or complete a newer turn', async () => {
  const elements = new Map(), sockets = [], sent = [];
  const element = () => ({value: '', textContent: '', disabled: false, children: [], style: {},
    classList: {add() {}, remove() {}}, addEventListener() {},
    querySelector: () => null, querySelectorAll: () => [], scrollIntoView() {},
    append(...nodes) {this.children.push(...nodes);}, replaceChildren(...nodes) {this.children = nodes;}});
  const get = (id) => {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);};
  for (const [id, value] of Object.entries({engine: 'sbv2', speaker: 'JVNV F1', style: 'Neutral', 'style-weight': '1', speed: '1'})) get(id).value = value;
  const context = vm.createContext({
    document: {getElementById: get, createElement: element},
    window: {addEventListener() {}}, location: {host: 'home.example-tailnet.ts.net', protocol: 'https:'},
    performance: {now: () => 1}, setTimeout, clearTimeout,
    WebSocket: class {static OPEN = 1; readyState = 1; constructor(url) {this.url = url; sockets.push(this);} send(data) {sent.push(JSON.parse(data));}},
    AudioContext: class {constructor() {throw new Error('Stale audio must never be played');}},
  });
  vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), context);
  vm.runInContext("healthy = true; scenarioReady = true; send({text: 'hello'}, 'hello');", context);
  const first = sent.at(-1).request_id, socket = sockets[0];
  assert.equal(socket.url, 'wss://home.example-tailnet.ts.net/ws');
  get('cancel').onclick();
  const deliver = (msg) => socket.onmessage({data: JSON.stringify(msg)});
  deliver({type: 'audio', request_id: first, data: 'stale'});
  deliver({type: 'done', request_id: first});
  assert.equal(get('send').disabled, true, 'wait for cancel acknowledgement');
  deliver({type: 'cancelled'});
  assert.equal(get('send').disabled, false);
  vm.runInContext("send({text: 'again'}, 'again');", context);
  const second = sent.at(-1).request_id;
  assert.notEqual(first, second);
  deliver({type: 'token', request_id: first, text: 'stale text'});
  deliver({type: 'token', request_id: second, text: 'new answer'});
  const bubbles = get('conversation').children;
  assert.equal(bubbles.at(-1).children[1].textContent, 'new answer');
  assert.equal(get('send').disabled, true);
});


test('heartbeat loss stops playback and recording before the close handshake completes', () => {
  const source = fs.readFileSync('static/app.js', 'utf8');
  const functions = source.slice(source.indexOf('function connectionLost()'), source.indexOf('async function checkHealth()'));
  let now = 0, beat, stopped = 0, discarded = 0, closed = 0;
  const context = vm.createContext({
    performance: {now: () => now}, location: {protocol: 'https:', host: 'home.example-tailnet.ts.net'},
    setInterval: (fn) => {beat = fn; return 1;}, clearInterval() {},
    initializeScenario() {}, checkHealth() {}, controls() {},
    stopPlayback: () => stopped++, finishRecording: (submit) => {assert.equal(submit, false); discarded++;},
    WebSocket: class {static OPEN = 1; readyState = 1; send() {} close() {closed++;}},
  });
  vm.runInContext('let ws, heartbeatTimer, lastPong, activeRequest = 1, healthy = true, scenarioReady = true, scenarioPending = true, busy = true;' + functions + 'connect(); ws.onopen();', context);
  now = 46000; beat();
  assert.equal(closed, 1); assert.equal(stopped, 1); assert.equal(discarded, 1);
  assert.equal(vm.runInContext('healthy || busy || scenarioReady || scenarioPending', context), false);
  assert.equal(vm.runInContext('activeRequest', context), null);
});
