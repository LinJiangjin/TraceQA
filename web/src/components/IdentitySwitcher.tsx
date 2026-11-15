/**
 * 身份切换器：在三个演示用户之间切换，用于直观展示权限隔离效果。
 *
 * 切换只改变 App 里的 identity 状态，不直接发请求；
 * 由 App 的 effect 负责重新拉 /me 并清空上一次答案。
 */
import { IDENTITIES, type Identity, type MeResponse } from '../types'

interface Props {
  /** 当前选中的用户 ID */
  value: string
  /** /api/v1/me 的回显，null 表示尚未加载 */
  me: MeResponse | null
  onChange: (id: string) => void
}

export function IdentitySwitcher({ value, me, onChange }: Props) {
  return (
    <div className="identity">
      <div className="identity__buttons">
        {IDENTITIES.map((it: Identity) => (
          <button
            key={it.id}
            type="button"
            className={`chip ${it.id === value ? 'chip--active' : ''}`}
            onClick={() => onChange(it.id)}
          >
            {it.label}
            <span className="chip__hint">{it.hint}</span>
          </button>
        ))}
      </div>
      {/* 展示服务端返回的真实 tenant / roles，便于核对 ACL 过滤的依据。 */}
      {me && (
        <p className="identity__meta">
          当前身份 <strong>{me.display_name}</strong> · tenant <code>{me.tenant_id}</code> · roles{' '}
          <code>{me.roles.join(', ')}</code>
        </p>
      )}
    </div>
  )
}
