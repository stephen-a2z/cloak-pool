import React, { useState, useEffect } from 'react'

export default function DefaultsEditor() {
  const [defaults, setDefaults] = useState(null)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({})
  const [saving, setSaving] = useState(false)

  const fetchDefaults = async () => {
    try {
      const r = await fetch('/api/defaults')
      if (r.ok) {
        const data = await r.json()
        setDefaults(data)
        setForm(data)
      }
    } catch (e) {}
  }

  useEffect(() => { fetchDefaults() }, [])

  const handleSave = async () => {
    setSaving(true)
    const body = {}
    for (const key of ['proxy', 'timezone', 'locale', 'platform', 'user_agent', 'screen_width', 'screen_height', 'notes']) {
      if (form[key] !== defaults[key]) body[key] = form[key] || null
    }
    if (Object.keys(body).length) {
      if (body.screen_width) body.screen_width = parseInt(body.screen_width)
      if (body.screen_height) body.screen_height = parseInt(body.screen_height)
      await fetch('/api/defaults', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      await fetchDefaults()
    }
    setEditing(false)
    setSaving(false)
  }

  if (!defaults) return null

  const field = (label, key, type = 'text') => (
    <div>
      <label className="block text-[10px] uppercase tracking-wide text-gray-500 mb-1">{label}</label>
      {editing ? (
        <input type={type} value={form[key] || ''} onChange={e => setForm({ ...form, [key]: e.target.value })}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm focus:border-blue-500/50 focus:outline-none transition-colors" />
      ) : (
        <div className="text-sm text-gray-300 py-1.5">{defaults[key] || <span className="text-gray-600">-</span>}</div>
      )}
    </div>
  )

  return (
    <section className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800/80">
        <div>
          <h2 className="text-sm font-medium text-gray-200">全局默认值</h2>
          <p className="text-[11px] text-gray-500 mt-0.5">Consumer acquire 未传值的字段将使用此配置</p>
        </div>
        {!editing ? (
          <button onClick={() => setEditing(true)} className="px-3 py-1.5 rounded-lg text-xs font-medium text-blue-400 hover:bg-blue-400/10 transition-colors">Edit</button>
        ) : (
          <div className="flex gap-2">
            <button onClick={() => { setEditing(false); setForm(defaults) }} className="px-3 py-1.5 rounded-lg text-xs text-gray-400 hover:bg-white/5 transition-colors">Cancel</button>
            <button onClick={handleSave} disabled={saving} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50 active:scale-95">{saving ? '...' : 'Save'}</button>
          </div>
        )}
      </div>
      <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-4">
        {field('Proxy', 'proxy')}
        {field('Timezone', 'timezone')}
        {field('Locale', 'locale')}
        <div>
          <label className="block text-[10px] uppercase tracking-wide text-gray-500 mb-1">Platform</label>
          {editing ? (
            <select value={form.platform || 'windows'} onChange={e => setForm({ ...form, platform: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm focus:border-blue-500/50 focus:outline-none">
              <option value="windows">Windows</option>
              <option value="macos">macOS</option>
              <option value="linux">Linux</option>
            </select>
          ) : (
            <div className="text-sm text-gray-300 py-1.5">{defaults.platform}</div>
          )}
        </div>
        {field('User Agent', 'user_agent')}
        {field('Screen Width', 'screen_width', 'number')}
        {field('Screen Height', 'screen_height', 'number')}
        {field('Notes', 'notes')}
      </div>
    </section>
  )
}
