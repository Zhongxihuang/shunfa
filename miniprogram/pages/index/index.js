const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    userInfo: null,
    loading: true,
    todayCompleted: false
  },

  onShow() {
    // Refresh on every show (tab switch, back navigation)
    this.loadUserStatus();
  },

  loadUserStatus() {
    this.setData({ loading: true });
    auth.ensureLoggedIn()
      .then(() => api.get('/api/user_status'))
      .then(data => {
        this.setData({
          userInfo: data,
          todayCompleted: data.today_completed,
          loading: false
        });
      })
      .catch(err => {
        this.setData({ loading: false });
        if (!this.data.userInfo) {
          // First time, try login
          auth.login().then(() => this.loadUserStatus());
        }
      });
  },

  onStartWriting() {
    wx.navigateTo({ url: '/pages/topics/topics' });
  }
});
