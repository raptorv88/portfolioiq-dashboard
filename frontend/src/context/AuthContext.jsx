import React, { createContext, useContext, useState, useEffect } from 'react'
import axios from 'axios'

const Ctx = createContext(null)

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)
  const [token,   setToken]   = useState(() => localStorage.getItem('piq_token'))
  const [loading, setLoading] = useState(true)

  // attach token to every axios request automatically
  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
    } else {
      delete axios.defaults.headers.common['Authorization']
    }
  }, [token])

  // restore session on first load
  useEffect(() => {
    const restore = async () => {
      if (!token) { setLoading(false); return }
      try {
        const { data } = await axios.get('/auth/me')
        setUser(data)
      } catch {
        localStorage.removeItem('piq_token')
        setToken(null)
      } finally {
        setLoading(false)
      }
    }
    restore()
  }, [])

  const login = async (username, password) => {
    const body = new URLSearchParams({ username, password })
    const { data } = await axios.post('/auth/login', body, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    localStorage.setItem('piq_token', data.access_token)
    localStorage.setItem('piq_user',  JSON.stringify(data.user))
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }

  const register = async (payload) => {
    const { data } = await axios.post('/auth/register', payload)
    localStorage.setItem('piq_token', data.access_token)
    setToken(data.access_token)
    setUser(data.user)
    return data.user
  }

  const logout = () => {
    localStorage.removeItem('piq_token')
    setToken(null)
    setUser(null)
  }

  return (
    <Ctx.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </Ctx.Provider>
  )
}

export const useAuth = () => useContext(Ctx)
