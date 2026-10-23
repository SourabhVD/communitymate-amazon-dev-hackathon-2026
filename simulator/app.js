/* Voice is browser-native; AWS credentials never enter this page. */
const $ = id => document.getElementById(id);
const ui = {token: null, cursor: 0, busy: false, pending: null, voice: true,
  listening: false, speaking: false, poll: null, generation: 0, turns: 0, tools: 0};
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition;
// Voices may arrive after page load. Prefer natural US English voices when
// exposed by this browser, then fall back to an available English voice.
const speechSettings = {rate: 0.95, pitch: 1.02};
let replyVoice = null;
function selectReplyVoice() {
  const voices = window.speechSynthesis.getVoices();
  const english = voices.filter(voice => /^en(?:[-_]|$)/i.test(voice.lang));
  function score(voice) {
    let value = /^en[-_]US$/i.test(voice.lang) ? 100 : 0;
    if (/natural|neural|premium|enhanced/i.test(voice.name)) value += 40;
    if (/aria|jenny/i.test(voice.name)) value += 20;
    if (/google.*US English/i.test(voice.name)) value += 15;
    if (/zira|samantha/i.test(voice.name)) value += 10;
    if (voice.default) value += 1;
    return value;
  }
  replyVoice = english.sort((a, b) => score(b) - score(a))[0] || null;
  $('voiceToggle').title = replyVoice
    ? `Spoken replies: ${replyVoice.name}; rate ${speechSettings.rate}, pitch ${speechSettings.pitch}`
    : 'Spoken replies use the browser default voice';
}
if ('speechSynthesis' in window) {
  window.speechSynthesis.addEventListener('voiceschanged', selectReplyVoice);
  selectReplyVoice();
}

function status(text, state = 'ready') {
  $('status').textContent = text;
  document.body.dataset.state = state;
}
function notice(text = '') { $('notice').textContent = text; $('notice').hidden = !text; }
function plain(text) {
  return String(text).replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/\*\*|__|^#{1,6}\s/gm, '');
}
// Spoken text needs sentence boundaries; visual Markdown line breaks alone
// do not reliably produce pauses in browser speech engines.
function speechText(text) {
  return plain(text)
    .replace(/`+/g, '')
    .replace(/\b(reservation|ticket|package|request)\s+ID\s*:\s*/gi, '$1 number ')
    .replace(/\bID\b/g, 'I D')
    .split(/\r?\n/)
    .map(line => line.replace(/^\s*(?:[-*•]|\d+[.)])\s+/, '').trim())
    .filter(Boolean)
    .map(line => /[.!?;:]$/.test(line) ? line : `${line}.`)
    .join(' ');
}
function addTurn(who, text) {
  const row = document.createElement('li');
  const label = document.createElement('span');
  label.className = `speaker ${who}`;
  label.textContent = who === 'resident' ? 'You' : 'CommunityMate';
  row.append(label, document.createTextNode(plain(text)));
  $('transcript').append(row);
  $('transcript').scrollTop = $('transcript').scrollHeight;
  $('turnCount').textContent = ++ui.turns;
}
function controls() {
  $('send').disabled = ui.busy && !ui.pending;
  $('message').disabled = ui.busy && !ui.pending;
  $('mic').disabled = !Recognition || (ui.busy && !ui.pending);
  document.querySelectorAll('[data-question]').forEach(button => button.disabled = ui.busy);
}
function speak(text) {
  if (!ui.voice || !('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(speechText(text));
  selectReplyVoice();
  if (replyVoice) utterance.voice = replyVoice;
  utterance.lang = replyVoice ? replyVoice.lang : 'en-US';
  utterance.rate = speechSettings.rate;
  utterance.pitch = speechSettings.pitch;
  utterance.onstart = () => { ui.speaking = true; status('Speaking · tap the microphone to interrupt', 'speaking'); };
  utterance.onend = utterance.onerror = () => {
    ui.speaking = false;
    if (ui.pending) status('Waiting for your confirmation', 'confirming');
    else if (ui.busy) status('Thinking…', 'thinking');
    else if (!ui.listening) status(Recognition ? 'Tap to speak, or type below' : 'Type your request below');
  };
  speechSynthesis.speak(utterance);
}
async function api(path, method = 'GET', data) {
  const headers = {'X-CommunityMate-Client': '1'};
  if (ui.token) headers.Authorization = `Bearer ${ui.token}`;
  if (method !== 'GET') headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {method, headers, body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
async function startSession() {
  const generation = ++ui.generation;
  clearTimeout(ui.poll);
  if (ui.token) { try { await api('/api/session', 'DELETE', {}); } catch (_) {} }
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  if (recognition && ui.listening) recognition.abort();
  ui.token = null; ui.cursor = 0; ui.busy = false; ui.pending = null;
  ui.turns = 0; ui.tools = 0;
  $('transcript').replaceChildren(); $('tools').replaceChildren();
  $('turnCount').textContent = ''; $('toolCount').textContent = '0';
  $('confirmation').hidden = true; $('heard').hidden = true;
  $('reply').textContent = 'Ask about your community, reserve a space, or get help with a repair.';
  $('suggestions').hidden = false;
  notice(); controls();
  try {
    const result = await api('/api/session', 'POST', {});
    if (generation !== ui.generation) return;
    ui.token = result.token;
    status(Recognition ? 'Tap to speak, or type below' : 'Speech input unavailable · type below');
    poll(generation);
  } catch (error) { notice(error.message); status('Could not connect'); }
}
async function poll(generation) {
  if (generation !== ui.generation || !ui.token) return;
  try {
    const result = await api(`/api/events?after=${ui.cursor}`);
    if (generation !== ui.generation) return;
    for (const event of result.events) {
      ui.cursor = event.id;
      handleEvent(event);
    }
    controls();
  } catch (error) { if (generation === ui.generation) notice(error.message); }
  if (generation === ui.generation) ui.poll = setTimeout(() => poll(generation), 650);
}
function handleEvent(event) {
  switch (event.type) {
    case 'resident':
      addTurn('resident', event.text);
      $('heard').textContent = `“${event.text}”`; $('heard').hidden = false;
      $('suggestions').hidden = true;
      break;
    case 'assistant':
      addTurn('assistant', event.text);
      $('reply').textContent = plain(event.text);
      speak(event.text);
      break;
    case 'state':
      ui.busy = event.state !== 'ready';
      if (!ui.speaking && !ui.pending && !ui.listening)
        status(ui.busy ? 'Thinking…' : (Recognition ? 'Tap to speak, or type below' : 'Type your request below'), event.state);
      break;
    case 'tool': {
      const item = document.createElement('li');
      item.textContent = event.name.replaceAll('_', ' ');
      $('tools').append(item); $('toolCount').textContent = ++ui.tools;
      status('Checking your community…', 'thinking');
      break;
    }
    case 'confirmation':
      ui.pending = event;
      $('confirmationTitle').textContent = event.action;
      $('confirmationDetails').replaceChildren();
      Object.entries(event.details).forEach(([key, value]) => {
        const term = document.createElement('dt');
        term.textContent = key.replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase());
        const detail = document.createElement('dd');
        detail.textContent = value === '' ? 'Not specified' : String(value).replaceAll('ask_first', 'Ask first');
        $('confirmationDetails').append(term, detail);
      });
      $('confirmation').hidden = false;
      $('confirm').disabled = false; $('decline').disabled = false;
      status('Waiting for your confirmation', 'confirming');
      speak(`Please confirm: ${event.action}. ${Object.entries(event.details).map(([k,v]) => `${k.replaceAll('_',' ')}: ${v || 'not specified'}`).join('. ')}. Say yes or no, or use the buttons.`);
      break;
    case 'confirmation_resolved':
      ui.pending = null; $('confirmation').hidden = true;
      if ('speechSynthesis' in window) speechSynthesis.cancel();
      status(event.accepted ? 'Confirmed · working on it…' : 'Declined · no action approved', 'thinking');
      if (event.reason === 'expired') notice('Confirmation expired. No action was approved.');
      break;
    case 'error':
      notice(event.text); $('reply').textContent = 'I couldn’t finish that request. Please review the message below.';
      addTurn('assistant', 'Request failed: ' + event.text);
      break;
  }
}
async function sendText(text) {
  text = text.trim(); if (!text || !ui.token) return;
  if (ui.pending) {
    const answer = text.toLowerCase().replace(/[.!?]/g, '').trim();
    if (['yes', 'confirm'].includes(answer)) return decide(true);
    if (['no', 'decline', 'cancel'].includes(answer)) return decide(false);
    notice('Please say yes or no, or use Confirm / Decline for the displayed details.'); return;
  }
  if (ui.busy) return;
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  notice(); ui.busy = true; controls(); status('Thinking…', 'thinking');
  try {
    await api('/api/messages', 'POST', {text, message_id: crypto.randomUUID()});
    $('message').value = '';
  } catch (error) { ui.busy = false; controls(); status('Ready'); notice(error.message); }
}
async function decide(accepted) {
  if (!ui.pending) return;
  $('confirm').disabled = true; $('decline').disabled = true;
  try {
    await api('/api/confirmation', 'POST', {approval_id: ui.pending.approval_id, accepted});
    $('message').value = '';
  } catch (error) { notice(error.message); $('confirm').disabled = false; $('decline').disabled = false; }
}

$('messageForm').addEventListener('submit', event => { event.preventDefault(); sendText($('message').value); });
$('confirm').onclick = () => decide(true);
$('decline').onclick = () => decide(false);
$('newChat').onclick = startSession;
document.querySelectorAll('[data-question]').forEach(button => button.onclick = () => sendText(button.dataset.question));
$('voiceToggle').onclick = () => {
  ui.voice = !ui.voice;
  $('voiceToggle').setAttribute('aria-pressed', String(ui.voice));
  $('voiceToggle').textContent = ui.voice ? 'Voice on' : 'Voice off';
  if (!ui.voice && 'speechSynthesis' in window) speechSynthesis.cancel();
};
if (Recognition) {
  recognition = new Recognition();
  recognition.lang = 'en-US'; recognition.interimResults = true; recognition.continuous = false;
  let finalText = '';
  recognition.onstart = () => { ui.listening = true; finalText = ''; status('Listening…', 'listening'); notice(); };
  recognition.onresult = event => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) finalText += event.results[i][0].transcript;
      else interim += event.results[i][0].transcript;
    }
    $('heard').textContent = finalText || interim; $('heard').hidden = false;
  };
  recognition.onerror = event => { notice(`Speech input: ${event.error}. You can type your request below.`); finalText = ''; };
  recognition.onend = () => {
    ui.listening = false;
    if (finalText.trim()) { const text = finalText; finalText = ''; sendText(text); }
    else if (ui.pending) status('Waiting for your confirmation', 'confirming');
    else if (!ui.busy) status('Tap to speak, or type below');
  };
  $('mic').onclick = () => {
    if (ui.listening) { recognition.stop(); return; }
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    ui.speaking = false;
    try { recognition.start(); } catch (_) { notice('Microphone is already active.'); }
  };
} else {
  $('mic').disabled = true;
  $('mic').title = 'Speech recognition is unavailable in this browser. Use the text field.';
}

(async () => {
  try {
    const health = await api('/api/health');
    if (health.mode === 'preview') {
      $('modeLabel').textContent = 'Interface preview';
      $('costLabel').textContent = 'No model connected. Nothing is saved.';
    } else $('costLabel').textContent = 'Messages use paid Amazon Bedrock inference.';
    await startSession();
  } catch (error) { notice(error.message); status('Local simulator unavailable'); }
})();
