const trainingService = require('../services/training.service');

exports.getStatus = async (req, res) => {
  const status = await trainingService.getStatus();
  return res.json({ status: 'success', data: status });
};

exports.startTraining = async (req, res) => {
  const config = req.body;
  const job = await trainingService.startTraining(config);
  return res.json({ status: 'success', job });
};
