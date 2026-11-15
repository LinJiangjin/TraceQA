/** 与后端 app/api/qa.py、app/main.py 的返回结构一一对应。 */

/** 一条召回/引用段落；index 与答案里的 [n] 编号一致（1-based）。 */
export interface Source {
  index: number
  chunk_id: string
  title: string
  source_uri: string
  content: string
  rerank_score: number
}

/** POST /api/v1/qa 的响应。 */
export interface QAResponse {
  question: string
  answer: string
  /** 答案里实际使用的引用编号列表 */
  citations: number[]
  /** 引用编号对应的 chunk_id，用于溯源核对 */
  cited_chunk_ids: string[]
  /** true 表示上下文闸门判定证据不足、未调用 LLM */
  refused: boolean
  confidence: number
  /** 送进 LLM 上下文的全部段落（含未被引用的） */
  sources: Source[]
  latency_ms: number
}

/** GET /api/v1/me 的响应：当前演示身份的租户与角色。 */
export interface MeResponse {
  id: string
  email: string
  display_name: string
  tenant_id: string
  roles: string[]
  auth_source: string
}

/** GET /api/v1/admin/qa-logs 的单条审计记录。 */
export interface QaLog {
  id: string
  user_id: string
  tenant_id: string
  question: string
  answer: string
  refused: boolean
  latency_ms: number
  created_at: string | null
}

/** 演示身份。三个用户是刻意设计的对照：普通员工 / HR / 另一租户。 */
export interface Identity {
  id: string
  label: string
  hint: string
}

/** 与 app/seed.py 的 DEMO_USERS 保持一致，切换它即可演示权限差异。 */
export const IDENTITIES: Identity[] = [
  { id: 'u-alice', label: 'Alice · 普通员工', hint: 'roles: employee' },
  { id: 'u-hr', label: 'HR · 人力资源', hint: 'roles: employee, hr' },
  { id: 'u-bob', label: 'Bob · 另一租户', hint: 'tenant: globex' },
]
