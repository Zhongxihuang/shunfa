const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    userInfo: null,
    loading: true
  },

  onShow() {
    this.loadProfile();
  },

  loadProfile() {
    this.setData({ loading: true });
    auth.ensureLoggedIn()
      .then(() => api.get('/api/user_status'))
      .then(data => {
        this.setData({ userInfo: data, loading: false });
      })
      .catch(() => {
        this.setData({ loading: false });
      });
  },

  onGoSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  }
});
