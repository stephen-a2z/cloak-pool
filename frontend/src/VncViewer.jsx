import { useEffect, useRef, useState } from 'react'

export default function VncViewer({ wsUrl, title, onClose }) {
  const containerRef = useRef(null)
  const rfbRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)
  const [fullscreen, setFullscreen] = useState(false)

  useEffect(() => {
    let rfb = null
    let cancelled = false

    async function connect() {
      try {
        const { default: RFB } = await import('@novnc/novnc/lib/rfb.js')
        if (cancelled || !containerRef.current) return

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const fullWsUrl = `${protocol}//${window.location.host}${wsUrl}`

        rfb = new RFB(containerRef.current, fullWsUrl, {
          wsProtocols: ['binary'],
        })
        rfbRef.current = rfb
        rfb.scaleViewport = true
        rfb.resizeSession = false
        rfb.showDotCursor = true

        rfb.addEventListener('connect', () => {
          if (!cancelled) setConnected(true)
        })
        rfb.addEventListener('disconnect', () => {
          if (!cancelled) setConnected(false)
        })
        rfb.addEventListener('securityfailure', (e) => {
          setError(`Security failure: ${e.detail?.reason}`)
        })
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to connect')
      }
    }

    connect()

    return () => {
      cancelled = true
      if (rfb) {
        try { rfb.disconnect() } catch (e) {}
      }
      rfbRef.current = null
    }
  }, [wsUrl])

  // Prevent scroll wheel from propagating
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const handler = (e) => e.preventDefault()
    el.addEventListener('wheel', handler, { passive: false })
    return () => el.removeEventListener('wheel', handler)
  }, [])

  const toggleFullscreen = () => {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen()
      setFullscreen(true)
    } else {
      document.exitFullscreen()
      setFullscreen(false)
    }
  }

  useEffect(() => {
    const handler = () => setFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  if (error) {
    return (
      <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center">
        <div className="bg-gray-800 rounded-lg p-6 text-center">
          <p className="text-red-400 mb-2">Connection failed</p>
          <p className="text-gray-400 text-sm mb-4">{error}</p>
          <button onClick={onClose} className="px-4 py-2 bg-gray-700 rounded hover:bg-gray-600">Close</button>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 bg-black/90 z-50 flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700 shrink-0">
        <div className="flex items-center gap-3">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-yellow-400 animate-pulse'}`}></span>
          <span className="text-sm">{title}</span>
          <span className="text-xs text-gray-500">{connected ? 'Connected' : 'Connecting...'}</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={toggleFullscreen} className="p-1.5 text-gray-400 hover:text-white rounded hover:bg-gray-700" title="Fullscreen">
            {fullscreen ? '⊡' : '⊞'}
          </button>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-white rounded hover:bg-gray-700 text-lg">×</button>
        </div>
      </div>
      {/* VNC canvas */}
      <div ref={containerRef} className="flex-1 overflow-hidden bg-black" />
    </div>
  )
}
