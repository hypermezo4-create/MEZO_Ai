const express = require('express');
const router = express.Router();
const fileController = require('../controllers/file.controller');
const trainingController = require('../controllers/training.controller');

router.get('/files/list', fileController.listFiles);
router.get('/files/read', fileController.readFile);
router.get('/training/status', trainingController.getStatus);
router.post('/training/start', trainingController.startTraining);

module.exports = router;
