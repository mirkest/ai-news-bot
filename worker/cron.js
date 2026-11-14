/**
 * Будильник для GitHub Actions.
 *
 * Раз в 10 минут Cloudflare проверяет, когда workflow запускался в последний
 * раз, и если давно — запускает его сам через GitHub API. Нужен на случай,
 * когда штатный cron GitHub молчит (у новых репозиториев бывает).
 *
 * Переменные окружения:
 *   GH_TOKEN — токен GitHub с правом Actions: Read and write (secret)
 */

const REPO = "mirkest/ai-news-bot";
const WORKFLOW = "watch.yml";
const FRESH_MS = 8 * 60 * 1000;

const HEADERS = {
  "User-Agent": "ai-news-bot-cron",
  Accept: "application/vnd.github+json",
};

async function lastRunAt() {
  try {
    const response = await fetch(`https://api.github.com/repos/${REPO}/actions/runs?per_page=1`, {
      headers: HEADERS,
      cf: { cacheTtl: 60 },
    });
    if (!response.ok) return null;
    const data = await response.json();
    return data.workflow_runs?.[0]?.created_at ?? null;
  } catch (error) {
    console.log("cron: история запусков недоступна", error);
    return null;
  }
}

async function dispatch(env) {
  const lastRun = await lastRunAt();
  if (lastRun && Date.now() - new Date(lastRun).getTime() < FRESH_MS) {
    return { skipped: true, reason: "свежий запуск", lastRun };
  }
  if (!env.GH_TOKEN) {
    return { skipped: true, reason: "не задан GH_TOKEN", lastRun };
  }

  const response = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: { ...HEADERS, Authorization: `Bearer ${env.GH_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main" }),
    }
  );
  return { dispatched: response.status === 204, status: response.status, lastRun };
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },

  // Ручная проверка: обычный GET на адрес воркера.
  async fetch(request, env) {
    return Response.json(await dispatch(env));
  },
};
