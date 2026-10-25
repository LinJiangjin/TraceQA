import { IDENTITIES, type Identity, type MeResponse } from '../types'

interface Props {
  value: string
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
      {me && (
        <p className="identity__meta">
          当前身份 <strong>{me.display_name}</strong> · tenant <code>{me.tenant_id}</code> · roles{' '}
          <code>{me.roles.join(', ')}</code>
        </p>
      )}
    </div>
  )
}
