const fileService = require('../services/file.service');

exports.listFiles = async (req, res) => {
  const targetPath = req.query.path || '';
  const files = await fileService.listFiles(targetPath);
  return res.json({ status: 'success', files });
};

exports.readFile = async (req, res) => {
  const targetPath = req.query.path;
  const content = await fileService.readFile(targetPath);
  return res.json({ status: 'success', content });
};
