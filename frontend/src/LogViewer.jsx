import React, { useState, useEffect, useRef, useCallback } from 'react'

export default function LogViewer() {
  const [logs, setLogs] = useState([])
  const [connected, setConnected] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const [filter, setFilter] = useState('')
  const [expanded, setExpanded] = useState(false)
  const containerRef = useRef(null)
  const esRef = useRef(null)

  useEffect(() => {
    // Load history first
    fetch('/api/logs/history').then(r => r.ok ? r.json() : []).then(hist => {
      setLogs(hist)
    }).catch(() => {})

    // Start SSE stream
    const es = new EventSource('/api/logs/stream')
    esRef.current = es
    es.onopen = () => setConnected(true)
    es.onmessage = (e) => {
      setLogs(prev => {
        const next = [...prev, e.data]
        return next.length > 500 ? next.slice(-500) : next
      })
    }
    es.onerror = () => setConnected(false)
    return () => es.close()
  }, [])

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40)
  }, [])

  const filtered = filter
    ? logs.filter(l => l.toLowerCase().includes(filter.toLowerCase()))
    : logs

  const levelColor = (line) => {
    if (line.includes('[ERROR]')) return 'text-red-400'
    if (line.includes('[WARNING]')) return 'text-amber-400'
    if (line.includes('[INFO]')) return 'text-gray-300'
    return 'text-gray-500'
  }

  if (!expanded) {
    return (
      <section className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800/80">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-medium text-gray-200">Logs</h2>
            <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-gray-600'}`}></span>
            <span className="text-[10px] text-gray-500">{logs.length} lines</span>
          </div>
          <button onClick={() => setExpanded(true)} className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:bg-white/5 hover:text-gray-200 transition-colors">Expand</button>
        </div>
        <div ref={containerRef} onScroll={handleScroll} className="h-32 overflow-y-auto px-4 py-2 font-mono text-[11px] leading-relaxed">
          {filtered.slice(-20).map((line, i) => (
            <div key={i} className={levelColor(line)}>{line}</div>
          ))}
          {filtered.length === 0 && <div className="text-gray-600">Waiting for logs...</div>}
        </div>
      </section>
    )
  }

  return (
    <section className="rounded-xl border border-gray-800/60 bg-gray-900/30 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800/80">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium text-gray-200">Logs</h2>
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-emerald-400' : 'bg-gray-600'}`}></span>
          <span className="text-[10px] text-gray-500">{filtered.length} / {logs.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter..."
            className="bg-gray-800 border border-gray-700 rounded-lg px-2.5 py-1 text-xs w-40 focus:border-blue-500/50 focus:outline-none" />
          <button onClick={() => setLogs([])} className="px-2 py-1 rounded text-[11px] text-gray-500 hover:bg-white/5">Clear</button>
          <button onClick={() => setAutoScroll(!autoScroll)}
            className={`px-2 py-1 rounded text-[11px] ${autoScroll ? 'text-emerald-400' : 'text-gray-500'} hover:bg-white/5`}>
            {autoScroll ? '⇣ Auto' : '⇣ Paused'}
          </button>
          <button onClick={() => setExpanded(false)} className="px-2 py-1 rounded text-[11px] text-gray-400 hover:bg-white/5">Collapse</button>
        </div>
      </div>
      <div ref={containerRef} onScroll={handleScroll} className="h-80 overflow-y-auto px-4 py-2 font-mono text-[11px] leading-relaxed bg-[#0a0a0f]">
        {filtered.map((line, i) => (
          <div key={i} className={`${levelColor(line)} hover:bg-white/[0.02]`}>{line}</div>
        ))}
        {filtered.length === 0 && <div className="text-gray-600 py-4 text-center">No logs matching filter</div>}
      </div>
    </section>
  )
}
