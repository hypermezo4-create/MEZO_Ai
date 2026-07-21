const crypto = require('crypto');

const ALGORITHM = 'aes-256-gcm';
const SECRET_KEY = crypto.scryptSync('mezo-secret-key-salt', 'salt', 32);

exports.encrypt = (text) => {
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv(ALGORITHM, SECRET_KEY, iv);
  let encrypted = cipher.update(text, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  const authTag = cipher.getAuthTag().toString('hex');
  return { iv: iv.toString('hex'), encrypted, authTag };
};

exports.decrypt = ({ iv, encrypted, authTag }) => {
  const decipher = crypto.createDecipheriv(ALGORITHM, SECRET_KEY, Buffer.from(iv, 'hex'));
  decipher.setAuthTag(Buffer.from(authTag, 'hex'));
  let decrypted = decipher.update(encrypted, 'hex', 'utf8');
  decrypted += decipher.final('utf8');
  return decrypted;
};
