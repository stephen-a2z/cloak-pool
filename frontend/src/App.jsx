import React, { useState, useEffect, useCallback } from 'react'
import VncViewer from './VncViewer'
import DefaultsEditor from './DefaultsEditor'

function StatCard({ label, value, max, accent = 'blue' }) {
  const colors = { blue: 'from-blue-500/10 to-transparent border-blue-500/20', green: 'from-emerald-500/10 to-transparent border-emerald-500/20', amber: 'from-amber-500/10 to-transparent border-amber-500/20' }
  const textColors = { blue: 'text-blue-400', green: 'text-emerald-400', amber: 'text-amber-400' }
  return (
    <div className={`relative overflow-hidden rounded-xl border bg-gradient-to-br p-5 ${colors[accent]}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-gray-400">{label}</div>
      <div className={`text-3xl font-semibold mt-2 tabular-nums ${textColors[accent]}`}>
        {value}{max !== undefined && <span className="text-gray-600 text-xl font-normal"> / {max}</span>}
      </div>
    </div>
  )
}

function Skeleton({ rows = 3 }) {
  return Array.from({ length: rows }).map((_, i) => (
    <tr key={i} className="border-t border-gray-800"><td colSpan="6" className="px-3 py-3"><div className="h-4 bg-gray-800 rounded animate-pulse" style={{ width: `${60 + Math.random() * 30}%` }}></div></td></tr>
  ))
}

function SessionRow({ session, onStop, onView, stopping }) {
  const mins = Math.floor(session.ttl_remaining / 60)
  const secs = session.ttl_remaining % 60
  const urgent = session.ttl_remaining < 120
  return (
    <tr className="border-t border-gray-800/60 transition-colors hover:bg-white/[0.02]">
      <td className="px-4 py-2.5 font-mono text-xs text-gray-300">{session.consumer_id.slice(0, 16)}</td>
      <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{session.profile_id.slice(0, 8)}</td>
      <td className="px-4 py-2.5 text-sm">{session.node_id}</td>
      <td className="px-4 py-2.5">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>active
        </span>
      </td>
      <td className={`px-4 py-2.5 font-mono text-sm tabular-nums ${urgent ? 'text-amber-400' : 'text-gray-300'}`}>{mins}:{secs.toString().padStart(2, '0')}</td>
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-1">
          <button onClick={() => onView(session)} className="px-2 py-1 rounded text-xs font-medium text-blue-400 hover:bg-blue-400/10 transition-colors">View</button>
          <a href={`/view/${session.session_id}?token=${session.view_token || ''}`} target="_blank" rel="noopener" className="px-2 py-1 rounded text-xs text-gray-500 hover:bg-white/5 transition-colors">Open</a>
          <button onClick={() => onStop(session.session_id)} disabled={stopping === session.session_id} className="px-2 py-1 rounded text-xs font-medium text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-40 active:scale-95">
            {stopping === session.session_id ? '...' : 'Stop'}
          </button>
        </div>
      </td>
    </tr>
  )
}

function MetricPill({ label, value }) {
  const color = value > 80 ? 'text-red-400' : value > 60 ? 'text-amber-400' : 'text-gray-400'
  return (
    <div className="text-center">
      <div className={`text-[11px] font-mono tabular-nums ${color}`}>{Math.round(value)}%</div>
      <div className="text-[9px] text-gray-600 uppercase">{label}</div>
    </div>
  )
}

function NodeCard({ node, onViewSession }) {
  const [expanded, setExpanded] = useState(false)
  const [profiles, setProfiles] = useState([])
  const [loading, setLoading] = useState(false)
  const [acting, setActing] = useState(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')

  const pct = node.max_sessions > 0 ? (node.current_sessions / node.max_sessions) * 100 : 0
  const barColor = pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-amber-500' : 'bg-emerald-500'

  const fetchProfiles = async () => {
    setLoading(true)
    try {
      const r = await fetch(`/api/nodes/${node.node_id}/profiles`)
      if (r.ok) setProfiles(await r.json())
    } catch (e) {}
    setLoading(false)
  }

  const handleToggle = () => {
    if (!expanded) fetchProfiles()
    setExpanded(!expanded)
  }

  const handleAction = async (profileId, action) => {
    setActing(profileId)
    await fetch(`/api/nodes/${node.node_id}/profiles/${profileId}/${action}`, { method: 'POST' })
    await fetchProfiles()
    setActing(null)
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!newName.trim()) return
    setActing('new')
    await fetch(`/api/nodes/${node.node_id}/profiles`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName.trim() })
    })
    setNewName('')
    setCreating(false)
    setActing(null)
    await fetchProfiles()
  }

  return (
    <div className={`rounded-xl border transition-colors ${expanded ? 'border-gray-600 bg-gray-800/80' : 'border-gray-800 bg-gray-900/50 hover:border-gray-700'}`}>
      <div className="p-4 flex items-center gap-3 cursor-pointer select-none" onClick={handleToggle}>
        <div className={`w-2.5 h-2.5 rounded-full ${node.online ? 'bg-emerald-400' : 'bg-red-400'} ${node.online ? 'shadow-[0_0_6px_rgba(52,211,153,0.4)]' : ''}`}></div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{node.node_id}</div>
          <div className="text-xs text-gray-500 truncate">{node.url}</div>
        </div>
        <div className="hidden sm:flex items-center gap-3 shrink-0">
          <MetricPill label="CPU" value={node.cpu_percent} />
          <MetricPill label="MEM" value={node.memory_percent} />
          <MetricPill label="DISK" value={node.disk_percent} />
        </div>
        <div className="w-28 shrink-0">
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }}></div>
          </div>
          <div className="text-[10px] text-gray-500 mt-1 text-right tabular-nums">{node.current_sessions} / {node.max_sessions}</div>
        </div>
        <svg className={`w-4 h-4 text-gray-500 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
      </div>
      {expanded && (
        <div className="border-t border-gray-800 px-4 pb-4 pt-3">
          {loading && (
            <div className="flex items-center gap-2 text-xs text-gray-500"><div className="w-3 h-3 border-2 border-gray-600 border-t-gray-400 rounded-full animate-spin"></div>Loading profiles...</div>
          )}
          {!loading && profiles.length === 0 && (
            <div className="text-xs text-gray-600 py-2">No profiles on this node</div>
          )}
          {!loading && profiles.length > 0 && (
            <div className="space-y-1.5">
              {profiles.map(p => (
                <div key={p.id} className="flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-white/[0.02] transition-colors">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${p.status === 'running' ? 'bg-emerald-400' : 'bg-gray-600'}`}></span>
                  <span className="text-sm truncate flex-1">{p.name}</span>
                  <span className="font-mono text-[10px] text-gray-600 shrink-0">{p.id?.slice(0, 8)}</span>
                  <div className="shrink-0">
                    {p.status === 'running' ? (
                      <div className="flex gap-1">
                        <button onClick={(e) => { e.stopPropagation(); onViewSession({ _browser: true, node_id: node.node_id, profile_id: p.id, name: p.name }) }} className="px-2 py-0.5 rounded text-[11px] font-medium text-blue-400 hover:bg-blue-400/10 transition-colors">View</button>
                        <button onClick={(e) => { e.stopPropagation(); handleAction(p.id, 'stop') }} disabled={acting === p.id} className="px-2 py-0.5 rounded text-[11px] font-medium text-red-400 hover:bg-red-400/10 transition-colors disabled:opacity-40 active:scale-95">{acting === p.id ? '...' : 'Stop'}</button>
                      </div>
                    ) : (
                      <button onClick={(e) => { e.stopPropagation(); handleAction(p.id, 'launch') }} disabled={acting === p.id} className="px-2 py-0.5 rounded text-[11px] font-medium text-emerald-400 hover:bg-emerald-400/10 transition-colors disabled:opacity-40 active:scale-95">{acting === p.id ? '...' : 'Launch'}</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {!loading && (
            <div className="mt-3 pt-2 border-t border-gray-800/50">
              {!creating ? (
                <button onClick={() => setCreating(true)} className="px-3 py-1.5 rounded-lg text-[11px] font-medium text-gray-400 hover:bg-white/5 hover:text-gray-200 transition-colors">+ New Profile</button>
              ) : (
                <form onSubmit={handleCreate} className="flex items-center gap-2">
                  <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Profile name" autoFocus
                    className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs focus:border-blue-500/50 focus:outline-none" />
                  <button type="submit" disabled={acting === 'new'} className="px-3 py-1.5 rounded-lg text-[11px] font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50 active:scale-95">{acting === 'new' ? '...' : 'Create'}</button>
                  <button type="button" onClick={() => { setCreating(false); setNewName('') }} className="px-2 py-1.5 rounded-lg text-[11px] text-gray-500 hover:bg-white/5">Cancel</button>
                </form>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function VncOverlay({ session, onClose }) {
  let wsUrl, title
  if (session._browser) {
    wsUrl = `/api/view/browser/${session.node_id}/${session.profile_id}/vnc`
    title = `${session.name || session.profile_id?.slice(0, 8)} on ${session.node_id}`
  } else {
    wsUrl = `/api/view/${session.session_id}/vnc?token=${session.view_token || ''}`
    title = `${session.consumer_id?.slice(0, 16)}... on ${session.node_id}`
  }
  return <VncViewer wsUrl={wsUrl} title={title} onClose={onClose} />
}

function SectionHeader({ title, count, children }) {
  return (
    <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800/80">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-medium text-gray-200">{title}</h2>
        {count !== undefined && <span className="text-[10px] font-mono bg-gray-800 text-gray-400 px-1.5 py-0.5 rounded-md">{count}</span>}
      </div>
      {children}
    </div>
  )
}

export default function App() {
  const [stats, setStats] = useState(null)
  const [sessions, setSessions] = useState([])
  const [running, setRunning] = useState([])
  const [viewing, setViewing] = useState(null)
  const [stopping, setStopping] = useState(null)
  const [loaded, setLoaded] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, sessionsRes, runningRes] = await Promise.all([
        fetch('/api/stats'), fetch('/api/sessions'), fetch('/api/sessions/running')
      ])
      if (statsRes.ok) setStats(await statsRes.json())
      if (sessionsRes.ok) setSessions(await sessionsRes.json())
      if (runningRes.ok) setRunning(await runningRes.json())
    } catch (e) {}
    setLoaded(true)
  }, [])

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 3000)
    return () => clearInterval(id)
  }, [fetchData])

  const handleStop = async (sessionId) => {
    setStopping(sessionId)
    await fetch(`/api/sessions/${sessionId}/stop`, { method: 'POST' })
    setStopping(null)
    fetchData()
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-gray-100">
      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-gray-800/60 bg-[#0a0a0f]/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-md bg-blue-500/20 border border-blue-500/30 flex items-center justify-center">
              <span className="text-blue-400 text-xs font-bold">P</span>
            </div>
            <span className="text-sm font-semibold tracking-tight">Browser Pool</span>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            {stats && <span className="tabular-nums">{stats.running_sessions} active</span>}
            <span className={`w-2 h-2 rounded-full ${stats?.nodes?.some(n => n.online) ? 'bg-emerald-400' : 'bg-gray-600'}`}></span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard label="使用中 Sessions" value={sessions.length} max={stats?.max_global_sessions} accent="blue" />
          <StatCard label="运行中 Browsers" value={running.length} accent="green" />
          <StatCard label="在线节点" value={stats?.nodes?.filter(n => n.online).length ?? 0} accent="amber" />
        </div>

        {/* Sessions */}
        <section className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
          <SectionHeader title="使用中 Sessions" count={sessions.length} />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-gray-500 bg-gray-900/50">
                  <th className="px-4 py-2.5 text-left font-medium">Consumer</th>
                  <th className="px-4 py-2.5 text-left font-medium">Profile</th>
                  <th className="px-4 py-2.5 text-left font-medium">Node</th>
                  <th className="px-4 py-2.5 text-left font-medium">Status</th>
                  <th className="px-4 py-2.5 text-left font-medium">TTL</th>
                  <th className="px-4 py-2.5 text-left font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {!loaded && <Skeleton rows={2} />}
                {loaded && sessions.map(s => (
                  <SessionRow key={s.session_id} session={s} onStop={handleStop} onView={setViewing} stopping={stopping} />
                ))}
                {loaded && sessions.length === 0 && (
                  <tr><td colSpan="6" className="px-4 py-10 text-center text-gray-600 text-sm">无使用中的 session</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Running browsers */}
        <section className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
          <SectionHeader title="运行中 Browsers" count={running.length} />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-gray-500 bg-gray-900/50">
                  <th className="px-4 py-2.5 text-left font-medium">Profile</th>
                  <th className="px-4 py-2.5 text-left font-medium">Name</th>
                  <th className="px-4 py-2.5 text-left font-medium">Node</th>
                  <th className="px-4 py-2.5 text-left font-medium">Status</th>
                  <th className="px-4 py-2.5 text-left font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {!loaded && <Skeleton rows={2} />}
                {loaded && running.map((r, i) => (
                  <tr key={i} className="border-t border-gray-800/60 transition-colors hover:bg-white/[0.02]">
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-400">{r.profile_id?.slice(0, 8)}</td>
                    <td className="px-4 py-2.5 text-sm">{r.name}</td>
                    <td className="px-4 py-2.5 text-sm text-gray-400">{r.node_id}</td>
                    <td className="px-4 py-2.5">
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>running
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1">
                        <button onClick={() => setViewing({ _browser: true, node_id: r.node_id, profile_id: r.profile_id, name: r.name })} className="px-2 py-1 rounded text-xs font-medium text-blue-400 hover:bg-blue-400/10 transition-colors">View</button>
                        <a href={`/view/browser/${r.node_id}/${r.profile_id}`} target="_blank" rel="noopener" className="px-2 py-1 rounded text-xs text-gray-500 hover:bg-white/5 transition-colors">Open</a>
                      </div>
                    </td>
                  </tr>
                ))}
                {loaded && running.length === 0 && (
                  <tr><td colSpan="5" className="px-4 py-10 text-center text-gray-600 text-sm">无运行中的浏览器</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Global Defaults */}
        <DefaultsEditor />

        {/* Nodes */}
        <section>
          <h2 className="text-sm font-medium text-gray-200 mb-3">Nodes</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {(stats?.nodes ?? []).map(n => <NodeCard key={n.node_id} node={n} onViewSession={setViewing} />)}
            {loaded && (!stats?.nodes || stats.nodes.length === 0) && (
              <div className="col-span-2 text-center py-10 text-gray-600 text-sm">等待节点注册...</div>
            )}
          </div>
        </section>
      </main>

      {/* VNC Viewer overlay */}
      {viewing && <VncOverlay session={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}
