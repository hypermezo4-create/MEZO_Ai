exports.getStatus = async () => {
  return {
    status: 'idle',
    lastRun: new Date().toISOString(),
    datasetCount: 14250,
    currentEpoch: 0,
    totalEpochs: 10
  };
};

exports.startTraining = async (config) => {
  return {
    jobId: `job_${Date.now()}`,
    status: 'started',
    config
  };
};
