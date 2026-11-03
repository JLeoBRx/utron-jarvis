// JARVIS WEB ORB — a presença remota da matriz-mãe. Esta página NÃO tem inteligência, memória, chaves nem estados
// próprios: tudo o que a ORBE mostra (estado, voz, autorização, identidade ULTRON) chega da matriz-mãe pelo
// gateway; o que o usuário digita ou fala vai para o MESMO JARVIS do computador principal.
import * as THREE from 'three';
import { Orb } from '/scene/js/orb.js';

const $ = (id) => document.getElementById(id);
const csrf = () => (document.cookie.match(/(?:^|; )jarvis_csrf=([^;]+)/) || [])[1] || '';
const STATE_LABEL = { aguardando: 'EM ESPERA', escutando: 'ESCUTANDO', reconhecendo: 'ESCUTANDO', pensando: 'PENSANDO',
  falando: 'FALANDO', executando: 'EXECUTANDO', confirmacao: 'AGUARDANDO AUTORIZAÇÃO', alerta: 'ALERTA', erro: 'ERRO',
  privacidade: 'PRIVACIDADE', inicializando: 'INICIALIZANDO', tardis: 'TARDIS' };

// ---------------------------------------------------------------- cena: só a ORBE
const canvas = $('stage');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
renderer.setClearColor(0x030712, 1);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.05, 50);
camera.position.set(0, 0, 3.2);
const orb = new Orb({ particleScale: window.innerWidth < 700 ? 0.7 : 1 });
scene.add(orb.group);
orb.apply({ state: 'inicializando', connected: false });
function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.position.z = w < h ? 4.1 : 3.2;                          // celular em pé: ORBE inteira na tela
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize); resize();
let ultronK = 0, ultronTarget = 0, voiceLevel = 0, micLevel = 0, last = performance.now();
function frame(now) {
  const dt = Math.min(0.1, (now - last) / 1000); last = now;
  ultronK += (ultronTarget - ultronK) * (1 - Math.exp(-dt * 1.2));
  orb.ultron = ultronK;
  orb.voice = Math.max(orb.voice * 0.9, voiceLevel); orb.mic = micLevel;
  orb.update(dt, now / 1000);
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ---------------------------------------------------------------- interface
function notice(text, ms = 5000) {
  $('notice').textContent = text; $('notice').classList.toggle('hidden', !text);
  if (text) { clearTimeout(notice.t); notice.t = setTimeout(() => $('notice').classList.add('hidden'), ms); }
}
function setConn(kind, text) { $('conn').dataset.kind = kind; $('conn-text').textContent = text; }
function line({ role, text, source, provenance }) {
  if (!text) return;
  const el = document.createElement('div');
  el.className = `line ${role === 'user' ? 'user' : 'jarvis'}`;
  const who = document.createElement('span'); who.className = 'who';
  who.textContent = role === 'user' ? `VOCÊ${source ? ` (${source})` : ''}` : (role === 'system' ? '//' : 'JARVIS');
  el.append(who, document.createTextNode(text));
  if (provenance) { const s = document.createElement('span'); s.className = 'src'; s.textContent = provenance; el.append(s); }
  $('log').append(el);
  while ($('log').children.length > 60) $('log').firstChild.remove();
  $('log').scrollTop = $('log').scrollHeight;
}
let matrizOnline = false, authId = null;
function applyState(s) {
  if (!s) return;
  const state = s.state || 'aguardando';
  orb.apply({ state, rgb: s.rgb, iris: s.iris, connected: matrizOnline });
  $('state-label').textContent = matrizOnline ? (s.label || STATE_LABEL[state] || state.toUpperCase()) : 'MATRIZ-MÃE DESCONECTADA';
  $('state-detail').textContent = matrizOnline ? (s.detail || '') : 'aguardando o computador principal';
  const ultron = !!(s.persona && s.persona.name === 'ultron');
  ultronTarget = ultron ? 1 : 0;
  document.body.classList.toggle('ultron', ultron);
  $('brand').firstChild.textContent = ultron ? 'U.L.T.R.O.N.' : 'J.A.R.V.I.S.';
  const auth = s.authorization;
  authId = auth ? auth.id : null;
  $('auth').classList.toggle('hidden', !auth || !matrizOnline);
  if (auth) {
    $('auth-text').textContent = auth.description || '';
    $('auth-buttons').classList.toggle('hidden', !auth.remote_ok);
    $('auth-local').classList.toggle('hidden', !!auth.remote_ok);
  }
}
function setMatriz(online) {
  matrizOnline = !!online;
  document.body.classList.toggle('offline', !matrizOnline);
  setConn(matrizOnline ? 'online' : 'offline', matrizOnline ? 'MATRIZ-MÃE CONECTADA' : 'MATRIZ-MÃE DESCONECTADA');
  if (!matrizOnline) applyState({ state: 'aguardando' });
}

// ---------------------------------------------------------------- áudio (voz da matriz-mãe)
let audioOn = localStorageGet('jarvis_audio', '1') === '1';
let audioCtx = null;
function localStorageGet(k, d) { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } }
function localStorageSet(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } }
function ensureAudio() { if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)(); return audioCtx; }
async function playWav(b64) {
  if (!audioOn) return;
  const ctx = ensureAudio();
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const buffer = await ctx.decodeAudioData(bytes.buffer);
  const src = ctx.createBufferSource(); src.buffer = buffer;
  const analyser = ctx.createAnalyser(); analyser.fftSize = 512;
  src.connect(analyser); analyser.connect(ctx.destination);
  const data = new Float32Array(analyser.fftSize);
  let playing = true;
  src.onended = () => { playing = false; voiceLevel = 0; };
  const meter = () => {                                 // a ORBE pulsa com a energia REAL do áudio tocado
    if (!playing) return;
    analyser.getFloatTimeDomainData(data);
    let sum = 0; for (const v of data) sum += v * v;
    voiceLevel = Math.min(1, Math.sqrt(sum / data.length) * 4);
    requestAnimationFrame(meter);
  };
  src.start(); meter();
}
function renderAudioButton() {
  $('audio').textContent = audioOn ? 'SOM: LIGADO' : 'SOM: DESLIGADO';
  $('audio').setAttribute('aria-pressed', audioOn ? 'true' : 'false');
}

// ---------------------------------------------------------------- conexão com a matriz-mãe (via gateway)
let ws = null, retry = 1000, revoked = false;
function send(obj) { if (ws && ws.readyState === 1) { ws.send(JSON.stringify(obj)); return true; } return false; }
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/orb`);
  setConn('pending', 'CONECTANDO…');
  ws.onopen = () => { retry = 1000; send({ type: 'audio_pref', on: audioOn }); };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === 'hello') {
      $('brand-sub').textContent = `WEB ORB · ${m.device}`;
      setMatriz(m.matriz);
      $('log').textContent = '';
      for (const l of m.history || []) line(l);
      applyState(m.state);
    } else if (m.type === 'matriz') { setMatriz(m.online); }
    else if (m.type === 'state') { applyState(m); }
    else if (m.type === 'line') { line(m); }
    else if (m.type === 'audio') { playWav(m.wav_b64).catch(() => notice('Não foi possível tocar a voz neste navegador.')); }
    else if (m.type === 'notice') { notice(m.text); }
  };
  ws.onclose = (ev) => {
    setMatriz(false);
    if (ev.code === 4001) { revoked = true; showPairing('Este dispositivo foi desconectado ou revogado no computador principal.'); return; }
    setConn('offline', 'SEM CONEXÃO COM O GATEWAY');
    setTimeout(connect, retry); retry = Math.min(30000, retry * 2);
  };
}

// ---------------------------------------------------------------- conversa
canvas.addEventListener('click', () => { if (!revoked && $('pair').classList.contains('hidden')) $('talk').classList.toggle('hidden'); });
$('say-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const text = $('say').value.trim();
  if (!text) return;
  if (!matrizOnline) { notice('MATRIZ-MÃE DESCONECTADA — a mensagem não foi enviada.'); return; }
  if (send({ type: 'say', text })) $('say').value = '';
});
$('stop').addEventListener('click', () => send({ type: 'cancel' }));
$('auth-yes').addEventListener('click', () => authId && send({ type: 'authorize', id: authId, approve: true }));
$('auth-no').addEventListener('click', () => authId && send({ type: 'authorize', id: authId, approve: false }));
$('audio').addEventListener('click', () => {
  audioOn = !audioOn; localStorageSet('jarvis_audio', audioOn ? '1' : '0'); renderAudioButton();
  send({ type: 'audio_pref', on: audioOn }); if (audioOn) ensureAudio().resume();
});
$('logout').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST', headers: { 'X-CSRF-Token': csrf() }, credentials: 'same-origin' });
  revoked = true; if (ws) ws.close(); showPairing('Dispositivo desconectado.');
});
renderAudioButton();

// microfone do navegador (com permissão): grava enquanto o botão está ativo e manda o áudio à matriz-mãe, que
// reconhece a fala com o MESMO reconhecedor do computador principal
let rec = null;
$('mic').addEventListener('click', async () => {
  if (rec) { stopRecording(); return; }
  if (!matrizOnline) { notice('MATRIZ-MÃE DESCONECTADA.'); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    const ctx = ensureAudio();
    const source = ctx.createMediaStreamSource(stream);
    const node = ctx.createScriptProcessor(4096, 1, 1);
    const chunks = [];
    node.onaudioprocess = (e) => {
      const d = e.inputBuffer.getChannelData(0);
      chunks.push(new Float32Array(d));
      let s = 0; for (const v of d) s += v * v; micLevel = Math.min(1, Math.sqrt(s / d.length) * 6);
    };
    source.connect(node); node.connect(ctx.destination);
    rec = { stream, node, source, chunks, rate: ctx.sampleRate, started: performance.now() };
    $('mic').setAttribute('aria-pressed', 'true'); $('mic').textContent = 'PARAR E ENVIAR';
    orb.apply({ state: 'escutando', connected: true });
    rec.timer = setTimeout(stopRecording, 20000);
  } catch (e) { notice('Microfone não autorizado neste navegador.'); }
});
function stopRecording() {
  if (!rec) return;
  clearTimeout(rec.timer);
  rec.node.disconnect(); rec.source.disconnect(); rec.stream.getTracks().forEach((t) => t.stop());
  const wav = encodeWav(rec.chunks, rec.rate, 16000);
  rec = null; micLevel = 0;
  $('mic').setAttribute('aria-pressed', 'false'); $('mic').textContent = 'MICROFONE';
  send({ type: 'audio', wav_b64: wav });
}
function encodeWav(chunks, rate, target) {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const all = new Float32Array(total); let o = 0; for (const c of chunks) { all.set(c, o); o += c.length; }
  const ratio = rate / target, n = Math.floor(all.length / ratio);
  const pcm = new Int16Array(n);
  for (let i = 0; i < n; i++) { const v = all[Math.floor(i * ratio)]; pcm[i] = Math.max(-1, Math.min(1, v)) * 32767; }
  const buf = new ArrayBuffer(44 + pcm.length * 2), dv = new DataView(buf);
  const w = (p, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(p + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); dv.setUint32(4, 36 + pcm.length * 2, true); w(8, 'WAVE'); w(12, 'fmt '); dv.setUint32(16, 16, true);
  dv.setUint16(20, 1, true); dv.setUint16(22, 1, true); dv.setUint32(24, target, true); dv.setUint32(28, target * 2, true);
  dv.setUint16(32, 2, true); dv.setUint16(34, 16, true); w(36, 'data'); dv.setUint32(40, pcm.length * 2, true);
  new Int16Array(buf, 44).set(pcm);
  let bin = ''; const bytes = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

// ---------------------------------------------------------------- pareamento
function showPairing(text = '') {
  $('talk').classList.add('hidden'); $('auth').classList.add('hidden');
  $('pair').classList.remove('hidden'); $('pair-status').textContent = text;
  setConn('pending', 'NÃO PAREADO');
  $('state-label').textContent = 'NÃO PAREADO'; $('state-detail').textContent = '';
}
async function claim(body) {
  $('pair-status').textContent = 'Enviando…';
  const r = await fetch('/api/pair/claim', { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() }, body: JSON.stringify(body) });
  if (!r.ok) { $('pair-status').textContent = await r.text(); return; }
  const { claim: id } = await r.json();
  $('pair-status').textContent = 'Confirme este dispositivo no computador principal…';
  for (let i = 0; i < 20; i++) {
    const w = await fetch(`/api/pair/wait?claim=${encodeURIComponent(id)}`, { credentials: 'same-origin' });
    if (!w.ok) { $('pair-status').textContent = 'Pareamento expirado — gere outro código no computador.'; return; }
    const { state } = await w.json();
    if (state === 'aprovado') { location.replace('/'); return; }
    if (state === 'negado') { $('pair-status').textContent = 'Pareamento negado no computador principal.'; return; }
    if (state === 'expirado') { $('pair-status').textContent = 'Pareamento expirado — gere outro código.'; return; }
  }
  $('pair-status').textContent = 'Sem confirmação a tempo — gere outro código no computador.';
}
$('pair-form').addEventListener('submit', (e) => {
  e.preventDefault();
  claim({ code: $('pair-code').value, device_name: $('pair-name').value || defaultName() }).catch(() => {
    $('pair-status').textContent = 'Sem conexão com o gateway.';
  });
});
function defaultName() {
  const ua = navigator.userAgent;
  return /iPhone|iPad/.test(ua) ? 'iPhone/iPad' : /Android/.test(ua) ? 'Android' : /Mac/.test(ua) ? 'Mac' : /Windows/.test(ua) ? 'Windows' : 'Navegador';
}

// ---------------------------------------------------------------- início
(async function start() {
  let session;
  try { session = await (await fetch('/api/session', { credentials: 'same-origin' })).json(); }
  catch (e) { setConn('offline', 'SEM CONEXÃO COM O GATEWAY'); return; }
  const link = (location.pathname.match(/^\/p\/([A-Za-z0-9_-]{10,120})$/) || [])[1];
  if (session.paired) { if (link) history.replaceState(null, '', '/'); connect(); return; }
  showPairing(session.matriz ? '' : 'A matriz-mãe está desconectada: ligue o JARVIS no computador principal.');
  if (link) { history.replaceState(null, '', '/'); await claim({ link, device_name: defaultName() }); }
})();
