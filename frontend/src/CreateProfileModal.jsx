import React, { useState } from 'react'

const RESOLUTION_PRESETS = {
  '1920 × 1080 (Full HD)': { width: 1920, height: 1080 },
  '2560 × 1440 (QHD)': { width: 2560, height: 1440 },
  '1366 × 768 (HD)': { width: 1366, height: 768 },
  '1440 × 900': { width: 1440, height: 900 },
  '1536 × 864': { width: 1536, height: 864 },
  '1280 × 720 (720p)': { width: 1280, height: 720 },
}

const GPU_PRESETS = {
  'NVIDIA RTX 3070': { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 (0x00002484) Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  'NVIDIA RTX 4070': { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 (0x00002786) Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  'AMD RX 6800 XT': { vendor: 'Google Inc. (AMD)', renderer: 'ANGLE (AMD, AMD Radeon RX 6800 XT (0x000073BF) Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  'Intel UHD 770': { vendor: 'Google Inc. (Intel)', renderer: 'ANGLE (Intel, Intel(R) UHD Graphics 770 (0x00004680) Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  'Apple M3 (macOS)': { vendor: 'Google Inc. (Apple)', renderer: 'ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)' },
}

const TAG_COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#a855f7', '#f97316', '#ec4899']

export default function CreateProfileModal({ nodeId, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: '', fingerprint_seed: '', proxy: '', timezone: '', locale: '',
    platform: 'windows', user_agent: '', screen_width: 1920, screen_height: 1080,
    gpu_vendor: '', gpu_renderer: '', hardware_concurrency: '',
    humanize: false, human_preset: 'default', headless: false,
    geoip: false, clipboard_sync: true, auto_launch: false,
    color_scheme: '', launch_args: [], notes: '', tags: []
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [tagColor, setTagColor] = useState('#6366f1')
  const [launchArgInput, setLaunchArgInput] = useState('')

  const set = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) return
    setSaving(true)
    setError('')
    const body = { name: form.name.trim() }
    if (form.fingerprint_seed) body.fingerprint_seed = parseInt(form.fingerprint_seed)
    if (form.proxy) body.proxy = form.proxy
    if (form.timezone) body.timezone = form.timezone
    if (form.locale) body.locale = form.locale
    if (form.platform) body.platform = form.platform
    if (form.user_agent) body.user_agent = form.user_agent
    body.screen_width = form.screen_width
    body.screen_height = form.screen_height
    if (form.gpu_vendor) body.gpu_vendor = form.gpu_vendor
    if (form.gpu_renderer) body.gpu_renderer = form.gpu_renderer
    if (form.hardware_concurrency) body.hardware_concurrency = parseInt(form.hardware_concurrency)
    body.humanize = form.humanize
    body.human_preset = form.human_preset
    body.headless = form.headless
    body.geoip = form.geoip
    body.clipboard_sync = form.clipboard_sync
    body.auto_launch = form.auto_launch
    if (form.color_scheme) body.color_scheme = form.color_scheme
    if (form.launch_args.length) body.launch_args = form.launch_args
    if (form.notes) body.notes = form.notes
    if (form.tags.length) body.tags = form.tags
    try {
      const res = await fetch(`/api/nodes/${nodeId}/profiles`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        setError(err.detail || `Failed (${res.status})`)
        setSaving(false)
        return
      }
    } catch (e) {
      setError('Network error')
      setSaving(false)
      return
    }
    setSaving(false)
    onCreated()
  }

  const applyGpuPreset = (name) => {
    const preset = GPU_PRESETS[name]
    if (preset) { set('gpu_vendor', preset.vendor); set('gpu_renderer', preset.renderer) }
  }

  const randomizeSeed = () => set('fingerprint_seed', String(Math.floor(Math.random() * 90000) + 10000))

  const currentResolution = Object.entries(RESOLUTION_PRESETS).find(
    ([, v]) => v.width === form.screen_width && v.height === form.screen_height
  )?.[0] ?? 'custom'

  const addTag = () => {
    const tag = tagInput.trim()
    if (!tag || form.tags.some(t => t.tag === tag)) return
    set('tags', [...form.tags, { tag, color: tagColor }])
    setTagInput('')
  }
  const removeTag = (tag) => set('tags', form.tags.filter(t => t.tag !== tag))

  const addLaunchArg = () => {
    const arg = launchArgInput.trim()
    if (!arg || form.launch_args.includes(arg)) return
    set('launch_args', [...form.launch_args, arg])
    setLaunchArgInput('')
  }
  const removeLaunchArg = (idx) => set('launch_args', form.launch_args.filter((_, i) => i !== idx))

  const inputCls = 'w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:border-blue-500/50 focus:outline-none transition-colors'
  const labelCls = 'block text-xs text-gray-400 mb-1.5'
  const sectionCls = 'space-y-4 pt-5 border-t border-gray-800/60'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-2xl max-h-[90vh] flex flex-col bg-gray-900 border border-gray-700 rounded-xl shadow-2xl" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 shrink-0">
          <h3 className="text-base font-medium text-gray-100">New Profile</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        {/* Form body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto px-6 py-5 space-y-6">

          {/* === Basic === */}
          <section className="space-y-4">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Basic</h4>
            <div>
              <label className={labelCls}>Profile Name</label>
              <input value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Amazon Seller #1" required className={inputCls} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>Platform</label>
                <select value={form.platform} onChange={e => set('platform', e.target.value)} className={inputCls}>
                  <option value="windows">Windows</option>
                  <option value="macos">macOS</option>
                  <option value="linux">Linux</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Fingerprint Seed</label>
                <div className="flex gap-2">
                  <input type="number" value={form.fingerprint_seed} onChange={e => set('fingerprint_seed', e.target.value)} placeholder="Auto (random)" className={inputCls} />
                  <button type="button" onClick={randomizeSeed} className="px-3 py-2 rounded-lg text-xs font-medium bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 transition-colors shrink-0">Random</button>
                </div>
              </div>
            </div>
          </section>

          {/* === Network === */}
          <section className={sectionCls}>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Network</h4>
            <div>
              <label className={labelCls}>Proxy</label>
              <input value={form.proxy} onChange={e => set('proxy', e.target.value)} placeholder="http://user:pass@host:port" className={inputCls} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>Timezone</label>
                <input value={form.timezone} onChange={e => set('timezone', e.target.value)} placeholder="America/New_York" className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Locale</label>
                <input value={form.locale} onChange={e => set('locale', e.target.value)} placeholder="en-US" className={inputCls} />
              </div>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.geoip} onChange={e => set('geoip', e.target.checked)} className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-800 text-blue-500" />
              <span className="text-xs text-gray-300">Auto-detect timezone/locale from proxy IP (GeoIP)</span>
            </label>
          </section>

          {/* === Hardware === */}
          <section className={sectionCls}>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Hardware</h4>
            <div>
              <label className={labelCls}>Screen Resolution</label>
              <select value={currentResolution} onChange={e => { const p = RESOLUTION_PRESETS[e.target.value]; if (p) { set('screen_width', p.width); set('screen_height', p.height) } }} className={inputCls}>
                {Object.keys(RESOLUTION_PRESETS).map(name => <option key={name} value={name}>{name}</option>)}
                <option value="custom">Custom</option>
              </select>
            </div>
            {currentResolution === 'custom' && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Width</label>
                  <input type="number" value={form.screen_width} onChange={e => set('screen_width', Number(e.target.value))} className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Height</label>
                  <input type="number" value={form.screen_height} onChange={e => set('screen_height', Number(e.target.value))} className={inputCls} />
                </div>
              </div>
            )}
            <div>
              <label className={labelCls}>Hardware Concurrency</label>
              <input type="number" value={form.hardware_concurrency} onChange={e => set('hardware_concurrency', e.target.value)} placeholder="Auto (from seed)" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>GPU Preset</label>
              <select defaultValue="" onChange={e => { if (e.target.value) applyGpuPreset(e.target.value) }} className={inputCls}>
                <option value="">Select preset...</option>
                {Object.keys(GPU_PRESETS).map(name => <option key={name} value={name}>{name}</option>)}
              </select>
            </div>
            <div>
              <label className={labelCls}>GPU Vendor</label>
              <input value={form.gpu_vendor} onChange={e => set('gpu_vendor', e.target.value)} placeholder="Auto (from seed)" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>GPU Renderer</label>
              <input value={form.gpu_renderer} onChange={e => set('gpu_renderer', e.target.value)} placeholder="Auto (from seed)" className={inputCls} />
            </div>
          </section>

          {/* === Behavior === */}
          <section className={sectionCls}>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Behavior</h4>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.humanize} onChange={e => set('humanize', e.target.checked)} className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-800 text-blue-500" />
              <span className="text-xs text-gray-300">Human-like mouse, keyboard, and scroll behavior</span>
            </label>
            {form.humanize && (
              <div>
                <label className={labelCls}>Human Preset</label>
                <select value={form.human_preset} onChange={e => set('human_preset', e.target.value)} className={inputCls}>
                  <option value="default">Default (normal speed)</option>
                  <option value="careful">Careful (slower, deliberate)</option>
                </select>
              </div>
            )}
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.clipboard_sync} onChange={e => set('clipboard_sync', e.target.checked)} className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-800 text-blue-500" />
              <span className="text-xs text-gray-300">Enable clipboard sync by default in VNC viewer</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.auto_launch} onChange={e => set('auto_launch', e.target.checked)} className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-800 text-blue-500" />
              <span className="text-xs text-gray-300">Launch automatically when container starts</span>
            </label>
            <div>
              <label className={labelCls}>Color Scheme</label>
              <select value={form.color_scheme} onChange={e => set('color_scheme', e.target.value)} className={inputCls}>
                <option value="">System default</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
                <option value="no-preference">No preference</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>User Agent</label>
              <input value={form.user_agent} onChange={e => set('user_agent', e.target.value)} placeholder="Auto (from binary)" className={inputCls} />
            </div>
          </section>

          {/* === Tags === */}
          <section className={sectionCls}>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Tags</h4>
            {form.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {form.tags.map(t => (
                  <span key={t.tag} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium text-white" style={{ backgroundColor: t.color }}>
                    {t.tag}
                    <button type="button" onClick={() => removeTag(t.tag)} className="hover:opacity-70">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1">
                {TAG_COLORS.map(c => (
                  <button key={c} type="button" onClick={() => setTagColor(c)}
                    className="w-4 h-4 rounded-full border-2 transition-transform"
                    style={{ backgroundColor: c, borderColor: tagColor === c ? '#fff' : 'transparent', transform: tagColor === c ? 'scale(1.2)' : undefined }} />
                ))}
              </div>
              <input value={tagInput} onChange={e => setTagInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTag() } }}
                placeholder="Add tag..." className={`flex-1 ${inputCls}`} />
              <button type="button" onClick={addTag} className="px-3 py-2 rounded-lg text-xs font-medium bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 transition-colors">Add</button>
            </div>
          </section>

          {/* === Launch Args === */}
          <section className={sectionCls}>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Launch Args</h4>
            <p className="text-[11px] text-gray-500">Custom Chromium flags passed at launch</p>
            {form.launch_args.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {form.launch_args.map((arg, idx) => (
                  <span key={idx} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono bg-gray-800 border border-gray-700 text-gray-300">
                    {arg}
                    <button type="button" onClick={() => removeLaunchArg(idx)} className="hover:opacity-70">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <input value={launchArgInput} onChange={e => setLaunchArgInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addLaunchArg() } }}
                placeholder="--load-extension=/data/extensions/ublock" className={`flex-1 ${inputCls}`} />
              <button type="button" onClick={addLaunchArg} className="px-3 py-2 rounded-lg text-xs font-medium bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 transition-colors">Add</button>
            </div>
          </section>

          {/* === Notes === */}
          <section className={sectionCls}>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Notes</h4>
            <textarea value={form.notes} onChange={e => set('notes', e.target.value)}
              placeholder="Optional notes about this profile..." rows={3}
              className={`${inputCls} resize-none`} />
          </section>
        </form>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-800 shrink-0">
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2 ml-auto">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:bg-white/5 transition-colors">Cancel</button>
            <button onClick={handleSubmit} disabled={saving || !form.name.trim()} className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50 active:scale-95">{saving ? 'Saving...' : 'Create'}</button>
          </div>
        </div>
      </div>
    </div>
  )
}
