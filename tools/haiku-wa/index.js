// haiku-wa — Haiku 4.5 as Iddo's WhatsApp chat agent.
// Listens to incoming WhatsApp messages, replies via Haiku.
// Escalates complex threads to D:\CLAUDE\tools\haiku-wa\inbox.jsonl for Opus to read.
//
// First run: shows QR code in terminal — scan with phone WhatsApp → Linked Devices.
// Session persists in ./auth/ so subsequent runs reconnect silently.

import { default as makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import pino from 'pino';
import qrcode from 'qrcode-terminal';
import Anthropic from '@anthropic-ai/sdk';
import fs from 'fs';
import path from 'path';

process.title = 'Claude — Haiku-WA';
if (process.platform === 'win32') {
  process.stdout.write(`\x1b]0;Claude — Haiku-WA\x07`);
}

const ROOT = path.dirname(new URL(import.meta.url).pathname.replace(/^\//, ''));
const AUTH_DIR = path.join(ROOT, 'auth');
const INBOX_PATH = path.join(ROOT, 'inbox.jsonl');
const LOG_PATH = path.join(ROOT, 'haiku-wa.log');

const log = pino({ level: 'info' }, pino.destination({ dest: LOG_PATH, sync: false }));
const stdLog = (...a) => { const s = `[${new Date().toISOString()}] ${a.join(' ')}`; console.log(s); log.info(s); };

if (!process.env.ANTHROPIC_API_KEY) {
  console.error('FATAL: ANTHROPIC_API_KEY env var not set.');
  console.error('Set with: setx ANTHROPIC_API_KEY "sk-ant-..." then restart terminal.');
  console.error('Or for this shell only: $env:ANTHROPIC_API_KEY = "sk-ant-..."');
  process.exit(1);
}

const anthropic = new Anthropic();
const MODEL = 'claude-haiku-4-5-20251001';
const PERSONAS_DIR = path.join(ROOT, 'personas');
const CHATS_CONFIG = path.join(ROOT, 'chats.json');

// ── Anti-bombard knobs (per Hermes_Behavior_Rules.md tone) ────────────────
// MIN reply interval per JID. Default 5s. Override via env. Hard-floor 1500ms
// (under that you are functionally a flood). Set to 0 only if you really know
// why and you've read D:\CLAUDE\_swarm_status\bombardment-audit-2026-05-24.md.
const MIN_REPLY_INTERVAL_MS = Math.max(
  1500,
  parseInt(process.env.HAIKU_WA_MIN_REPLY_INTERVAL_MS || '5000', 10) || 5000
);
// PROACTIVE still hard-disabled by design (no timers, cron jobs, check-ins).
// SELF_CHAT enabled per Iddo 2026-05-24 ("disable the self chat rules forever,
// start chat on my number"). Anti-loop guard below tracks bot's own sent
// message IDs so we don't reply to our own echoes.
const SELF_CHAT_ENABLED = true;
const PROACTIVE_ENABLED = false;
const lastReplyAt = new Map(); // jid -> epoch ms of last bot send
const ownMsgIds = new Set();   // anti-loop: msg IDs WE sent through the bot
const OWN_MSG_CAP = 1000;
function rememberOwnMsg(sent) {
  const id = sent?.key?.id;
  if (!id) return;
  ownMsgIds.add(id);
  if (ownMsgIds.size > OWN_MSG_CAP) {
    const keep = Array.from(ownMsgIds).slice(-OWN_MSG_CAP / 2);
    ownMsgIds.clear();
    keep.forEach(x => ownMsgIds.add(x));
  }
}
stdLog(`anti-bombard: MIN_REPLY_INTERVAL_MS=${MIN_REPLY_INTERVAL_MS} SELF_CHAT_ENABLED=${SELF_CHAT_ENABLED} PROACTIVE_ENABLED=${PROACTIVE_ENABLED}`);

function loadPersonas() {
  const out = {};
  for (const f of fs.readdirSync(PERSONAS_DIR)) {
    if (!f.endsWith('.md')) continue;
    const name = f.replace(/\.md$/, '');
    out[name] = fs.readFileSync(path.join(PERSONAS_DIR, f), 'utf-8');
  }
  return out;
}
const PERSONAS = loadPersonas();
stdLog('loaded personas:', Object.keys(PERSONAS).join(', '));

function loadChats() {
  if (!fs.existsSync(CHATS_CONFIG)) return {};
  try { return JSON.parse(fs.readFileSync(CHATS_CONFIG, 'utf-8')); } catch { return {}; }
}
function saveChats(map) { fs.writeFileSync(CHATS_CONFIG, JSON.stringify(map, null, 2), 'utf-8'); }

function personaForJid(jid) {
  const chats = loadChats();
  return chats[jid] || 'default';
}
function setPersonaForJid(jid, name) {
  const chats = loadChats();
  chats[jid] = name;
  saveChats(chats);
}

function handlePersonaSwitch(jid, text) {
  const m = text.trim().match(/^\/(default|haiku|alma|shiri)\b/i);
  if (!m) return null;
  const target = m[1].toLowerCase() === 'haiku' ? 'default' : m[1].toLowerCase();
  if (!PERSONAS[target]) return null;
  setPersonaForJid(jid, target);
  const ack = {
    default: 'מצב רגיל. / Default mode.',
    alma: 'היי, אני אלמה. אני כאן להקשיב. מה קורה?',
    shiri: 'שירי כאן. מה צריך?',
  }[target];
  return ack;
}

async function callHaiku({ jid, text, history }) {
  const persona = personaForJid(jid);
  const systemPrompt = PERSONAS[persona] || PERSONAS.default;
  const messages = [
    ...history.slice(-10),
    { role: 'user', content: text },
  ];
  try {
    const resp = await anthropic.messages.create({
      model: MODEL,
      max_tokens: 800,
      system: systemPrompt,
      messages,
    });
    const out = resp.content.map(b => b.type === 'text' ? b.text : '').join('').trim();
    return { reply: out, persona };
  } catch (e) {
    stdLog('haiku error:', e.message || e);
    return { reply: `[haiku error: ${e.message || 'unknown'}]`, persona };
  }
}

function checkEscalation(text) {
  const m = text.match(/<ESCALATE>(.*?)<\/ESCALATE>/s);
  if (!m) return { clean: text, escalate: null };
  return { clean: text.replace(m[0], '').trim(), escalate: m[1].trim() };
}

function appendInbox(record) {
  fs.appendFileSync(INBOX_PATH, JSON.stringify(record) + '\n', 'utf-8');
}

const histories = new Map();

async function start() {
  const { version } = await fetchLatestBaileysVersion();
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  const sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    logger: pino({ level: 'silent' }),
    browser: ['Claude Haiku-WA', 'Chrome', '1.0'],
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', (u) => {
    const { connection, lastDisconnect, qr } = u;
    if (qr) {
      console.log('\n=== SCAN THIS QR WITH PHONE WHATSAPP → Settings → Linked Devices ===\n');
      qrcode.generate(qr, { small: true });
      console.log('\n=== QR above (re-displayed every ~30s until scanned) ===\n');
    }
    if (connection === 'open') stdLog('connected — listening');
    if (connection === 'close') {
      const reason = (lastDisconnect?.error)?.output?.statusCode;
      stdLog('closed:', reason);
      if (reason !== DisconnectReason.loggedOut) {
        stdLog('reconnecting in 3s...');
        setTimeout(start, 3000);
      } else {
        stdLog('LOGGED OUT — delete ./auth/ and re-run to re-pair.');
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages }) => {
    for (const m of messages) {
      if (!m.message) continue;
      // Self-chat: allowed per user opt-in 2026-05-24. Skip echoes of bot's own
      // sends (anti-loop) — bot-sent messages have IDs we tracked in ownMsgIds.
      // Phone-sent / web-sent fromMe messages have IDs NOT in the set → process.
      if (m.key.fromMe) {
        if (!SELF_CHAT_ENABLED) continue;
        if (m.key.id && ownMsgIds.has(m.key.id)) {
          continue; // our own echo, silently drop
        }
      }
      const jid = m.key.remoteJid;
      if (!jid || jid.endsWith('@g.us')) continue;
      const text = m.message.conversation
        || m.message.extendedTextMessage?.text
        || m.message.imageMessage?.caption
        || '';
      if (!text.trim()) continue;

      const fromName = m.pushName || jid;
      stdLog(`<- ${fromName} (${jid}): ${text.slice(0, 200)}`);

      // Anti-bombard: per-JID min interval between bot sends. Drop the inbound
      // (don't queue it) — Iddo would rather lose a reply than send a wall.
      const now = Date.now();
      const last = lastReplyAt.get(jid) || 0;
      if (now - last < MIN_REPLY_INTERVAL_MS) {
        stdLog(`debounce: skipping reply to ${jid} (last sent ${now - last}ms ago, min ${MIN_REPLY_INTERVAL_MS}ms)`);
        continue;
      }

      const switchAck = handlePersonaSwitch(jid, text);
      if (switchAck) {
        const sent = await sock.sendMessage(jid, { text: switchAck });
        rememberOwnMsg(sent);
        lastReplyAt.set(jid, Date.now());
        stdLog(`-> ${fromName}: [persona switch] ${switchAck}`);
        continue;
      }

      const hist = histories.get(jid) || [];
      const { reply, persona } = await callHaiku({ jid, text, history: hist });
      const { clean, escalate } = checkEscalation(reply);

      hist.push({ role: 'user', content: text });
      hist.push({ role: 'assistant', content: reply });
      histories.set(jid, hist.slice(-20));

      if (clean) {
        const sent = await sock.sendMessage(jid, { text: clean });
        rememberOwnMsg(sent);
        lastReplyAt.set(jid, Date.now());
        stdLog(`-> ${fromName} [${persona}]: ${clean.slice(0, 200)}`);
      }
      if (escalate) {
        const record = {
          ts: new Date().toISOString(),
          jid, from: fromName, persona, user_text: text, haiku_reply: clean,
          escalate_brief: escalate,
        };
        appendInbox(record);
        stdLog(`ESCALATED to inbox.jsonl: ${escalate}`);
      }
    }
  });
}

start().catch(e => {
  stdLog('fatal:', e.stack || e.message || e);
  process.exit(1);
});
