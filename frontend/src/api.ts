export interface Role { id: string; name: string; public_title: string }
export interface Session { id: string; stage: string; status: string; state_version: number; roles: Role[] }
export interface Message { id: string; role_id: string; sender: string; content: string; reply_mode?: 'preset' | 'model' | 'fallback' }
export type Credentials = { id: string; token: string }
export type Saved = { key: string; notice?: string } | Credentials

export const root = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(root + path, init)
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))).detail
    throw new Error(typeof detail === 'string' ? detail : '请求失败，请重试。')
  }
  return res.json()
}

export function auth(c: Credentials) {
  return { Authorization: 'Bearer ' + c.token }
}

export async function streamReply(c: Credentials, role: string, content: string, version: number,
                                  key: string, onText: (text: string) => void, replyTo?: string) {
  const res = await fetch(root + '/sessions/' + c.id + '/messages', {
    method: 'POST', headers: { ...auth(c), 'Content-Type': 'application/json', 'Idempotency-Key': key },
    body: JSON.stringify({ role_id: role, content, expected_version: version, reply_to: replyTo }),
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || '发送失败，请重试。')
  if (!res.body) throw new Error('未收到回复。')
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = '', complete = false
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += value
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() || ''
      for (const frame of frames) {
        const lines = frame.split(/\r?\n/)
        const event = lines.find(s => s.startsWith('event:'))?.slice(6).trim()
        const json = lines.filter(s => s.startsWith('data:')).map(s => s.slice(5).trimStart()).join('\n')
        if (event === 'delta') onText(JSON.parse(json).text)
        if (event === 'complete') complete = true
      }
    }
  } finally { reader.releaseLock() }
  if (!complete) throw new Error('回复传输中断，请核对私聊记录。')
}
