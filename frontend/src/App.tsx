import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            <div className="flex min-h-screen items-center justify-center bg-slate-50">
              <div className="text-center">
                <h1 className="text-3xl font-bold text-slate-800">FinAudit</h1>
                <p className="mt-2 text-slate-500">
                  Financial Reconciliation &amp; Audit Platform
                </p>
                <p className="mt-4 text-sm text-slate-400">
                  Foundation ready — Phase 2 will add authentication and
                  ingestion.
                </p>
              </div>
            </div>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}

export default App
