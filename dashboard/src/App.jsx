import React, { useEffect, useRef, useState } from 'react'
import './App.css'
import { supabase } from './lib/supabase'

const API_BASE = 'http://127.0.0.1:8001'
const AGENT_INSTALLER_WIN_URL = import.meta.env.VITE_AGENT_INSTALLER_WIN_URL || ''
const AGENT_INSTALLER_MAC_URL = import.meta.env.VITE_AGENT_INSTALLER_MAC_URL || ''
const AGENT_SETUP_GUIDE_URL = import.meta.env.VITE_AGENT_SETUP_GUIDE_URL || ''

function App() {
  const [session, setSession] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [authMode, setAuthMode] = useState('otp')
  const [authFlow, setAuthFlow] = useState('signin')
  const [authEmail, setAuthEmail] = useState('')
  const [authOtp, setAuthOtp] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authStatus, setAuthStatus] = useState('')
  const [recoveryMode, setRecoveryMode] = useState(false)
  const [recoveryPassword, setRecoveryPassword] = useState('')
  const [recoveryStatus, setRecoveryStatus] = useState('')
  const [resetEmail, setResetEmail] = useState('')
  const [showAppPasswordHelp, setShowAppPasswordHelp] = useState(false)
  const [needsProfileSetup, setNeedsProfileSetup] = useState(false)
  const [profileName, setProfileName] = useState('')
  const [profileProfession, setProfileProfession] = useState('')
  const [profilePassword, setProfilePassword] = useState('')
  const [profileAppPassword, setProfileAppPassword] = useState('')
  const [profileStatus, setProfileStatus] = useState('')
  const [activePage, setActivePage] = useState('home')
  const [menuOpen, setMenuOpen] = useState(false)
  const [volume, setVolume] = useState(0)
  const [status, setStatus] = useState('Connecting to Python Core...')
  const [cameras, setCameras] = useState([])
  const [selectedCameraId, setSelectedCameraId] = useState('')
  const [avatarMode, setAvatarMode] = useState('3d')

  const [linkInput, setLinkInput] = useState('')
  const [textInput, setTextInput] = useState('')
  const [historyItems, setHistoryItems] = useState([])
  const [dataStatus, setDataStatus] = useState('Ready')
  const [losInput, setLosInput] = useState('')
  const [losStatus, setLosStatus] = useState('Ready')
  const [losItems, setLosItems] = useState([])
  const [automationStatus, setAutomationStatus] = useState('Ready')
  const [automationItems, setAutomationItems] = useState([])
  const [senderConfigured, setSenderConfigured] = useState(false)
  const [senderEmail, setSenderEmail] = useState('')
  const [senderAppPassword, setSenderAppPassword] = useState('')
  const [senderHost, setSenderHost] = useState('smtp.gmail.com')
  const [senderPort, setSenderPort] = useState('587')
  const [senderUseTls, setSenderUseTls] = useState(true)
  const [showSenderSetup, setShowSenderSetup] = useState(true)
  const [requesterEmail, setRequesterEmail] = useState('')
  const [recipientsInput, setRecipientsInput] = useState('')
  const [automationInstruction, setAutomationInstruction] = useState('')
  const [automationMode, setAutomationMode] = useState('ai_schedule')
  const [sendMode, setSendMode] = useState('single')
  const [bulkSendMode, setBulkSendMode] = useState('together')
  const [recipientRows, setRecipientRows] = useState([{ recipient: '', subject: '', message: '', attachments: [] }])
  const [sharedAttachments, setSharedAttachments] = useState([])
  const [emailSubject, setEmailSubject] = useState('')
  const [emailBody, setEmailBody] = useState('')
  const [scheduleDate, setScheduleDate] = useState('')
  const [scheduleTime24h, setScheduleTime24h] = useState('')
  const [activeAgent, setActiveAgent] = useState('command_agent')
  const [agentAutonomyMode, setAgentAutonomyMode] = useState('suggest_actions')
  const [agentExecutionStatus, setAgentExecutionStatus] = useState({})
  const [agentInterfaceOpen, setAgentInterfaceOpen] = useState(false)
  const [agentInput, setAgentInput] = useState('')
  const [agentChat, setAgentChat] = useState([])
  const [isListeningLos, setIsListeningLos] = useState(false)
  const [isListeningAgent, setIsListeningAgent] = useState(false)
  const [meetingsStatus, setMeetingsStatus] = useState('Ready')
  const [meetingItems, setMeetingItems] = useState([])
  const [selectedMeeting, setSelectedMeeting] = useState(null)
  const [meetingQuery, setMeetingQuery] = useState('')
  const [meetingReply, setMeetingReply] = useState('')
  const [sessionMeetingUrl, setSessionMeetingUrl] = useState('')
  const [sessionProfileEmail, setSessionProfileEmail] = useState('')
  const [sessionAssistantName, setSessionAssistantName] = useState('Aria')
  const [sessionAvatarMode, setSessionAvatarMode] = useState('3d')
  const [sessionStatus, setSessionStatus] = useState('Idle')
  const [sessionDevice, setSessionDevice] = useState(null)
  const [sessionPlatform, setSessionPlatform] = useState(null)
  const [setupPlatformOverride, setSetupPlatformOverride] = useState('')
  const [audioValidation, setAudioValidation] = useState('')
  const [sessionLogs, setSessionLogs] = useState([])
  const [sessionTranscriptLogs, setSessionTranscriptLogs] = useState([])
  const [agentInstallStatus, setAgentInstallStatus] = useState('')
  const [connectName, setConnectName] = useState('')
  const [connectEmail, setConnectEmail] = useState('')
  const [connectItems, setConnectItems] = useState([])

  const inferExecutionStatus = (data, mode) => {
    const reply = String(data?.reply || '').toLowerCase()
    const reminderCount = Number(data?.automation_reminder?.count || 0)
    if (mode === 'execute_with_approval') {
      if (reply.includes('approval needed') || reply.includes('reply with \'approve\'')) return 'answered'
      if (reminderCount > 0 || reply.includes('execution complete after approval')) return 'answered'
      return 'answered'
    }
    if (mode === 'autonomous_mode') {
      if (reminderCount > 0 || reply.includes('autonomous execution complete') || reply.includes('executed')) return 'answered'
      return 'answered'
    }
    return 'answered'
  }

  const statusColor = (status) => {
    if (status === 'working') return '#f4c430' // yellow
    if (status === 'answered') return '#8b8b8b' // grey
    return '#e74c3c' // red (unused)
  }

  const statusLabel = (status) => {
    if (status === 'working') return 'doing work'
    if (status === 'answered') return 'answered/executed'
    return 'unused'
  }
  const [connectStatus, setConnectStatus] = useState('Ready')

  const videoRef = useRef(null)
  const wsRef = useRef(null)
  const scheduleDateRef = useRef(null)
  const scheduleTimeRef = useRef(null)
  const loggedInEmail = (session?.user?.email || '').trim().toLowerCase()
  const userMeta = session?.user?.user_metadata || {}
  const displayName = (userMeta.full_name || userMeta.name || '').trim()
  const displayProfession = (userMeta.profession || '').trim()

  const apiFetch = (url, options = {}) => {
    const headers = { ...(options.headers || {}) }
    if (loggedInEmail) {
      headers['X-User-Email'] = loggedInEmail
    }
    const accessToken = session?.access_token
    if (accessToken) {
      headers.Authorization = `Bearer ${accessToken}`
    }
    return fetch(url, { ...options, headers })
  }

  useEffect(() => {
    let mounted = true
    ;(async () => {
      try {
        const url = new URL(window.location.href)
        if (url.pathname === '/auth/callback') {
          const nextUrl = `/${url.search || ''}${url.hash || ''}`
          window.history.replaceState({}, '', nextUrl)
        }

        const fresh = new URL(window.location.href)
        const queryParams = fresh.searchParams
        const hashParams = new URLSearchParams((fresh.hash || '').replace(/^#/, ''))
        const authType = hashParams.get('type') || queryParams.get('type')
        const code = queryParams.get('code')
        const hasRecoveryToken = Boolean(hashParams.get('access_token') || queryParams.get('access_token'))

        if (code) {
          await supabase.auth.exchangeCodeForSession(code)
        }
        if (authType === 'recovery' || hasRecoveryToken) {
          setRecoveryMode(true)
          setRecoveryStatus('Set your new password below.')
        }

        const { data } = await supabase.auth.getSession()
        if (!mounted) return
        const currentSession = data.session || null
        setSession(currentSession)
        const userMeta = currentSession?.user?.user_metadata || {}
        const provider = currentSession?.user?.app_metadata?.provider
        const currentMethod = provider === 'google' ? 'google' : 'email_otp'
        const lockedMethod = userMeta?.signup_method
        if (lockedMethod && lockedMethod !== currentMethod) {
          setAuthStatus('You created account using a different login method. Please use that same method.')
          setNeedsProfileSetup(false)
          supabase.auth.signOut()
        } else {
          setNeedsProfileSetup(Boolean(currentSession?.user && !userMeta?.profile_completed))
        }
      } catch {
        if (!mounted) return
      } finally {
        if (mounted) setAuthLoading(false)
      }
    })()

    const {
      data: { subscription }
    } = supabase.auth.onAuthStateChange((event, currentSession) => {
      if (event === 'PASSWORD_RECOVERY') {
        setRecoveryMode(true)
        setRecoveryStatus('Set your new password below.')
      }
      setSession(currentSession || null)
      if (currentSession?.user?.email) {
        setSessionProfileEmail(currentSession.user.email)
      }
      const userMeta = currentSession?.user?.user_metadata || {}
      const provider = currentSession?.user?.app_metadata?.provider
      const currentMethod = provider === 'google' ? 'google' : 'email_otp'
      const lockedMethod = userMeta?.signup_method
      if (lockedMethod && lockedMethod !== currentMethod) {
        setAuthStatus('You created account using a different login method. Please use that same method.')
        setNeedsProfileSetup(false)
        supabase.auth.signOut()
        return
      }
      setNeedsProfileSetup(Boolean(currentSession?.user && !userMeta?.profile_completed))
    })

    return () => {
      mounted = false
      subscription.unsubscribe()
    }
  }, [])

  const signInWithGoogle = async () => {
    try {
      setAuthStatus('Opening Google sign-in...')
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/`
        }
      })
      if (error) throw error
    } catch (err) {
      setAuthStatus(`Google sign-in failed: ${err.message}`)
    }
  }

  const sendOtp = async () => {
    if (authFlow !== 'signup') {
      setAuthStatus('OTP is only for Sign Up. Use password for Sign In.')
      return
    }
    const email = authEmail.trim().toLowerCase()
    if (!email) {
      setAuthStatus('Enter email first')
      return
    }
    if (!email.endsWith('@gmail.com')) {
      setAuthStatus('Only @gmail.com is allowed for Email OTP right now.')
      return
    }
    try {
      setAuthStatus('Sending OTP...')
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: {
          shouldCreateUser: authFlow === 'signup'
        }
      })
      if (error) throw error
      setAuthStatus('OTP sent. Check inbox/spam and enter code.')
    } catch (err) {
      setAuthStatus(`OTP send failed: ${err.message}`)
    }
  }

  const verifyOtp = async () => {
    const email = authEmail.trim().toLowerCase()
    if (!email || !authOtp.trim()) {
      setAuthStatus('Enter email and OTP code')
      return
    }
    if (!email.endsWith('@gmail.com')) {
      setAuthStatus('Only @gmail.com is allowed for Email OTP right now.')
      return
    }
    try {
      setAuthStatus('Verifying OTP...')
      const { error } = await supabase.auth.verifyOtp({
        email,
        token: authOtp.trim(),
        type: 'email'
      })
      if (error) throw error
      setAuthStatus('Signed in')
    } catch (err) {
      setAuthStatus(`OTP verify failed: ${err.message}`)
    }
  }

  const signInWithEmailPassword = async () => {
    const email = authEmail.trim().toLowerCase()
    const password = authPassword
    if (!email || !password) {
      setAuthStatus('Enter email and password')
      return
    }
    if (!email.endsWith('@gmail.com')) {
      setAuthStatus('Only @gmail.com is allowed right now.')
      return
    }
    try {
      setAuthStatus('Signing in...')
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error
      setAuthStatus('Signed in')
    } catch (err) {
      setAuthStatus(`Sign in failed: ${err.message}`)
    }
  }

  const completeProfileSetup = async () => {
    const provider = session?.user?.app_metadata?.provider
    const isGoogleAccount = provider === 'google'
    if (!profileName.trim() || !profileProfession.trim() || (!isGoogleAccount && !profilePassword.trim()) || !profileAppPassword.trim()) {
      setProfileStatus('All fields are required')
      return
    }
    try {
      setProfileStatus('Saving profile...')
      const signupMethod = provider === 'google' ? 'google' : 'email_otp'
      const updatePayload = {
        data: {
          full_name: profileName.trim(),
          profession: profileProfession.trim(),
          signup_method: session?.user?.user_metadata?.signup_method || signupMethod,
          profile_completed: true
        }
      }
      if (!isGoogleAccount) {
        updatePayload.password = profilePassword
      }
      const { error: metaError } = await supabase.auth.updateUser(updatePayload)
      if (metaError) throw metaError

      const payload = {
        email: session?.user?.email || '',
        app_password: profileAppPassword.trim(),
        smtp_host: 'smtp.gmail.com',
        smtp_port: 587,
        smtp_username: session?.user?.email || '',
        smtp_from_email: session?.user?.email || '',
        use_tls: true
      }
      const senderRes = await apiFetch(`${API_BASE}/api/automation/sender/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!senderRes.ok) {
        let msg = 'base mail setup failed'
        try {
          const j = await senderRes.json()
          msg = j?.detail || msg
        } catch {
          // ignore
        }
        throw new Error(msg)
      }

      setSenderEmail(session?.user?.email || '')
      setRequesterEmail(session?.user?.email || '')
      setSenderConfigured(true)
      setShowSenderSetup(false)
      setNeedsProfileSetup(false)
      setProfileStatus('Profile setup complete')
    } catch (err) {
      setProfileStatus(`Setup failed: ${err.message}`)
    }
  }

  const doLogout = async () => {
    await supabase.auth.signOut()
  }

  const completePasswordRecovery = async () => {
    if (!recoveryPassword.trim() || recoveryPassword.trim().length < 8) {
      setRecoveryStatus('Password must be at least 8 characters.')
      return
    }
    try {
      setRecoveryStatus('Updating password...')
      const { error } = await supabase.auth.updateUser({ password: recoveryPassword.trim() })
      if (error) throw error
      setRecoveryStatus('Password updated. You can now sign in.')
      setRecoveryMode(false)
      setRecoveryPassword('')
      await supabase.auth.signOut()
    } catch (err) {
      setRecoveryStatus(`Reset failed: ${err.message}`)
    }
  }

  const sendPasswordReset = async () => {
    const email = (resetEmail || authEmail || '').trim()
    if (!email) {
      setAuthStatus('Enter email for password reset')
      return
    }
    if (!email.toLowerCase().endsWith('@gmail.com')) {
      setAuthStatus('Only @gmail.com is allowed for Email OTP right now.')
      return
    }
    try {
      setAuthStatus('Sending password reset email...')
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/`
      })
      if (error) throw error
      setAuthStatus('Password reset email sent. Check inbox/spam.')
    } catch (err) {
      setAuthStatus(`Password reset failed: ${err.message}`)
    }
  }

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket('ws://localhost:8765')
      wsRef.current = ws

      ws.onopen = () => {
        setStatus('Connected | Ready')
      }

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'volume') {
          setVolume(data.value)
          if (data.value > 0.05) {
            setStatus('Aria is speaking...')
          } else {
            setStatus('Connected | Ready')
          }
        }
      }

      ws.onclose = () => {
        setStatus('Disconnected. Waiting for main.py...')
        setTimeout(connect, 2000)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  useEffect(() => {
    const getDevices = async () => {
      try {
        await navigator.mediaDevices.getUserMedia({ video: true })
        const devices = await navigator.mediaDevices.enumerateDevices()
        const videoDevices = devices.filter((device) => device.kind === 'videoinput')
        setCameras(videoDevices)

        if (videoDevices.length > 0) {
          const obs = videoDevices.find(
            (d) => d.label.toLowerCase().includes('obs') || d.label.toLowerCase().includes('unity')
          )
          setSelectedCameraId(obs ? obs.deviceId : videoDevices[0].deviceId)
        }
      } catch (err) {
        console.error('Error enumerating devices:', err)
      }
    }
    getDevices()
  }, [])

  useEffect(() => {
    if (!selectedCameraId) return

    const startCamera = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { deviceId: { exact: selectedCameraId } }
        })
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
      } catch (err) {
        console.error('Error accessing webcam:', err)
      }
    }

    startCamera()
  }, [selectedCameraId])

  const fetchHistory = async () => {
    try {
      const res = await apiFetch(`${API_BASE}/api/data/history`)
      const data = await res.json()
      setHistoryItems(data.items || [])
      setDataStatus('Synced')
    } catch (err) {
      console.error(err)
      setDataStatus('Data backend offline')
    }
  }

  useEffect(() => {
    if (activePage === 'data') {
      fetchHistory()
    }
    if (activePage === 'los') {
      fetchLosHistory()
      fetchAgentMessages(activeAgent)
    }
    if (activePage === 'automation') {
      loadDefaultSender()
      fetchAutomationHistory()
      if (requesterEmail) checkSenderConfig(requesterEmail)
    }
    if (activePage === 'meetings') {
      fetchMeetings()
    }
    if (activePage === 'connects') {
      fetchConnects()
    }
    if (activePage === 'home') {
      fetchSessionDeviceAuto()
      fetchSessionPlatformCheck()
      fetchSessionStatus()
    }
  }, [activePage])

  useEffect(() => {
    if (activePage !== 'home') return
    const id = setInterval(() => {
      fetchSessionStatus()
      fetchSessionLogs()
    }, 2000)
    return () => clearInterval(id)
  }, [activePage])

  useEffect(() => {
    if (activePage === 'los') {
      fetchAgentMessages(activeAgent)
    }
  }, [activeAgent])

  useEffect(() => {
    if (!agentInterfaceOpen) return
    fetchAgentMessages(activeAgent)
  }, [agentInterfaceOpen])

  const onFilesSelected = async (event) => {
    const files = Array.from(event.target.files || [])
    if (!files.length) return

    const form = new FormData()
    for (const file of files) {
      form.append('files', file)
    }

    try {
      setDataStatus('Uploading...')
      await apiFetch(`${API_BASE}/api/data/upload`, { method: 'POST', body: form })
      await fetchHistory()
    } catch (err) {
      console.error(err)
      setDataStatus('Upload failed')
    }

    event.target.value = ''
  }

  const onAddLink = async () => {
    const trimmed = linkInput.trim()
    if (!trimmed) return

    try {
      setDataStatus('Ingesting link...')
      await apiFetch(`${API_BASE}/api/data/link`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmed })
      })
      setLinkInput('')
      await fetchHistory()
    } catch (err) {
      console.error(err)
      setDataStatus('Link ingest failed')
    }
  }

  const deleteHistoryItem = async (id) => {
    try {
      setDataStatus('Deleting...')
      await apiFetch(`${API_BASE}/api/data/${id}`, { method: 'DELETE' })
      await fetchHistory()
    } catch (err) {
      console.error(err)
      setDataStatus('Delete failed')
    }
  }

  const reprocessHistoryItem = async (id) => {
    try {
      setDataStatus('Reprocessing...')
      await apiFetch(`${API_BASE}/api/data/reprocess/${id}`, { method: 'POST' })
      await fetchHistory()
    } catch (err) {
      console.error(err)
      setDataStatus('Reprocess failed')
    }
  }

  const onAddText = async () => {
    const trimmed = textInput.trim()
    if (!trimmed) return
    try {
      setDataStatus('Saving text...')
      await apiFetch(`${API_BASE}/api/data/text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed, title: `note_${new Date().toISOString()}` })
      })
      setTextInput('')
      await fetchHistory()
    } catch (err) {
      console.error(err)
      setDataStatus('Text save failed')
    }
  }

  const formatDateTime = (iso) => {
    try {
      return new Date(iso).toLocaleString()
    } catch {
      return iso
    }
  }

  const getLosGroups = () => {
    const groups = {}
    for (const item of losItems) {
      const key = (item.group_name || 'General').trim() || 'General'
      if (!groups[key]) groups[key] = []
      groups[key].push(item)
    }
    const out = Object.entries(groups).map(([name, items]) => {
      const sorted = [...items].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      return {
        name,
        latestAt: sorted[0]?.created_at || '',
        items: sorted
      }
    })
    out.sort((a, b) => new Date(b.latestAt) - new Date(a.latestAt))
    return out
  }

  const fetchLosHistory = async () => {
    try {
      const res = await apiFetch(`${API_BASE}/api/los/history`)
      const data = await res.json()
      setLosItems(data.items || [])
      setLosStatus('Synced')
    } catch (err) {
      console.error(err)
      setLosStatus('LOS backend offline')
    }
  }

  const fetchAutomationHistory = async () => {
    try {
      const owner = (session?.user?.email || requesterEmail || senderEmail || '').trim()
      const q = owner ? `?requester_email=${encodeURIComponent(owner)}` : ''
      const res = await apiFetch(`${API_BASE}/api/automation/history${q}`)
      const data = await res.json()
      setAutomationItems(data.items || [])
      setAutomationStatus('Synced')
    } catch (err) {
      console.error(err)
      setAutomationStatus('Automation backend offline')
    }
  }


  const fetchMeetings = async () => {
    try {
      const res = await apiFetch(`${API_BASE}/api/meetings`)
      const data = await res.json()
      setMeetingItems(data.items || [])
      setMeetingsStatus('Synced')
    } catch (err) {
      console.error(err)
      setMeetingsStatus('Meetings backend offline')
    }
  }

  const openMeeting = async (id) => {
    try {
      const res = await apiFetch(`${API_BASE}/api/meetings/${id}`)
      const data = await res.json()
      setSelectedMeeting(data)
    } catch (err) {
      console.error(err)
      setMeetingsStatus('Failed to open meeting')
    }
  }

  const askMeeting = async () => {
    if (!selectedMeeting?.id || !meetingQuery.trim()) return
    try {
      setMeetingReply('Thinking...')
      const res = await apiFetch(`${API_BASE}/api/meetings/${selectedMeeting.id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: meetingQuery.trim() })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'query failed')
      setMeetingReply(data.reply || 'No answer.')
    } catch (err) {
      setMeetingReply(`Error: ${err.message}`)
    }
  }

  const fetchConnects = async () => {
    try {
      const res = await apiFetch(`${API_BASE}/api/connects`)
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Failed to fetch connects')
      setConnectItems(data.items || [])
      setConnectStatus('Synced')
    } catch (err) {
      console.error(err)
      setConnectStatus(`Connects backend offline: ${err.message}`)
    }
  }

  const saveConnect = async () => {
    const name = (connectName || '').trim()
    const email = (connectEmail || '').trim()
    if (!name || !email) {
      setConnectStatus('Name and email are required')
      return
    }
    try {
      setConnectStatus('Saving...')
      const res = await apiFetch(`${API_BASE}/api/connects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email })
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Failed to save contact')
      setConnectName('')
      setConnectEmail('')
      await fetchConnects()
    } catch (err) {
      console.error(err)
      setConnectStatus(`Save failed: ${err.message}`)
    }
  }

  const deleteConnect = async (id) => {
    try {
      setConnectStatus('Deleting...')
      const res = await apiFetch(`${API_BASE}/api/connects/${encodeURIComponent(id)}`, { method: 'DELETE' })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Failed to delete contact')
      await fetchConnects()
    } catch (err) {
      console.error(err)
      setConnectStatus(`Delete failed: ${err.message}`)
    }
  }

  const fetchSessionDeviceAuto = async () => {
    try {
      const res = await apiFetch(`${API_BASE}/api/session/device-auto`)
      const data = await res.json()
      setSessionDevice({
        id: data.selected_device_id,
        name: data.selected_device_name
      })
    } catch (err) {
      console.error(err)
    }
  }

  const fetchSessionPlatformCheck = async () => {
    try {
      const res = await apiFetch(`${API_BASE}/api/session/platform-check`)
      const data = await res.json()
      setSessionPlatform(data || null)
    } catch (err) {
      console.error(err)
    }
  }

  const validateAudioFlow = async () => {
    try {
      setAudioValidation('Validating audio flow...')
      const selectedId = sessionDevice?.id
      const url = selectedId != null
        ? `${API_BASE}/api/session/audio-validate?device_id=${encodeURIComponent(selectedId)}`
        : `${API_BASE}/api/session/audio-validate`
      const res = await apiFetch(url)
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Audio validation failed')
      setAudioValidation(
        data.flowing
          ? `Audio OK (peak RMS ${data.peak_rms}).`
          : `Audio not detected (peak RMS ${data.peak_rms}). ${data.hint || ''}`
      )
    } catch (err) {
      setAudioValidation(`Validation error: ${err.message}`)
    }
  }

  const fetchSessionStatus = async () => {
    try {
      const res = await apiFetch(`${API_BASE}/api/session/status`)
      const data = await res.json()
      setSessionStatus(data.running ? `Running (pid ${data.pid})` : 'Idle')
    } catch (err) {
      console.error(err)
      setSessionStatus('Backend offline')
    }
  }

  const fetchSessionLogs = async () => {
    try {
      const res = await apiFetch(`${API_BASE}/api/session/logs?limit=250`)
      const data = await res.json()
      setSessionLogs(data.items || [])
      setSessionTranscriptLogs(data.transcript_items || [])
    } catch (err) {
      console.error(err)
    }
  }

  const startMeetingSession = async () => {
    const lockedEmail = (session?.user?.email || '').trim().toLowerCase()
    if (!sessionMeetingUrl.trim() || !lockedEmail) {
      setSessionStatus('Meeting URL and profile email are required')
      return
    }
    try {
      setSessionStatus('Starting...')
      const rawLink = sessionMeetingUrl.trim()
      const normalizedLink = rawLink
        .replace(/^https?:\/\//i, '')
        .replace(/^\/+/, '')
      const payload = {
        meeting_url: `https://${normalizedLink}`,
        profile_email: lockedEmail,
        assistant_name: sessionAssistantName.trim() || 'Aria',
        avatar_mode: sessionAvatarMode
      }
      const res = await apiFetch(`${API_BASE}/api/session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Session start failed')
      setSessionStatus(`Running (pid ${data.pid})`)
      if (data.selected_device_id != null) {
        setSessionDevice({ id: data.selected_device_id, name: data.selected_device_name || '' })
      }
    } catch (err) {
      console.error(err)
      setSessionStatus(`Start failed: ${err.message}`)
    }
  }

  const stopMeetingSession = async () => {
    try {
      setSessionStatus('Stopping...')
      await apiFetch(`${API_BASE}/api/session/stop`, { method: 'POST' })
      setSessionStatus('Idle')
    } catch (err) {
      console.error(err)
      setSessionStatus('Stop failed')
    }
  }

  const formatSeconds = (n) => {
    const s = Number(n || 0)
    const mm = Math.floor(s / 60)
    const ss = Math.floor(s % 60)
    return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
  }

  const loadDefaultSender = async () => {
    try {
      const owner = (session?.user?.email || requesterEmail || senderEmail || '').trim()
      const q = owner ? `?requester_email=${encodeURIComponent(owner)}` : ''
      const res = await apiFetch(`${API_BASE}/api/automation/sender-default${q}`)
      const data = await res.json()
      if (data?.configured && data?.item) {
        const item = data.item
        setSenderConfigured(true)
        setShowSenderSetup(false)
        setSenderEmail(item.email || '')
        setRequesterEmail(item.email || '')
        setSenderHost(item.smtp_host || 'smtp.gmail.com')
        setSenderPort(String(item.smtp_port || 587))
        setSenderUseTls(Boolean(item.use_tls))
      }
    } catch {
      // ignore
    }
  }

  const checkSenderConfig = async (email) => {
    const e = (email || '').trim()
    if (!e || !e.includes('@')) {
      setSenderConfigured(false)
      return
    }
    try {
      const res = await apiFetch(`${API_BASE}/api/automation/sender/${encodeURIComponent(e)}`)
      const data = await res.json()
      setSenderConfigured(!!data?.configured)
      setShowSenderSetup(!data?.configured)
      if (data?.configured && data?.item) {
        setSenderHost(data.item.smtp_host || 'smtp.gmail.com')
        setSenderPort(String(data.item.smtp_port || '587'))
        setSenderUseTls(Boolean(data.item.use_tls))
      }
    } catch {
      setSenderConfigured(false)
    }
  }

  const saveSenderConfig = async () => {
    if (!senderEmail.trim() || !senderAppPassword.trim()) {
      setAutomationStatus('Sender email and app password are required')
      return
    }
    try {
      setAutomationStatus('Saving sender setup...')
      const payload = {
        email: senderEmail.trim(),
        app_password: senderAppPassword.trim(),
        smtp_host: senderHost.trim() || 'smtp.gmail.com',
        smtp_port: parseInt(senderPort || '587', 10),
        smtp_username: senderEmail.trim(),
        smtp_from_email: senderEmail.trim(),
        use_tls: senderUseTls
      }
      const res = await apiFetch(`${API_BASE}/api/automation/sender/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      let data = {}
      try {
        data = await res.json()
      } catch {
        data = {}
      }
      if (!res.ok) throw new Error(data?.detail || 'Failed to save sender')
      setSenderAppPassword('')
      setRequesterEmail(senderEmail.trim())
      setSenderConfigured(true)
      setShowSenderSetup(false)
      setAutomationStatus('Sender configured')
    } catch (err) {
      console.error(err)
      setAutomationStatus(`Sender setup failed: ${err.message}`)
    }
  }

  const uploadSharedAttachments = async (event) => {
    const files = Array.from(event.target.files || [])
    if (!files.length) return
    const form = new FormData()
    for (const f of files) form.append('files', f)
    try {
      setAutomationStatus(`Uploading attachments... (${files.length} file(s))`)
      const res = await apiFetch(`${API_BASE}/api/automation/attachments`, { method: 'POST', body: form })
      let data = {}
      let raw = ''
      try {
        raw = await res.text()
        data = raw ? JSON.parse(raw) : {}
      } catch {
        data = {}
      }
      if (!res.ok) throw new Error(data?.detail || raw || `Attachment upload failed (HTTP ${res.status})`)
      setSharedAttachments((prev) => [...prev, ...(data.items || [])].slice(0, 24))
      setAutomationStatus(`Attachments uploaded (${(data.items || []).length})`)
    } catch (err) {
      setAutomationStatus(`Attachment upload failed: ${err.message}`)
    }
    event.target.value = ''
  }

  const removeSharedAttachment = (idx) => {
    setSharedAttachments((prev) => prev.filter((_, i) => i !== idx))
  }

  const addRecipientRow = () => {
    setRecipientRows((prev) => {
      if (prev.length >= 12) return prev
      return [...prev, { recipient: '', subject: '', message: '', attachments: [] }]
    })
  }

  const removeRecipientRow = (idx) => {
    setRecipientRows((prev) => prev.filter((_, i) => i !== idx))
  }

  const updateRecipientRow = (idx, patch) => {
    setRecipientRows((prev) => prev.map((row, i) => (i === idx ? { ...row, ...patch } : row)))
  }

  const uploadRowAttachments = async (idx, event) => {
    const files = Array.from(event.target.files || [])
    if (!files.length) return
    const form = new FormData()
    for (const f of files) form.append('files', f)
    try {
      setAutomationStatus(`Uploading row attachments... (${files.length} file(s))`)
      const res = await apiFetch(`${API_BASE}/api/automation/attachments`, { method: 'POST', body: form })
      let data = {}
      let raw = ''
      try {
        raw = await res.text()
        data = raw ? JSON.parse(raw) : {}
      } catch {
        data = {}
      }
      if (!res.ok) throw new Error(data?.detail || raw || `Attachment upload failed (HTTP ${res.status})`)
      const uploaded = data.items || []
      setRecipientRows((prev) =>
        prev.map((row, i) =>
          i === idx ? { ...row, attachments: [...(row.attachments || []), ...uploaded].slice(0, 24) } : row
        )
      )
      setAutomationStatus('Row attachments uploaded')
    } catch (err) {
      setAutomationStatus(`Attachment upload failed: ${err.message}`)
    }
    event.target.value = ''
  }

  const removeRowAttachment = (rowIdx, attIdx) => {
    setRecipientRows((prev) =>
      prev.map((row, i) =>
        i === rowIdx ? { ...row, attachments: (row.attachments || []).filter((_, j) => j !== attIdx) } : row
      )
    )
  }

  const scheduleAutomationEmail = async () => {
    if (!requesterEmail.trim()) return
    try {
      setAutomationStatus('Scheduling...')
      let scheduleAtIso = null
      if (scheduleDate && scheduleTime24h) {
        scheduleAtIso = new Date(`${scheduleDate}T${scheduleTime24h}:00`).toISOString()
      }
      const recipientsArr = recipientsInput
        .split(/[\n,;\t]+/)
        .map((x) => x.trim())
        .filter(Boolean)
      if (recipientsArr.length > 12) {
        setAutomationStatus('Maximum 12 recipients allowed')
        return
      }
      const resolvedBulkMode =
        sendMode === 'single'
          ? 'same_for_all'
          : bulkSendMode === 'custom'
            ? 'custom_per_email'
            : 'same_for_all'

      let recipientEntries = []
      if (resolvedBulkMode === 'custom_per_email') {
        recipientEntries = recipientRows
          .map((row) => ({
            recipient: (row.recipient || '').trim(),
            subject: (row.subject || '').trim(),
            message: (row.message || '').trim(),
            attachment_paths: (row.attachments || []).map((a) => a.path).join(',')
          }))
          .filter((row) => row.recipient || row.subject || row.message || row.attachment_paths)
        if (!recipientEntries.length || recipientEntries.length > 12) {
          setAutomationStatus('Use 1-12 custom recipient rows')
          return
        }
      }
      const payload = {
        requester_email: (requesterEmail || senderEmail).trim(),
        recipients: sendMode === 'single' ? (recipientsInput.split(',')[0] || '').trim() : recipientsInput.trim(),
        mode: automationMode,
        bulk_mode: resolvedBulkMode,
        recipient_entries: recipientEntries,
        shared_attachment_paths: sharedAttachments.map((x) => x.path),
        instruction: automationInstruction.trim(),
        subject: emailSubject.trim(),
        message: emailBody.trim(),
        schedule_at: scheduleAtIso,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
      }
      const res = await apiFetch(`${API_BASE}/api/automation/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || 'Failed to schedule')
      setAutomationInstruction('')
      setEmailSubject('')
      setEmailBody('')
      setScheduleDate('')
      setScheduleTime24h('')
      await fetchAutomationHistory()
    } catch (err) {
      console.error(err)
      setAutomationStatus(`Schedule failed: ${err.message}`)
    }
  }

  const saveLosNote = async (text, sourceMode = 'typed') => {
    const trimmed = (text || '').trim()
    if (!trimmed) return
    try {
      setLosStatus('Organizing and saving...')
      const res = await apiFetch(`${API_BASE}/api/los/note`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed, source_mode: sourceMode })
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data?.detail || 'Save failed')
      }
      const reminderCount = Number(data?.automation_reminder?.count || 0)
      if (reminderCount > 0) {
        setLosStatus(`Saved. Auto reminder scheduled (${reminderCount}).`)
      } else {
        setLosStatus('Saved')
      }
      setLosInput('')
      await fetchLosHistory()
    } catch (err) {
      console.error(err)
      setLosStatus(`Save failed: ${err.message || 'unknown error'}`)
    }
  }

  const fetchAgentMessages = async (agentName) => {
    try {
      const res = await apiFetch(`${API_BASE}/api/los/subagents/${encodeURIComponent(agentName)}/messages`)
      const data = await res.json()
      setAgentChat(data.items || [])
    } catch (err) {
      console.error(err)
      setLosStatus('Sub-agent history unavailable')
    }
  }

  const sendAgentMessage = async (sourceMode = 'typed', overrideText = '') => {
    const trimmed = (overrideText || agentInput).trim()
    if (!trimmed) return
    try {
      setLosStatus(`Talking to ${activeAgent}...`)
      const localUser = {
        id: `local-user-${Date.now()}`,
        role: 'user',
        message: trimmed,
        created_at: new Date().toISOString()
      }
      setAgentExecutionStatus((prev) => ({ ...prev, [activeAgent]: 'working' }))
      setAgentChat((prev) => [...prev, localUser])
      setAgentInput('')
      const res = await apiFetch(`${API_BASE}/api/los/subagents/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_name: activeAgent,
          message: trimmed,
          source_mode: sourceMode,
          autonomy_mode: agentAutonomyMode
        })
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data?.detail || 'Sub-agent reply failed')
      }
      const statusTag = inferExecutionStatus(data, agentAutonomyMode)
      setAgentExecutionStatus((prev) => ({ ...prev, [activeAgent]: statusTag }))
      const localAssistant = {
        id: data?.message?.id || `local-assistant-${Date.now()}`,
        role: 'assistant',
        message: data?.reply || 'Noted.',
        created_at: data?.message?.created_at || new Date().toISOString()
      }
      setAgentChat((prev) => [...prev, localAssistant])
      setLosStatus('Synced')
    } catch (err) {
      console.error(err)
      setLosStatus('Sub-agent reply failed')
      fetchAgentMessages(activeAgent)
    }
  }

  const startSpeechToLos = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      setLosStatus('Speech recognition is not supported in this browser')
      return
    }
    const rec = new SR()
    rec.lang = 'en-US'
    rec.interimResults = false
    rec.maxAlternatives = 1
    setIsListeningLos(true)
    rec.onresult = (event) => {
      const spoken = event.results?.[0]?.[0]?.transcript || ''
      setLosInput(spoken)
      saveLosNote(spoken, 'voice')
    }
    rec.onerror = () => setLosStatus('Voice input failed')
    rec.onend = () => setIsListeningLos(false)
    rec.start()
  }

  const startSpeechToAgent = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      setLosStatus('Speech recognition is not supported in this browser')
      return
    }
    const rec = new SR()
    rec.lang = 'en-US'
    rec.interimResults = false
    rec.maxAlternatives = 1
    setIsListeningAgent(true)
    rec.onresult = (event) => {
      const spoken = event.results?.[0]?.[0]?.transcript || ''
      setAgentInput(spoken)
      setTimeout(() => sendAgentMessage('voice', spoken), 0)
    }
    rec.onerror = () => setLosStatus('Voice input failed')
    rec.onend = () => setIsListeningAgent(false)
    rec.start()
  }

  const startAgentSetup = () => {
    const p = (navigator.platform || '').toLowerCase()
    const isMac = p.includes('mac')
    const isWindows = p.includes('win')
    const installerUrl = isMac ? AGENT_INSTALLER_MAC_URL : (isWindows ? AGENT_INSTALLER_WIN_URL : '')

    if (!installerUrl) {
      const osLabel = isMac ? 'macOS' : (isWindows ? 'Windows' : 'your OS')
      setAgentInstallStatus(
        `Installer link not configured for ${osLabel}. Set VITE_AGENT_INSTALLER_WIN_URL / VITE_AGENT_INSTALLER_MAC_URL in dashboard env.`
      )
      return
    }

    window.open(installerUrl, '_blank', 'noopener,noreferrer')
    if (AGENT_SETUP_GUIDE_URL) {
      window.open(AGENT_SETUP_GUIDE_URL, '_blank', 'noopener,noreferrer')
    }
    setAgentInstallStatus(
      `Installer opened for ${isMac ? 'macOS' : 'Windows'}. Complete installer, then do one-time OBS + audio setup and click Validate Audio Flow.`
    )
  }

  const selectedSetupPlatform = setupPlatformOverride || (
    (sessionPlatform?.os || '').toLowerCase().includes('darwin') ? 'mac' : 'windows'
  )
  const setupGuide = selectedSetupPlatform === 'mac'
    ? {
        driver: 'BlackHole',
        steps: [
          'Install OBS Studio from obsproject.com and open OBS.',
          'In OBS, click Start Virtual Camera.',
          'In OBS, add your camera source (Sources -> + -> Video Capture Device), then confirm preview is visible.',
          'Disconnect extra audio and mic devices from this Mac (keep only the devices you want for agent machine).',
          'Install BlackHole 2ch and open System Settings -> Sound.',
          'In Sound -> Output, select BlackHole 2ch.',
          'In Sound -> Input, select BlackHole 2ch.',
          'Open meeting app (Zoom/Meet/Teams). Set Speaker/Output = BlackHole 2ch.',
          'In meeting app, set Microphone/Input = BlackHole 2ch.',
          'Return to Aria Dashboard Home, click Refresh.',
          'Click Validate Audio Flow and confirm it says Audio OK.',
          'Paste meeting link and click Join Meeting.',
        ],
      }
    : {
        driver: 'VB-CABLE',
        steps: [
          'Install OBS Studio from obsproject.com and open OBS.',
          'In OBS, click Start Virtual Camera.',
          'In OBS, add your camera source (Sources -> + -> Video Capture Device), then confirm preview is visible.',
          'Disconnect extra audio and mic devices from this PC (keep only the devices you want for agent machine).',
          'Install VB-CABLE and restart Windows if installer asks.',
          'Open mmsys.cpl.',
          'In Playback tab, right-click CABLE Input (VB-Audio Virtual Cable) -> Set as Default Device.',
          'In Recording tab, right-click CABLE Output (VB-Audio Virtual Cable) -> Set as Default Device.',
          'Open meeting app (Zoom/Meet/Teams). Set Speaker/Output = CABLE Input (VB-Audio Virtual Cable).',
          'In meeting app, set Microphone/Input = CABLE Output (VB-Audio Virtual Cable).',
          'Return to Aria Dashboard Home, click Refresh.',
          'Click Validate Audio Flow and confirm it says Audio OK.',
          'Paste meeting link and click Join Meeting.',
        ],
      }

  if (authLoading) {
    return (
      <div className="app-container">
        <main className="canvas-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <section className="data-card" style={{ width: 'min(520px, 92vw)', textAlign: 'center' }}>
            <h2>CyclopsAI</h2>
            <p>Checking authentication...</p>
          </section>
        </main>
      </div>
    )
  }

  if (!session) {
    if (recoveryMode) {
      return (
        <div className="app-container">
          <main className="canvas-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <section className="data-card" style={{ width: 'min(520px, 92vw)' }}>
              <h2>Reset Password</h2>
              <p>Enter a new password for your account.</p>
              <label className="data-label">New password</label>
              <input
                className="data-input"
                type="password"
                placeholder="At least 8 characters"
                value={recoveryPassword}
                onChange={(e) => setRecoveryPassword(e.target.value)}
              />
              <button className="add-btn" onClick={completePasswordRecovery}>Update Password</button>
              {recoveryStatus && <p style={{ marginTop: '12px', color: '#9aa7be' }}>{recoveryStatus}</p>}
            </section>
          </main>
        </div>
      )
    }
    return (
      <div className="app-container">
        <main className="canvas-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <section className="data-card" style={{ width: 'min(520px, 92vw)' }}>
            <h2>Sign in to CyclopsAI</h2>
            <p>Google works normally. Email Sign Up uses OTP; Email Sign In uses password.</p>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
              <button className="add-btn" onClick={() => setAuthFlow('signin')} style={{ opacity: authFlow === 'signin' ? 1 : 0.75 }}>
                Sign In
              </button>
              <button className="add-btn" onClick={() => setAuthFlow('signup')} style={{ opacity: authFlow === 'signup' ? 1 : 0.75 }}>
                Sign Up
              </button>
            </div>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
              <button className="add-btn" onClick={() => setAuthMode('google')}>Google</button>
              <button className="add-btn" onClick={() => setAuthMode('otp')}>Email</button>
            </div>
            {authMode === 'google' ? (
              <button className="add-btn" onClick={signInWithGoogle}>
                {authFlow === 'signup' ? 'Sign up with Google' : 'Sign in with Google'}
              </button>
            ) : (
              <>
                <label className="data-label">Email</label>
                <input
                  className="data-input"
                  type="email"
                  placeholder="you@gmail.com"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                />
                {authFlow === 'signup' ? (
                  <>
                    <button className="add-btn" onClick={sendOtp}>Send OTP for Sign Up</button>
                    <label className="data-label" style={{ marginTop: '12px' }}>OTP code</label>
                    <input
                      className="data-input"
                      type="text"
                      placeholder="Enter OTP from email"
                      value={authOtp}
                      onChange={(e) => setAuthOtp(e.target.value)}
                    />
                    <button className="add-btn" onClick={verifyOtp}>Verify OTP</button>
                  </>
                ) : (
                  <>
                    <label className="data-label" style={{ marginTop: '12px' }}>Password</label>
                    <input
                      className="data-input"
                      type="password"
                      placeholder="Enter your password"
                      value={authPassword}
                      onChange={(e) => setAuthPassword(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          signInWithEmailPassword()
                        }
                      }}
                    />
                    <button className="add-btn" onClick={signInWithEmailPassword}>Sign In with Email</button>
                    <label className="data-label" style={{ marginTop: '12px' }}>Forgot password</label>
                    <input
                      className="data-input"
                      type="email"
                      placeholder="Enter your email for reset link"
                      value={resetEmail}
                      onChange={(e) => setResetEmail(e.target.value)}
                    />
                    <button className="add-btn" onClick={sendPasswordReset}>Send password reset email</button>
                  </>
                )}
              </>
            )}
            <div style={{ marginTop: '10px' }}>
              <button className="add-btn" onClick={() => setShowAppPasswordHelp((v) => !v)}>
                Base Mail Help
              </button>
            </div>
            {showAppPasswordHelp && (
              <div className="history-meta" style={{ marginTop: '8px' }}>
                Base mail password note: you cannot recover old Gmail app password. Generate a new app password:
                Google Account - Security - 2-Step Verification ON - App passwords - Mail - Generate 16-char password.
                Then update it after login in Automation - Permanent Sender Setup.
              </div>
            )}
            <p className="history-meta" style={{ marginTop: '8px' }}>
              If account was created with Google, use Google sign-in. For email accounts: sign up with OTP, then sign in with password.
            </p>
            {authStatus && <p style={{ marginTop: '12px', color: '#9aa7be' }}>{authStatus}</p>}
          </section>
        </main>
      </div>
    )
  }

  if (needsProfileSetup) {
    const isGoogleAccount = session?.user?.app_metadata?.provider === 'google'
    return (
      <div className="app-container">
        <main className="canvas-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <section className="data-card" style={{ width: 'min(620px, 94vw)' }}>
            <h2>Complete Your Account Setup</h2>
            <p>Finish this once to continue.</p>
            <label className="data-label">Name</label>
            <input className="data-input" type="text" value={profileName} onChange={(e) => setProfileName(e.target.value)} />
            <label className="data-label">Profession</label>
            <input className="data-input" type="text" value={profileProfession} onChange={(e) => setProfileProfession(e.target.value)} />
            {!isGoogleAccount && (
              <>
                <label className="data-label">Account password (used for future sign in)</label>
                <input
                  className="data-input"
                  type="password"
                  placeholder="Set a strong password"
                  value={profilePassword}
                  onChange={(e) => setProfilePassword(e.target.value)}
                />
              </>
            )}
            <label className="data-label">Base mail app password</label>
            <input
              className="data-input"
              type="password"
              placeholder="16-character app password"
              value={profileAppPassword}
              onChange={(e) => setProfileAppPassword(e.target.value)}
            />
            <div className="history-meta" style={{ marginBottom: '10px' }}>
              Gmail guide: Google Account - Security - 2-Step Verification ON - App passwords - select Mail - copy 16-character password.
            </div>
            <button className="add-btn" onClick={completeProfileSetup}>Save and Continue</button>
            {profileStatus && <p style={{ marginTop: '12px', color: '#9aa7be' }}>{profileStatus}</p>}
          </section>
        </main>
      </div>
    )
  }

  return (
    <div className="app-container">
      <header className="header" style={{ position: 'relative' }}>
        <button className="menu-button" onClick={() => setMenuOpen((prev) => !prev)} aria-label="Open menu">
          <span></span>
          <span></span>
          <span></span>
        </button>

        <div className="header-main">
          <div className="header-title-wrap">
            <h1>Cyclops AI - Command Center</h1>
            <p>Live Neural 3D Human Interface</p>
          </div>
          <div className="header-user-actions">
            <span className="history-meta" style={{ marginTop: 0 }}>{session?.user?.email || ''}</span>
            <span className="history-meta" style={{ marginTop: 0 }}>
              {displayName || 'Name not set'} | {displayProfession || 'Profession not set'}
            </span>
            <button className="add-btn" onClick={() => setShowAppPasswordHelp((v) => !v)}>Base Mail Help</button>
            <button className="delete-btn" onClick={doLogout}>Logout</button>
          </div>
        </div>
        {showAppPasswordHelp && (
          <div style={{ marginTop: '10px', maxWidth: '520px', marginLeft: 'auto' }} className="history-row">
            <div className="history-meta">
              Base mail password note: app passwords cannot be recovered. Generate a new Gmail app password and update it in Automation sender setup.
            </div>
          </div>
        )}

        {activePage === 'home' && (
          <div className="header-home-controls">
            <select
              value={avatarMode}
              onChange={(e) => {
                const newValue = e.target.value
                setAvatarMode(newValue)
                if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                  const msg = JSON.stringify({ type: 'change_avatar', avatar: newValue })
                  wsRef.current.send(msg)
                  setStatus(`Switching to ${newValue} avatar...`)
                }
              }}
              style={{ padding: '8px', background: '#1e1e2d', color: '#00f2fe', border: '1px solid #00f2fe', borderRadius: '4px' }}
            >
              <option value="3d">3D Generated Avatar (Default)</option>
              <option value="female">Female Avatar</option>
            </select>

            {cameras.length > 0 && (
              <select
                value={selectedCameraId}
                onChange={(e) => setSelectedCameraId(e.target.value)}
                style={{ padding: '8px', background: '#1e1e2d', color: '#00f2fe', border: '1px solid #00f2fe', borderRadius: '4px' }}
              >
                {cameras.map((cam) => (
                  <option key={cam.deviceId} value={cam.deviceId}>
                    {cam.label || `Camera ${cam.deviceId.substring(0, 5)}`}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}
      </header>

      {menuOpen && <div className="drawer-backdrop" onClick={() => setMenuOpen(false)} />}
      <aside className={`drawer ${menuOpen ? 'open' : ''}`}>
        <button
          className={`drawer-item ${activePage === 'home' ? 'active' : ''}`}
          onClick={() => {
            setActivePage('home')
            setMenuOpen(false)
          }}
        >
          Home
        </button>
        <button
          className={`drawer-item ${activePage === 'data' ? 'active' : ''}`}
          onClick={() => {
            setActivePage('data')
            setMenuOpen(false)
          }}
        >
          Data
        </button>
        <button
          className={`drawer-item ${activePage === 'los' ? 'active' : ''}`}
          onClick={() => {
            setActivePage('los')
            setMenuOpen(false)
          }}
        >
          LOS (Life Operating System)
        </button>
        <button
          className={`drawer-item ${activePage === 'automation' ? 'active' : ''}`}
          onClick={() => {
            setActivePage('automation')
            setMenuOpen(false)
          }}
        >
          Automation
        </button>
        <button
          className={`drawer-item ${activePage === 'connects' ? 'active' : ''}`}
          onClick={() => {
            setActivePage('connects')
            setMenuOpen(false)
          }}
        >
          Connects
        </button>
        <button
          className={`drawer-item ${activePage === 'meetings' ? 'active' : ''}`}
          onClick={() => {
            setActivePage('meetings')
            setMenuOpen(false)
          }}
        >
          Meetings
        </button>
      </aside>

      {activePage === 'home' ? (
        <main className="canvas-container home-layout-wrap">
          <div className="home-layout-grid">
            <div className="home-video-wrap">
              <video ref={videoRef} autoPlay playsInline muted style={{ width: '100%', height: 'auto', display: 'block' }} />

              <div className="home-volume-bar" style={{ width: `${Math.min(volume * 100, 100)}%` }}></div>
            </div>
            <section className="data-card home-side-panel" style={{ textAlign: 'left' }}>
              <div className="agent-setup-banner">
                <div>
                  <div className="history-title">Install Agent Setup</div>
                  <div className="history-meta">Required for local Chrome cookies, VB-CABLE, and live runtime automation on user machines.</div>
                </div>
                <button className="add-btn" onClick={startAgentSetup}>Install Agent Setup</button>
              </div>
              <div className="history-row" style={{ display: 'block', marginBottom: '12px' }}>
                <div className="history-title">One-Time Audio Setup Guide</div>
                <div className="history-meta" style={{ marginBottom: '8px' }}>Select your laptop/PC platform:</div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <button
                    className="add-btn"
                    onClick={() => setSetupPlatformOverride('windows')}
                    style={{ opacity: selectedSetupPlatform === 'windows' ? 1 : 0.72 }}
                  >
                    Windows
                  </button>
                  <button
                    className="add-btn"
                    onClick={() => setSetupPlatformOverride('mac')}
                    style={{ opacity: selectedSetupPlatform === 'mac' ? 1 : 0.72 }}
                  >
                    macOS
                  </button>
                </div>
                <div className="history-meta" style={{ marginTop: '8px' }}>Recommended virtual driver: {setupGuide.driver}</div>
                <div className="guide-steps-scroll">
                  {setupGuide.steps.map((step, idx) => (
                    <div key={`detailed-setup-${idx}`} className="history-meta">{idx + 1}. {step}</div>
                  ))}
                </div>
              </div>
              {agentInstallStatus && <div className="history-meta" style={{ marginBottom: '12px' }}>{agentInstallStatus}</div>}
              <h2>Join Meeting</h2>
              <p><strong>Session:</strong> {sessionStatus}</p>
              <label className="data-label">Meeting link (Zoom or GMeet)</label>
              <div className="meeting-link-row">
                <input className="data-input" type="text" readOnly value="https://" style={{ width: '108px', flex: '0 0 108px' }} />
                <input
                  className="data-input"
                  type="text"
                  value={sessionMeetingUrl}
                  onChange={(e) => setSessionMeetingUrl(e.target.value)}
                  placeholder="meet.google.com/... or us05web.zoom.us/..."
                  style={{ flex: 1, minWidth: 0 }}
                />
              </div>
              <div className="history-meta">
                It may take up to 5 minutes to start and join the meeting. Always enter the link at least 5 minutes before the meeting time (all devices).
              </div>
              <label className="data-label">Signed-in profile email</label>
              <input className="data-input" type="email" value={sessionProfileEmail} readOnly placeholder="Locked to logged-in account" />
              <div className="history-meta" style={{ marginTop: '-8px', marginBottom: '10px' }}>
                This is locked to your logged-in account and cannot be changed.
              </div>
              <label className="data-label">Assistant name</label>
              <input className="data-input" type="text" value={sessionAssistantName} onChange={(e) => setSessionAssistantName(e.target.value)} />
              <label className="data-label">Avatar</label>
              <select className="data-input" value={sessionAvatarMode} onChange={(e) => setSessionAvatarMode(e.target.value)}>
                <option value="3d">3D</option>
                <option value="female">Female</option>
              </select>
              <div className="history-meta">
                Auto-selected audio device: {sessionDevice ? `${sessionDevice.id} - ${sessionDevice.name}` : 'Detecting...'}
              </div>
              <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
                <button className="add-btn" onClick={startMeetingSession}>Join Meeting</button>
                <button className="delete-btn" onClick={stopMeetingSession}>Stop Session</button>
                <button className="add-btn" onClick={() => { fetchSessionDeviceAuto(); fetchSessionPlatformCheck(); fetchSessionStatus() }}>Refresh</button>
                <button className="add-btn" onClick={validateAudioFlow}>Validate Audio Flow</button>
              </div>
              {audioValidation && <div className="history-meta" style={{ marginTop: '10px' }}>{audioValidation}</div>}
              {sessionPlatform && (
                <div className="history-row" style={{ display: 'block', marginTop: '12px' }}>
                  <div className="history-title">Audio Setup Guide ({sessionPlatform.os || 'Unknown OS'})</div>
                  <div className="history-meta">Preferred virtual driver: {sessionPlatform.preferred_driver || 'Auto-detected'}</div>
                  <div style={{ marginTop: '8px', display: 'grid', gap: '4px' }}>
                    {(sessionPlatform.setup_steps || []).map((step, idx) => (
                      <div key={`setup-step-${idx}`} className="history-meta">{idx + 1}. {step}</div>
                    ))}
                  </div>
                </div>
              )}
              <div style={{ marginTop: '14px' }}>
                <div className="history-title">Live Transcript</div>
                <div className="history-list" style={{ maxHeight: '160px' }}>
                  {sessionTranscriptLogs.length === 0 ? (
                    <div className="empty-history">No transcript lines yet.</div>
                  ) : (
                    sessionTranscriptLogs.map((line, idx) => (
                      <div key={`t-${idx}`} className="transcript-line">{line}</div>
                    ))
                  )}
                </div>
              </div>
              <div style={{ marginTop: '14px' }}>
                <div className="history-title">Runtime Logs</div>
                <div className="history-list" style={{ maxHeight: '180px' }}>
                  {sessionLogs.length === 0 ? (
                    <div className="empty-history">No logs yet.</div>
                  ) : (
                    sessionLogs.map((line, idx) => (
                      <div key={`l-${idx}`} className="runtime-log-line">{line}</div>
                    ))
                  )}
                </div>
              </div>
            </section>
          </div>
        </main>
      ) : activePage === 'data' ? (
        <main className="data-page">
          <section className="data-card">
            <h2>Data Vault</h2>
            <p>Add files, images, docs, and links for Aria memory.</p>
            <p><strong>Backend:</strong> {dataStatus}</p>

            <label className="data-label">Upload files (any extension)</label>
            <input className="data-input" type="file" multiple onChange={onFilesSelected} />

            <label className="data-label">Add link</label>
            <div className="link-row">
              <input
                className="data-input"
                type="text"
                placeholder="https://..."
                value={linkInput}
                onChange={(e) => setLinkInput(e.target.value)}
              />
              <button className="add-btn" onClick={onAddLink}>Add</button>
            </div>

            <label className="data-label">Add quick text (press Enter)</label>
            <input
              className="data-input"
              type="text"
              placeholder="Type text and press Enter..."
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  onAddText()
                }
              }}
            />

            <button className="add-btn" onClick={fetchHistory}>Refresh</button>
          </section>

          <section className="data-card history-card">
            <h2>History</h2>
            <p>User-uploaded and meeting-derived assets with timestamps.</p>
            <div className="history-list">
              {historyItems.length === 0 ? (
                <div className="empty-history">No items yet.</div>
              ) : (
                historyItems.map((item) => (
                  <div key={item.id} className="history-row">
                    <div>
                      <div className="history-title">{item.name}</div>
                      <div className="history-meta">
                        {item.source_type} | {item.mime} | {item.status} | {formatDateTime(item.created_at)}
                        {` | text:${item.text_length ?? 0} chars | chunks:${item.chunk_count ?? 0}`}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button className="add-btn" onClick={() => reprocessHistoryItem(item.id)}>Reprocess</button>
                      <button className="delete-btn" onClick={() => deleteHistoryItem(item.id)}>Delete</button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </main>
      ) : activePage === 'connects' ? (
        <main className="data-page">
          <section className="data-card">
            <h2>Connects</h2>
            <p>Save people name + email. LOS and avatar can use these for scheduling emails.</p>
            <p><strong>Backend:</strong> {connectStatus}</p>
            <label className="data-label">Name</label>
            <input
              className="data-input"
              type="text"
              placeholder="Raj"
              value={connectName}
              onChange={(e) => setConnectName(e.target.value)}
            />
            <label className="data-label">Email</label>
            <input
              className="data-input"
              type="email"
              placeholder="raj@gmail.com"
              value={connectEmail}
              onChange={(e) => setConnectEmail(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  saveConnect()
                }
              }}
            />
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="add-btn" onClick={saveConnect}>Save</button>
              <button className="add-btn" onClick={fetchConnects}>Refresh</button>
            </div>
          </section>
          <section className="data-card history-card">
            <h2>Saved Connects</h2>
            <div className="history-list">
              {connectItems.length === 0 ? (
                <div className="empty-history">No contacts yet.</div>
              ) : (
                connectItems.map((c) => (
                  <div key={c.id} className="history-row">
                    <div>
                      <div className="history-title">{c.name}</div>
                      <div className="history-meta">{c.email}</div>
                    </div>
                    <button className="delete-btn" onClick={() => deleteConnect(c.id)}>Delete</button>
                  </div>
                ))
              )}
            </div>
          </section>
        </main>
      ) : activePage === 'meetings' ? (
        <main className="data-page">
          <section className="data-card">
            <h2>Meetings</h2>
            <p><strong>Backend:</strong> {meetingsStatus}</p>
            <button className="add-btn" onClick={fetchMeetings}>Refresh</button>
            <div className="history-list">
              {meetingItems.length === 0 ? (
                <div className="empty-history">No meetings found.</div>
              ) : (
                meetingItems.map((m) => (
                  <div key={m.id} className="history-row" style={{ display: 'block' }}>
                    <div className="history-title">{m.id}</div>
                    <div className="history-meta">created: {formatDateTime(m.created_at)} | diarization: {m.has_diarization ? 'yes' : 'no'}</div>
                    <button className="add-btn" onClick={() => openMeeting(m.id)}>Open</button>
                  </div>
                ))
              )}
            </div>
          </section>
          <section className="data-card history-card">
            <h2>Meeting Context Chat</h2>
            {!selectedMeeting ? (
              <p>Select a meeting first.</p>
            ) : (
              <>
                <div className="history-meta">Selected: {selectedMeeting.id}</div>
                <textarea className="data-input" rows={10} readOnly value={selectedMeeting.summary || selectedMeeting.transcript || ''} />
                {selectedMeeting.speaker_transcript ? (
                  <textarea
                    className="data-input"
                    rows={8}
                    readOnly
                    value={selectedMeeting.speaker_transcript}
                  />
                ) : null}
                <div className="history-list" style={{ maxHeight: '220px' }}>
                  {Array.isArray(selectedMeeting.diarization) && selectedMeeting.diarization.length > 0 ? (
                    selectedMeeting.diarization.map((d, idx) => (
                      <div key={`${idx}-${d.start}`} className="history-row" style={{ display: 'block' }}>
                        <div className="history-title">{d.speaker || 'Speaker'}</div>
                        <div className="history-meta">{formatSeconds(d.start)} - {formatSeconds(d.end)}</div>
                        <div className="history-meta">{d.text}</div>
                      </div>
                    ))
                  ) : (
                    <div className="empty-history">No diarization timeline yet.</div>
                  )}
                </div>
                <input
                  className="data-input"
                  type="text"
                  placeholder="Semantic search / chat over this meeting + backend data..."
                  value={meetingQuery}
                  onChange={(e) => setMeetingQuery(e.target.value)}
                />
                <button className="add-btn" onClick={askMeeting}>Ask</button>
                {meetingReply && <div className="history-row" style={{ display: 'block' }}><div className="history-meta">{meetingReply}</div></div>}
              </>
            )}
          </section>
        </main>
      ) : activePage === 'los' ? (
        <main className="canvas-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
          <div style={{ width: '90%', maxWidth: '1100px', height: '80vh', display: 'grid', gridTemplateRows: '1fr 1fr', gap: '18px' }}>
            <section className="data-card" style={{ textAlign: 'left', minHeight: 0, overflow: 'auto' }}>
              <h2>Assistant tasks and notes</h2>
              <p>Type or speak. LOS groups and stores with timestamp.</p>
              <p><strong>Backend:</strong> {losStatus}</p>
              <input
                className="data-input"
                type="text"
                placeholder="Add a task or note..."
                value={losInput}
                onChange={(e) => setLosInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    saveLosNote(losInput, 'typed')
                  }
                }}
              />
              <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                <button className="add-btn" onClick={() => saveLosNote(losInput, 'typed')}>Save</button>
                <button className="add-btn" onClick={startSpeechToLos}>{isListeningLos ? 'Listening...' : 'Speak'}</button>
                <button className="add-btn" onClick={fetchLosHistory}>Refresh</button>
              </div>
              <div className="history-list">
                {losItems.length === 0 ? (
                  <div className="empty-history">No LOS items yet.</div>
                ) : (
                  getLosGroups().map((group) => (
                    <div key={group.name} className="history-row" style={{ display: 'block' }}>
                      <div className="history-title">{group.name}</div>
                      <div className="history-meta">
                        latest: {formatDateTime(group.latestAt)} | items: {group.items.length}
                      </div>
                      <div style={{ marginTop: '8px', display: 'grid', gap: '8px' }}>
                        {group.items.map((item) => (
                          <div key={item.id} style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '8px' }}>
                            <div className="history-title">{item.title}</div>
                            <div className="history-meta">
                              {item.item_type} | {item.source_mode} | {formatDateTime(item.created_at)}
                            </div>
                            <div className="history-meta">{item.content}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </section>

            <section className="data-card" style={{ textAlign: 'left', minHeight: 0, overflow: 'auto' }}>
              <h2>Sub agents</h2>
              {!agentInterfaceOpen ? (
                <div
                  style={{
                    marginTop: '12px',
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr 1fr',
                    gap: '10px'
                  }}
                >
                  {[
                    'command_agent',
                    'identity_agent',
                    'calendar_agent',
                    'email_communication_agent',
                    'opportunity_agent',
                    'finance_agent',
                    'research_agent',
                    'negotiation_agent',
                    'content_agent',
                    'business_builder_agent',
                    'network_agent',
                    'execution_agent',
                    'social_media_agent',
                    'cofounder_agent'
                  ].map((agent) => (
                    <button
                      key={agent}
                      className="history-row"
                      style={{ cursor: 'pointer', minHeight: '72px', textAlign: 'left' }}
                      onClick={() => {
                        setActiveAgent(agent)
                        setAgentInterfaceOpen(true)
                      }}
                    >
                      <div className="history-title">{agent}</div>
                      <div className="history-meta" style={{ color: statusColor(agentExecutionStatus[agent]) }}>
                        status: {statusLabel(agentExecutionStatus[agent])}
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div style={{ marginTop: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <div className="history-meta" style={{ color: statusColor(agentExecutionStatus[activeAgent]) }}>
                      Active: {activeAgent} | status: {statusLabel(agentExecutionStatus[activeAgent])}
                    </div>
                    <button className="add-btn" onClick={() => setAgentInterfaceOpen(false)}>Back to agents</button>
                  </div>
                  <div className="link-row" style={{ marginBottom: '8px' }}>
                    <label className="data-label" style={{ minWidth: '150px' }}>Autonomy mode</label>
                    <select
                      className="data-input"
                      value={agentAutonomyMode}
                      onChange={(e) => setAgentAutonomyMode(e.target.value)}
                    >
                      <option value="suggest_actions">suggest_actions</option>
                      <option value="execute_with_approval">execute_with_approval</option>
                      <option value="autonomous_mode">autonomous_mode</option>
                    </select>
                  </div>
                  <div className="history-list" style={{ maxHeight: '200px' }}>
                    {agentChat.map((m) => (
                      <div key={m.id} className="history-row">
                        <div>
                          <div className="history-title">{m.role}</div>
                          <div className="history-meta">{m.message}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="link-row" style={{ marginTop: '10px' }}>
                    <input
                      className="data-input"
                      type="text"
                      placeholder={`Message ${activeAgent}...`}
                      value={agentInput}
                      onChange={(e) => setAgentInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          sendAgentMessage('typed')
                        }
                      }}
                    />
                    <button className="add-btn" onClick={() => sendAgentMessage('typed')}>Send</button>
                  </div>
                  <button className="add-btn" onClick={startSpeechToAgent}>{isListeningAgent ? 'Listening...' : 'Speak to Agent'}</button>
                </div>
              )}
            </section>
          </div>
        </main>
      ) : (
        <main className="data-page">
          <section className="data-card">
            <h2>Automation</h2>
            <p>Schedule autonomous email reminders/messages from AI instruction prompts.</p>
            <p><strong>Backend:</strong> {automationStatus}</p>
            <div className="history-row" style={{ display: 'block', marginBottom: '12px' }}>
              <div className="history-title">Permanent Sender Setup</div>
              <div className="history-meta">Configure the mailbox Aria will send from. You can update this later.</div>
              <div className="history-meta">
                Gmail setup: Google Account -&gt; Security -&gt; 2-Step Verification ON -&gt; App passwords -&gt; Mail -&gt; copy 16-char password.
                Use app password here, not your normal Gmail password. If forgotten, generate a new app password and update sender setup.
              </div>
              {senderConfigured && !showSenderSetup ? (
                <div style={{ marginTop: '8px' }}>
                  <div className="history-meta">Sender configured for this email.</div>
                  <button className="add-btn" onClick={() => setShowSenderSetup(true)}>Update sender mail</button>
                </div>
              ) : (
                <>
              <label className="data-label">Sender email</label>
              <input
                className="data-input"
                type="email"
                placeholder="sender@gmail.com"
                value={senderEmail}
                onChange={(e) => setSenderEmail(e.target.value)}
              />
              <label className="data-label">App password</label>
              <input
                className="data-input"
                type="password"
                placeholder="16-character app password"
                value={senderAppPassword}
                onChange={(e) => setSenderAppPassword(e.target.value)}
              />
              <div className="link-row">
                <input className="data-input" type="text" placeholder="SMTP host" value={senderHost} onChange={(e) => setSenderHost(e.target.value)} />
                <input className="data-input" type="number" placeholder="Port" value={senderPort} onChange={(e) => setSenderPort(e.target.value)} />
              </div>
              <label className="data-label">
                <input type="checkbox" checked={senderUseTls} onChange={(e) => setSenderUseTls(e.target.checked)} /> Use TLS
              </label>
              <button className="add-btn" onClick={saveSenderConfig}>{senderConfigured ? 'Update sender' : 'Save sender'}</button>
                </>
              )}
            </div>
            <label className="data-label">Sender email (locked from configured base mail)</label>
            <input
              className="data-input"
              type="email"
              value={requesterEmail || senderEmail}
              readOnly
            />
            <label className="data-label">Send mode</label>
            <select className="data-input" value={sendMode} onChange={(e) => setSendMode(e.target.value)}>
              <option value="single">Single mode</option>
              <option value="bulk">Bulk mode</option>
            </select>
            {sendMode === 'single' && (
              <>
                <label className="data-label">Receiver email</label>
                <input
                  className="data-input"
                  type="text"
                  placeholder="receiver@example.com"
                  value={recipientsInput}
                  onChange={(e) => setRecipientsInput(e.target.value)}
                />
                <label className="data-label">Mode</label>
                <select className="data-input" value={automationMode} onChange={(e) => setAutomationMode(e.target.value)}>
                  <option value="ai_schedule">Ask AI (schedule from instruction)</option>
                  <option value="custom_schedule">Custom schedule</option>
                  <option value="send_now">Send now</option>
                </select>
              </>
            )}
            {sendMode === 'bulk' && (
              <>
                <label className="data-label">Bulk mode type</label>
                <select className="data-input" value={bulkSendMode} onChange={(e) => setBulkSendMode(e.target.value)}>
                  <option value="together">Together mode</option>
                  <option value="custom">Custom mode</option>
                </select>
                {bulkSendMode === 'together' && (
                  <>
                    <label className="data-label">Receiver emails (max 12; comma, semicolon, or one per line)</label>
                    <textarea
                      className="data-input"
                      rows={4}
                      placeholder={"a@x.com\nb@y.com\nc@z.com"}
                      value={recipientsInput}
                      onChange={(e) => setRecipientsInput(e.target.value)}
                    />
                  </>
                )}
                <label className="data-label">Mode</label>
                <select className="data-input" value={automationMode} onChange={(e) => setAutomationMode(e.target.value)}>
                  <option value="ai_schedule">Ask AI (schedule from instruction)</option>
                  <option value="custom_schedule">Custom schedule</option>
                  <option value="send_now">Send now</option>
                </select>
              </>
            )}
            {(sendMode === 'single' || bulkSendMode !== 'custom') && (
              <>
                <label className="data-label">Shared attachments (single upload for all selected recipients, max 15 MB per file)</label>
                <input className="data-input" type="file" multiple onChange={uploadSharedAttachments} />
                {sharedAttachments.length > 0 && (
                  <div style={{ display: 'grid', gap: '6px' }}>
                    {sharedAttachments.map((a, idx) => (
                      <div key={`${a.id}-${idx}`} className="history-row">
                        <div className="history-meta">{a.name}</div>
                        <button className="delete-btn" onClick={() => removeSharedAttachment(idx)}>Remove</button>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
            {sendMode === 'bulk' && bulkSendMode === 'custom' && (
              <>
                <label className="data-label">Custom recipient rows (max 12)</label>
                <div style={{ display: 'grid', gap: '10px' }}>
                  {recipientRows.map((row, idx) => (
                    <div key={idx} className="history-row" style={{ display: 'block' }}>
                      <div className="history-meta">Recipient #{idx + 1}</div>
                      <input
                        className="data-input"
                        type="email"
                        placeholder="recipient@example.com"
                        value={row.recipient}
                        onChange={(e) => updateRecipientRow(idx, { recipient: e.target.value })}
                      />
                      <input
                        className="data-input"
                        type="text"
                        placeholder="Subject"
                        value={row.subject}
                        onChange={(e) => updateRecipientRow(idx, { subject: e.target.value })}
                      />
                      <textarea
                        className="data-input"
                        rows={3}
                        placeholder="Message"
                        value={row.message}
                        onChange={(e) => updateRecipientRow(idx, { message: e.target.value })}
                      />
                      <input className="data-input" type="file" multiple onChange={(e) => uploadRowAttachments(idx, e)} />
                      {(row.attachments || []).length > 0 && (
                        <div style={{ display: 'grid', gap: '6px' }}>
                          {(row.attachments || []).map((a, j) => (
                            <div key={`${a.id}-${j}`} className="history-row">
                              <div className="history-meta">{a.name}</div>
                              <button className="delete-btn" onClick={() => removeRowAttachment(idx, j)}>Remove</button>
                            </div>
                          ))}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button className="add-btn" onClick={addRecipientRow} disabled={recipientRows.length >= 12}>Add Row</button>
                        <button className="delete-btn" onClick={() => removeRecipientRow(idx)} disabled={recipientRows.length <= 1}>Remove Row</button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
            {(automationMode === 'custom_schedule' || automationMode === 'send_now') && (
              <>
                <label className="data-label">Subject</label>
                <input
                  className="data-input"
                  type="text"
                  placeholder="Email subject"
                  value={emailSubject}
                  onChange={(e) => setEmailSubject(e.target.value)}
                />
                <label className="data-label">Email body</label>
                <textarea
                  className="data-input"
                  rows={5}
                  placeholder="Type message body..."
                  value={emailBody}
                  onChange={(e) => setEmailBody(e.target.value)}
                />
              </>
            )}
            {(automationMode === 'ai_schedule' || automationMode === 'custom_schedule') && (
              <>
                <label className="data-label">Schedule date</label>
                <div className="picker-row">
                  <input
                    ref={scheduleDateRef}
                    className="data-input"
                    type="date"
                    value={scheduleDate}
                    onChange={(e) => setScheduleDate(e.target.value)}
                  />
                  <button
                    className="add-btn"
                    type="button"
                    onClick={() => {
                      const el = scheduleDateRef.current
                      if (!el) return
                      if (el.showPicker) el.showPicker()
                      else el.focus()
                    }}
                  >
                    Open Calendar
                  </button>
                </div>
                <label className="data-label">Schedule time</label>
                <div className="picker-row">
                  <input
                    ref={scheduleTimeRef}
                    className="data-input"
                    type="time"
                    value={scheduleTime24h}
                    onChange={(e) => setScheduleTime24h(e.target.value)}
                    step="60"
                  />
                  <button
                    className="add-btn"
                    type="button"
                    onClick={() => {
                      const el = scheduleTimeRef.current
                      if (!el) return
                      if (el.showPicker) el.showPicker()
                      else el.focus()
                    }}
                  >
                    Open Clock
                  </button>
                </div>
                <div className="history-meta">
                  Timezone is auto-detected from device: {Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'}
                </div>
              </>
            )}
            <label className="data-label">Instruction to AI</label>
            <textarea
              className="data-input"
              rows={5}
              placeholder='Example: "Remind me tomorrow at 8 AM to send the Q2 deck"'
              value={automationInstruction}
              onChange={(e) => setAutomationInstruction(e.target.value)}
            />
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="add-btn" onClick={scheduleAutomationEmail}>Schedule</button>
              <button className="add-btn" onClick={fetchAutomationHistory}>Refresh</button>
            </div>
          </section>
          <section className="data-card history-card">
            <h2>Automation History</h2>
            <p>All scheduled/sent/failed messages are recorded for audit and memory.</p>
            <div className="history-list">
              {automationItems.length === 0 ? (
                <div className="empty-history">No automation items yet.</div>
              ) : (
                automationItems.map((item) => (
                  <div key={item.id} className="history-row" style={{ display: 'block' }}>
                    <div className="history-title">{item.subject}</div>
                    <div className="history-meta">
                      status: {item.status} | by: {item.created_by_email} | to: {(item.recipients || []).join(', ')}
                    </div>
                    <div className="history-meta">
                      scheduled: {formatDateTime(item.schedule_at)} | sent: {item.sent_at ? formatDateTime(item.sent_at) : '-'}
                    </div>
                    <div className="history-meta">attachments: {(item.attachments || []).length}</div>
                    <div className="history-meta">{item.message}</div>
                    {item.error_text && <div className="history-meta">error: {item.error_text}</div>}
                  </div>
                ))
              )}
            </div>
          </section>
        </main>
      )}

      <footer className="footer">
        <div className="status-indicator">
          <div
            className="pulse"
            style={{
              backgroundColor:
                status === 'Aria is speaking...'
                  ? '#00f2fe'
                  : status.includes('Disconnected')
                    ? '#ff4b4b'
                    : '#00e676',
              boxShadow: status === 'Aria is speaking...' ? '0 0 8px #00f2fe' : 'none'
            }}
          ></div>
          <span>Status: {status}</span>
        </div>
      </footer>
    </div>
  )
}

export default App

