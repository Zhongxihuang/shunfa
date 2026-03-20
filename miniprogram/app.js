App({
  globalData: {
    userInfo: null,
    token: null,
    baseUrl: 'http://localhost:8000'
  },
  onLaunch() {
    // Check login status on launch
    const token = wx.getStorageSync('token');
    if (token) {
      this.globalData.token = token;
    }
  }
})
