const api = require('./api');

const app = getApp();

const login = () => {
  return new Promise((resolve, reject) => {
    wx.login({
      success: (res) => {
        if (res.code) {
          api.post('/api/login', { code: res.code })
            .then((data) => {
              // Store token
              app.globalData.token = data.token;
              app.globalData.userInfo = data.user;
              wx.setStorageSync('token', data.token);
              resolve(data);
            })
            .catch(reject);
        } else {
          reject(new Error('wx.login failed: ' + res.errMsg));
        }
      },
      fail: reject
    });
  });
};

const logout = () => {
  app.globalData.token = null;
  app.globalData.userInfo = null;
  wx.removeStorageSync('token');
};

const ensureLoggedIn = () => {
  if (app.globalData.token) {
    return Promise.resolve(app.globalData.userInfo);
  }
  return login();
};

module.exports = { login, logout, ensureLoggedIn };
