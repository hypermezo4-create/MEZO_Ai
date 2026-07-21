import React, { useState, useEffect, useRef } from 'react';
import './WorkflowPanel.css';

const STATUS_ICONS = {
  pending:                  '⏳',
  running:                  '🔄',
  done:                     '✅',
  failed:                   '❌',
  blocked_on_confirmation:  '⏸️',
  skipped:                  '⏭️',
};

const STATUS_LABELS = {
  pending:                  'في الانتظار',
  running:                  'جارٍ التنفيذ...',
  done:                     'مكتمل',
  failed:                   'فشل',
  blocked_on_confirmation:  'بانتظار التأكيد',
  skipped:                  'تم التخطي',
};

/**
 * WorkflowPanel — live multi-step workflow tracker.
 *
 * Connects to GET /api/tasks/{taskId}/stream (SSE) and shows
 * per-step status in real time. Renders a confirmation dialog
 * for Tier.IRREVERSIBLE steps.
 */
export default function WorkflowPanel({ taskId, onClose }) {
  const [task, setTask] = useState(null);
  const [steps, setSteps] = useState([]);
  const [taskStatus, setTaskStatus] = useState('pending');
  const [confirmStep, setConfirmStep] = useState(null); // step with pending confirmation
  const [confirmCountdown, setConfirmCountdown] = useState(60);
  const esRef = useRef(null);
  const countdownRef = useRef(null);

  // ── SSE connection ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!taskId) return;

    const es = new EventSource(`/api/tasks/${taskId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);

        if (data.event === 'snapshot') {
          setTask(data.task);
          setSteps(data.task.steps || []);
          setTaskStatus(data.task.status);
        } else if (data.event === 'step_update') {
          setTaskStatus(data.task_status);
          setSteps(prev => {
            const next = [...prev];
            if (data.step_index < next.length) {
              next[data.step_index] = { ...next[data.step_index], ...data.step };
            }
            return next;
          });

          // Surface confirmation request
          if (data.step?.status === 'blocked_on_confirmation' && data.step?.confirmation_request) {
            setConfirmStep({ index: data.step_index, req: data.step.confirmation_request });
            setConfirmCountdown(60);
          }
        } else if (data.event === 'done') {
          es.close();
        }
      } catch (err) {
        console.error('[WorkflowPanel] SSE parse error:', err);
      }
    };

    es.onerror = () => es.close();

    return () => es.close();
  }, [taskId]);

  // ── Auto-cancel countdown for confirmation dialogs ──────────────────────────
  useEffect(() => {
    if (!confirmStep) return;
    countdownRef.current = setInterval(() => {
      setConfirmCountdown(c => {
        if (c <= 1) {
          clearInterval(countdownRef.current);
          handleConfirmResponse(false);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(countdownRef.current);
  }, [confirmStep]);

  // ── Confirmation response ───────────────────────────────────────────────────
  const handleConfirmResponse = async (confirmed) => {
    if (!confirmStep) return;
    clearInterval(countdownRef.current);
    setConfirmStep(null);

    try {
      await fetch(`/api/tasks/${taskId}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_index: confirmStep.index, confirmed }),
      });
    } catch (err) {
      console.error('[WorkflowPanel] confirm error:', err);
    }
  };

  const overallDone   = taskStatus === 'done';
  const overallFailed = taskStatus === 'failed';

  return (
    <div className="workflow-panel">
      <div className="workflow-header">
        <div className="workflow-title">
          <span className="workflow-icon">⚙️</span>
          <span>{task?.name || 'تنفيذ مهمة متعددة الخطوات'}</span>
          <span className={`task-badge task-badge--${taskStatus}`}>{taskStatus}</span>
        </div>
        {onClose && (
          <button className="workflow-close-btn" onClick={onClose} aria-label="إغلاق">×</button>
        )}
      </div>

      {task?.description && (
        <p className="workflow-description">{task.description}</p>
      )}

      {/* Step list */}
      <ol className="workflow-steps">
        {steps.map((step, i) => (
          <li
            key={i}
            className={`workflow-step workflow-step--${step.status}`}
          >
            <span className="step-icon" aria-label={STATUS_LABELS[step.status]}>
              {STATUS_ICONS[step.status] || '○'}
            </span>
            <div className="step-body">
              <div className="step-name">{step.name}</div>
              {step.description && <div className="step-desc">{step.description}</div>}
              {step.status === 'running' && (
                <div className="step-spinner">
                  <span className="spinner" />
                  <span>{STATUS_LABELS.running}</span>
                </div>
              )}
              {step.status === 'failed' && step.error && (
                <div className="step-error">⚠️ {step.error}</div>
              )}
              {step.status === 'done' && step.result && (
                <div className="step-result">
                  {typeof step.result === 'string' ? step.result : JSON.stringify(step.result, null, 2)}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>

      {/* Tier-3 Confirmation Dialog */}
      {confirmStep && (
        <div className="confirm-overlay" role="dialog" aria-modal="true">
          <div className="confirm-dialog">
            <div className="confirm-header">
              <span className="confirm-warning-icon">⚠️</span>
              <strong>إجراء غير قابل للتراجع — يتطلب تأكيدًا</strong>
            </div>
            <div className="confirm-action">
              <span className="confirm-label">الإجراء:</span>
              <code>{confirmStep.req.action_name}</code>
            </div>
            <div className="confirm-target">
              <span className="confirm-label">الهدف:</span>
              <code className="confirm-target-path">{confirmStep.req.target}</code>
            </div>
            {confirmStep.req.impact && (
              <div className="confirm-impact">
                <span className="confirm-label">التأثير:</span>
                <span>{confirmStep.req.impact}</span>
              </div>
            )}
            <div className="confirm-countdown">
              سيتم الإلغاء تلقائيًا خلال <strong>{confirmCountdown}s</strong>
            </div>
            <div className="confirm-actions">
              <button
                id="confirm-reject-btn"
                className="btn-secondary confirm-btn"
                onClick={() => handleConfirmResponse(false)}
              >
                إلغاء
              </button>
              <button
                id="confirm-approve-btn"
                className="btn-danger confirm-btn"
                onClick={() => handleConfirmResponse(true)}
              >
                تأكيد التنفيذ
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Completion banner */}
      {overallDone && (
        <div className="workflow-done-banner">✅ اكتملت جميع الخطوات بنجاح</div>
      )}
      {overallFailed && (
        <div className="workflow-failed-banner">❌ فشل سير العمل — راجع الخطأ أعلاه</div>
      )}
    </div>
  );
}
