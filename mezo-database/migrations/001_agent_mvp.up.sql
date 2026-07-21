CREATE TABLE users (
  id VARCHAR(36) PRIMARY KEY,
  email VARCHAR(320) NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role VARCHAR(16) NOT NULL CHECK (role IN ('owner','operator','viewer')),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_users_email ON users(email);

CREATE TABLE repositories (
  id VARCHAR(36) PRIMARY KEY,
  full_name VARCHAR(255) NOT NULL UNIQUE,
  default_branch VARCHAR(255) NOT NULL DEFAULT 'main',
  github_installation_id VARCHAR(64),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_by VARCHAR(36) NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_repositories_full_name ON repositories(full_name);

CREATE TABLE projects (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  repository_id VARCHAR(36) NOT NULL REFERENCES repositories(id),
  owner_id VARCHAR(36) NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_projects_repository_id ON projects(repository_id);
CREATE INDEX ix_projects_owner_id ON projects(owner_id);

CREATE TABLE runners (
  id VARCHAR(36) PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE,
  auth_token_hash TEXT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'online',
  version VARCHAR(64) NOT NULL,
  capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
  current_task_id VARCHAR(36),
  last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  disk_total_bytes BIGINT,
  disk_free_bytes BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_runners_last_heartbeat_at ON runners(last_heartbeat_at);

CREATE TABLE tasks (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(36) NOT NULL REFERENCES users(id),
  project_id VARCHAR(36) REFERENCES projects(id),
  repository_id VARCHAR(36) NOT NULL REFERENCES repositories(id),
  repository VARCHAR(255) NOT NULL,
  base_branch VARCHAR(255) NOT NULL,
  working_branch VARCHAR(255) NOT NULL UNIQUE,
  title VARCHAR(240) NOT NULL,
  description TEXT NOT NULL,
  status VARCHAR(40) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','provisioning','planning','running','waiting_for_approval','validating','creating_pull_request','completed','failed','cancelled')),
  current_step VARCHAR(200),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  runner_id VARCHAR(36) REFERENCES runners(id),
  workspace_id VARCHAR(255),
  error TEXT,
  approval_state VARCHAR(24) NOT NULL DEFAULT 'none' CHECK (approval_state IN ('none','pending','approved','rejected','expired','invalidated')),
  pull_request_url TEXT,
  diff_text TEXT,
  diff_hash VARCHAR(64),
  commit_sha VARCHAR(40),
  changed_files JSONB NOT NULL DEFAULT '[]'::jsonb,
  validation_report JSONB NOT NULL DEFAULT '{}'::jsonb,
  pull_request_title VARCHAR(240),
  pull_request_body TEXT,
  cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
  lease_expires_at TIMESTAMPTZ
);
CREATE INDEX ix_tasks_user_id ON tasks(user_id);
CREATE INDEX ix_tasks_status ON tasks(status);
CREATE INDEX ix_tasks_created_at ON tasks(created_at);
CREATE INDEX ix_tasks_user_created ON tasks(user_id, created_at);
CREATE INDEX ix_tasks_status_created ON tasks(status, created_at);

CREATE TABLE task_steps (
  id VARCHAR(36) PRIMARY KEY,
  task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  step_index INTEGER NOT NULL,
  name VARCHAR(160) NOT NULL,
  description TEXT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','completed','failed','skipped','blocked','waiting_for_approval')),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  command TEXT,
  exit_code INTEGER,
  result_summary TEXT,
  error TEXT,
  requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT uq_task_step_index UNIQUE(task_id, step_index)
);
CREATE INDEX ix_task_steps_task_id ON task_steps(task_id);

CREATE TABLE task_events (
  id BIGSERIAL PRIMARY KEY,
  task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  event_type VARCHAR(64) NOT NULL,
  stream VARCHAR(16),
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_task_events_task_id ON task_events(task_id);

CREATE TABLE approvals (
  id VARCHAR(36) PRIMARY KEY,
  task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  diff_hash VARCHAR(64) NOT NULL,
  user_id VARCHAR(36) NOT NULL REFERENCES users(id),
  action VARCHAR(64) NOT NULL,
  state VARCHAR(24) NOT NULL DEFAULT 'pending' CHECK (state IN ('none','pending','approved','rejected','expired','invalidated')),
  request_snapshot JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMPTZ NOT NULL,
  decided_at TIMESTAMPTZ
);
CREATE INDEX ix_approvals_task_id ON approvals(task_id);
CREATE INDEX ix_approvals_task_created ON approvals(task_id, created_at);

CREATE TABLE audit_logs (
  id BIGSERIAL PRIMARY KEY,
  actor_type VARCHAR(32) NOT NULL,
  actor_id VARCHAR(64) NOT NULL,
  action VARCHAR(128) NOT NULL,
  task_id VARCHAR(36),
  request_id VARCHAR(64),
  result VARCHAR(32) NOT NULL,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  previous_hash VARCHAR(64) NOT NULL,
  entry_hash VARCHAR(64) NOT NULL UNIQUE
);
CREATE INDEX ix_audit_logs_task_id ON audit_logs(task_id);

CREATE TABLE audit_chain_head (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  head_hash VARCHAR(64) NOT NULL,
  signature VARCHAR(64) NOT NULL
);

CREATE TABLE system_settings (
  key VARCHAR(100) PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE provider_configs (
  name VARCHAR(64) PRIMARY KEY,
  model VARCHAR(160) NOT NULL,
  base_url TEXT,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  priority INTEGER NOT NULL DEFAULT 100,
  updated_by VARCHAR(36) NOT NULL REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
