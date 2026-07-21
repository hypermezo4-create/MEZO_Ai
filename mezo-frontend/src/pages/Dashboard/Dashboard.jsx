import React from 'react';
import ControlPanel from '../../components/ControlPanel/ControlPanel';
import TrainingDashboard from '../../components/TrainingDashboard/TrainingDashboard';

export default function Dashboard() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <ControlPanel />
      <TrainingDashboard />
    </div>
  );
}
