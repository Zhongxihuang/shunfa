const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    userInfo: null,
    achievements: [],
    recentCheckins: [],
    draftCount: 0,
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
        api.get('/api/achievements'),
        api.get('/api/my/checkins', { limit: 3, offset: 0 }),
        api.get('/api/my/checkins', { status_filter: 'draft', limit: 1, offset: 0 })
      ]))
      .then(([userData, achData, checkinsData, draftsData]) => {
        this.setData({
          userInfo: userData,
          achievements: achData.achievements,
          recentCheckins: checkinsData.checkins,
          draftCount: draftsData.draft_count,
          loading: false
        });
      })
      .catch(() => this.setData({ loading: false }));
  },

  onGoSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' });
  },

  onGoHistory(e) {
    const filter = e.currentTarget.dataset.filter || 'all';
    wx.navigateTo({ url: `/pages/history/history?tab=${filter}` });
  },

  onGoDrafts() {
    wx.navigateTo({ url: '/pages/drafts/drafts' });
  },

  onViewCheckin(e) {
    const { id } = e.currentTarget.dataset;
    wx.navigateTo({ url: `/pages/preview/preview?checkin_id=${id}` });
  }
});
