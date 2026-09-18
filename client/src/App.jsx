import { Routes ,Route} from 'react-router-dom'
import Dashboard from './pages/Dashboard'

function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        {/* <Route path="/about" element={<h1>About Page</h1>} /> */}
      </Routes>
    </>
  )
}

export default App
