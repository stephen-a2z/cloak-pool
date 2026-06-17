import React, { useState, useEffect } from 'react'

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
        <button onClick={() => onStop(session.session_id)} className="text-red-400 hover:text-red-300 text-sm">Stop</button>
      </td>
    </tr>
  )
}

function NodeRow({ node }) {
  const pct = node.max_sessions > 0 ? (node.current_sessions / node.max_sessions) * 100 : 0
  return (
    <div className="bg-gray-800 rounded-lg p-3 border border-gray-700 flex items-center gap-3">
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
    </div>
  )
}

function VncViewer({ session, onClose }) {
  const viewUrl = `/view/${session.session_id}?token=${session.view_token || ''}`
  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <span className="text-sm">Viewing: {session.consumer_id.slice(0, 16)}... on {session.node_id}</span>
        <button onClick={onClose} className="text-gray-400 hover:text-white text-lg">&times;</button>
      </div>
      <iframe src={viewUrl} className="flex-1 w-full border-0" />
    </div>
  )
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
              <th className="px-3 py-2">CDP</th>
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
                <td className="px-3 py-2 font-mono text-xs text-gray-400">{r.cdp_url || '-'}</td>
              </tr>
            ))}
            {running.length === 0 && (
              <tr><td colSpan="5" className="px-3 py-6 text-center text-gray-500">无运行中的浏览器</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Nodes */}
      <div className="mb-6">
        <div className="font-medium mb-3">Nodes</div>
        <div className="grid grid-cols-2 gap-3">
          {(stats?.nodes ?? []).map(n => <NodeRow key={n.node_id} node={n} />)}
        </div>
      </div>

      {/* VNC Viewer overlay */}
      {viewing && <VncViewer session={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}
