/**
 * 召回段落列表：展示送进 LLM 上下文的原文，并支持引用联动定位。
 *
 * 点击答案里的 [n] 后，App 更新 activeCitation，这里把对应段落滚动到视野中央
 * 并加上高亮样式 —— 这就是「答案可溯源」在前端的落点。
 */
import { useEffect, useRef } from 'react'
import type { Source } from '../types'

interface Props {
  sources: Source[]
  /** 当前选中的引用编号；null 表示不高亮 */
  activeCitation: number | null
}

export function SourceList({ sources, activeCitation }: Props) {
  // 用对象缓存每个编号对应的 DOM 节点，避免为每个段落单独创建 ref。
  const refs = useRef<Record<number, HTMLLIElement | null>>({})

  useEffect(() => {
    if (activeCitation === null) return
    refs.current[activeCitation]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeCitation])

  // 权限过滤后无可见文档时，给出明确提示，而不是显示空白列表。
  if (sources.length === 0) {
    return <p className="empty">没有召回任何段落（权限过滤后为空，或检索无结果）。</p>
  }

  return (
    <ol className="sources">
      {sources.map((s) => (
        <li
          key={s.chunk_id}
          ref={(el) => {
            refs.current[s.index] = el
          }}
          className={`source ${activeCitation === s.index ? 'source--active' : ''}`}
        >
          <div className="source__head">
            <span className="source__index">[{s.index}]</span>
            <span className="source__title">{s.title}</span>
            <span className="source__score">rerank {s.rerank_score.toFixed(4)}</span>
          </div>
          {/* source_uri 是入库时的文件路径，content 是切分后的段落原文。 */}
          <p className="source__uri">{s.source_uri}</p>
          <p className="source__content">{s.content}</p>
        </li>
      ))}
    </ol>
  )
}
