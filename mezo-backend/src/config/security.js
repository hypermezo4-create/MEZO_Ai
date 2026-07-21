module.exports = {
  JWT_SECRET: process.env.JWT_SECRET || 'mezo-super-secret-jwt-key-2026',
  SALT_ROUNDS: 10,
  ADMIN_USERNAME: process.env.ADMIN_USERNAME || 'mezo_admin',
  ADMIN_PASSWORD: process.env.ADMIN_PASSWORD || 'MezoSecureP@ss2026!'
};

