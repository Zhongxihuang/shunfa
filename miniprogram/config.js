const getEnv = () => {
  try {
    const envVersion = wx.getAccountInfoSync().miniProgram.envVersion;
    return envVersion === 'release' ? 'production' : 'development';
  } catch (err) {
    return 'development';
  }
};

const ENV = getEnv();

const configs = {
  development: {
    baseUrl: 'http://127.0.0.1:8080',
    reminderTemplateId: 'JVoKTiV5hVsvD916S3Ma5AbcgW7QRGGR6dYrPItzpzM',
  },
  production: {
    baseUrl: 'https://shunfa-production.up.railway.app',
    reminderTemplateId: 'JVoKTiV5hVsvD916S3Ma5AbcgW7QRGGR6dYrPItzpzM',
  }
};

module.exports = configs[ENV];
