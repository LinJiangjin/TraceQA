/**
 * 后端 HTTP 请求的统一封装。
 *
 * 演示身份通过 X-User-Id 头传递。
 * 后端只在非 production 环境开这个通道（见 app/security.py），
 * 生产要换成 Bearer token，那时这里改成 Authorization 头即可。
 *
 * 所有路径都用相对路径（/api/...），由 Vite dev server 代理到后端；
 * 生产部署时换成 nginx 同域反向代理，前端无需感知后端地址。
 */
import type { MeResponse, QAResponse, QaLog } from './types'

/**
 * 通用请求函数：附带演示身份头、统一抛错、统一解析 JSON。
 *
 * @param path 相对路径，例如 /api/v1/qa
 * @param userId 演示用户 ID，写入 X-User-Id
 * @param init 额外的 fetch 配置（method / body / headers）
 * @throws Error 响应非 2xx 时抛出，消息里带上状态码与后端 detail 的前 200 字符
 */
async function request<T>(path: string, userId: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId,
      // 放在展开之后：允许调用方覆盖默认头。
      ...(init?.headers ?? {}),
    },
  })

  if (!resp.ok) {
    const detail = await resp.text().catch(() => '')
    throw new Error(`${resp.status} ${resp.statusText}${detail ? ` — ${detail.slice(0, 200)}` : ''}`)
  }
  return (await resp.json()) as T
}

/** 取当前身份信息（租户、角色、凭据来源），用于页面顶部的身份展示。 */
export function fetchMe(userId: string): Promise<MeResponse> {
  return request<MeResponse>('/api/v1/me', userId)
}

/** 发起一次问答，返回答案、引用编号与召回段落。 */
export function askQuestion(userId: string, question: string): Promise<QAResponse> {
  return request<QAResponse>('/api/v1/qa', userId, {
    method: 'POST',
    body: JSON.stringify({ question }),
  })
}

/**
 * 取最近若干条问答审计记录。
 *
 * 这个接口是全局日志、不按身份过滤，因此固定借用 u-alice 通过鉴权即可；
 * 生产环境应改为带管理员权限的接口。
 */
export function fetchQaLogs(limit = 8): Promise<QaLog[]> {
  return request<QaLog[]>(`/api/v1/admin/qa-logs?limit=${limit}`, 'u-alice')
}
