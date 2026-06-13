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
        if (data.reminder_needed) {
          wx.showToast({
            title: '该写今天的内容了！',
            icon: 'none',
            duration: 3000
          });
        }
      })
      .catch(err => {
        this.setData({ loading: false });
        if (!this.data.userInfo) {
          wx.showModal({
            title: '登录失败',
            content: '无法获取登录状态，请检查网络后重试',
            confirmText: '重新登录',
            cancelText: '取消',
            success: res => {
              if (res.confirm) {
                auth.login()
                  .then(() => this.loadUserStatus())
                  .catch(() => {
                    wx.showToast({ title: '登录失败，请稍后重试', icon: 'none' });
                  });
              }
            }
          });
        }
      });
  },

  onStartWriting() {
    wx.navigateTo({ url: '/pages/topics/topics' });
  },

  goComposeImage() {
    wx.navigateTo({ url: '/pages/compose-image/compose-image' });
  }
});
