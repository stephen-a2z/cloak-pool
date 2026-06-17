import RFB from '@novnc/novnc/lib/rfb.js'

const params = new URLSearchParams(window.location.search)
const wsPath = params.get('ws')

if (!wsPath) {
  document.getElementById('status').textContent = 'Error: missing ws parameter'
} else {
  const wsUrl = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + wsPath
  const rfb = new RFB(document.getElementById('screen'), wsUrl, { wsProtocols: ['binary'] })
  rfb.scaleViewport = true
  rfb.resizeSession = false
  rfb.addEventListener('connect', () => {
    document.getElementById('status').textContent = 'Connected'
    setTimeout(() => { document.getElementById('status').style.display = 'none' }, 2000)
  })
  rfb.addEventListener('disconnect', () => {
    document.getElementById('status').textContent = 'Disconnected'
    document.getElementById('status').style.display = 'block'
  })
}
