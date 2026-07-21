const authController = require('../src/controllers/auth.controller');
const { ADMIN_USERNAME, ADMIN_PASSWORD } = require('../src/config/security');

// Mock response builder
function createMockRes() {
  const res = {};
  res.statusCode = 200;
  res.jsonData = null;
  res.status = function(code) {
    this.statusCode = code;
    return this;
  };
  res.json = function(data) {
    this.jsonData = data;
    return this;
  };
  return res;
}

async function runAuthTests() {
  console.log('--- Running Auth Vulnerability Security Verification ---');

  // Test 1: Wrong credentials MUST return HTTP 401
  const reqWrong = {
    body: { username: 'wrong_user', password: 'wrong_password' }
  };
  const resWrong = createMockRes();
  await authController.login(reqWrong, resWrong);

  if (resWrong.statusCode !== 401) {
    throw new Error(`FAIL: Expected status 401 for wrong credentials, got ${resWrong.statusCode}`);
  }
  if (!resWrong.jsonData || resWrong.jsonData.status !== 'error') {
    throw new Error(`FAIL: Expected error json response, got ${JSON.stringify(resWrong.jsonData)}`);
  }
  console.log('✔ Test 1 Passed: Invalid credentials returned 401 Unauthorized.');

  // Test 2: Valid credentials MUST return HTTP 200 with JWT token
  const reqValid = {
    body: { username: ADMIN_USERNAME, password: ADMIN_PASSWORD }
  };
  const resValid = createMockRes();
  await authController.login(reqValid, resValid);

  if (resValid.statusCode !== 200) {
    throw new Error(`FAIL: Expected status 200 for valid credentials, got ${resValid.statusCode}`);
  }
  if (!resValid.jsonData || !resValid.jsonData.token) {
    throw new Error(`FAIL: Expected token in json response, got ${JSON.stringify(resValid.jsonData)}`);
  }
  console.log('✔ Test 2 Passed: Valid credentials returned 200 with JWT token.');

  console.log('--- All Auth Vulnerability Security Verification Tests Passed Successfully! ---');
}

if (require.main === module) {
  runAuthTests().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { runAuthTests };
