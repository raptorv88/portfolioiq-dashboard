import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import LoginPage    from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import HistoryPage  from './pages/HistoryPage'
import SnapshotPage from './pages/SnapshotPage'
import AppShell     from './components/AppShell'


function Guard({ children }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <span className="w-6 h-6 border-2 border-ink-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
  return user ? children : <Navigate to="/login" replace />
}

function Public({ children }) {
  const { user, loading } = useAuth()
  if (loading) return null
  return user ? <Navigate to="/" replace /> : children
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login"    element={<Public><LoginPage    /></Public>} />
        <Route path="/register" element={<Public><RegisterPage /></Public>} />
        <Route element={<Guard><AppShell /></Guard>}>
          <Route index              element={<DashboardPage />} />
          <Route path="/history"    element={<HistoryPage   />} />
          <Route path="/history/:id" element={<SnapshotPage  />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
