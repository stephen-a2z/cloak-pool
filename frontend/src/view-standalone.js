const params = new URLSearchParams(window.location.search)
const wsPath = params.get('ws')
let mode = params.get('mode') || 'vnc'

const statusDot = document.getElementById('status-dot')
const info = document.getElementById('info')
const badge = document.getElementById('mode-badge')
const fpsDisplay = document.getElementById('fps-display')
const switchBtn = document.getElementById('switch-btn')
const viewer = document.getElementById('viewer')

if (!wsPath) {
  info.textContent = 'Error: missing ws parameter'
} else {
  startViewer()
}

function startViewer() {
  viewer.innerHTML = ''
  badge.textContent = mode.toUpperCase()
  switchBtn.textContent = mode === 'vnc' ? 'Switch to CDP' : 'Switch to VNC'
  switchBtn.onclick = () => {
    mode = mode === 'vnc' ? 'cdp' : 'vnc'
    const newParams = new URLSearchParams(window.location.search)
    newParams.set('mode', mode)
    window.history.replaceState(null, '', '?' + newParams.toString())
    startViewer()
  }

  if (mode === 'vnc') {
    startVnc()
  } else {
    startCdp()
  }
}

async function startVnc() {
  fpsDisplay.textContent = ''
  const { default: RFB } = await import('@novnc/novnc/lib/rfb.js')
  const el = document.createElement('div')
  el.id = 'screen'
  el.style.cssText = 'width:100%;height:100%'
  viewer.appendChild(el)

  const wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + wsPath
  const rfb = new RFB(el, wsUrl, { wsProtocols: ['binary'] })
  rfb.scaleViewport = true
  rfb.resizeSession = false
  rfb.addEventListener('connect', () => { statusDot.classList.add('on'); info.textContent = 'Connected' })
  rfb.addEventListener('disconnect', () => { statusDot.classList.remove('on'); info.textContent = 'Disconnected' })
}

function startCdp() {
  // Replace /vnc with /cdp in ws path
  const cdpPath = wsPath.replace('/vnc', '/cdp')
  const wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + cdpPath

  const canvas = document.createElement('canvas')
  canvas.style.cssText = 'max-width:100%;max-height:100%;cursor:default'
  canvas.tabIndex = 0
  viewer.appendChild(canvas)

  const ws = new WebSocket(wsUrl)
  let idCounter = 1
  let frameCount = 0
  let deviceSize = { width: 1920, height: 1080 }

  const send = (method, p = {}) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ id: idCounter++, method, params: p }))
  }

  ws.onopen = () => {
    statusDot.classList.add('on')
    info.textContent = 'Connected'
    send('Page.startScreencast', { format: 'jpeg', quality: 70, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 })
  }

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.method === 'Page.screencastFrame') {
        const { data, metadata, sessionId } = msg.params
        deviceSize = { width: metadata.deviceWidth, height: metadata.deviceHeight }
        const img = new Image()
        img.onload = () => { canvas.width = img.width; canvas.height = img.height; canvas.getContext('2d').drawImage(img, 0, 0) }
        img.src = 'data:image/jpeg;base64,' + data
        send('Page.screencastFrameAck', { sessionId })
        frameCount++
      }
    } catch {}
  }

  ws.onclose = () => { statusDot.classList.remove('on'); info.textContent = 'Disconnected' }
  ws.onerror = () => { info.textContent = 'Connection failed' }

  // FPS counter
  setInterval(() => { fpsDisplay.textContent = frameCount + ' fps'; frameCount = 0 }, 1000)

  // Input forwarding
  const getCoords = (e) => {
    const rect = canvas.getBoundingClientRect()
    return { x: Math.round((e.clientX - rect.left) * (deviceSize.width / rect.width)), y: Math.round((e.clientY - rect.top) * (deviceSize.height / rect.height)) }
  }

  canvas.onmousedown = (e) => { e.preventDefault(); const c = getCoords(e); send('Input.dispatchMouseEvent', { type: 'mousePressed', x: c.x, y: c.y, button: 'left', clickCount: 1 }) }
  canvas.onmouseup = (e) => { e.preventDefault(); const c = getCoords(e); send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: c.x, y: c.y, button: 'left' }) }
  canvas.onmousemove = (e) => { const c = getCoords(e); send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: c.x, y: c.y }) }
  canvas.onwheel = (e) => { e.preventDefault(); const c = getCoords(e); send('Input.dispatchMouseEvent', { type: 'mouseWheel', x: c.x, y: c.y, deltaX: e.deltaX, deltaY: e.deltaY }) }
  canvas.oncontextmenu = (e) => e.preventDefault()

  canvas.onkeydown = (e) => {
    e.preventDefault()
    const mod = (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.metaKey ? 4 : 0) | (e.shiftKey ? 8 : 0)
    send('Input.dispatchKeyEvent', { type: 'keyDown', key: e.key, code: e.code, windowsVirtualKeyCode: e.keyCode, modifiers: mod })
    if (e.key.length === 1) send('Input.dispatchKeyEvent', { type: 'char', key: e.key, text: e.key, modifiers: mod })
  }
  canvas.onkeyup = (e) => {
    e.preventDefault()
    send('Input.dispatchKeyEvent', { type: 'keyUp', key: e.key, code: e.code, windowsVirtualKeyCode: e.keyCode })
  }

  canvas.focus()
}
