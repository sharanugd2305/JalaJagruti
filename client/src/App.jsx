import { Routes ,Route} from 'react-router-dom'

function App() {
  <>
      <Routes>
        {/* <Route path="/" element={<Dashboard />} /> */}
        <Route path="/" element={<h1 className="text-3xl font-bold underline">Dashboard</h1>} />
      </Routes>
    </>
}

export default App;
