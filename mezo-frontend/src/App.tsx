import { FormEvent, useEffect, useRef, useState } from "react"
import { AlertTriangle, CheckCircle2, CircleStop, Code2, FileCode2, FolderGit2, GitPullRequest, History, ListChecks, LoaderCircle, LockKeyhole, Play, Radio, Server, ShieldCheck } from "lucide-react"

import { Approval, MezoApi, MezoApiError, Project, Repository, Runner, Task, TaskEvent } from "@/lib/api"

const api = new MezoApi()
const terminalTypes = new Set(["command_start", "stdout", "stderr", "command_finish"])
const terminalText = (event: TaskEvent) => String(event.payload.message || event.payload.command || `${event.type}${event.payload.exit_code !== undefined ? ` (exit ${event.payload.exit_code})` : ""}`)
const terminalState = new Set(["completed", "failed", "cancelled"])

function Login({ onReady }: { onReady: () => void }) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [bootstrapToken, setBootstrapToken] = useState("")
  const [bootstrap, setBootstrap] = useState(false)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("")
    try {
      if (bootstrap) await api.bootstrap(email, password, bootstrapToken)
      else await api.login(email, password)
      onReady()
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Authentication failed") }
    finally { setBusy(false) }
  }
  return <main className="login-shell"><form className="login-card" onSubmit={submit}>
    <div className="logo"><Code2 /><span>MEZO AI</span></div>
    <h1>{bootstrap ? "Create the first owner" : "Sign in to the control plane"}</h1>
    <p>Credentials are exchanged for an expiring bearer token and kept in memory only.</p>
    <label>Email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
    <label>Password<input type="password" required minLength={bootstrap ? 12 : undefined} value={password} onChange={e => setPassword(e.target.value)} /></label>
    {bootstrap && <label>Bootstrap token<input type="password" required value={bootstrapToken} onChange={e => setBootstrapToken(e.target.value)} /></label>}
    {error && <div className="error"><AlertTriangle />{error}</div>}
    <button className="primary" disabled={busy}>{busy ? <LoaderCircle className="spin" /> : <LockKeyhole />}{bootstrap ? "Bootstrap owner" : "Sign in"}</button>
    <button type="button" className="link" onClick={() => setBootstrap(value => !value)}>{bootstrap ? "Return to sign in" : "First deployment? Bootstrap the owner"}</button>
  </form></main>
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(false)
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [runners, setRunners] = useState<Runner[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [events, setEvents] = useState<TaskEvent[]>([])
  const [approval, setApproval] = useState<Approval | null>(null)
  const [auditValid, setAuditValid] = useState<boolean | null>(null)
  const [repoId, setRepoId] = useState("")
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const selected = tasks.find(task => task.id === selectedId) || null
  const terminalEvents = events.filter(event => terminalTypes.has(event.type))
  const installedSkills = Array.from(new Set(runners.flatMap(runner => {
    const skills = runner.capabilities.skills
    return Array.isArray(skills) ? skills.filter((skill): skill is string => typeof skill === "string") : []
  })))

  const refreshOverview = async () => {
    const [nextRepos, nextProjects, nextTasks, nextRunners, audit] = await Promise.all([
      api.repositories(), api.projects(), api.tasks(), api.runners(), api.audit(),
    ])
    setRepositories(nextRepos); setProjects(nextProjects); setTasks(nextTasks); setRunners(nextRunners); setAuditValid(audit.integrity_valid)
    if (!repoId && nextRepos[0]) setRepoId(nextRepos[0].id)
  }

  const refreshApproval = async (taskId: string) => {
    try {
      setApproval(await api.approval(taskId))
    } catch (cause) {
      if (cause instanceof MezoApiError && cause.status === 404) {
        setApproval(null)
        return
      }
      throw cause
    }
  }

  useEffect(() => {
    if (!authenticated) return
    void refreshOverview().catch(cause => setError(cause instanceof Error ? cause.message : "Could not load MEZO"))
    const timer = window.setInterval(() => {
      void refreshOverview().catch(cause => setError(cause instanceof Error ? cause.message : "Could not refresh MEZO"))
    }, 5000)
    return () => window.clearInterval(timer)
  }, [authenticated])

  useEffect(() => {
    abortRef.current?.abort(); setEvents([]); setApproval(null)
    if (!selectedId || !authenticated) return
    const controller = new AbortController(); abortRef.current = controller
    let lastId = 0
    const refreshTask = async () => {
      const task = await api.task(selectedId)
      setTasks(current => current.map(item => item.id === task.id ? task : item))
      if (task.approval_state !== "none") {
        await refreshApproval(task.id)
      } else {
        setApproval(null)
      }
      return task
    }
    const watch = async () => {
      while (!controller.signal.aborted) {
        try {
          await api.streamTask(selectedId, lastId, controller.signal, event => {
            lastId = Math.max(lastId, event.id)
            setEvents(current => current.some(item => item.id === event.id) ? current : [...current, event])
          })
          const task = await refreshTask()
          if (terminalState.has(task.status)) return
          await new Promise(resolve => window.setTimeout(resolve, 1000))
        } catch (cause) {
          if (controller.signal.aborted) return
          setError(cause instanceof Error ? cause.message : "Task stream disconnected")
          await new Promise(resolve => window.setTimeout(resolve, 1500))
        }
      }
    }
    void refreshTask().catch(cause => setError(cause instanceof Error ? cause.message : "Could not refresh task"))
    const refreshTimer = window.setInterval(() => {
      void refreshTask().catch(cause => setError(cause instanceof Error ? cause.message : "Could not refresh task"))
    }, 2000)
    void watch()
    return () => { controller.abort(); window.clearInterval(refreshTimer) }
  }, [selectedId, authenticated])

  if (!authenticated) return <Login onReady={() => setAuthenticated(true)} />

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("")
    try {
      const task = await api.createTask({ repository_id: repoId, title, description })
      setTasks(current => [task, ...current]); setSelectedId(task.id); setTitle(""); setDescription("")
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Task creation failed") }
    finally { setBusy(false) }
  }

  const runTaskAction = async (action: () => Promise<unknown>) => {
    setBusy(true); setError("")
    try {
      await action()
      await refreshOverview()
      if (selectedId) {
        const task = await api.task(selectedId)
        setTasks(current => current.map(item => item.id === task.id ? task : item))
        await refreshApproval(selectedId)
      }
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Action failed") }
    finally { setBusy(false) }
  }

  return <div className="mezo-shell">
    <aside className="left-panel">
      <div className="brand"><div className="brand-icon"><Code2 /></div><div><strong>MEZO AI</strong><span>Agent control plane</span></div></div>
      <NavSection icon={<FolderGit2 />} title="Projects">{projects.length ? projects.map(project => <div className="nav-row" key={project.id}>{project.name}</div>) : <Empty text="No projects" />}</NavSection>
      <NavSection icon={<History />} title="Conversations"><div className="nav-row active">Task workspace</div></NavSection>
      <NavSection icon={<ListChecks />} title="Tasks">{tasks.map(task => <button key={task.id} className={`task-row ${selectedId === task.id ? "active" : ""}`} onClick={() => setSelectedId(task.id)}><span>{task.title}</span><Status value={task.status} /></button>)}</NavSection>
      <NavSection icon={<Server />} title="Runners">{runners.length ? runners.map(runner => <div className="runner-row" key={runner.id}><span className={`runner-dot ${runner.status}`} /> <div><strong>{runner.name}</strong><small>{runner.status}{runner.current_task_id ? " · busy" : ""}</small></div></div>) : <Empty text="No registered runner" />}</NavSection>
      <NavSection icon={<ShieldCheck />} title="Skills">{installedSkills.length ? <div className="skills">{installedSkills.map(skill => <span key={skill}>{skill}</span>)}</div> : <Empty text="No runner skills reported" />}</NavSection>
      <div className={`audit ${auditValid === true ? "ok" : "bad"}`}><ShieldCheck /> Audit chain {auditValid === true ? "verified" : auditValid === false ? "invalid" : "checking"}</div>
    </aside>

    <main className="center-panel">
      <header><div><span className="kicker">REMOTE DEVELOPMENT AGENT</span><h1>{selected?.title || "Start a repository task"}</h1></div>{selected && <Status value={selected.status} />}</header>
      {error && <div className="error banner"><AlertTriangle />{error}</div>}
      {!selected ? <form className="task-composer" onSubmit={submit}>
        <div className="chat-intro"><div className="agent-avatar">M</div><div><strong>MEZO</strong><p>Choose an authorized repository and describe the change. The runner will stop before every external write.</p></div></div>
        <label>Repository<select required value={repoId} onChange={event => setRepoId(event.target.value)}><option value="" disabled>Select repository</option>{repositories.map(repo => <option value={repo.id} key={repo.id}>{repo.full_name}</option>)}</select></label>
        <label>Task title<input required minLength={3} value={title} onChange={event => setTitle(event.target.value)} placeholder="Fix the failing validation workflow" /></label>
        <label>Development task<textarea required minLength={3} value={description} onChange={event => setDescription(event.target.value)} placeholder="Describe the desired outcome, constraints, and acceptance criteria…" /></label>
        <button className="primary" disabled={busy || !repoId}>{busy ? <LoaderCircle className="spin" /> : <Play />}Queue task</button>
      </form> : <>
        <section className="task-summary"><div><span>Repository</span><strong>{selected.repository}</strong></div><div><span>Branch</span><strong>{selected.working_branch}</strong></div><div><span>Runner</span><strong>{selected.runner_id || "Waiting"}</strong></div></section>
        <section className="timeline"><h2><Radio /> Live task timeline</h2>{selected.steps.map(step => <div className={`step ${step.status}`} key={step.id}><div className="step-index">{step.step_index + 1}</div><div><strong>{step.name}</strong><p>{step.description}</p>{step.result_summary && <small>{step.result_summary}</small>}{step.error && <small className="bad">{step.error}</small>}</div><Status value={step.status} /></div>)}</section>
        {selected.status === "waiting_for_approval" && approval && <ApprovalCard approval={approval} busy={busy} onApprove={() => runTaskAction(() => api.decideApproval(selected.id, "approve"))} onReject={() => runTaskAction(() => api.decideApproval(selected.id, "reject"))} onCreate={() => runTaskAction(() => api.createDraftPullRequest(selected.id))} />}
        {selected.error && <div className="failure"><AlertTriangle /><div><strong>Task failed</strong><p>{selected.error}</p></div></div>}
        {selected.pull_request_url && <a className="pr-link" href={selected.pull_request_url} target="_blank" rel="noreferrer"><GitPullRequest />Open Draft Pull Request</a>}
        {!terminalState.has(selected.status) && <button className="danger" disabled={busy} onClick={() => runTaskAction(() => api.cancelTask(selected.id))}><CircleStop />Cancel task</button>}
      </>}
    </main>

    <aside className="right-panel">
      <header><FileCode2 /><div><strong>Workspace evidence</strong><span>Read-only</span></div></header>
      {!selected ? <Empty text="Select a task to inspect its evidence" /> : <>
        <EvidenceSection title="Changed files"><div className="file-list">{selected.changed_files.length ? selected.changed_files.map(file => <div key={file.path}><code>{file.path}</code><span className="plus">+{file.additions ?? "bin"}</span><span className="minus">-{file.deletions ?? "bin"}</span></div>) : <Empty text="No validated changes yet" />}</div></EvidenceSection>
        <EvidenceSection title="Unified diff"><pre className="diff">{selected.diff_text || "Diff becomes available after validation."}</pre></EvidenceSection>
        <EvidenceSection title="Terminal"><pre className="terminal">{terminalEvents.length ? terminalEvents.map(event => `[${new Date(event.timestamp).toLocaleTimeString()}] ${terminalText(event)}`).join("\n") : "Waiting for runner output…"}</pre></EvidenceSection>
        <EvidenceSection title="Tests"><ResultList items={selected.validation_report.tests || []} /></EvidenceSection>
        <EvidenceSection title="Guards"><ResultList items={selected.validation_report.guards || []} /></EvidenceSection>
      </>}
    </aside>
  </div>
}

function NavSection({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) { return <section className="nav-section"><h2>{icon}{title}</h2>{children}</section> }
function EvidenceSection({ title, children }: { title: string; children: React.ReactNode }) { return <section className="evidence"><h2>{title}</h2>{children}</section> }
function Empty({ text }: { text: string }) { return <p className="empty">{text}</p> }
function Status({ value }: { value: string }) { return <span className={`status status-${value}`}>{value.replaceAll("_", " ")}</span> }
function ResultList({ items }: { items: Array<{ command?: string; name?: string; status?: string; exit_code: number }> }) { return <div className="results">{items.length ? items.map((item, index) => <div key={`${item.command || item.name}-${index}`}>{item.exit_code === 0 ? <CheckCircle2 /> : <AlertTriangle />}<code>{item.command || item.name}</code><span>{item.status || `exit ${item.exit_code}`}</span></div>) : <Empty text="No results yet" />}</div> }

function ApprovalCard({ approval, busy, onApprove, onReject, onCreate }: { approval: Approval; busy: boolean; onApprove: () => void; onReject: () => void; onCreate: () => void }) {
  const approved = approval.state === "approved"
  const request = approval.request
  return <section className="approval-card"><div className="approval-head"><ShieldCheck /><div><span>EXTERNAL WRITE APPROVAL</span><h2>Create Draft Pull Request</h2></div></div>
    <dl><dt>Repository</dt><dd>{request.repository}</dd><dt>Branch</dt><dd>{request.working_branch} → {request.base_branch}</dd><dt>Diff hash</dt><dd><code>{approval.diff_hash}</code></dd><dt>Commit</dt><dd><code>{request.commit_sha}</code></dd><dt>Expires</dt><dd>{new Date(approval.expires_at).toLocaleString()}</dd><dt>Diff summary</dt><dd>{request.diff_summary.files} files, +{request.diff_summary.additions} / -{request.diff_summary.deletions}</dd><dt>PR title</dt><dd>{request.pull_request_title}</dd></dl>
    <details><summary>Changed files ({request.changed_files.length})</summary><div className="approval-evidence">{request.changed_files.map(file => <code key={file.path}>{file.path} (+{file.additions ?? "bin"} / -{file.deletions ?? "bin"})</code>)}</div></details>
    <details><summary>Commands and tests</summary><ResultList items={[...request.commands, ...request.tests]} /></details>
    <details><summary>Guard results</summary><ResultList items={request.guards} /></details>
    <details><summary>Known risks ({request.known_risks.length})</summary>{request.known_risks.length ? <ul>{request.known_risks.map(risk => <li key={risk}>{risk}</li>)}</ul> : <p className="empty">No known risks reported.</p>}</details>
    <details><summary>Pull Request body preview</summary><pre className="approval-preview">{request.pull_request_body}</pre></details>
    {!approved ? <div className="approval-actions"><button className="danger" disabled={busy} onClick={onReject}>Reject</button><button className="primary" disabled={busy} onClick={onApprove}>Approve exact diff</button></div> : <button className="primary full" disabled={busy} onClick={onCreate}><GitPullRequest />Create Draft Pull Request now</button>}
  </section>
}
