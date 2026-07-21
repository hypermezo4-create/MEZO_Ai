exports.info = (msg, meta = {}) => {
  console.log(`[INFO] [${new Date().toISOString()}] ${msg}`, JSON.stringify(meta));
};

exports.error = (msg, err = {}) => {
  console.error(`[ERROR] [${new Date().toISOString()}] ${msg}`, err);
};
