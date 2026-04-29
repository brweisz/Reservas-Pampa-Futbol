import { useState, useRef } from 'react'
import './App.css'

const API = 'http://localhost:8000'

function App() {
  const [step, setStep] = useState('login') // login | picking | polling | booked | failed
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [wantEmail, setWantEmail] = useState(false)
  const [classes, setClasses] = useState([])
  const [jobId, setJobId] = useState(null)
  const [bookedClass, setBookedClass] = useState(null)
  const pollRef = useRef(null)

  // --- Login ---
  async function handleLogin(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    const fd = new FormData(e.target)
    try {
      const res = await fetch(`${API}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          documento: fd.get('documento'),
          password: fd.get('password'),
          email: wantEmail ? fd.get('email') : null,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Login failed')
      }
      const data = await res.json()
      setJobId(data.job_id)
      setClasses(data.classes)
      setStep('picking')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // --- Check job status once, return the status string ---
  async function checkStatus(id) {
    try {
      const res = await fetch(`${API}/status/${id}`)
      if (!res.ok) return null
      const data = await res.json()
      return data.status
    } catch {
      return null
    }
  }

  // --- Pick class & start booking ---
  async function handleBook(clase) {
    setError('')
    setLoading(true)
    setBookedClass(clase)
    const classTuple = { fecha: clase.fecha, nivel: clase.nivel, sede: clase.sede }
    try {
      const res = await fetch(`${API}/book`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId, class_tuple: classTuple }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Booking request failed')
      }

      // The backend books immediately if available — check right away
      // Small delay to let the async task complete
      await new Promise(r => setTimeout(r, 500))
      const status = await checkStatus(jobId)
      if (status === 'booked') {
        setStep('booked')
      } else if (status === 'failed') {
        setStep('failed')
      } else {
        setStep('polling')
        startPolling(jobId)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // --- Poll status ---
  function startPolling(id) {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      const status = await checkStatus(id)
      if (status === 'booked') {
        clearInterval(pollRef.current)
        setStep('booked')
      } else if (status === 'failed') {
        clearInterval(pollRef.current)
        setStep('failed')
      }
    }, 5000)
  }

  // --- Cancel ---
  async function handleCancel() {
    if (pollRef.current) clearInterval(pollRef.current)
    try {
      await fetch(`${API}/job/${jobId}`, { method: 'DELETE' })
    } catch {
      // best effort
    }
    setStep('login')
    setJobId(null)
    setClasses([])
    setBookedClass(null)
    setError('')
  }

  // --- Render ---
  return (
    <div className="container">
      <h1>Pampa Futbol</h1>

      {error && <div className="error">{error}</div>}

      {step === 'login' && (
        <form onSubmit={handleLogin} className="form">
          <input name="documento" placeholder="Documento" required />
          <div className="password-field">
            <input name="password" type={showPassword ? 'text' : 'password'} placeholder="Contrasena" required />
            <button type="button" className="toggle-password" onClick={() => setShowPassword(!showPassword)}>
              {showPassword ? 'Ocultar' : 'Ver'}
            </button>
          </div>
          <label className="checkbox-label">
            <input type="checkbox" checked={wantEmail} onChange={() => setWantEmail(!wantEmail)} />
            Quiero recibir una notificacion por mail
          </label>
          {wantEmail && <input name="email" type="email" placeholder="Email para notificacion" required />}
          <button type="submit" disabled={loading}>
            {loading ? <><span className="spinner-small" /> Ingresando...</> : 'Ingresar'}
          </button>
        </form>
      )}

      {step === 'picking' && (
        <div>
          <h2>Clases disponibles</h2>
          <div className="class-list">
            {classes.map((c, i) => (
              <div key={i} className={`class-card ${c.disponible ? 'available' : 'unavailable'}`}>
                <div className="class-info">
                  <strong>{c.fecha}</strong>
                  <span>{c.nivel}</span>
                  <span>{c.sede}{c.cancha ? ` - ${c.cancha}` : ''}</span>
                  <span className="availability">{c.disponibilidad}</span>
                </div>
                <button onClick={() => handleBook(c)} disabled={loading}>
                  Reservar
                </button>
              </div>
            ))}
          </div>
          <button className="cancel-btn" onClick={handleCancel}>Cancelar</button>
        </div>
      )}

      {step === 'polling' && (
        <div className="status-view">
          <h2>Esperando lugar...</h2>
          <p>
            <strong>{bookedClass?.fecha}</strong> | {bookedClass?.nivel} | {bookedClass?.sede}{bookedClass?.cancha ? ` - ${bookedClass.cancha}` : ''}
          </p>
          <div className="spinner" />
          <p className="hint">Revisando cada 30 segundos. Recibiras un email cuando se reserve.</p>
          <button className="cancel-btn" onClick={handleCancel}>Cancelar</button>
        </div>
      )}

      {step === 'booked' && (
        <div className="status-view success">
          <h2>Clase reservada!</h2>
          <p>
            <strong>{bookedClass?.fecha}</strong> | {bookedClass?.nivel} | {bookedClass?.sede}{bookedClass?.cancha ? ` - ${bookedClass.cancha}` : ''}
          </p>
          <p>Se envio un email de confirmacion.</p>
          <button onClick={() => { setStep('login'); setJobId(null); setClasses([]); setBookedClass(null); }}>
            Volver al inicio
          </button>
        </div>
      )}

      {step === 'failed' && (
        <div className="status-view failed">
          <h2>Error al reservar</h2>
          <p>Hubo un problema. Intenta nuevamente.</p>
          <button onClick={() => { setStep('login'); setJobId(null); setClasses([]); setBookedClass(null); }}>
            Volver al inicio
          </button>
        </div>
      )}
    </div>
  )
}

export default App
