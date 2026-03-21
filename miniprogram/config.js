// Environment configuration
// To switch environment: change ENV to 'production', then recompile
const ENV = 'development';

const configs = {
  development: {
    baseUrl: 'http://localhost:8000',
  },
  production: {
    baseUrl: 'https://api.your-domain.com',  // Replace with real domain before deploying
  }
};

module.exports = configs[ENV];
