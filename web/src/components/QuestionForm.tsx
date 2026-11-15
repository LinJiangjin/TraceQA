/** 提问表单：预设问题 + 自由输入，提交动作交给 App 的 ask() 处理。 */
import type { FormEvent } from 'react'

interface Props {
  question: string
  /** 请求进行中时禁用提交按钮 */
  loading: boolean
  onQuestionChange: (q: string) => void
  onSubmit: () => void
}

/**
 * 四个预设问题刻意覆盖三种典型场景：
 * 普通制度问答、HR 机密（普通员工应看不到）、调薪窗口（越权）、
 * 以及知识库里一定没有答案的天气问题（应触发拒答）。
 */
const PRESETS = [
  '年假需要提前几天申请？',
  '公司薪酬带宽是多少？P6 的上限是多少？',
  '调薪窗口期是什么时候？',
  '今天上海天气怎么样？',
]

export function QuestionForm({ question, loading, onQuestionChange, onSubmit }: Props) {
  // 阻止浏览器默认提交（会刷新页面），改为调用父组件的回调。
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
