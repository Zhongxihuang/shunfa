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
    baseUrl: 'http://127.0.0.1:8000',
    reminderTemplateId: 'YOUR_WECHAT_SUBSCRIBE_TEMPLATE_ID',
  },
  production: {
    baseUrl: 'https://your-backend.example.com',
    reminderTemplateId: 'YOUR_WECHAT_SUBSCRIBE_TEMPLATE_ID',
  }
};

module.exports = configs[ENV];
