import type { QaLog } from '../types'

interface Props {
  logs: QaLog[]
}

function time(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false })
}

export function AuditLog({ logs }: Props) {
  if (logs.length === 0) return null

  return (
    <section className="audit">
      <h3>审计日志（最近 {logs.length} 条）</h3>
      <table className="audit__table">
        <thead>
          <tr>
            <th>时间</th>
            <th>用户</th>
            <th>问题</th>
            <th>结果</th>
            <th>耗时</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id}>
              <td>{time(l.created_at)}</td>
              <td>{l.user_id}</td>
              <td className="audit__q">{l.question}</td>
              <td>
                <span className={`badge ${l.refused ? 'badge--warn' : 'badge--ok'}`}>
                  {l.refused ? '拒答' : '回答'}
                </span>
              </td>
              <td>{l.latency_ms} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
