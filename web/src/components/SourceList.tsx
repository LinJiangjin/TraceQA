import { useEffect, useRef } from 'react'
import type { Source } from '../types'

interface Props {
  sources: Source[]
  activeCitation: number | null
}

export function SourceList({ sources, activeCitation }: Props) {
  const refs = useRef<Record<number, HTMLLIElement | null>>({})

  useEffect(() => {
    if (activeCitation === null) return
    refs.current[activeCitation]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeCitation])

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
          <p className="source__uri">{s.source_uri}</p>
          <p className="source__content">{s.content}</p>
        </li>
      ))}
    </ol>
  )
}
