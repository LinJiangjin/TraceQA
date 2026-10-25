/** 与后端 app/api/qa.py、app/main.py 的返回结构一一对应。 */

export interface Source {
  index: number
  chunk_id: string
  title: string
  source_uri: string
  content: string
  rerank_score: number
}

export interface QAResponse {
  question: string
  answer: string
  citations: number[]
  cited_chunk_ids: string[]
  refused: boolean
  confidence: number
  sources: Source[]
  latency_ms: number
}

export interface MeResponse {
  id: string
  email: string
  display_name: string
  tenant_id: string
  roles: string[]
  auth_source: string
}

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

export const IDENTITIES: Identity[] = [
  { id: 'u-alice', label: 'Alice · 普通员工', hint: 'roles: employee' },
  { id: 'u-hr', label: 'HR · 人力资源', hint: 'roles: employee, hr' },
  { id: 'u-bob', label: 'Bob · 另一租户', hint: 'tenant: globex' },
]
