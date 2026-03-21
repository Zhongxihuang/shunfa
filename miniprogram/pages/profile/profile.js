const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    userInfo: null,
    achievements: [],
    loading: true
  },

  onShow() {
    this.loadProfile();
  },

  loadProfile() {
    this.setData({ loading: true });
    auth.ensureLoggedIn()
      .then(() => Promise.all([
        api.get('/api/user_status'),
        api.get('/api/achievements')
      ]))
      .then(([userData, achData]) => {
        this.setData({
          userInfo: userData,
          achievements: achData.achievements,
          loading: false
        });
      })
      .catch(() => this.setData({ loading: false }));
  },

  onGoSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  }
});
