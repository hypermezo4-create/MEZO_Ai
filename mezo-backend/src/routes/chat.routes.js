const express = require('express');
const router = express.Router();
const chatController = require('../controllers/chat.controller');

router.post('/message', chatController.sendMessage);
router.get('/conversations', chatController.getConversations);

module.exports = router;
