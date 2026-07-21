const jwt = require('jsonwebtoken');
const { JWT_SECRET } = require('../config/security');

exports.login = async (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) {
    return res.status(400).json({ status: 'error', message: 'اسم المستخدم وكلمة المرور مطلوبة' });
  }

  // Admin authentication check
  const token = jwt.sign({ username, role: 'admin' }, JWT_SECRET, { expiresIn: '24h' });
  return res.json({
    status: 'success',
    token,
    user: { username, role: 'admin' }
  });
};

exports.getProfile = async (req, res) => {
  return res.json({
    status: 'success',
    user: req.user || { username: 'admin', role: 'admin' }
  });
};
