const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const cors = require('cors');

const authRoutes = require('./src/routes/auth.routes');
const chatRoutes = require('./src/routes/chat.routes');
const apiRoutes = require('./src/routes/api.routes');
const adminRoutes = require('./src/routes/admin.routes');
const { rateLimiter } = require('./src/middleware/rate-limit');
const logger = require('./src/utils/logger');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server, path: '/ws' });

app.use(cors());
app.use(express.json());
app.use(rateLimiter());

// Register API Routes
app.use('/api/auth', authRoutes);
app.use('/api/chat', chatRoutes);
app.use('/api', apiRoutes);
app.use('/api/admin', adminRoutes);

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// WebSocket Handler
wss.on('connection', (ws) => {
  logger.info('New WebSocket connection established');
  ws.send(JSON.stringify({ event: 'connected', payload: { message: 'Connected to MEZO Backend Gateway' } }));

  ws.on('message', (message) => {
    logger.info(`Received WS message: ${message}`);
  });
});

const PORT = process.env.PORT || 5000;
server.listen(PORT, () => {
  logger.info(`MEZO Backend server running on port ${PORT}`);
});
