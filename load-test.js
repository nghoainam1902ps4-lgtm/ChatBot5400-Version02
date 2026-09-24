#!/usr/bin/env node
/**
 * Load test — ChatBot 5400 (Agribank Chi nhánh Lâm Đồng)
 * ============================================================================
 * Đo khả năng chịu tải của hệ thống với 2 chế độ và có ramp-up (tăng dần user).
 *
 * CHẾ ĐỘ (--mode):
 *   chat    (mặc định) Bắn đồng thời POST /api/chat/execute — đo cả LLM.
 *   backend           Bắn đồng thời GET /api/notebooks — đo sức thuần của
 *                     API + SurrealDB (không gọi LLM), để tách nút thắt.
 *
 * RAMP-UP (--ramp): chạy lần lượt nhiều mức tải rồi in bảng so sánh
 *   p95 / throughput / tỷ lệ lỗi theo từng mức, giúp tìm NGƯỠNG chịu tải.
 *
 * Luồng API thật (chat theo SESSION, không phải POST /notebooks/:id/chat):
 *   POST /api/auth/login    -> JWT { access_token }
 *   POST /api/users         -> (admin) tạo test1..testN nếu chưa có
 *   GET  /api/notebooks     -> lấy id 2 notebook (nếu không chỉ định)
 *   POST /api/chat/context  -> dựng context (toàn bộ tài liệu của notebook)
 *   POST /api/chat/sessions -> mỗi user 1 session/mức tải (setup, không tính giờ)
 *   POST /api/chat/execute  -> câu hỏi (PHẦN ĐƯỢC ĐO ở chế độ chat)
 *
 * Chỉ dùng `fetch` có sẵn trong Node >= 18 (không cần cài axios).
 *
 * ------------------------------ CÁCH DÙNG -----------------------------------
 * Tham số dòng lệnh (khỏi phải set biến môi trường — tiện cho Windows/PowerShell):
 *   --base-url=<url>            URL API           (mặc định http://localhost:5055)
 *   --admin-username=<tên>      admin             (mặc định admin)
 *   --admin-password=<mk>       mật khẩu admin    (mặc định admin)
 *   --test-password=<mk>        mk cho test1..N   (mặc định Test@12345)
 *   --users=<n>                 số user 1 mức     (mặc định 10)
 *   --ramp=5,10,20,30           chạy nhiều mức tải (ghi đè --users)
 *   --notebook-a=<id>           id Notebook A     (mặc định: tự lấy)
 *   --notebook-b=<id>           id Notebook B     (mặc định: tự lấy)
 *   --question="..."            câu hỏi chat
 *   --mode=chat|backend         chế độ           (mặc định chat)
 *   --timeout=<ms>              timeout/request   (mặc định 120000)
 *   --cooldown=<ms>             nghỉ giữa các mức (mặc định 3000)
 *   --help                      in trợ giúp
 * (Vẫn hỗ trợ biến môi trường cũ: BASE_URL, ADMIN_PASSWORD, TOTAL_USERS, ...)
 *
 * VÍ DỤ (PowerShell / CMD / bash đều chạy được — dùng tham số):
 *   node load-test.js --base-url=https://api.5491sotay.io.vn --admin-password=admin --users=10
 *   node load-test.js --base-url=https://api.5491sotay.io.vn --admin-password=admin --ramp=5,10,20,30
 *   node load-test.js --base-url=https://api.5491sotay.io.vn --admin-password=admin --mode=backend --ramp=10,25,50,100
 */

'use strict'

// --------------------------- Đọc tham số / env -------------------------------
function parseArgs(argv) {
  const out = {}
  for (const a of argv) {
    if (!a.startsWith('--')) continue
    const eq = a.indexOf('=')
    if (eq !== -1) out[a.slice(2, eq)] = a.slice(eq + 1)
    else out[a.slice(2)] = true // cờ boolean, ví dụ --help
  }
  return out
}
const ARGS = parseArgs(process.argv.slice(2))
const pick = (argKey, envKey, def) =>
  ARGS[argKey] !== undefined ? ARGS[argKey] : process.env[envKey] !== undefined ? process.env[envKey] : def

if (ARGS.help) {
  // In phần header hướng dẫn ở trên rồi thoát.
  console.log(require('fs').readFileSync(__filename, 'utf8').split('*/')[0].replace(/^\/\*+|^ \*?/gm, ''))
  process.exit(0)
}

const CFG = {
  baseUrl: String(pick('base-url', 'BASE_URL', 'http://localhost:5055')).replace(/\/$/, ''),
  adminUsername: String(pick('admin-username', 'ADMIN_USERNAME', 'admin')),
  adminPassword: String(pick('admin-password', 'ADMIN_PASSWORD', 'admin')),
  testPassword: String(pick('test-password', 'TEST_PASSWORD', 'Test@12345')),
  question: String(pick('question', 'QUESTION', 'Hãy tóm tắt các quy định chính trong sổ tay này.')),
  notebookA: String(pick('notebook-a', 'NOTEBOOK_A_ID', '')),
  notebookB: String(pick('notebook-b', 'NOTEBOOK_B_ID', '')),
  mode: String(pick('mode', 'MODE', 'chat')),
  timeoutMs: Number(pick('timeout', 'REQUEST_TIMEOUT_MS', 120000)),
  cooldownMs: Number(pick('cooldown', 'COOLDOWN_MS', 3000)),
}

// Danh sách mức tải: --ramp="5,10,20" ghi đè --users/TOTAL_USERS.
const rampRaw = pick('ramp', 'RAMP', '')
const singleUsers = Number(pick('users', 'TOTAL_USERS', 10))
const LEVELS = rampRaw
  ? String(rampRaw)
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => Number.isInteger(n) && n > 0)
  : [singleUsers]
if (LEVELS.length === 0) {
  console.error('Danh sách --ramp không hợp lệ. Ví dụ: --ramp=5,10,20,30')
  process.exit(2)
}
const MAX_USERS = Math.max(...LEVELS)

// ------------------------------- Tiện ích ------------------------------------
const nowMs = () => Number(process.hrtime.bigint() / 1000000n)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const log = (...a) => console.log(...a)

/** fetch JSON có timeout; trả về { ok, status, data, error }. */
async function apiFetch(path, { method = 'GET', token, body } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), CFG.timeoutMs)
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    const res = await fetch(`${CFG.baseUrl}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
    let data = null
    const text = await res.text()
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = text
    }
    return { ok: res.ok, status: res.status, data }
  } catch (err) {
    return { ok: false, status: 0, error: err?.name === 'AbortError' ? 'timeout' : String(err) }
  } finally {
    clearTimeout(timer)
  }
}

async function login(username, password) {
  const r = await apiFetch('/api/auth/login', { method: 'POST', body: { username, password } })
  return r.ok && r.data?.access_token ? r.data.access_token : null
}

function percentile(sortedAsc, p) {
  if (sortedAsc.length === 0) return 0
  const idx = Math.min(sortedAsc.length - 1, Math.ceil((p / 100) * sortedAsc.length) - 1)
  return sortedAsc[Math.max(0, idx)]
}

function shortErr(data) {
  if (!data) return 'no body'
  if (typeof data === 'string') return data.slice(0, 120)
  if (data.detail) return String(data.detail).slice(0, 120)
  return JSON.stringify(data).slice(0, 120)
}

/** Tính các chỉ số thống kê từ mảng kết quả request của một mức tải. */
function summarize(level, results, totalMs) {
  const ok = results.filter((r) => r.ok)
  const times = results.map((r) => r.ms).sort((a, b) => a - b)
  const sum = times.reduce((s, t) => s + t, 0)
  return {
    level,
    sent: results.length,
    ok: ok.length,
    fail: results.length - ok.length,
    totalMs,
    min: times[0] || 0,
    avg: times.length ? Math.round(sum / times.length) : 0,
    p50: percentile(times, 50),
    p90: percentile(times, 90),
    p95: percentile(times, 95),
    max: times[times.length - 1] || 0,
    rps: totalMs > 0 ? results.length / (totalMs / 1000) : 0,
    results,
  }
}

// --------------------------------- Setup -------------------------------------
async function loginAdmin() {
  log(`\n[Setup] Đăng nhập admin (${CFG.adminUsername}) tại ${CFG.baseUrl} ...`)
  const token = await login(CFG.adminUsername, CFG.adminPassword)
  if (!token) {
    throw new Error('Không đăng nhập được admin. Kiểm tra --base-url / --admin-username / --admin-password.')
  }
  log('        -> OK')
  return token
}

async function ensureUsersAndLogin(adminToken, n) {
  log(`\n[Setup] Chuẩn bị & đăng nhập ${n} tài khoản test ...`)
  const users = []
  for (let i = 1; i <= n; i++) {
    const username = `test${i}`
    let token = await login(username, CFG.testPassword)
    if (!token) {
      const created = await apiFetch('/api/users', {
        method: 'POST',
        token: adminToken,
        body: { username, password: CFG.testPassword, role: 'user', name: username },
      })
      if (!created.ok && created.status !== 409) {
        log(`        ! Tạo ${username} lỗi (status ${created.status}) — vẫn thử đăng nhập.`)
      }
      token = await login(username, CFG.testPassword)
    }
    if (!token) {
      throw new Error(
        `Không lấy được token cho ${username}. Nếu user đã tồn tại với mật khẩu khác, ` +
          `dùng --test-password cho đúng hoặc xoá user cũ.`,
      )
    }
    users.push({ username, token })
  }
  log(`        -> Đã có ${users.length} token.`)
  return users
}

async function resolveNotebooks(adminToken) {
  log('\n[Setup] Xác định 2 Notebook (A/B) ...')
  if (CFG.notebookA && CFG.notebookB) {
    log(`        -> Dùng id chỉ định: A=${CFG.notebookA}  B=${CFG.notebookB}`)
    return { a: CFG.notebookA, b: CFG.notebookB }
  }
  const r = await apiFetch('/api/notebooks', { token: adminToken })
  if (!r.ok || !Array.isArray(r.data)) throw new Error(`Không lấy được danh sách notebook (status ${r.status}).`)
  if (r.data.length < 2) {
    throw new Error(
      `Cần ít nhất 2 notebook trong DB (hiện có ${r.data.length}). ` +
        `Tạo trước 2 notebook hoặc dùng --notebook-a / --notebook-b.`,
    )
  }
  const a = r.data[0].id
  const b = r.data[1].id
  log(`        -> Tự chọn: A=${a} ("${r.data[0].name}") | B=${b} ("${r.data[1].name}")`)
  return { a, b }
}

async function buildContext(token, notebookId) {
  const r = await apiFetch('/api/chat/context', {
    method: 'POST',
    token,
    body: { notebook_id: notebookId, context_config: {} }, // {} -> gồm tất cả nguồn/ghi chú
  })
  if (!r.ok) {
    log(`        ! Dựng context cho ${notebookId} lỗi (status ${r.status}) — dùng context rỗng.`)
    return {}
  }
  return r.data?.context ?? {}
}

// ------------------------------ Một mức tải ----------------------------------
/** Một request được đo thời gian, tuỳ chế độ. */
async function oneRequest(u) {
  const start = nowMs()
  let r
  if (CFG.mode === 'backend') {
    // Không gọi LLM: đọc danh sách notebook (có truy vấn đếm ở SurrealDB).
    r = await apiFetch('/api/notebooks', { token: u.token })
  } else {
    r = await apiFetch('/api/chat/execute', {
      method: 'POST',
      token: u.token,
      body: { session_id: u.sessionId, message: CFG.question, context: u.context },
    })
  }
  const ms = nowMs() - start
  return { username: u.username, notebookId: u.notebookId, ok: r.ok, status: r.status, ms, error: r.error || (r.ok ? null : shortErr(r.data)) }
}

/** Chuẩn bị (không tính giờ) rồi bắn đồng thời `count` request. */
async function runLevel(allUsers, count, notebooks, contextCache) {
  const users = allUsers.slice(0, count)
  const half = Math.ceil(count / 2)
  users.forEach((u, i) => {
    u.notebookId = i < half ? notebooks.a : notebooks.b
  })

  if (CFG.mode === 'chat') {
    // Tạo session MỚI cho mỗi user ở mỗi mức (tránh lịch sử chat dồn lại làm sai số).
    for (const u of users) {
      if (!contextCache.has(u.notebookId)) {
        contextCache.set(u.notebookId, await buildContext(u.token, u.notebookId))
      }
      u.context = contextCache.get(u.notebookId)
      const r = await apiFetch('/api/chat/sessions', {
        method: 'POST',
        token: u.token,
        body: { notebook_id: u.notebookId, title: `LoadTest ${u.username}` },
      })
      if (!r.ok || !r.data?.id) throw new Error(`Tạo session cho ${u.username} lỗi (status ${r.status}).`)
      u.sessionId = r.data.id
    }
  }

  const t0 = nowMs()
  const results = await Promise.all(users.map((u) => oneRequest(u)))
  const totalMs = nowMs() - t0
  return summarize(count, results, totalMs)
}

// -------------------------------- Báo cáo ------------------------------------
function printLevelDetail(s) {
  const endpoint = CFG.mode === 'backend' ? 'GET /api/notebooks' : 'POST /api/chat/execute'
  log('\n' + '='.repeat(72))
  log(`KẾT QUẢ — mức ${s.level} user đồng thời  (chế độ: ${CFG.mode}, endpoint: ${endpoint})`)
  log('='.repeat(72))
  log(`Thành công / thất bại : ${s.ok} / ${s.fail}`)
  log(`Tổng thời gian        : ${s.totalMs} ms (${(s.totalMs / 1000).toFixed(2)} s)`)
  log(`Response time (ms)    : min ${s.min} | avg ${s.avg} | max ${s.max}`)
  log(`Phân vị (ms)          : p50 ${s.p50} | p90 ${s.p90} | p95 ${s.p95}`)
  log(`Throughput            : ${s.rps.toFixed(2)} req/s`)

  log('\nChi tiết từng request:')
  log('  #  user      notebook                         status  time(ms)  kết quả')
  log('  ' + '-'.repeat(76))
  s.results
    .slice()
    .sort((a, b) => a.username.localeCompare(b.username, undefined, { numeric: true }))
    .forEach((r, i) => {
      const nb = String(r.notebookId || '-').padEnd(32).slice(0, 32)
      log(
        `  ${String(i + 1).padStart(2)}  ${r.username.padEnd(8)}  ${nb}  ${String(r.status).padStart(6)}  ` +
          `${String(r.ms).padStart(8)}  ${r.ok ? 'OK' : 'FAIL: ' + (r.error || '')}`,
      )
    })
  if (s.fail) {
    const byErr = new Map()
    for (const f of s.results.filter((r) => !r.ok)) {
      const key = `${f.status} ${f.error || ''}`.trim()
      byErr.set(key, (byErr.get(key) || 0) + 1)
    }
    log('\nTóm tắt lỗi:')
    for (const [k, v] of byErr) log(`  - (${v}x) ${k}`)
  }
}

function printComparison(summaries) {
  log('\n' + '#'.repeat(72))
  log('BẢNG SO SÁNH THEO MỨC TẢI' + (CFG.mode === 'backend' ? '  (backend — không LLM)' : '  (chat — có LLM)'))
  log('#'.repeat(72))
  log(' Mức | Gửi |  OK | Lỗi | %Lỗi  | avg(ms) | p50(ms) | p95(ms) | max(ms) | req/s')
  log('-----+-----+-----+-----+-------+---------+---------+---------+---------+-------')
  for (const s of summaries) {
    const pctFail = s.sent ? ((s.fail / s.sent) * 100).toFixed(0) : '0'
    log(
      ` ${String(s.level).padStart(3)} | ${String(s.sent).padStart(3)} | ${String(s.ok).padStart(3)} | ` +
        `${String(s.fail).padStart(3)} | ${(pctFail + '%').padStart(5)} | ${String(s.avg).padStart(7)} | ` +
        `${String(s.p50).padStart(7)} | ${String(s.p95).padStart(7)} | ${String(s.max).padStart(7)} | ` +
        `${s.rps.toFixed(2).padStart(5)}`,
    )
  }
  log('#'.repeat(72))

  // Gợi ý ngưỡng: mức cuối cùng còn 0 lỗi.
  const lastClean = [...summaries].reverse().find((s) => s.fail === 0)
  const firstFail = summaries.find((s) => s.fail > 0)
  log('\nNhận xét nhanh:')
  if (lastClean) log(`  • Chịu tốt (0 lỗi) tới mức ${lastClean.level} user, p95 ≈ ${lastClean.p95} ms, ${lastClean.rps.toFixed(2)} req/s.`)
  if (firstFail) log(`  • Bắt đầu có lỗi từ mức ${firstFail.level} user (${firstFail.fail}/${firstFail.sent} lỗi) — đây là vùng ngưỡng cần lưu ý.`)
  if (!firstFail) log('  • Chưa thấy lỗi ở mọi mức đã thử — có thể đẩy --ramp lên cao hơn để tìm ngưỡng.')
  log('')
}

// --------------------------------- Main --------------------------------------
async function main() {
  log('ChatBot 5400 — Load Test')
  log(`Chế độ: ${CFG.mode} | Các mức tải: ${LEVELS.join(', ')} | ${CFG.mode === 'chat' ? `câu hỏi="${CFG.question}"` : ''}`)

  const adminToken = await loginAdmin()
  const users = await ensureUsersAndLogin(adminToken, MAX_USERS)
  const notebooks = await resolveNotebooks(adminToken)
  const contextCache = new Map()

  const summaries = []
  for (let i = 0; i < LEVELS.length; i++) {
    const level = LEVELS[i]
    log(`\n>>> Đang chạy mức ${level} user đồng thời (${i + 1}/${LEVELS.length}) ...`)
    const s = await runLevel(users, level, notebooks, contextCache)
    summaries.push(s)
    // Ở chế độ 1 mức: in chi tiết đầy đủ. Ở ramp: in tóm tắt 1 dòng cho gọn.
    if (LEVELS.length === 1) {
      printLevelDetail(s)
    } else {
      log(
        `    -> OK ${s.ok}/${s.sent}, lỗi ${s.fail}, avg ${s.avg}ms, p95 ${s.p95}ms, ${s.rps.toFixed(2)} req/s`,
      )
      if (i < LEVELS.length - 1 && CFG.cooldownMs > 0) {
        log(`    (nghỉ ${CFG.cooldownMs}ms cho server hạ nhiệt trước mức tiếp theo)`)
        await sleep(CFG.cooldownMs)
      }
    }
  }

  if (LEVELS.length > 1) printComparison(summaries)

  const anyFail = summaries.some((s) => s.fail > 0)
  process.exit(anyFail ? 1 : 0)
}

main().catch((err) => {
  console.error('\n[LỖI KHÔNG XỬ LÝ]', err?.message || err)
  process.exit(2)
})
