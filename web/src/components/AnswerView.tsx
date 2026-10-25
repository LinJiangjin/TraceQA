import type { QAResponse } from '../types'

interface Props {
  result: QAResponse
  activeCitation: number | null
  onCite: (index: number) => void
}

/** 把 "[1]"、"[2]" 这类引用标记渲染成可点击的上标。 */
function renderAnswer(answer: string, onCite: (index: number) => void) {
  return answer.split(/(\[\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/)
    if (!m) return <span key={i}>{part}</span>
    const n = Number(m[1])
    return (
      <button key={i} type="button" className="cite" onClick={() => onCite(n)}>
        [{n}]
      </button>
    )
  })
}

export function AnswerView({ result, activeCitation, onCite }: Props) {
  return (
    <section className={`answer ${result.refused ? 'answer--refused' : ''}`}>
      <header className="answer__head">
        <span className={`badge ${result.refused ? 'badge--warn' : 'badge--ok'}`}>
          {result.refused ? '已拒答' : '已回答'}
        </span>
        <span className="answer__stats">
          {result.latency_ms} ms · confidence {result.confidence.toFixed(2)} · 引用{' '}
          {result.citations.length} 处
        </span>
      </header>

      <p className="answer__text">{renderAnswer(result.answer, onCite)}</p>

      {result.refused && (
        <p className="answer__note">
          上下文闸门判定「最高分段落不足以支撑答案」，因此不调用 LLM 生成。
          {activeCitation === null && ' 这正是 RAG 最容易翻车的地方：不知道却硬编。'}
        </p>
      )}
    </section>
  )
}
