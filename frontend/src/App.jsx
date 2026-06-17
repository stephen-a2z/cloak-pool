import React, { useState, useEffect } from 'react'
import VncViewer from './VncViewer'
import ProfileManager from './ProfileManager'

function StatCard({ label, value, max }) {
  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <div className="text-sm text-gray-400">{label}</div>
      <div className="text-2xl font-bold mt-1">
        {value}{max !== undefined && <span className="text-gray-500 text-lg"> / {max}</span>}
      </div>
    </div>
  )
}

function SessionRow({ session, onStop, onView }) {
  const mins = Math.floor(session.ttl_remaining / 60)
  const secs = session.ttl_remaining % 60
  return (
    <tr className="border-t border-gray-700 hover:bg-gray-800/50">
      <td className="px-3 py-2 font-mono text-xs">{session.consumer_id.slice(0, 12)}...</td>
      <td className="px-3 py-2 font-mono text-xs">{session.profile_id.slice(0, 8)}...</td>
      <td className="px-3 py-2">{session.node_id}</td>
      <td className="px-3 py-2">
        <span className="inline-block w-2 h-2 rounded-full bg-green-400 mr-2"></span>
        {session.status}
      </td>
      <td className="px-3 py-2 font-mono">{mins}:{secs.toString().padStart(2, '0')}</td>
      <td className="px-3 py-2 space-x-2">
        <button onClick={() => onView(session)} className="text-blue-400 hover:text-blue-300 text-sm">View</button>
        <a href={`/view/${session.session_id}?token=${session.view_token || ''}`} target="_blank" className="text-gray-400 hover:text-gray-300 text-sm">↗ Open</a>
        <button onClick={() => onStop(session.session_id)} className="text-red-400 hover:text-red-300 text-sm">Stop</button>
      </td>
    </tr>
  )
}

function NodeCard({ node, onViewSession }) {
  const [expanded, setExpanded] = useState(false)
  const [profiles, setProfiles] = useState([])
  const [loading, setLoading] = useState(false)

  const pct = node.max_sessions > 0 ? (node.current_sessions / node.max_sessions) * 100 : 0

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

  const handleLaunch = async (profileId) => {
    await fetch(`/api/nodes/${node.node_id}/profiles/${profileId}/launch`, { method: 'POST' })
    fetchProfiles()
  }

  const handleStop = async (profileId) => {
    await fetch(`/api/nodes/${node.node_id}/profiles/${profileId}/stop`, { method: 'POST' })
    fetchProfiles()
  }

  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700">
      <div className="p-3 flex items-center gap-3 cursor-pointer hover:bg-gray-750" onClick={handleToggle}>
        <span className={`w-2 h-2 rounded-full ${node.online ? 'bg-green-400' : 'bg-red-400'}`}></span>
        <div className="flex-1">
          <div className="text-sm font-medium">{node.node_id}</div>
          <div className="text-xs text-gray-400">{node.url}</div>
        </div>
        <div className="w-24">
          <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full" style={{ width: `${pct}%` }}></div>
          </div>
          <div className="text-xs text-gray-400 mt-1 text-center">{node.current_sessions}/{node.max_sessions}</div>
        </div>
        <span className="text-gray-500 text-xs">{expanded ? '▲' : '▼'}</span>
      </div>
      {expanded && (
        <div className="border-t border-gray-700 p-3">
          {loading && <div className="text-xs text-gray-500">Loading...</div>}
          {!loading && profiles.length === 0 && <div className="text-xs text-gray-500">No profiles on this node</div>}
          {!loading && profiles.length > 0 && (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500">
                  <th className="text-left pb-1">Name</th>
                  <th className="text-left pb-1">ID</th>
                  <th className="text-left pb-1">Status</th>
                  <th className="text-left pb-1">Actions</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map(p => (
                  <tr key={p.id} className="border-t border-gray-700/50">
                    <td className="py-1.5">{p.name}</td>
                    <td className="py-1.5 font-mono text-gray-400">{p.id?.slice(0, 8)}...</td>
                    <td className="py-1.5">
                      <span className={`inline-flex items-center gap-1 ${p.status === 'running' ? 'text-green-400' : 'text-gray-500'}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${p.status === 'running' ? 'bg-green-400' : 'bg-gray-600'}`}></span>
                        {p.status}
                      </span>
                    </td>
                    <td className="py-1.5 space-x-2">
                      {p.status === 'running' ? (
                        <>
                          <button onClick={() => onViewSession({ _browser: true, node_id: node.node_id, profile_id: p.id, name: p.name })} className="text-blue-400 hover:text-blue-300">View</button>
                          <button onClick={() => handleStop(p.id)} className="text-red-400 hover:text-red-300">Stop</button>
                        </>
                      ) : (
                        <button onClick={() => handleLaunch(p.id)} className="text-green-400 hover:text-green-300">Launch</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

function VncOverlay({ session, onClose }) {
  let wsUrl, title, viewPageUrl
  if (session._browser) {
    wsUrl = `/api/view/browser/${session.node_id}/${session.profile_id}/vnc`
    title = `${session.name || session.profile_id?.slice(0, 8)} on ${session.node_id}`
    viewPageUrl = `/view/browser/${session.node_id}/${session.profile_id}`
  } else {
    wsUrl = `/api/view/${session.session_id}/vnc?token=${session.view_token || ''}`
    title = `${session.consumer_id?.slice(0, 16)}... on ${session.node_id}`
    viewPageUrl = `/view/${session.session_id}?token=${session.view_token || ''}`
  }
  return <VncViewer wsUrl={wsUrl} title={title} onClose={onClose} />
}

export default function App() {
  const [stats, setStats] = useState(null)
  const [sessions, setSessions] = useState([])
  const [running, setRunning] = useState([])
  const [viewing, setViewing] = useState(null)

  const fetchData = async () => {
    try {
      const [statsRes, sessionsRes, runningRes] = await Promise.all([
        fetch('/api/stats'), fetch('/api/sessions'), fetch('/api/sessions/running')
      ])
      if (statsRes.ok) setStats(await statsRes.json())
      if (sessionsRes.ok) setSessions(await sessionsRes.json())
      if (runningRes.ok) setRunning(await runningRes.json())
    } catch (e) { /* ignore */ }
  }

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 3000)
    return () => clearInterval(id)
  }, [])

  const handleStop = async (sessionId) => {
    await fetch(`/api/sessions/${sessionId}/stop`, { method: 'POST' })
    fetchData()
  }

  return (
    <div className="min-h-screen p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Browser Pool Dashboard</h1>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <StatCard label="使用中 Sessions" value={sessions.length} max={stats?.max_global_sessions} />
        <StatCard label="运行中 Browsers" value={running.length} />
        <StatCard label="Nodes Online" value={stats?.nodes?.filter(n => n.online).length ?? 0} />
      </div>

      {/* 正在被使用的 sessions (consumer 持有中) */}
      <div className="bg-gray-800/50 rounded-lg border border-gray-700 mb-6 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-700 font-medium">使用中 Sessions（Consumer 持有）</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-left">
              <th className="px-3 py-2">Consumer</th>
              <th className="px-3 py-2">Profile</th>
              <th className="px-3 py-2">Node</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">TTL</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map(s => (
              <SessionRow key={s.session_id} session={s} onStop={handleStop} onView={setViewing} />
            ))}
            {sessions.length === 0 && (
              <tr><td colSpan="6" className="px-3 py-6 text-center text-gray-500">无使用中的 session</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 活跃的 sessions (所有节点上已启动的浏览器) */}
      <div className="bg-gray-800/50 rounded-lg border border-gray-700 mb-6 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-700 font-medium">运行中 Browsers（所有节点）</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-left">
              <th className="px-3 py-2">Profile</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Node</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {running.map((r, i) => (
              <tr key={i} className="border-t border-gray-700 hover:bg-gray-800/50">
                <td className="px-3 py-2 font-mono text-xs">{r.profile_id?.slice(0, 8)}...</td>
                <td className="px-3 py-2">{r.name}</td>
                <td className="px-3 py-2">{r.node_id}</td>
                <td className="px-3 py-2">
                  <span className="inline-block w-2 h-2 rounded-full bg-green-400 mr-2"></span>running
                </td>
                <td className="px-3 py-2 space-x-2">
                  <button onClick={() => setViewing({ _browser: true, node_id: r.node_id, profile_id: r.profile_id, name: r.name })} className="text-blue-400 hover:text-blue-300 text-sm">View</button>
                  <a href={`/view/browser/${r.node_id}/${r.profile_id}`} target="_blank" className="text-gray-400 hover:text-gray-300 text-sm">↗ Open</a>
                </td>
              </tr>
            ))}
            {running.length === 0 && (
              <tr><td colSpan="5" className="px-3 py-6 text-center text-gray-500">无运行中的浏览器</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Profiles */}
      <ProfileManager />

      {/* Nodes */}
      <div className="mb-6">
        <div className="font-medium mb-3">Nodes</div>
        <div className="grid grid-cols-2 gap-3">
          {(stats?.nodes ?? []).map(n => <NodeCard key={n.node_id} node={n} onViewSession={setViewing} />)}
        </div>
      </div>

      {/* VNC Viewer overlay */}
      {viewing && <VncOverlay session={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}
