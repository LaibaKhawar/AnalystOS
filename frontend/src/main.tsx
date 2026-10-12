import '@fontsource/geist-sans/400.css'
import '@fontsource/geist-sans/500.css'
import '@fontsource/geist-sans/600.css'
import '@fontsource/geist-mono/400.css'
import '@fontsource/geist-mono/500.css'
import './index.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { installReplay, REPLAY, type ReplayInfo } from './api/replay'
import { ReplayBanner } from './components/replay/ReplayBanner'

const root = document.getElementById('root')
if (!root) throw new Error('Root element missing')

function render(replay: ReplayInfo | null) {
  createRoot(root!).render(
    <StrictMode>
      <App />
      {replay && <ReplayBanner info={replay} />}
    </StrictMode>,
  )
}

if (REPLAY) void installReplay().then(render)
else render(null)
