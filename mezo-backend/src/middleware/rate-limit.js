const requests = new Map();

exports.rateLimiter = (maxRequests = 100, windowMs = 60000) => {
  return (req, res, next) => {
    const ip = req.ip || '127.0.0.1';
    const now = Date.now();

    if (!requests.has(ip)) {
      requests.set(ip, []);
    }

    const timestamps = requests.get(ip).filter(t => now - t < windowMs);
    if (timestamps.length >= maxRequests) {
      return res.status(429).json({ status: 'error', message: 'تم تجاوز الحد المسموح من الطلبات' });
    }

    timestamps.push(now);
    requests.set(ip, timestamps);
    next();
  };
};
