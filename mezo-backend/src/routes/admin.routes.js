const express = require('express');
const router = express.Router();

router.get('/metrics', (req, res) => {
  res.json({
    status: 'success',
    metrics: {
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      activeServices: 10
    }
  });
});

module.exports = router;
