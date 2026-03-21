const config = require('./config');

App({
  globalData: {
    userInfo: null,
    token: null,
    baseUrl: config.baseUrl
  },
  onLaunch() {
    // Check login status on launch
    const token = wx.getStorageSync('token');
    if (token) {
      this.globalData.token = token;
    }
  }
})
