import { Component, StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// A link from an older version, or a damaged one, must not leave a blank page: say so and
// offer to start again (the address is cleared, the drafts are kept).
class Recover extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="recover">
        <h1>This page could not be opened</h1>
        <p>The link may come from an older version of the portal, or may have been cut when it was copied.</p>
        <button className="btn btn-primary" onClick={() => { window.location.replace(window.location.pathname) }}>Start again</button>
      </div>
    )
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Recover>
      <App />
    </Recover>
  </StrictMode>,
)
