import { FormEvent, useEffect, useMemo, useState } from "react"
import { api, ClusterStatus, Mode, Project, Task, TaskEvent } from "./lib/api"
import { Bot, CheckCircle2, CircleStop, Code2, Download, FileCode2, FolderGit2, LoaderCircle, Plus, Radio, Server, Terminal } from "lucide-react"

const terminal = new Set(["completed", "failed", "cancelled"])

export default function App() {
  const [status, setStatus] = useState<ClusterStatus | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [selectedId, setSelectedId] = useState("")
  const [events, setEvents] = useState<TaskEvent[]>([])
  const [prompt, setPrompt] = useState("")
  const [mode, setMode] = useState<Mode>("auto")
  const [projectId, setProjectId] = useState("")
  const [repoUrl, setRepoUrl] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const selected = useMemo(() => tasks.find(task => task.id === selectedId), [tasks, selectedId])

  const refresh = async () => {
    const [nextStatus, nextProjects, nextTasks] = await Promise.all([api.status(), api.projects(), api.tasks()])
    setStatus(nextStatus); setProjects(nextProjects); setTasks(nextTasks)
    if (!projectId && nextProjects[0]) setProjectId(nextProjects[0].id)
  }
  useEffect(() => { void refresh().catch(cause => setError(String(cause))); const timer = setInterval(() => void refresh().catch(() => undefined), 5000); return () => clearInterval(timer) }, [])
  useEffect(() => {
    if (!selectedId) return
    setEvents([]); const controller = new AbortController(); let cursor = 0
    const connect = async () => {
      while (!controller.signal.aborted) {
        try { await api.stream(selectedId, cursor, controller.signal, event => { cursor = event.id; setEvents(current => [...current, event]) }) }
        catch { if (!controller.signal.aborted) await new Promise(resolve => setTimeout(resolve, 1200)) }
      }
    }
    void connect(); return () => controller.abort()
  }, [selectedId])

  const addProject = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("")
    try {
      const parsed = new URL(repoUrl); const name = parsed.pathname.replace(/\.git$/, "").split("/").filter(Boolean).pop() || "Repository"
      const project = await api.createProject({ name, repository_url: repoUrl, default_branch: "main" })
      setProjects(current => [project, ...current]); setProjectId(project.id); setRepoUrl("")
    } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) } finally { setBusy(false) }
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!projectId) return; setBusy(true); setError("")
    try { const task = await api.createTask({ project_id: projectId, prompt, mode }); setTasks(current => [task, ...current]); setSelectedId(task.id); setPrompt("") }
    catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)) } finally { setBusy(false) }
  }
  const action = async (work: () => Promise<Task>) => { setBusy(true); try { const updated = await work(); setTasks(current => current.map(item => item.id === updated.id ? updated : item)) } finally { setBusy(false) } }

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><Code2/><div><strong>MEZO AI</strong><span>Private Fly cluster</span></div></div>
      <section><h2><FolderGit2/>Projects</h2>{projects.map(project => <button className={project.id === projectId ? "active" : ""} key={project.id} onClick={() => setProjectId(project.id)}>{project.name}</button>)}</section>
      <form className="repo-form" onSubmit={addProject}><input aria-label="Repository URL" type="url" required value={repoUrl} onChange={event => setRepoUrl(event.target.value)} placeholder="https://github.com/owner/repo"/><button disabled={busy}><Plus/>Add</button></form>
      <section><h2><Bot/>Conversations</h2>{tasks.map(task => <button className={task.id === selectedId ? "active" : ""} key={task.id} onClick={() => setSelectedId(task.id)}><span>{task.prompt.slice(0, 42)}</span><small>{task.status}</small></button>)}</section>
      <div className="cluster"><Server/><span>{status?.machines.length || 0}/20 Machines</span><i className={status?.router.healthy ? "ok" : "bad"}/></div>
    </aside>
    <main>
      <header><div><span className="eyebrow">NO LOGIN · PRIVATE TUNNEL</span><h1>{selected ? selected.prompt.slice(0, 80) : "What should MEZO build?"}</h1></div><div className="model-state"><Radio/>{mode}</div></header>
      {error && <div className="error">{error}</div>}
      <section className="chat">
        {!selected && <div className="welcome"><div className="avatar">M</div><h2>Your models and runners live on Fly</h2><p>Add a public repository, choose a routing mode, and describe the task.</p></div>}
        {selected && <><article className="message user"><strong>You</strong><p>{selected.prompt}</p></article>{events.map(event => <article className="event" key={event.id}><Terminal/><div><strong>{event.event_type.replaceAll("_", " ")}</strong><pre>{typeof event.payload.message === "string" ? event.payload.message : JSON.stringify(event.payload, null, 2)}</pre></div></article>)}</>}
      </section>
      <form className="composer" onSubmit={submit}><select aria-label="Model mode" value={mode} onChange={event => setMode(event.target.value as Mode)}><option value="auto">Auto</option><option value="fast">Fast</option><option value="coding">Coding</option><option value="deep">Deep reasoning</option><option value="vision">Vision</option><option value="multi">Multi-model review</option></select><textarea aria-label="Task" required value={prompt} onChange={event => setPrompt(event.target.value)} placeholder="Ask MEZO to inspect, change, test, or explain this repository…"/><button disabled={busy || !projectId}>{busy ? <LoaderCircle className="spin"/> : <Bot/>}Run</button></form>
    </main>
    <aside className="evidence">
      <h2><FileCode2/>Workspace evidence</h2>
      <div className="health"><h3>Models</h3>{Object.entries(status?.router.models || {}).map(([name, value]) => <div key={name}><i className={value.healthy ? "ok" : "bad"}/><span>{name}</span><small>{value.latency_ms ? `${value.latency_ms}ms` : "offline"}</small></div>)}</div>
      {selected && <><h3>Reviewer chain</h3><p>{selected.reviewer_chain?.join(" → ") || "Waiting"}</p><h3>Changed files</h3>{selected.changed_files.map(file => <code key={file.path}>{file.status} {file.path}</code>)}<h3>Unified diff</h3><pre className="diff">{selected.diff_text || "Waiting for changes…"}</pre><div className="actions">{!terminal.has(selected.status) && <button onClick={() => void action(() => api.cancel(selected.id))}><CircleStop/>Cancel</button>}{selected.status === "completed" && <><button onClick={() => void action(() => api.decide(selected.id, "accept"))}><CheckCircle2/>Accept</button><button onClick={() => void action(() => api.decide(selected.id, "reject"))}>Reject</button><a href={`/api/tasks/${selected.id}/patch`}><Download/>Patch</a><a href={`/api/tasks/${selected.id}/archive`}><Download/>Archive</a></>}</div></>}
    </aside>
  </div>
}
