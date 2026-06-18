import { useEffect, useRef, useState, useCallback } from 'react'

export default function CdpViewer({ wsUrl, title, onClose, onSwitchMode }) {
  const canvasRef = useRef(null)
  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(null)
  const [fps, setFps] = useState(0)
  const [fullscreen, setFullscreen] = useState(false)
  const idRef = useRef(1)
  const sizeRef = useRef({ width: 1920, height: 1080 })
  const frameCountRef = useRef(0)
  const containerRef = useRef(null)

  const sendCmd = useCallback((method, params = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ id: idRef.current++, method, params }))
    }
  }, [])

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const fullUrl = `${protocol}//${window.location.host}${wsUrl}`
    const ws = new WebSocket(fullUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      // Start screencast
      sendCmd('Page.startScreencast', { format: 'jpeg', quality: 70, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 })
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.method === 'Page.screencastFrame') {
          const { data, metadata, sessionId } = msg.params
          sizeRef.current = { width: metadata.deviceWidth, height: metadata.deviceHeight }
          renderFrame(data)
          // Acknowledge frame
          sendCmd('Page.screencastFrameAck', { sessionId })
          frameCountRef.current++
        }
      } catch {}
    }

    ws.onerror = () => setError('WebSocket connection failed')
    ws.onclose = () => setConnected(false)

    // FPS counter
    const fpsInterval = setInterval(() => {
      setFps(frameCountRef.current)
      frameCountRef.current = 0
    }, 1000)

    return () => {
      clearInterval(fpsInterval)
      if (ws.readyState === WebSocket.OPEN) {
        try { sendCmd('Page.stopScreencast') } catch {}
      }
      ws.close()
    }
  }, [wsUrl, sendCmd])

  const renderFrame = (base64Data) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const img = new Image()
    img.onload = () => {
      canvas.width = img.width
      canvas.height = img.height
      canvas.getContext('2d').drawImage(img, 0, 0)
    }
    img.src = `data:image/jpeg;base64,${base64Data}`
  }

  // Input event helpers
  const getCoords = (e) => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const scaleX = sizeRef.current.width / rect.width
    const scaleY = sizeRef.current.height / rect.height
    return {
      x: Math.round((e.clientX - rect.left) * scaleX),
      y: Math.round((e.clientY - rect.top) * scaleY),
    }
  }

  const handleMouse = (e, type) => {
    e.preventDefault()
    const { x, y } = getCoords(e)
    const button = e.button === 2 ? 'right' : e.button === 1 ? 'middle' : 'left'
    const buttons = e.buttons
    sendCmd('Input.dispatchMouseEvent', { type, x, y, button, buttons, clickCount: type === 'mousePressed' ? 1 : 0 })
  }

  const handleWheel = (e) => {
    e.preventDefault()
    const { x, y } = getCoords(e)
    sendCmd('Input.dispatchMouseEvent', { type: 'mouseWheel', x, y, deltaX: e.deltaX, deltaY: e.deltaY })
  }

  const handleKey = (e, type) => {
    e.preventDefault()
    const params = {
      type,
      key: e.key,
      code: e.code,
      windowsVirtualKeyCode: e.keyCode,
      nativeVirtualKeyCode: e.keyCode,
      modifiers: (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.metaKey ? 4 : 0) | (e.shiftKey ? 8 : 0),
    }
    if (type === 'char') params.text = e.key
    sendCmd('Input.dispatchKeyEvent', params)
  }

  const toggleFullscreen = () => {
    if (!containerRef.current) return
    if (!document.fullscreenElement) containerRef.current.requestFullscreen()
    else document.exitFullscreen()
  }

  useEffect(() => {
    const h = () => setFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', h)
    return () => document.removeEventListener('fullscreenchange', h)
  }, [])

  useEffect(() => {
    if (connected && canvasRef.current) canvasRef.current.focus()
  }, [connected])

  if (error) {
    return (
      <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center">
        <div className="bg-gray-800 rounded-lg p-6 text-center">
          <p className="text-red-400 mb-2">CDP Connection Failed</p>
          <p className="text-gray-400 text-sm mb-4">{error}</p>
          <button onClick={onClose} className="px-4 py-2 bg-gray-700 rounded hover:bg-gray-600">Close</button>
        </div>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="fixed inset-0 bg-black/90 z-50 flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700 shrink-0">
        <div className="flex items-center gap-3">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-yellow-400 animate-pulse'}`}></span>
          <span className="text-sm">{title}</span>
          <span className="text-[10px] font-mono text-gray-500 bg-gray-900 px-1.5 py-0.5 rounded">CDP</span>
          <span className="text-xs text-gray-500">{connected ? `${fps} fps` : 'Connecting...'}</span>
        </div>
        <div className="flex items-center gap-2">
          {onSwitchMode && <button onClick={onSwitchMode} className="px-2 py-1 rounded text-[11px] font-medium text-blue-400 hover:bg-blue-400/10 transition-colors">Switch to VNC</button>}
          <button onClick={toggleFullscreen} className="p-1.5 text-gray-400 hover:text-white rounded hover:bg-gray-700" title="Fullscreen">
            {fullscreen ? '⊡' : '⊞'}
          </button>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-white rounded hover:bg-gray-700 text-lg">×</button>
        </div>
      </div>
      {/* Canvas */}
      <div className="flex-1 flex items-center justify-center overflow-hidden bg-black" onClick={() => canvasRef.current?.focus()}>
        <canvas
          ref={canvasRef}
          className="max-w-full max-h-full cursor-default outline-none"
          tabIndex={0}
          onMouseDown={e => { canvasRef.current?.focus(); handleMouse(e, 'mousePressed') }}
          onMouseUp={e => handleMouse(e, 'mouseReleased')}
          onMouseMove={e => handleMouse(e, 'mouseMoved')}
          onWheel={handleWheel}
          onKeyDown={e => { handleKey(e, 'keyDown'); if (e.key.length === 1) handleKey(e, 'char') }}
          onKeyUp={e => handleKey(e, 'keyUp')}
          onContextMenu={e => e.preventDefault()}
        />
      </div>
    </div>
  )
}
