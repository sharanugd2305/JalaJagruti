import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import 'leaflet/dist/leaflet.css'
import App from './App.jsx'
import { BrowserRouter } from 'react-router-dom'
import { WaterRiskProvider } from './context/WaterRiskContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <WaterRiskProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </WaterRiskProvider>
  </StrictMode>,
)
