const fs = require('fs').promises;
const path = require('path');

exports.listFiles = async (subPath = '') => {
  const rootDir = process.cwd();
  const targetDir = path.join(rootDir, subPath);
  try {
    const items = await fs.readdir(targetDir, { withFileTypes: true });
    return items.map(item => ({
      name: item.name,
      isDirectory: item.isDirectory(),
      path: path.join(subPath, item.name)
    }));
  } catch (err) {
    return [];
  }
};

exports.readFile = async (filePath) => {
  const rootDir = process.cwd();
  const fullPath = path.join(rootDir, filePath);
  try {
    const data = await fs.readFile(fullPath, 'utf8');
    return data;
  } catch (err) {
    return 'Error reading file content';
  }
};
