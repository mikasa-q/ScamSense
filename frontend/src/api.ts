export interface Role { id: string; name: string; public_title: string }
export interface Session { id: string; stage: string; status: string; state_version: number; roles: Role[] }
export interface Message { id: string; role_id: string; sender: string; content: string }
export type Credentials = { id: string; token: string }
export type Saved = { key: string } | Credentials

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
