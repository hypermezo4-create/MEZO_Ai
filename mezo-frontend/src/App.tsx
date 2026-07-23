import { FormEvent, useEffect, useMemo, useState } from "react"
import {
  Activity,
  Archive,
  Bot,
  BrainCircuit,
  Check,
  ChevronRight,
  CircleStop,
  Code2,
  Download,
  Eye,
  FileCode2,
  FolderGit2,
  GitBranch,
  Layers3,
  LoaderCircle,
  MessageSquarePlus,
  PanelRightOpen,
  Plus,
  RefreshCw,
  Send,
  Server,
  ShieldCheck,
  Sparkles,
  Terminal,
  X,
  Zap,
} from "lucide-react"

import {
  api,
  type ClusterStatus,
  type Conversation,
  type Interaction,
  type Message,
  type Mode,
  type ModelHealth,
  type Project,
  type Task,
  type TaskEvent,
} from "./lib/api"

const terminalStates = new Set(["completed", "failed", "cancelled"])

const modeOptions: Array<{
  value: Mode
  label: string
  short: string
  description: string
  icon: typeof Sparkles
}> = [
  { value: "auto", label: "Auto", short: "Best model", description: "MEZO chooses the right specialist", icon: Sparkles },
  { value: "fast", label: "Fast", short: "Quick reply", description: "Chat, summaries and lightweight work", icon: Zap },
  { value: "coding", label: "Coding", short: "Build & fix", description: "Repository-aware coding agent", icon: Code2 },
  { value: "deep", label: "Reasoning", short: "Think deeply", description: "Architecture and complex planning", icon: BrainCircuit },
  { value: "vision", label: "Vision", short: "See & analyse", description: "Images, screenshots and interfaces", icon: Eye },
  { value: "multi", label: "Multi-agent", short: "Team mode", description: "Several specialists collaborate", icon: Layers3 },
]

const modelCards = [
  { key: "fast", label: "MEZO Fast", purpose: "Routing, chat and short tasks", icon: Zap },
  { key: "coding", label: "Qwen Coder", purpose: "Code, repositories and tests", icon: Code2 },
  { key: "deep", label: "GLM Reasoning", purpose: "Architecture and difficult analysis", icon: BrainCircuit },
  { key: "debug", label: "DeepSeek Reviewer", purpose: "Review, debugging and security", icon: ShieldCheck },
  { key: "vision", label: "Qwen Vision", purpose: "Images, screenshots and UI", icon: Eye },
]

const suggestionCards = [
  {
    icon: Code2,
    title: "Build or fix code",
    body: "Inspect the selected repository and implement the right change.",
    prompt: "Inspect the selected repository, identify the root cause of its most important issue, and fix only what is necessary.",
  },
  {
    icon: BrainCircuit,
    title: "Plan a system",
    body: "Use deep reasoning for architecture and technical decisions.",
    prompt: "Review the project architecture and propose a practical improvement plan with risks and priorities.",
  },
  {
    icon: ShieldCheck,
    title: "Review a patch",
    body: "Find correctness, security and regression risks.",
    prompt: "Review the current project for correctness, security risks, missing tests, and unsafe assumptions.",
  },
]

function humanStatus(value: string): string {
  return value.replaceAll("_", " ")
}

function eventSummary(event: TaskEvent): string {
  const candidate = event.payload.message ?? event.payload.command ?? event.payload.name ?? event.payload.error
  if (typeof candidate === "string" && candidate.trim()) return candidate
  if (typeof event.payload.exit_code === "number") return `Exit code ${event.payload.exit_code}`
  return humanStatus(event.event_type)
}

function ModelRow({ name, purpose, health, icon: Icon }: {
  name: string
  purpose: string
  health?: ModelHealth
  icon: typeof Zap
}) {
  const healthy = Boolean(health?.healthy)
  const replicas = health?.replicas?.filter(item => item.healthy).length ?? 0

  return <article className="model-row">
    <span className="model-symbol"><Icon /></span>
    <span className="model-details">
      <span className="model-name"><strong>{name}</strong><i className={healthy ? "online" : "offline"} /></span>
      <small>{purpose}</small>
    </span>
    <span className="model-state">{healthy ? `${replicas || 1} active` : "offline"}</span>
  </article>
}

function MessageBubble({ message }: { message: Message }) {
  const assistant = message.role === "assistant"
  return <article className={`message ${assistant ? "assistant" : "user"}`}>
    <div className="message-avatar">{assistant ? <span className="mini-logo">M</span> : <span>You</span>}</div>
    <div className="message-body">
      <div className="message-meta">
        <strong>{assistant ? "MEZO" : "You"}</strong>
        <time>{message.created_at ? new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}</time>
      </div>
      <div className="message-content" dir="auto">{message.content}</div>
    </div>
  </article>
}

export default function App() {
  const [status, setStatus] = useState<ClusterStatus | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [events, setEvents] = useState<TaskEvent[]>([])
  const [conversationId, setConversationId] = useState("")
  const [projectId, setProjectId] = useState("")
  const [repoUrl, setRepoUrl] = useState("")
  const [repoBranch, setRepoBranch] = useState("main")
  const [prompt, setPrompt] = useState("")
  const [mode, setMode] = useState<Mode>("auto")
  const [interaction, setInteraction] = useState<Interaction>("auto")
  const [busy, setBusy] = useState(false)
  const [projectBusy, setProjectBusy] = useState(false)
  const [showProjectForm, setShowProjectForm] = useState(false)
  const [showInspector, setShowInspector] = useState(false)
  const [error, setError] = useState("")

  const selectedConversation = useMemo(
    () => conversations.find(item => item.id === conversationId) ?? null,
    [conversations, conversationId],
  )
  const selectedProject = useMemo(
    () => projects.find(item => item.id === projectId) ?? null,
    [projects, projectId],
  )
  const selectedTask = useMemo(
    () => tasks.find(task => task.conversation_id === conversationId) ?? null,
    [tasks, conversationId],
  )
  const activeMode = modeOptions.find(item => item.value === mode) ?? modeOptions[0]
  const ActiveModeIcon = activeMode.icon
  const onlineMachines = status?.machines.filter(machine => machine.status === "online" || machine.status === "busy").length ?? 0
  const totalMachines = status?.configured_machine_count ?? status?.machines.length ?? 9
  const runningTask = Boolean(selectedTask && !terminalStates.has(selectedTask.status))

  const refresh = async () => {
    const [nextStatus, nextProjects, nextConversations, nextTasks] = await Promise.all([
      api.status(),
      api.projects(),
      api.conversations(),
      api.tasks(),
    ])
    setStatus(nextStatus)
    setProjects(nextProjects)
    setConversations(nextConversations)
    setTasks(nextTasks)
    setProjectId(current => current || nextProjects[0]?.id || "")
  }

  useEffect(() => {
    void refresh().catch(cause => setError(cause instanceof Error ? cause.message : "Could not load MEZO"))
    const timer = window.setInterval(() => void refresh().catch(() => undefined), 5000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (!conversationId) {
      setMessages([])
      return
    }
    void api.messages(conversationId)
      .then(setMessages)
      .catch(cause => setError(cause instanceof Error ? cause.message : "Could not load conversation"))
  }, [conversationId])

  useEffect(() => {
    setEvents([])
    if (!selectedTask || terminalStates.has(selectedTask.status)) return
    const controller = new AbortController()
    let cursor = 0
    void api.stream(selectedTask.id, cursor, controller.signal, event => {
      cursor = Math.max(cursor, event.id)
      setEvents(current => current.some(item => item.id === event.id) ? current : [...current, event])
    }).catch(cause => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Task stream disconnected")
    })
    return () => controller.abort()
  }, [selectedTask?.id, selectedTask?.status])

  useEffect(() => {
    if (!selectedTask || !terminalStates.has(selectedTask.status) || !conversationId) return
    void api.messages(conversationId).then(setMessages).catch(() => undefined)
  }, [selectedTask?.status, conversationId])

  const newChat = () => {
    setConversationId("")
    setMessages([])
    setEvents([])
    setPrompt("")
    setError("")
  }

  const addProject = async (event: FormEvent) => {
    event.preventDefault()
    setProjectBusy(true)
    setError("")
    try {
      const parsed = new URL(repoUrl)
      if (parsed.protocol !== "https:") throw new Error("Repository URL must use HTTPS")
      const name = parsed.pathname.split("/").filter(Boolean).pop()?.replace(/\.git$/i, "") || "Repository"
      const project = await api.createProject({
        name,
        repository_url: repoUrl.trim(),
        default_branch: repoBranch.trim() || "main",
      })
      setProjects(current => [project, ...current])
      setProjectId(project.id)
      setRepoUrl("")
      setRepoBranch("main")
      setShowProjectForm(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not add repository")
    } finally {
      setProjectBusy(false)
    }
  }

  const send = async (event: FormEvent) => {
    event.preventDefault()
    const cleanPrompt = prompt.trim()
    if (!cleanPrompt) return
    if (interaction === "agent" && !projectId) {
      setError("Choose a project before starting an agent task")
      return
    }

    setBusy(true)
    setError("")
    setEvents([])
    try {
      const result = await api.dispatch({
        prompt: cleanPrompt,
        conversation_id: conversationId || undefined,
        project_id: projectId || undefined,
        mode,
        interaction,
      })
      setConversationId(result.conversation_id)
      setMessages(await api.messages(result.conversation_id))
      setPrompt("")
      if (result.task) setShowInspector(true)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "MEZO could not complete the request")
    } finally {
      setBusy(false)
    }
  }

  const cancelTask = async () => {
    if (!selectedTask) return
    setBusy(true)
    setError("")
    try {
      await api.cancel(selectedTask.id)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not cancel task")
    } finally {
      setBusy(false)
    }
  }

  const decideTask = async (value: "accept" | "reject") => {
    if (!selectedTask) return
    setBusy(true)
    setError("")
    try {
      await api.decide(selectedTask.id, value)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save decision")
    } finally {
      setBusy(false)
    }
  }

  return <div className="mezo-app">
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-logo" aria-label="MEZO AI logo"><span>M</span><i /></div>
        <div><strong>MEZO AI</strong><small>Private intelligence</small></div>
      </div>

      <button className="new-chat" onClick={newChat}><MessageSquarePlus /> New chat</button>

      <nav className="sidebar-block" aria-label="Conversations">
        <div className="sidebar-heading"><span>Recent</span><small>{conversations.length}</small></div>
        <div className="conversation-list">
          {conversations.length === 0 && <p className="sidebar-empty">Your conversations will appear here.</p>}
          {conversations.map(conversation => <button
            key={conversation.id}
            className={conversation.id === conversationId ? "active" : ""}
            onClick={() => setConversationId(conversation.id)}
          ><span>{conversation.title}</span><ChevronRight /></button>)}
        </div>
      </nav>

      <section className="sidebar-block projects-block">
        <div className="sidebar-heading">
          <span>Projects</span>
          <button className="small-icon" aria-label="Add project" onClick={() => setShowProjectForm(value => !value)}><Plus /></button>
        </div>

        {showProjectForm && <form className="project-form" onSubmit={addProject}>
          <label>Repository URL<input aria-label="Repository URL" type="url" required value={repoUrl} onChange={event => setRepoUrl(event.target.value)} placeholder="https://github.com/owner/repo.git" /></label>
          <label>Default branch<input value={repoBranch} onChange={event => setRepoBranch(event.target.value)} placeholder="main" /></label>
          <div><button type="button" onClick={() => setShowProjectForm(false)}>Cancel</button><button className="primary" disabled={projectBusy}>{projectBusy ? <LoaderCircle className="spin" /> : <Plus />} Add</button></div>
        </form>}

        <div className="project-list">
          {projects.length === 0 && !showProjectForm && <button className="empty-project" onClick={() => setShowProjectForm(true)}><FolderGit2 /> Connect a repository</button>}
          {projects.map(project => <button key={project.id} className={project.id === projectId ? "active" : ""} onClick={() => setProjectId(project.id)}>
            <span><FolderGit2 />{project.name}</span><small>{project.default_branch}</small>
          </button>)}
        </div>
      </section>

      <button className="cluster-card" onClick={() => setShowInspector(true)}>
        <span className="cluster-icon"><Server /></span>
        <span><strong>{onlineMachines}/{totalMachines}</strong><small>machines online</small></span>
        <i className={status?.router.healthy ? "online" : "offline"} />
      </button>
    </aside>

    <main className="workspace">
      <header className="topbar">
        <div className="topbar-title">
          <span className="mobile-logo">M</span>
          <div><strong>{selectedConversation?.title || "New conversation"}</strong><small>{selectedProject ? selectedProject.name : "No project selected"}</small></div>
        </div>
        <div className="topbar-actions">
          <button className="connection-pill" onClick={() => void refresh()}><span className={status?.router.healthy ? "online" : "offline"} /><span>{status?.router.healthy ? "Ready" : "Local API"}</span><RefreshCw /></button>
          <button className="inspector-toggle" aria-label="Open MEZO status" onClick={() => setShowInspector(true)}><PanelRightOpen /></button>
        </div>
      </header>

      {error && <div className="error-banner"><X /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X /></button></div>}

      <section className="conversation-view">
        {messages.length === 0 ? <div className="welcome">
          <div className="hero-logo"><span>M</span><i /></div>
          <p className="hero-kicker"><Sparkles /> PRIVATE AI WORKSPACE</p>
          <h1>What should MEZO build?</h1>
          <p className="hero-copy" dir="auto">اكتب طلبك بالعربي أو الإنجليزي. MEZO يختار الموديل المناسب، أو يشغّل فريقًا كاملًا على مشروعك.</p>

          <div className="suggestions">
            {suggestionCards.map(card => <button key={card.title} onClick={() => setPrompt(card.prompt)}>
              <span><card.icon /></span>
              <strong>{card.title}</strong>
              <small>{card.body}</small>
            </button>)}
          </div>
        </div> : <div className="messages">
          {messages.map(message => <MessageBubble key={message.id} message={message} />)}
          {runningTask && selectedTask && <article className="message assistant working-message">
            <div className="message-avatar"><span className="mini-logo">M</span></div>
            <div className="message-body">
              <div className="message-meta"><strong>MEZO</strong><time>{humanStatus(selectedTask.status)}</time></div>
              <div className="working-line"><LoaderCircle className="spin" /><span>Working through the repository…</span><button onClick={() => setShowInspector(true)}>View activity</button></div>
            </div>
          </article>}
        </div>}
      </section>

      <form className="composer" onSubmit={send}>
        <div className="composer-tools">
          <label className="select-chip"><ActiveModeIcon /><select aria-label="MEZO mode" value={mode} onChange={event => setMode(event.target.value as Mode)}>{modeOptions.map(option => <option key={option.value} value={option.value}>{option.label} · {option.short}</option>)}</select></label>
          <label className="select-chip"><Bot /><select aria-label="Interaction type" value={interaction} onChange={event => setInteraction(event.target.value as Interaction)}><option value="auto">Auto action</option><option value="chat">Chat only</option><option value="agent">Agent task</option></select></label>
          <label className="select-chip project-chip"><FolderGit2 /><select aria-label="Project" value={projectId} onChange={event => setProjectId(event.target.value)}><option value="">No project</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name} · {project.default_branch}</option>)}</select></label>
        </div>

        <div className="composer-input">
          <textarea
            aria-label="Message MEZO"
            value={prompt}
            onChange={event => setPrompt(event.target.value)}
            placeholder={selectedProject ? `Message MEZO about ${selectedProject.name}…` : "Message MEZO…"}
            dir="auto"
            onKeyDown={event => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                event.currentTarget.form?.requestSubmit()
              }
            }}
          />
          {runningTask ? <button type="button" className="stop-button" onClick={() => void cancelTask()} disabled={busy} aria-label="Stop task"><CircleStop /></button> : <button className="send-button" disabled={busy || !prompt.trim()} aria-label="Send message">{busy ? <LoaderCircle className="spin" /> : <Send />}</button>}
        </div>
        <p className="composer-note">MEZO can make mistakes. Review changes before accepting them.</p>
      </form>
    </main>

    <div className={`drawer-backdrop ${showInspector ? "visible" : ""}`} onClick={() => setShowInspector(false)} />
    <aside className={`inspector ${showInspector ? "open" : ""}`} aria-hidden={!showInspector}>
      <header className="inspector-header"><div><small>MEZO CONTROL</small><h2>System activity</h2></div><button aria-label="Close MEZO status" onClick={() => setShowInspector(false)}><X /></button></header>

      <section className="inspector-section">
        <div className="section-title"><span><Activity /> Cluster</span><small>{onlineMachines}/{totalMachines} online</small></div>
        <div className="cluster-stats">
          <div><strong>{onlineMachines}</strong><span>Online</span></div>
          <div><strong>{status?.max_machine_count ?? 20}</strong><span>Capacity</span></div>
          <div><strong>{status?.max_concurrent_tasks ?? 4}</strong><span>Tasks</span></div>
        </div>
        <div className="model-list">{modelCards.map(model => <ModelRow key={model.key} name={model.label} purpose={model.purpose} health={status?.router.models?.[model.key]} icon={model.icon} />)}</div>
      </section>

      <section className="inspector-section task-section">
        <div className="section-title"><span><FileCode2 /> Task</span><small>{selectedTask ? humanStatus(selectedTask.status) : "idle"}</small></div>
        {!selectedTask && <div className="empty-evidence"><Terminal /><p>Agent tools, changed files, reviews and patches will appear here.</p></div>}
        {selectedTask && <>
          <div className="task-meta"><div><span>Mode</span><strong>{selectedTask.mode}</strong></div><div><span>Runner</span><strong>{selectedTask.runner_id || "Waiting"}</strong></div><div><span>Files</span><strong>{selectedTask.changed_files.length}</strong></div></div>
          {events.length > 0 && <div className="event-feed">{events.slice(-12).map(event => <div className="event-row" key={event.id}><span><Terminal /></span><div><strong>{humanStatus(event.event_type)}</strong><pre>{eventSummary(event)}</pre></div></div>)}</div>}
          {selectedTask.changed_files.length > 0 && <div className="changed-files"><h3><GitBranch />Changed files</h3>{selectedTask.changed_files.map(file => <div key={file.path}><code>{file.path}</code><span>{file.status || "M"}</span></div>)}</div>}
          {selectedTask.diff_text && <details className="diff-panel"><summary>View patch</summary><pre>{selectedTask.diff_text}</pre></details>}
          {selectedTask.error && <div className="task-error"><X /><span>{selectedTask.error}</span></div>}
          {selectedTask.reviewer_chain.length > 0 && <div className="review-chain"><h3><ShieldCheck />Review chain</h3><p>{selectedTask.reviewer_chain.join(" → ")}</p></div>}
          {selectedTask.status === "completed" && <div className="task-actions">
            <button className="approve" disabled={busy || selectedTask.decision === "accept"} onClick={() => void decideTask("accept")}><Check />Accept</button>
            <button className="reject" disabled={busy || selectedTask.decision === "reject"} onClick={() => void decideTask("reject")}><X />Reject</button>
            <a href={api.patchUrl(selectedTask.id)}><Download />Patch</a>
            <a href={api.archiveUrl(selectedTask.id)}><Archive />Archive</a>
          </div>}
        </>}
      </section>
    </aside>
  </div>
}
