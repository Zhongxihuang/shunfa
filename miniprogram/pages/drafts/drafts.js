const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    checkins: [],
    loading: false,
    error: false
  },

  onLoad() {
    auth.ensureLoggedIn().then(() => {
      this.loadDrafts();
    });
  },

  loadDrafts() {
    this.setData({ loading: true, error: false });
    api.get('/api/my/checkins', {
      status_filter: 'draft',
      limit: 100,
      offset: 0
    })
      .then(data => {
        this.setData({
          checkins: data.checkins,
          loading: false,
          error: false
        });
      })
      .catch(err => {
        this.setData({
          loading: false,
          error: true
        });
      });
  },

  onContinueDraft(e) {
    const { id, status } = e.currentTarget.dataset;
    if (status === 'topic_selected' || status === 'discussing') {
      wx.navigateTo({
        url: `/pages/discuss/discuss?checkin_id=${id}`
      });
      return;
    }
    wx.navigateTo({
      url: `/pages/preview/preview?checkin_id=${id}`
    });
  },

  onRetryLoad() {
    this.loadDrafts();
  },

  onGoTopics() {
    wx.switchTab({ url: '/pages/index/index' });
  }
});
