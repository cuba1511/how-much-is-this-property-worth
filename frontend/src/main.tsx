import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './lib/i18n'
import './index.css'
import App from './App'
import CoachPage from './pages/CoachPage'

const root = document.getElementById('root')
if (!root) {
  throw new Error('Root element #root not found')
}

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/coach" element={<CoachPage />} />
        <Route path="/coach/:transactionId" element={<CoachPage />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
