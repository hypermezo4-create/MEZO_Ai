const aiService = require('../services/ai.service');

exports.sendMessage = async (req, res) => {
  try {
    const { prompt, model } = req.body;
    const response = await aiService.generateText(prompt, model);
    return res.json({
      status: 'success',
      data: response
    });
  } catch (error) {
    return res.status(500).json({ status: 'error', message: error.message });
  }
};

exports.getConversations = async (req, res) => {
  return res.json({
    status: 'success',
    conversations: [
      { id: '1', title: 'محادثة تطوير النظام', createdAt: new Date() }
    ]
  });
};
