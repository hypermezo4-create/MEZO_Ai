import React, { useState, useEffect } from 'react';
import './KillSwitch.css';

/**
 * KillSwitch — header button + status indicator.
 * 
 * Shows the current kill switch state in the top navigation bar.
 * ARMED = green shield = normal operation.
 * DISARMED = red pulsing stop icon = all plugin executions blocked.
 *
 * Requires: POST /api/control/kill-switch/disarm | /arm
 */
export default function KillSwitch() {
  const [armed, setArmed] = useState(true);
  const [loading, setLoading] = useState(false);
  const [disarmedBy, setDisarmedBy] = useState(null);

  useEffect(() => {
    fetchStatus();
    // Poll every 15s to stay in sync if another client changes state
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/control/kill-switch/status');
      const data = await res.json();
      setArmed(data.armed);
      setDisarmedBy(data.disarmed_by);
    } catch { /* silent — don't flash errors for status polls */ }
  };

  const toggle = async () => {
    if (loading) return;
    const action = armed ? 'disarm' : 'arm';

    if (armed) {
      // Ask for confirmation before disarming
      const confirmed = window.confirm(
        'هل أنت متأكد؟ سيؤدي إيقاف وكيل MEZO AI إلى حظر جميع عمليات الإضافات الجديدة.'
      );
      if (!confirmed) return;
    }

    setLoading(true);
    try {
      const res = await fetch(`/api/control/kill-switch/${action}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-ID': localStorage.getItem('mezo_user_id') || 'frontend-user',
        },
      });
      const data = await res.json();
      setArmed(data.status.armed);
      setDisarmedBy(data.status.disarmed_by);
    } catch (err) {
      console.error('[KillSwitch] Toggle error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`kill-switch ${armed ? 'kill-switch--armed' : 'kill-switch--disarmed'}`}>
      <button
        id="kill-switch-btn"
        className={`kill-switch-btn ${loading ? 'kill-switch-btn--loading' : ''}`}
        onClick={toggle}
        disabled={loading}
        aria-label={armed ? 'إيقاف وكيل MEZO AI' : 'تشغيل وكيل MEZO AI'}
        title={armed ? 'انقر لإيقاف الوكيل' : `موقوف بواسطة: ${disarmedBy || 'غير معروف'}`}
      >
        {loading ? (
          <span className="ks-spinner" />
        ) : armed ? (
          <>
            <span className="ks-icon">🛡️</span>
            <span className="ks-label">الوكيل نشط</span>
          </>
        ) : (
          <>
            <span className="ks-icon ks-icon--pulsing">🛑</span>
            <span className="ks-label">موقوف</span>
          </>
        )}
      </button>
    </div>
  );
}
