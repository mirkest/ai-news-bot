/**
 * AI-news bot: интерактивная часть.
 *
 * Cloudflare Worker принимает вебхук Telegram и отвечает на команды:
 *   /start  — приветствие и кнопки
 *   /top    — рейтинг моделей (/top 21, /top labs)
 *   /new    — новые модели за неделю
 *   /model  — карточка модели по названию
 *   /help   — как это работает
 *
 * Данные берутся из data/leaderboard.json и data/recent.json
 * (их обновляет GitHub Actions), поэтому воркер ничего не считает сам.
 *
 * Переменные окружения (Settings -> Variables and Secrets):
 *   BOT_TOKEN       — токен из @BotFather (secret)
 *   DATA_BASE       — https://raw.githubusercontent.com/<user>/<repo>/main/data
 *   WEBHOOK_SECRET  — любая строка, попадает в путь вебхука
 *   INSTALL_KEY     — чтобы открыть /install?key=... и зарегистрировать вебхук
 *   GH_TOKEN        — токен GitHub с правом Actions: write (secret, необязателен)
 *   GH_REPO         — user/repo, по умолчанию mirkest/ai-news-bot
 *
 * Плюс Cron Trigger (Settings -> Triggers -> Cron): каждые 10 минут воркер
 * проверяет, не забыл ли GitHub запустить workflow, и при необходимости
 * запускает его сам.
 */

const PAGE_SIZE = 10;
const MAX_PAGES = 5;
const WEEK = 7 * 86400;

const MODS = { text: "текст", image: "фото", file: "файлы", audio: "аудио", video: "видео" };
const MOD_ICONS = { text: "📝", image: "📷", file: "📄", audio: "🔊", video: "🎬" };
const MOD_ORDER = ["text", "image", "file", "audio", "video"];

/* ---------------------------------------------------------------- утилиты */

const esc = (value) =>
  String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

function sortMods(mods) {
  const list = mods || [];
  const known = MOD_ORDER.filter((mod) => list.includes(mod));
  return known.concat(list.filter((mod) => !MOD_ORDER.includes(mod)));
}

function money(value) {
  if (value === null || value === undefined) return "—";
  if (value === 0) return "0";
  let text;
  if (value < 0.01) text = value.toFixed(4);
  else if (value < 0.1) text = value.toFixed(3);
  else if (value < 100) text = value.toFixed(2);
  else text = value.toFixed(0);
  return text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text;
}

function ctx(value) {
  if (!value) return "";
  if (value >= 1e6) return `${(value / 1e6).toFixed(1).replace(".0", "")}M`;
  if (value >= 1000) return `${Math.round(value / 1000)}K`;
  return String(value);
}

function priceText(model) {
  if (model.in === 0 && model.out === 0) return "бесплатно";
  if (model.in == null && model.out == null) return "—";
  return `$${money(model.in)}/$${money(model.out)}`;
}

function dateText(seconds) {
  if (!seconds) return "";
  const d = new Date(seconds * 1000);
  return `${String(d.getUTCDate()).padStart(2, "0")}.${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

function prettyDate(iso) {
  const parts = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  return parts ? `${parts[3]}.${parts[2]}.${parts[1]}` : iso || "";
}

/* ---------------------------------------------------------------- telegram */

async function tg(env, method, payload) {
  const response = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json().catch(() => ({}));
}

async function send(env, chatId, text, keyboard) {
  return tg(env, "sendMessage", {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
    ...(keyboard ? { reply_markup: keyboard } : {}),
  });
}

async function edit(env, chatId, messageId, text, keyboard) {
  const result = await tg(env, "editMessageText", {
    chat_id: chatId,
    message_id: messageId,
    text,
    parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
    ...(keyboard ? { reply_markup: keyboard } : {}),
  });
  // «message is not modified» — не ошибка, просто нажали ту же кнопку.
  return result;
}

/* ---------------------------------------------------------------- данные */

async function loadData(env, name) {
  const base = (env.DATA_BASE || "").replace(/\/+$/, "");
  if (!base) throw new Error("DATA_BASE не задан");
  const response = await fetch(`${base}/${name}`, {
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
  return response.json();
}

/* ---------------------------------------------------------------- рейтинг */

function topList(board, kind) {
  const models = board.models || [];
  const pool = kind === "labs" ? models.filter((model) => model.lab) : models;
  return pool.slice(0, PAGE_SIZE * MAX_PAGES);
}

function renderTop(board, kind, requestedPage) {
  const list = topList(board, kind);
  const pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
  const page = Math.min(Math.max(1, requestedPage), pages);
  const slice = list.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const lines = [
    `🏆 <b>Топ-50 · ${kind === "labs" ? "топ-лаборатории" : "все модели"}</b>`,
    `<i>LMArena · ${esc(prettyDate(board.board_date) || board.updated || "")}</i>`,
    "",
  ];

  slice.forEach((model, index) => {
    const place = (page - 1) * PAGE_SIZE + index + 1;
    lines.push(`<b>${place}.</b> ${esc(model.name)} — ${esc(model.org)}`);
    const bits = [`${Math.round(model.elo)} Elo`, priceText(model)];
    if (model.ctx) bits.push(ctx(model.ctx));
    const icons = sortMods(model.mods).map((mod) => MOD_ICONS[mod]).filter(Boolean).join("");
    if (icons) bits.push(icons);
    lines.push(`   ${bits.join(" · ")}`);
  });

  if (!slice.length) lines.push("Рейтинг пока пуст, попробуй позже.");

  return { text: lines.join("\n"), page, pages };
}

function topKeyboard(kind, page, pages) {
  return {
    inline_keyboard: [
      [
        { text: "🌍 Все", callback_data: `t|all|${kind === "all" ? page : 1}` },
        { text: "🏢 Топ-лабы", callback_data: `t|labs|${kind === "labs" ? page : 1}` },
      ],
      [
        { text: "⬅️", callback_data: `t|${kind}|${Math.max(1, page - 1)}` },
        { text: `${page}/${pages}`, callback_data: "x" },
        { text: "➡️", callback_data: `t|${kind}|${Math.min(pages, page + 1)}` },
      ],
    ],
  };
}

/* ---------------------------------------------------------------- тексты */

function startText() {
  return [
    "👋 <b>Привет! Я слежу за новыми ИИ.</b>",
    "",
    "В канале — релизы топ-лабораторий: цена за 1M токенов,",
    "контекст, модальности и оценка LMArena.",
    "",
    "Здесь можно посмотреть рейтинг:",
  ].join("\n");
}

function startKeyboard() {
  return {
    inline_keyboard: [
      [{ text: "🏆 Рейтинг моделей", callback_data: "t|all|1" }],
      [
        { text: "🆕 Что нового", callback_data: "cmd|new" },
        { text: "ℹ️ Помощь", callback_data: "cmd|help" },
      ],
    ],
  };
}

function helpText() {
  return [
    "ℹ️ <b>Как это работает</b>",
    "",
    "/top — топ-50 моделей по LMArena с ценами и контекстом",
    "/top 21 — сразу с 21-й позиции",
    "/top labs — только топ-лаборатории",
    "/new — что вышло за последние 7 дней",
    "/model &lt;название&gt; — карточка модели",
    "",
    "<b>Источники</b>",
    "• OpenRouter — цены и характеристики",
    "• LMArena — рейтинг «ума»",
    "",
    "Посты о новых моделях выходят в канале автоматически.",
  ].join("\n");
}

function modelCard(model) {
  const lines = [`<b>${esc(model.name)}</b> — ${esc(model.org)}`];
  if (model.elo) lines.push(`🏆 ${Math.round(model.elo)} Elo · #${model.rank} в LMArena`);
  lines.push(`💵 ${priceText(model)} за 1M токенов`);
  if (model.ctx) lines.push(`📏 Контекст: ${ctx(model.ctx)}`);
  const mods = sortMods(model.mods).map((mod) => MODS[mod]).filter(Boolean);
  if (mods.length) lines.push(`👁 Вход: ${mods.join(", ")}`);
  if (model.or) lines.push(`🔗 <a href="https://openrouter.ai/${esc(model.or)}">Открыть на OpenRouter</a>`);
  return lines.join("\n");
}

function newText(recent) {
  const items = (recent.items || []).filter((item) => Date.now() / 1000 - item.created < WEEK);
  const lines = ["🆕 <b>Новые модели за 7 дней</b>", ""];
  if (!items.length) {
    lines.push("Пока ничего нового. Загляни позже.");
  } else {
    items.slice(0, 15).forEach((item) => {
      const elo = item.elo ? ` · ${item.elo} Elo` : "";
      lines.push(`• <a href="https://openrouter.ai/${esc(item.id)}">${esc(item.name)}</a> — ${esc(item.lab)} · ${dateText(item.created)}${elo}`);
    });
  }
  return lines.join("\n");
}

/* ---------------------------------------------------------------- команды */

async function onMessage(message, env) {
  if (!message.chat) return;
  const chatId = message.chat.id;
  const text = (message.text || "").trim();
  if (!text.startsWith("/")) {
    return send(env, chatId, "Я понимаю команды. Нажми /start или /help.", startKeyboard());
  }

  const [rawCommand, ...rest] = text.split(/\s+/);
  const command = rawCommand.split("@")[0].toLowerCase();
  const argument = rest.join(" ").trim();

  try {
    if (command === "/start") {
      return send(env, chatId, startText(), startKeyboard());
    }

    if (command === "/help") {
      return send(env, chatId, helpText());
    }

    if (command === "/top") {
      const board = await loadData(env, "leaderboard.json");
      const kind = /^(labs|лабы|топ)$/i.test(argument) ? "labs" : "all";
      const page = /^\d+$/.test(argument) ? Math.ceil(Number(argument) / PAGE_SIZE) : 1;
      const { text: body, page: current, pages } = renderTop(board, kind, page);
      return send(env, chatId, body, topKeyboard(kind, current, pages));
    }

    if (command === "/new") {
      const recent = await loadData(env, "recent.json");
      return send(env, chatId, newText(recent));
    }

    if (command === "/model") {
      if (!argument) {
        return send(env, chatId, "Напиши так: <code>/model gemini</code>");
      }
      const board = await loadData(env, "leaderboard.json");
      const query = argument.toLowerCase();
      const found = (board.models || [])
        .filter(
          (model) =>
            model.name.toLowerCase().includes(query) ||
            model.org.toLowerCase().includes(query) ||
            (model.or || "").toLowerCase().includes(query)
        )
        .slice(0, 3);
      if (!found.length) {
        return send(env, chatId, `Ничего не нашёл по запросу «${esc(argument)}». Попробуй часть названия.`);
      }
      return send(env, chatId, found.map(modelCard).join("\n\n"));
    }

    return send(env, chatId, "Не знаю такую команду. Вот что умею:", startKeyboard());
  } catch (error) {
    console.log("command error", command, error);
    return send(env, chatId, "Данные временно недоступны. Попробуй через минуту.");
  }
}

async function onCallback(query, env) {
  const chatId = query.message?.chat?.id;
  const messageId = query.message?.message_id;
  await tg(env, "answerCallbackQuery", { callback_query_id: query.id });
  if (!chatId || !messageId) return;

  const data = query.data || "";
  if (data === "x") return;

  const [kindTag, a, b] = data.split("|");

  try {
    if (kindTag === "t") {
      const board = await loadData(env, "leaderboard.json");
      const { text, page, pages } = renderTop(board, a, Number(b) || 1);
      await edit(env, chatId, messageId, text, topKeyboard(a, page, pages));
      return;
    }

    if (kindTag === "cmd" && a === "new") {
      const recent = await loadData(env, "recent.json");
      await edit(env, chatId, messageId, newText(recent), {
        inline_keyboard: [[{ text: "🏆 Рейтинг", callback_data: "t|all|1" }]],
      });
      return;
    }

    if (kindTag === "cmd" && a === "help") {
      await edit(env, chatId, messageId, helpText(), {
        inline_keyboard: [[{ text: "🏆 Рейтинг", callback_data: "t|all|1" }]],
      });
    }
  } catch (error) {
    console.log("callback error", data, error);
  }
}

/* ---------------------------------------------------------------- cron */

/**
 * Страховка от планировщика GitHub: раз в 10 минут проверяем, когда workflow
 * запускался в последний раз, и если давно — дёргаем его через API.
 * Работает только когда задан GH_TOKEN.
 */
async function dispatchGitHub(env) {
  const repo = env.GH_REPO || "mirkest/ai-news-bot";
  const headers = { "User-Agent": "ai-news-bot-cron", Accept: "application/vnd.github+json" };

  let lastRun = null;
  try {
    const response = await fetch(`https://api.github.com/repos/${repo}/actions/runs?per_page=1`, {
      headers,
      cf: { cacheTtl: 60 },
    });
    if (response.ok) {
      const data = await response.json();
      lastRun = data.workflow_runs?.[0]?.created_at ?? null;
    }
  } catch (error) {
    console.log("cron: история запусков недоступна", error);
  }

  if (lastRun && Date.now() - new Date(lastRun).getTime() < 8 * 60 * 1000) {
    return { skipped: true, reason: "свежий запуск", lastRun };
  }
  if (!env.GH_TOKEN) {
    return { skipped: true, reason: "не задан GH_TOKEN", lastRun };
  }

  const response = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/watch.yml/dispatches`,
    {
      method: "POST",
      headers: { ...headers, Authorization: `Bearer ${env.GH_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main" }),
    }
  );
  return { dispatched: response.status === 204, status: response.status, lastRun };
}

/* ---------------------------------------------------------------- вебхук */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return Response.json({ ok: true, service: "ai-news-bot" });
    }

    // Регистрация вебхука: /install?key=<INSTALL_KEY>
    if (request.method === "GET" && url.pathname === "/install") {
      if (!env.INSTALL_KEY || url.searchParams.get("key") !== env.INSTALL_KEY) {
        return new Response("forbidden", { status: 403 });
      }
      const result = await tg(env, "setWebhook", {
        url: `${url.origin}/tg/${env.WEBHOOK_SECRET}`,
        allowed_updates: ["message", "callback_query"],
        drop_pending_updates: true,
      });
      return Response.json(result);
    }

    // Ручная проверка планировщика: /cron?key=<INSTALL_KEY>
    if (request.method === "GET" && url.pathname === "/cron") {
      if (!env.INSTALL_KEY || url.searchParams.get("key") !== env.INSTALL_KEY) {
        return new Response("forbidden", { status: 403 });
      }
      return Response.json(await dispatchGitHub(env));
    }

    if (!env.WEBHOOK_SECRET) {
      return new Response("WEBHOOK_SECRET не задан", { status: 500 });
    }

    if (request.method === "POST" && url.pathname === `/tg/${env.WEBHOOK_SECRET}`) {
      const update = await request.json().catch(() => null);
      if (update) {
        ctx.waitUntil(
          (update.callback_query ? onCallback(update.callback_query, env) : onMessage(update.message || {}, env)).catch(
            (error) => console.log("update error", error)
          )
        );
      }
      return new Response("ok");
    }

    return new Response("not found", { status: 404 });
  },

  // Запускается по Cron Trigger из настроек воркера.
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatchGitHub(env));
  },
};
