const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    userInfo: null,
    achievements: [],
    recentCheckins: [],
    draftCount: 0,
    loading: true,
    freezeCost: 5,
    redeeming: false
  },

  onShow() {
    this.loadProfile();
  },

  loadProfile() {
    this.setData({ loading: true, error: false });
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
      .catch(() => this.setData({ loading: false, error: true }));
  },

  onRetryLoad() {
    this.loadProfile();
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
  },

  onRedeemFreeze() {
    if (this.data.redeeming) return;
    this.setData({ redeeming: true });
    api.post('/api/redeem', { item: 'streak_freeze' })
      .then((res) => {
        // Reflect the new balance immediately, then re-sync from the server.
        this.setData({
          'userInfo.diamonds': res.diamonds,
          'userInfo.streak_freezes': res.streak_freezes,
          redeeming: false
        });
        wx.showToast({ title: `已兑换，共 ${res.streak_freezes} 张`, icon: 'success' });
      })
      .catch((err) => {
        this.setData({ redeeming: false });
        const msg = (err && err.data && (err.data.message || err.data.detail)) || '兑换失败，请稍后重试';
        wx.showToast({ title: msg, icon: 'none' });
      });
  }
});
