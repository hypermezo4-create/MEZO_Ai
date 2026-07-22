import { FormEvent, useEffect, useMemo, useState } from "react"
import { api, ClusterStatus, Conversation, Message, Mode, Project, Task, TaskEvent } from "./lib/api"
import { Bot, Code2, FileCode2, FolderGit2, LoaderCircle, MessageSquarePlus, Plus, Radio, Server, Terminal } from "lucide-react"

const terminal = new Set(["completed", "failed", "cancelled"])

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
  const [prompt, setPrompt] = useState("")
  const [mode, setMode] = useState<Mode>("auto")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const selectedTask = useMemo(() => tasks.find(task => task.conversation_id === conversationId), [tasks, conversationId])

  const refresh = async () => {
    const [s,p,c,t] = await Promise.all([api.status(), api.projects(), api.conversations(), api.tasks()])
    setStatus(s); setProjects(p); setConversations(c); setTasks(t)
    if (!projectId) setProjectId(p[0]?.id || "")
  }

  useEffect(() => { void refresh().catch(e => setError(String(e))); const id = setInterval(() => void refresh().catch(() => undefined), 5000); return () => clearInterval(id) }, [])
  useEffect(() => { if (!conversationId) return; void api.messages(conversationId).then(setMessages) }, [conversationId])

  useEffect(() => {
    if (!selectedTask) return
    const controller = new AbortController(); let cursor = 0
    void api.stream(selectedTask.id, cursor, controller.signal, event => { cursor = event.id; setEvents(v => [...v, event]) })
    return () => controller.abort()
  }, [selectedTask?.id])

  const addProject = async (e: FormEvent) => {
    e.preventDefault(); const url = new URL(repoUrl); const name = url.pathname.split("/").filter(Boolean).pop()?.replace(".git", "") || "Repo"
    const project = await api.createProject({ name, repository_url: repoUrl, default_branch: "main" }); setProjects(v => [project, ...v]); setProjectId(project.id); setRepoUrl("")
  }

  const send = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError("")
    try {
      const result = await api.dispatch({ prompt, conversation_id: conversationId || undefined, project_id: projectId || undefined, mode, interaction: "auto" })
      setConversationId(result.conversation_id); setMessages(await api.messages(result.conversation_id)); setPrompt(""); await refresh()
    } catch (err) { setError(String(err)) } finally { setBusy(false) }
  }

  return <div className="shell">
    <aside className="sidebar"><div className="brand"><Code2/><b>MEZO AI</b></div><section><h2><FolderGit2/>Projects</h2>{projects.map(p => <button key={p.id} className={p.id===projectId?"active":""} onClick={()=>setProjectId(p.id)}>{p.name}</button>)}</section><form className="repo-form" onSubmit={addProject}><input value={repoUrl} onChange={e=>setRepoUrl(e.target.value)} placeholder="GitHub URL"/><button><Plus/></button></form><section><h2><MessageSquarePlus/>Chats</h2>{conversations.map(c=><button key={c.id} onClick={()=>setConversationId(c.id)}>{c.title}</button>)}</section><div><Server/> {status?.machines.length || 0} Machines</div></aside>
    <main><header><h1>Auto Chat + Agent</h1><span><Radio/> {mode}</span></header><section className="chat">{messages.map(m=><article className="message" key={m.id}><b>{m.role}</b><p>{m.content}</p></article>)}{selectedTask&&!terminal.has(selectedTask.status)&&<article><LoaderCircle/> MEZO working...</article>}{events.length>0&&<details><summary><Terminal/> Execution</summary>{events.map(e=><pre key={e.id}>{e.event_type}</pre>)}</details>}</section><form className="composer" onSubmit={send}><select value={mode} onChange={e=>setMode(e.target.value as Mode)}><option value="auto">Auto</option><option value="fast">Fast</option><option value="coding">Coding</option></select><textarea value={prompt} onChange={e=>setPrompt(e.target.value)} /><button disabled={busy}><Bot/></button></form></main><aside className="evidence"><h2><FileCode2/>Evidence</h2>{selectedTask?.changed_files.map(f=><code key={f.path}>{f.path}</code>)}</aside>
  </div>
}
