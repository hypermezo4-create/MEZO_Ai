module.exports = {
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  user: process.env.DB_USER || 'mezo_user',
  password: process.env.DB_PASSWORD || 'mezo_password',
  database: process.env.DB_NAME || 'mezo_db'
};
