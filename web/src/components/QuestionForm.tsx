import type { FormEvent } from 'react'

interface Props {
  question: string
  loading: boolean
  onQuestionChange: (q: string) => void
  onSubmit: () => void
}

const PRESETS = [
  '年假需要提前几天申请？',
  '公司薪酬带宽是多少？P6 的上限是多少？',
  '调薪窗口期是什么时候？',
  '今天上海天气怎么样？',
]

export function QuestionForm({ question, loading, onQuestionChange, onSubmit }: Props) {
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <form className="ask" onSubmit={submit}>
      <div className="ask__presets">
        {PRESETS.map((p) => (
          <button key={p} type="button" className="preset" onClick={() => onQuestionChange(p)}>
            {p}
          </button>
        ))}
      </div>
      <textarea
        className="ask__input"
        rows={3}
        placeholder="输入问题，例如：年假需要提前几天申请？"
        value={question}
        onChange={(e) => onQuestionChange(e.target.value)}
      />
      <div className="ask__actions">
        <button type="submit" className="btn btn--primary" disabled={loading || !question.trim()}>
          {loading ? '检索中…' : '提问'}
        </button>
        <span className="ask__tip">答案里的 [1] [2] 可点击，会高亮对应原文</span>
      </div>
    </form>
  )
}
