/** Chat tabi: tanlangan maydon haqida AI bilan savol-javob (scroll yoʻq — soʻnggi xabarlar sahifalab). */
import { api } from "../api/client.js";
import { uz } from "../i18n/uz.js";
import { mdNodes } from "./report_view.js";
import { esc, h } from "./format.js";
import { paginate } from "./paginate.js";
import { toast } from "./toast.js";

let runId = null;
let messages = [];
let busy = false;

const host = () => document.getElementById("chat-pages");
const input = () => document.getElementById("chat-input");
const send = () => document.getElementById("btn-chat-send");
const clearBtn = () => document.getElementById("btn-chat-clear");

function bubble(m) {
  const div = h(`<div class="msg ${m.role}"><div class="msg-meta">${esc(m.role === "user" ? uz.chat.you : uz.chat.ai)} · ${esc(m.created_at_local || "")}</div><div class="msg-body"></div></div>`);
  const body = div.querySelector(".msg-body");
  if (m.role === "assistant") mdNodes(m.content).forEach((n) => body.appendChild(n));
  else body.textContent = m.content;
  return div;
}

function render() {
  const nodes = messages.length
    ? messages.map(bubble)
    : [h(`<div class="empty">${esc(runId ? uz.chat.empty : uz.common.empty_run)}</div>`)];
  if (busy) nodes.push(h(`<div class="msg assistant"><div class="msg-body"><i>${esc(uz.chat.thinking)}</i></div></div>`));
  paginate(host(), nodes, { lastPage: true });
  const can = runId !== null && !busy;
  input().disabled = !can;
  send().disabled = !can;
  clearBtn().disabled = !can || !messages.length;
}

export async function loadChat(id) {
  runId = id;
  messages = [];
  busy = false;
  if (id !== null) {
    try {
      messages = (await api.chat(id)).messages;
    } catch (_e) {
      messages = [];
    }
  }
  render();
}

async function ask() {
  const q = input().value.trim();
  if (!q || runId === null || busy) return;
  busy = true;
  messages = [...messages, { role: "user", content: q, created_at_local: "" }];
  input().value = "";
  render();
  try {
    const res = await api.ask(runId, q);
    messages = [...messages.slice(0, -1), res.question, res.answer];
  } catch (e) {
    messages = messages.slice(0, -1);
    input().value = q;
    toast(e.message, "error", 6000);
  }
  busy = false;
  render();
  input().focus();
}

export function initChat() {
  send().addEventListener("click", ask);
  input().addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask();
    }
  });
  clearBtn().addEventListener("click", async () => {
    if (runId === null || !confirm(uz.chat.clear_confirm)) return;
    await api.clearChat(runId);
    messages = [];
    render();
  });
  loadChat(null);
}
