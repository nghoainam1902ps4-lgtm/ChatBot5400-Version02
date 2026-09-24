#!/usr/bin/env node
/**
 * Load test — ChatBot 5400 (Agribank Chi nhánh Lâm Đồng)
 * ------------------------------------------------------------------
 * Kịch bản: N user gửi tin nhắn chat ĐỒNG THỜI vào 2 Notebook.
 *   - User nửa đầu  -> Notebook A
 *   - User nửa sau  -> Notebook B
 *
 * Luồng API thật của hệ thống (chat theo SESSION, không phải
 * POST /notebooks/:id/chat):
 *   1. POST /api/auth/login      -> lấy JWT  { access_token }
 *   2. POST /api/users           -> (admin) tạo user test1..testN nếu chưa có
 *   3. GET  /api/notebooks       -> lấy id 2 notebook (nếu không hardcode)
 *   4. POST /api/chat/context    -> dựng context (toàn bộ tài liệu của notebook)
 *   5. POST /api/chat/sessions   -> mỗi user tạo 1 session gắn với notebook
 *   6. POST /api/chat/execute    -> BẮN ĐỒNG THỜI câu hỏi (phần được đo tải)
 *
 * Chỉ dùng `fetch` có sẵn trong Node >= 18 (không cần cài axios).
 *
 * Cấu hình qua biến môi trường (đều có mặc định):
 *   BASE_URL          (mặc định http://localhost:5055)
 *   ADMIN_USERNAME    (mặc định admin)
 *   ADMIN_PASSWORD    (mặc định admin)
 *   TOTAL_USERS       (mặc định 20 -> 10 user/notebook; đặt 10 cho kịch bản 10 user)
 *   TEST_PASSWORD     (mặc định Test@12345 — mật khẩu cho test1..testN)
 *   NOTEBOOK_A_ID     (tuỳ chọn; nếu bỏ trống sẽ tự lấy notebook đầu tiên)
 *   NOTEBOOK_B_ID     (tuỳ chọn; nếu bỏ trống sẽ tự lấy notebook thứ hai)
 *   QUESTION          (câu hỏi gửi vào chat)
 *   REQUEST_TIMEOUT_MS(mặc định 120000 — chat gọi LLM nên có thể chậm)
 *
 * Ví dụ chạy với hệ thống trên VPS:
 *   BASE_URL=https://api.5491sotay.io.vn ADMIN_PASSWORD='***' node load-test.js
 */

'use strict'

// ----------------------------- Cấu hình --------------------------------------
const BASE_URL = (process.env.BASE_URL || 'http://localhost:5055').replace(/\/$/, '')
const ADMIN_USERNAME = process.env.ADMIN_USERNAME || 'admin'
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin'
const TOTAL_USERS = Number(process.env.TOTAL_USERS || 20)
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'Test@12345'
const QUESTION =
  process.env.QUESTION || 'Hãy tóm tắt các quy định chính trong sổ tay này.'
const REQUEST_TIMEOUT_MS = Number(process.env.REQUEST_TIMEOUT_MS || 120000)

// Notebook IDs — hardcode ở đây hoặc để trống để tự động lấy 2 notebook đầu tiên.
let NOTEBOOK_A_ID = process.env.NOTEBOOK_A_ID || ''
let NOTEBOOK_B_ID = process.env.NOTEBOOK_B_ID || ''

// ----------------------------- Tiện ích --------------------------------------
const nowMs = () => Number(process.hrtime.bigint() / 1000000n)

/** fetch JSON có timeout; trả về { ok, status, data, error }. */
async function apiFetch(path, { method = 'GET', token, body } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
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
  const r = await apiFetch('/api/auth/login', {
    method: 'POST',
    body: { username, password },
  })
  if (r.ok && r.data?.access_token) return r.data.access_token
  return null
}

// Thống kê phân vị (percentile) trên mảng thời gian phản hồi (ms).
function percentile(sortedAsc, p) {
  if (sortedAsc.length === 0) return 0
  const idx = Math.min(sortedAsc.length - 1, Math.ceil((p / 100) * sortedAsc.length) - 1)
  return sortedAsc[Math.max(0, idx)]
}

function log(...a) {
  console.log(...a)
}

// ----------------------------- Các bước --------------------------------------

/** Đăng nhập admin (bắt buộc để tạo user & liệt kê notebook). */
async function loginAdmin() {
  log(`\n[1/5] Đăng nhập admin (${ADMIN_USERNAME}) tại ${BASE_URL} ...`)
  const token = await login(ADMIN_USERNAME, ADMIN_PASSWORD)
  if (!token) {
    throw new Error(
      `Không đăng nhập được admin. Kiểm tra BASE_URL / ADMIN_USERNAME / ADMIN_PASSWORD.`,
    )
  }
  log('      -> OK')
  return token
}

/** Tạo test1..testN nếu chưa tồn tại (bỏ qua nếu đã có), rồi đăng nhập lấy token. */
async function ensureUsersAndLogin(adminToken) {
  log(`\n[2/5] Chuẩn bị & đăng nhập ${TOTAL_USERS} tài khoản test ...`)
  const users = []
  for (let i = 1; i <= TOTAL_USERS; i++) {
    const username = `test${i}`
    // Thử đăng nhập trước; nếu chưa có thì tạo mới rồi đăng nhập lại.
    let token = await login(username, TEST_PASSWORD)
    if (!token) {
      const created = await apiFetch('/api/users', {
        method: 'POST',
        token: adminToken,
        body: { username, password: TEST_PASSWORD, role: 'user', name: username },
      })
      if (!created.ok && created.status !== 409) {
        // 409/400: có thể user đã tồn tại với mật khẩu khác -> vẫn thử login.
        log(`      ! Tạo ${username} lỗi (status ${created.status}) — vẫn thử đăng nhập.`)
      }
      token = await login(username, TEST_PASSWORD)
    }
    if (!token) {
      throw new Error(
        `Không lấy được token cho ${username}. Nếu user đã tồn tại với mật khẩu khác, ` +
          `đặt TEST_PASSWORD cho đúng hoặc xoá user cũ.`,
      )
    }
    users.push({ username, token })
  }
  log(`      -> Đã có ${users.length} token.`)
  return users
}

/** Lấy 2 notebook ID (hardcode qua env, hoặc tự lấy 2 notebook đầu tiên). */
async function resolveNotebooks(adminToken) {
  log('\n[3/5] Xác định 2 Notebook (A/B) ...')
  if (NOTEBOOK_A_ID && NOTEBOOK_B_ID) {
    log(`      -> Dùng ID hardcode: A=${NOTEBOOK_A_ID}  B=${NOTEBOOK_B_ID}`)
    return { a: NOTEBOOK_A_ID, b: NOTEBOOK_B_ID }
  }
  const r = await apiFetch('/api/notebooks', { token: adminToken })
  if (!r.ok || !Array.isArray(r.data)) {
    throw new Error(`Không lấy được danh sách notebook (status ${r.status}).`)
  }
  if (r.data.length < 2) {
    throw new Error(
      `Cần ít nhất 2 notebook trong DB (hiện có ${r.data.length}). ` +
        `Tạo trước 2 notebook (mỗi cái 10 tài liệu) hoặc đặt NOTEBOOK_A_ID/NOTEBOOK_B_ID.`,
    )
  }
  const a = r.data[0].id
  const b = r.data[1].id
  log(
    `      -> Tự chọn: A=${a} ("${r.data[0].name}", ${r.data[0].source_count} nguồn) | ` +
      `B=${b} ("${r.data[1].name}", ${r.data[1].source_count} nguồn)`,
  )
  return { a, b }
}

/** Dựng context (toàn bộ tài liệu của notebook) — làm 1 lần/notebook, KHÔNG tính vào thời gian tải. */
async function buildContext(token, notebookId) {
  const r = await apiFetch('/api/chat/context', {
    method: 'POST',
    token,
    body: { notebook_id: notebookId, context_config: {} }, // {} -> gồm tất cả nguồn/ghi chú
  })
  if (!r.ok) {
    log(`      ! Dựng context cho ${notebookId} lỗi (status ${r.status}) — dùng context rỗng.`)
    return {}
  }
  return r.data?.context ?? {}
}

/** Mỗi user tạo 1 session gắn với notebook của mình (setup, không tính giờ). */
async function createSessions(users, assignment) {
  log(`\n[4/5] Tạo session chat cho từng user & dựng context 2 notebook ...`)
  const contextCache = new Map()
  for (const u of users) {
    const notebookId = assignment.get(u.username)
    if (!contextCache.has(notebookId)) {
      contextCache.set(notebookId, await buildContext(u.token, notebookId))
    }
    const r = await apiFetch('/api/chat/sessions', {
      method: 'POST',
      token: u.token,
      body: { notebook_id: notebookId, title: `LoadTest ${u.username}` },
    })
    if (!r.ok || !r.data?.id) {
      throw new Error(`Tạo session cho ${u.username} lỗi (status ${r.status}).`)
    }
    u.sessionId = r.data.id
    u.notebookId = notebookId
    u.context = contextCache.get(notebookId)
  }
  log(`      -> Đã tạo ${users.length} session.`)
}

/** Một request chat có đo thời gian. */
async function chatOnce(u) {
  const start = nowMs()
  const r = await apiFetch('/api/chat/execute', {
    method: 'POST',
    token: u.token,
    body: { session_id: u.sessionId, message: QUESTION, context: u.context },
  })
  const ms = nowMs() - start
  return {
    username: u.username,
    notebookId: u.notebookId,
    ok: r.ok,
    status: r.status,
    ms,
    error: r.error || (r.ok ? null : shortErr(r.data)),
  }
}

function shortErr(data) {
  if (!data) return 'no body'
  if (typeof data === 'string') return data.slice(0, 120)
  if (data.detail) return String(data.detail).slice(0, 120)
  return JSON.stringify(data).slice(0, 120)
}

// ----------------------------- Báo cáo ---------------------------------------
function report(results, totalMs) {
  const ok = results.filter((r) => r.ok)
  const fail = results.filter((r) => !r.ok)
  const times = results.map((r) => r.ms).sort((a, b) => a - b)
  const sum = times.reduce((s, t) => s + t, 0)
  const avg = times.length ? sum / times.length : 0

  log('\n' + '='.repeat(64))
  log('KẾT QUẢ LOAD TEST')
  log('='.repeat(64))
  log(`Endpoint chat     : POST /api/chat/execute`)
  log(`Tổng request      : ${results.length} (đồng thời)`)
  log(`Thành công        : ${ok.length}`)
  log(`Thất bại          : ${fail.length}`)
  log(`Tổng thời gian    : ${totalMs} ms (${(totalMs / 1000).toFixed(2)} s)`)
  if (times.length) {
    log(`Response time     : min ${times[0]} ms | avg ${avg.toFixed(0)} ms | max ${times[times.length - 1]} ms`)
    log(`Phân vị           : p50 ${percentile(times, 50)} ms | p90 ${percentile(times, 90)} ms | p95 ${percentile(times, 95)} ms`)
  }
  if (totalMs > 0) {
    log(`Throughput        : ${(results.length / (totalMs / 1000)).toFixed(2)} req/s`)
  }

  log('\nChi tiết từng request:')
  log('  #  user      notebook                         status   time(ms)  kết quả')
  log('  ' + '-'.repeat(78))
  results
    .slice()
    .sort((a, b) => a.username.localeCompare(b.username, undefined, { numeric: true }))
    .forEach((r, i) => {
      const nb = String(r.notebookId || '').padEnd(32).slice(0, 32)
      const st = String(r.status).padStart(6)
      const tm = String(r.ms).padStart(8)
      const res = r.ok ? 'OK' : `FAIL: ${r.error || ''}`
      log(`  ${String(i + 1).padStart(2)}  ${r.username.padEnd(8)}  ${nb}  ${st}  ${tm}  ${res}`)
    })

  if (fail.length) {
    log('\nTóm tắt lỗi:')
    const byErr = new Map()
    for (const f of fail) {
      const key = `${f.status} ${f.error || ''}`.trim()
      byErr.set(key, (byErr.get(key) || 0) + 1)
    }
    for (const [k, v] of byErr) log(`  - (${v}x) ${k}`)
  }
  log('='.repeat(64) + '\n')
}

// ----------------------------- Main ------------------------------------------
async function main() {
  log('ChatBot 5400 — Load Test')
  log(`Cấu hình: TOTAL_USERS=${TOTAL_USERS}, câu hỏi="${QUESTION}"`)

  const adminToken = await loginAdmin()
  const users = await ensureUsersAndLogin(adminToken)
  const { a, b } = await resolveNotebooks(adminToken)

  // Phân bổ: nửa đầu -> Notebook A, nửa sau -> Notebook B.
  const half = Math.ceil(users.length / 2)
  const assignment = new Map()
  users.forEach((u, idx) => assignment.set(u.username, idx < half ? a : b))
  log(`      -> Phân bổ: ${half} user -> Notebook A, ${users.length - half} user -> Notebook B`)

  await createSessions(users, assignment)

  // ---- Phần được đo: bắn ĐỒNG THỜI toàn bộ request chat ----
  log(`\n[5/5] Bắn ĐỒNG THỜI ${users.length} request chat (Promise.all) ...`)
  const t0 = nowMs()
  const results = await Promise.all(users.map((u) => chatOnce(u)))
  const totalMs = nowMs() - t0

  report(results, totalMs)

  // Thoát với mã lỗi nếu có request thất bại (tiện cho CI).
  const failed = results.filter((r) => !r.ok).length
  process.exit(failed > 0 ? 1 : 0)
}

main().catch((err) => {
  console.error('\n[LỖI KHÔNG XỬ LÝ]', err?.message || err)
  process.exit(2)
})
