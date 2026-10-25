import type { MeResponse, QAResponse, QaLog } from './types'

/**
 * 演示身份通过 X-User-Id 头传递。
 * 后端只在非 production 环境开这个通道（见 app/security.py），
 * 生产要换成 Bearer token，那时这里改成 Authorization 头即可。
 */

async function request<T>(path: string, userId: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId,
      ...(init?.headers ?? {}),
    },
  })

  if (!resp.ok) {
    const detail = await resp.text().catch(() => '')
    throw new Error(`${resp.status} ${resp.statusText}${detail ? ` — ${detail.slice(0, 200)}` : ''}`)
  }
  return (await resp.json()) as T
}

export function fetchMe(userId: string): Promise<MeResponse> {
  return request<MeResponse>('/api/v1/me', userId)
}

export function askQuestion(userId: string, question: string): Promise<QAResponse> {
  return request<QAResponse>('/api/v1/qa', userId, {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}

export function fetchQaLogs(limit = 8): Promise<QaLog[]> {
  return request<QaLog[]>(`/api/v1/admin/qa-logs?limit=${limit}`, 'u-alice')
}
