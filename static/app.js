const $ = (id) => document.getElementById(id);
let engines = [], previewUrls = [], previewing = false, previewMetric = null;
let scenario = null, scenarioReady = false, scenarioPending = false;
let requestSequence = 0, activeRequest = null, finishingRecording = false, startingRecording = false;
let recordingGeneration = 0, flushRecording = null, sentAt = 0, playbackLatency = null;
const scenarioStorageKey = 'sts-world-v1';
let ws,
  ctx,
  mic,
  node,
  source,
  chunks = [],
  recording = false,
  workletLoaded = false,
  timer,
  meterFrame;
let busy = false,
  healthy = false,
  currentUser,
  currentAnswer,
  scheduled = [],
  playAt = 0,
  audioChain = Promise.resolve(),
  epoch = 0;
function status(text) {
  $("status").textContent = text;
}
function showScenario() {
  $("roleplay-enabled").checked = scenario?.enabled ?? false;
  $("scenario-state").textContent = scenario
    ? `${scenario.enabled ? '通話中の世界' : '通常会話（世界設定は休止中）'}: ${scenario.name} · ${Array.from(scenario.markdown).length}文字`
    : '世界設定はまだ読み込まれていません。';
  // Imported Markdown is displayed as text, never as executable HTML.
  $("scenario-content").textContent = scenario?.markdown || '';
}
function validateScenario(value) {
  if (!value || typeof value.enabled !== 'boolean' || typeof value.name !== 'string' ||
      !value.name.toLowerCase().endsWith('.md') || Array.from(value.name).length > 120 ||
      typeof value.markdown !== 'string') throw new Error('有効な.mdファイルを選んでください。');
  const markdown = value.markdown.replace(/^\uFEFF/, '').trim();
  if (!markdown || Array.from(markdown).length > 4000 || new TextEncoder().encode(markdown).length > 16000)
    throw new Error('空でない、4000文字・16KB以下のMarkdownを選んでください。');
  if (/[\x00-\x08\x0B\x0C\x0E-\x1F]/.test(markdown)) throw new Error('読めない制御文字が含まれています。');
  return {...value, markdown};
}
async function standardScenario() {
  const response = await fetch('/api/scenario/default');
  if (!response.ok) throw new Error('標準の歴史を取得できませんでした。');
  return validateScenario(await response.json());
}
function applyScenario(value) {
  const validated = validateScenario(value);
  if (ws.readyState !== WebSocket.OPEN) throw new Error('接続を待ってからもう一度お試しください。');
  stopPlayback();
  scenarioPending = true;
  controls();
  $("scenario-state").textContent = '世界設定を適用しています…';
  ws.send(JSON.stringify({type: 'scenario', scenario: validated}));
}
function scenarioError(error) {
  scenarioPending = false;
  showScenario();
  $("scenario-state").textContent += ' ／ 読み込めませんでした: ' + error.message;
  controls();
}
async function initializeScenario() {
  scenarioReady = false;
  scenarioPending = true;
  controls();
  try {
    let saved = scenario;
    if (!saved) {
      try {
        const raw = localStorage.getItem(scenarioStorageKey);
        if (raw) saved = validateScenario(JSON.parse(raw));
      } catch { /* Invalid or unavailable browser storage falls back to the bundled world. */ }
    }
    applyScenario(saved || await standardScenario());
  } catch (error) { scenarioError(error); }
}
function controls() {
  const waiting = !scenarioReady || scenarioPending || finishingRecording || startingRecording;
  $("record").disabled = !healthy || busy || waiting;
  $("send").disabled = !healthy || busy || recording || waiting;
  $("upload").disabled = !healthy || busy || recording || waiting;
  $("preview").disabled = !healthy || busy || recording || waiting;
  $("engine").disabled = busy || recording;
  $("speaker").disabled = busy || recording;
  for (const id of ['scenario-file', 'scenario-default', 'roleplay-enabled']) {
    $(id).disabled = busy || recording || finishingRecording || startingRecording || scenarioPending || ws?.readyState !== WebSocket.OPEN;
  }
}
async function audioContext() {
  if (!ctx) ctx = new AudioContext({ sampleRate: 48000, latencyHint: 'interactive' });
  await ctx.resume();
  return ctx;
}
function bubble(who, text) {
  $("conversation").querySelector(".empty")?.remove();
  const el = document.createElement("div");
  el.className = "message " + who;
  const label = document.createElement("small");
  label.textContent = who === "user" ? "YOU" : previewing ? "試聴" : scenario?.enabled ? "2030 · 電話の向こう" : "GEMMA";
  const body = document.createElement("span");
  body.textContent = text;
  el.append(label, body);
  $("conversation").append(el);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return body;
}
function stopPlayback(except = null) {
  epoch++;
  for (const audio of $("previews").querySelectorAll('audio')) {
    if (audio !== except) { audio.pause(); audio.currentTime = 0; }
  }
  for (const node of scheduled) {
    try {
      node.stop();
    } catch {}
  }
  scheduled = [];
  playAt = 0;
  audioChain = Promise.resolve();
}
async function enqueueAudio(encoded, version) {
  if (version !== epoch) return;
  const bytes = Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0));
  const context = await audioContext();
  const buffer = STSAudio.decodePcm16(context, bytes.buffer) || await context.decodeAudioData(bytes.buffer);
  if (version !== epoch) return;
  const player = context.createBufferSource();
  player.buffer = buffer;
  player.connect(context.destination);
  const when = Math.max(context.currentTime + 0.015, playAt);
  if (playbackLatency === null) {
    playbackLatency = performance.now() - sentAt + (when - context.currentTime) * 1000;
    $("playback-metric")?.remove();
    const metric = document.createElement('div');
    metric.id = 'playback-metric';
    metric.textContent = `送信から再生予約まで ${Math.round(playbackLatency)}ms`;
    $("metrics").after(metric);
  }
  player.start(when);
  playAt = when + buffer.duration;
  scheduled.push(player);
  player.onended = () => {
    scheduled = scheduled.filter((x) => x !== player);
  };
}
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { initializeScenario(); checkHealth(); };
  ws.onclose = () => {
    activeRequest = null;
    stopPlayback();
    finishRecording(false);
    healthy = false;
    scenarioReady = false;
    scenarioPending = false;
    busy = false;
    controls();
    status("接続が切れました。再接続しています…");
    setTimeout(connect, 2000);
  };
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    // A cancelled turn can still have packets in flight. Never play or display them.
    if ('request_id' in msg && msg.request_id !== activeRequest) return;
    if (msg.type === 'scenario_applied') {
      scenario = msg.scenario;
      scenarioReady = true;
      scenarioPending = false;
      if (msg.reset) {
        stopPlayback();
        $("conversation").replaceChildren();
        $("metrics").textContent = '';
        currentUser = currentAnswer = null;
      }
      showScenario();
      try { localStorage.setItem(scenarioStorageKey, JSON.stringify(scenario)); }
      catch { $("scenario-state").textContent += '（ブラウザへの保存不可。この接続中のみ有効）'; }
      controls();
      status(scenario.enabled ? '2030年の相手につながりました。話しかけてください。' : '通常の会話に切り替えました。');
    }
    if (msg.type === "status") status(msg.text);
    if (msg.type === "transcript" && currentUser) currentUser.textContent = "🎙 " + msg.text;
    if (msg.type === "token" && currentAnswer) currentAnswer.textContent += msg.text;
    if (msg.type === "audio") {
      if (msg.preview) addPreview(msg);
      const version = epoch;
      audioChain = audioChain
        .then(() => enqueueAudio(msg.data, version))
        .catch((e) => status("再生エラー: " + e.message));
      status("返答を再生しています…");
    }
    if (msg.type === "done") {
      busy = false;
      controls();
      const m = msg.metrics;
      $("metrics").textContent =
        `最初の音声 ${(m.first_audio_s ?? 0).toFixed(2)}s / 生成完了 ${m.total_s.toFixed(2)}s / TTS ${m.tts_s.toFixed(2)}s`;
      if (previewing && previewMetric) previewMetric.textContent = `生成 ${m.tts_s.toFixed(2)}秒 / 音声 ${m.audio_s.toFixed(2)}秒`;
      status(previewing ? "試聴音声ができました。別のモデルを選んで比較できます。" : "返答の生成が完了しました。続けて話しかけられます。");
    }
    if (msg.type === "cancelled") {
      busy = false;
      controls();
      status("停止しました。");
    }
    if (msg.type === "error") {
      if (scenarioPending) {
        scenarioPending = false;
        showScenario();
        $("scenario-state").textContent += ' ／ 読み込めませんでした: ' + msg.text;
      }
      busy = false;
      controls();
      status(msg.text);
    }
  };
}
async function checkHealth() {
  try {
    const h = await (await fetch("/api/health")).json();
    healthy = h.ready && ws.readyState === WebSocket.OPEN;
    if (healthy) {
      engines = h.engines;
      const selected = $("engine").value;
      $("engine").replaceChildren(...engines.map((e) => {
        const option = new Option(e.name + (e.available ? '' : '（未導入）'), e.id);
        option.disabled = !e.available;
        return option;
      }));
      $("engine").value = selected;
      updateEngine();
      if (!busy && !recording) status("準備できました。話しかけてください。");
    } else status(h.error || "モデルを準備しています…");
    controls();
  } catch {
    healthy = false;
    controls();
  }
  if (!healthy) setTimeout(checkHealth, 3000);
}
function send(payload, label) {
  if (busy || !healthy || !scenarioReady || scenarioPending) return;
  stopPlayback();
  previewing = payload.type === 'preview';
  previewMetric = null;
  currentUser = previewing ? null : bubble("user", label);
  currentAnswer = previewing ? null : bubble("assistant", "");
  busy = true;
  activeRequest = ++requestSequence;
  sentAt = performance.now();
  playbackLatency = null;
  controls();
  ws.send(
    JSON.stringify({
      type: "message",
      ...payload,
      request_id: activeRequest,
      engine: $("engine").value,
      speaker: $("speaker").value,
      style: $("style").value,
      style_weight: $("engine").value === 'sbv2' ? Number($("style-weight").value) : 1,
      speed: $("engine").value === 'sbv2' ? Number($("speed").value) : 1,
    }),
  );
}
function updateEngine() {
  const engine = engines.find((e) => e.id === $("engine").value);
  if (!engine) return;
  const style = $("style").value, speaker = $("speaker").value;
  $("style").replaceChildren(...engine.styles.map((s) => new Option(s, s)));
  $("style").value = engine.styles.includes(style) ? style : 'Neutral';
  $("speaker").replaceChildren(...engine.speakers.map((s) => new Option(s === 'ono_anna' ? 'Ono Anna（日本語）' : s, s)));
  $("speaker").value = engine.speakers.includes(speaker) ? speaker : engine.speakers[0];
  const supported = engine.id === 'sbv2';
  for (const id of ['style', 'style-weight', 'speed']) $(id).disabled = !supported;
  $("style-weight-hint").hidden = !supported;
  $("engine-hint").textContent = engine.description + ' 切替後の初回はモデルを読み込みます。';
}
function addPreview(message) {
  const bytes = Uint8Array.from(atob(message.data), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], {type: 'audio/wav'}));
  previewUrls.push(url);
  const card = document.createElement('div');
  card.className = 'preview-result';
  const label = document.createElement('p');
  const settings = message.engine === 'sbv2' ? `${message.style} / 強さ ${message.style_weight} / 速さ ${message.speed}` : message.speaker;
  label.textContent = (engines.find((e) => e.id === message.engine)?.name || message.engine) + ' / ' + settings + '\n' + message.text;
  previewMetric = document.createElement('small');
  const audio = document.createElement('audio');
  audio.controls = true; audio.src = url;
  audio.onplay = () => stopPlayback(audio);
  card.append(label, audio, previewMetric);
  $("previews").prepend(card);
  if (previewUrls.length > 6) {
    URL.revokeObjectURL(previewUrls.shift());
    $("previews").lastElementChild.remove();
  }
}
$("engine").onchange = updateEngine;
$("scenario-file").onchange = async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  scenarioPending = true;
  controls();
  try {
    if (!file.name.toLowerCase().endsWith('.md') || file.size > 16000)
      throw new Error('.mdファイル（16KB以下）を選んでください。');
    let markdown;
    try { markdown = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer()); }
    catch { throw new Error('UTF-8で保存されたMarkdownを選んでください。'); }
    applyScenario({enabled: true, name: file.name, markdown});
  } catch (error) { scenarioError(error); }
  finally { event.target.value = ''; }
};
$("scenario-default").onclick = async () => {
  scenarioPending = true;
  controls();
  try { applyScenario(await standardScenario()); }
  catch (error) { scenarioError(error); }
};
$("roleplay-enabled").onchange = (event) => {
  try {
    if (!scenario) throw new Error('先に歴史のMarkdownを読み込んでください。');
    applyScenario({...scenario, enabled: event.target.checked});
  } catch (error) { scenarioError(error); }
};
$("previewform").onsubmit = (event) => {
  event.preventDefault();
  const text = $("preview-text").value.trim();
  if (text) {
    audioContext().catch((e) => status(e.message));
    send({type: 'preview', text}, '試聴: ' + text);
  }
};
function base64(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 8192)
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}
function encodeWav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2),
    v = new DataView(buffer);
  function text(pos, s) {
    for (let i = 0; i < s.length; i++) v.setUint8(pos + i, s.charCodeAt(i));
  }
  text(0, "RIFF");
  v.setUint32(4, 36 + samples.length * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  text(36, "data");
  v.setUint32(40, samples.length * 2, true);
  samples.forEach((s, i) =>
    v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 32767, true),
  );
  return new Uint8Array(buffer);
}
async function startRecording() {
  if (startingRecording || finishingRecording || recording || !healthy || busy) return;
  const generation = ++recordingGeneration;
  startingRecording = true;
  controls();
  stopPlayback();
  try {
    const context = await audioContext();
    mic = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    if (generation !== recordingGeneration) { mic.getTracks().forEach((t) => t.stop()); return; }
    chunks = [];
    source = context.createMediaStreamSource(mic);
    if (!workletLoaded) {
      await context.audioWorklet.addModule("/static/recorder.js");
      workletLoaded = true;
    }
    if (generation !== recordingGeneration) { mic.getTracks().forEach((t) => t.stop()); return; }
    node = new AudioWorkletNode(context, "pcm-recorder");
    node.port.onmessage = (e) => {
      if (e.data === 'flushed') flushRecording?.();
      else chunks.push(new Float32Array(e.data));
    };
    source.connect(node);
    node.connect(context.destination);
    const analyser = context.createAnalyser();
    source.connect(analyser);
    const data = new Uint8Array(analyser.fftSize);
    let heardSpeech = false, speechSince = 0, lastSpeech = performance.now();
    function meter() {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) sum += (v - 128) ** 2;
      const rms = Math.sqrt(sum / data.length) / 128, now = performance.now();
      if (rms > .012) {
        if (!speechSince) speechSince = now;
        if (now - speechSince > 120) heardSpeech = true;
        lastSpeech = now;
      } else speechSince = 0;
      $("level").style.width =
        Math.min(100, Math.sqrt(sum / data.length) * 4) + "%";
      if ($("auto-send").checked && heardSpeech && now - lastSpeech >= Number($("silence-ms").value) && recording) {
        finishRecording(true);
        return;
      }
      meterFrame = requestAnimationFrame(meter);
    }
    meter();
    recording = true;
    $("record").textContent = "■ 送信する";
    $("record").classList.add("recording");
    status("録音中… もう一度押すと送信します。");
    controls();
    timer = setTimeout(() => finishRecording(true), 27500);
  } catch (e) {
    mic?.getTracks().forEach((t) => t.stop());
    status("マイクを使用できません: " + e.message);
  } finally {
    startingRecording = false;
    controls();
  }
}
async function finishRecording(submit) {
  if (!submit) recordingGeneration++;
  if (!recording) return;
  const generation = recordingGeneration;
  finishingRecording = true;
  recording = false;
  controls();
  clearTimeout(timer);
  cancelAnimationFrame(meterFrame);
  source.disconnect();
  if (submit) {
    await new Promise((resolve) => {
      const deadline = setTimeout(resolve, 250);
      flushRecording = () => { clearTimeout(deadline); resolve(); };
      node.port.postMessage('flush');
    });
  }
  flushRecording = null;
  mic.getTracks().forEach((t) => t.stop());
  node.disconnect();
  node.port.onmessage = null;
  finishingRecording = false;
  $("record").textContent = "● 話す";
  $("record").classList.remove("recording");
  $("level").style.width = "0";
  controls();
  if (submit && generation === recordingGeneration) {
    const length = chunks.reduce((n, c) => n + c.length, 0),
      samples = new Float32Array(length);
    let offset = 0;
    for (const chunk of chunks) {
      samples.set(chunk, offset);
      offset += chunk.length;
    }
    send(
      { audio: base64(encodeWav(samples, ctx.sampleRate)) },
      `🎙 音声メッセージ (${(length / ctx.sampleRate).toFixed(1)}秒)`,
    );
  }
  chunks = [];
}
$("record").onclick = () =>
  recording ? finishRecording(true) : startRecording();
$("cancel").onclick = () => {
  activeRequest = null;
  finishRecording(false);
  stopPlayback();
  if (ws.readyState === WebSocket.OPEN) {
    busy = true; controls();
    ws.send(JSON.stringify({ type: "cancel" }));
  }
};
$("reset").onclick = () => {
  activeRequest = null;
  finishRecording(false);
  stopPlayback();
  $("conversation").replaceChildren();
  $("metrics").textContent = "";
  if (ws.readyState === WebSocket.OPEN) {
    busy = true; controls();
    ws.send(JSON.stringify({ type: "reset" }));
  }
};
$("textform").onsubmit = async (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (text) {
    audioContext().catch((e) => status(e.message));
    send({ text }, text);
    $("text").value = "";
  }
};
$("upload").onchange = async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 4000000) {
    status("WAVは4MB以下・28秒以内にしてください。");
    return;
  }
  audioContext().catch((e) => status(e.message));
  send(
    { audio: base64(new Uint8Array(await file.arrayBuffer())) },
    "🎙 " + file.name,
  );
  event.target.value = "";
};
$("style-weight").addEventListener("input", () => {
  $("style-weight-value").value = Number($("style-weight").value).toFixed(1);
});
window.addEventListener("beforeunload", () => {
  mic?.getTracks().forEach((t) => t.stop());
  ws?.close();
});
connect();
