exports.validateBody = (requiredFields) => {
  return (req, res, next) => {
    for (const field of requiredFields) {
      if (!req.body || req.body[field] === undefined) {
        return res.status(400).json({ status: 'error', message: `الحقل المطلوبة مفقود: ${field}` });
      }
    }
    next();
  };
};
