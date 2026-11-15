/**
 * 单页控制台的根组件：负责状态编排，本身不包含任何问答逻辑。
 *
 * 数据流向：QuestionForm 触发 ask() -> api.askQuestion() -> /api/v1/qa
 *        -> 结果交给 AnswerView + SourceList 展示，同时刷新 AuditLog。
 * 身份切换（IdentitySwitcher）会清空上一次结果，避免把上一个身份的答案
 * 误当成新身份可见的内容。
 */
import { useCallback, useEffect, useState } from 'react'
import { AnswerView } from './components/AnswerView'
import { AuditLog } from './components/AuditLog'
import { IdentitySwitcher } from './components/IdentitySwitcher'
import { QuestionForm } from './components/QuestionForm'
import { SourceList } from './components/SourceList'
import { askQuestion, fetchMe, fetchQaLogs } from './api'
import type { MeResponse, QaLog, QAResponse } from './types'

export default function App() {
  // identity：当前演示用户 ID，随每个请求放进 X-User-Id 头。
  const [identity, setIdentity] = useState('u-alice')
  const [me, setMe] = useState<MeResponse | null>(null)
  const [question, setQuestion] = useState('年假需要提前几天申请？')
  const [result, setResult] = useState<QAResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // 当前被点击的引用编号，用于联动高亮对应的召回段落；null 表示未选中。
  const [activeCitation, setActiveCitation] = useState<number | null>(null)
  const [logs, setLogs] = useState<QaLog[]>([])

  // 切换身份后重新拉 /me 并清空上一次结果：不同身份看到的东西本来就不一样。
  useEffect(() => {
    setResult(null)
    setError(null)
    setActiveCitation(null)
    fetchMe(identity)
      .then(setMe)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [identity])

  // 每次产生新答案（包括拒答）后刷新审计日志，让「谁问了什么」立即可见。
  useEffect(() => {
    fetchQaLogs()
      .then(setLogs)
      .catch(() => setLogs([]))
  }, [result])

  /** 提交问题：统一处理 loading / error / 引用选中态，失败时保留错误文案。 */
  const ask = useCallback(async () => {
    const q = question.trim()
    if (!q) return
    setLoading(true)
    setError(null)
    setResult(null)
    setActiveCitation(null)
    try {
      const r = await askQuestion(identity, q)
      setResult(r)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [identity, question])

  return (
    <div className="app">
      <header className="app__header">
        <div>
          <h1>TraceQA</h1>
          <p className="app__sub">带溯源、带权限的企业知识问答 · 权限在检索层前置过滤</p>
        </div>
        <IdentitySwitcher value={identity} me={me} onChange={setIdentity} />
      </header>

      <main className="app__main">
        <QuestionForm
          question={question}
          loading={loading}
          onQuestionChange={setQuestion}
          onSubmit={ask}
        />

        {error && <p className="error">请求失败：{error}</p>}
        {loading && <p className="loading">检索 + 精排 + 生成中…</p>}
        {/* AnswerView 的引用点击与 SourceList 的高亮靠 activeCitation 联动。 */}
        {result && (
          <>
            <AnswerView result={result} activeCitation={activeCitation} onCite={setActiveCitation} />
            <section className="panel">
              <h3>召回段落（{result.sources.length}）</h3>
              <SourceList sources={result.sources} activeCitation={activeCitation} />
            </section>
          </>
        )}
        <AuditLog logs={logs} />
      </main>
    </div>
  )
}
