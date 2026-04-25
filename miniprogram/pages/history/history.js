const api = require('../../utils/api');
const auth = require('../../utils/auth');

const PAGE_SIZE = 20;

Page({
  data: {
    checkins: [],
    activeTab: 'all',
    loading: false,
    loadingMore: false,
    error: false,
    hasMore: true,
    offset: 0
  },

  onLoad(options) {
    const tab = options.tab || 'all';
    this.setData({ activeTab: tab });
    auth.ensureLoggedIn().then(() => {
      this.loadCheckins(true);
    });
  },

  onSwitchTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (tab === this.data.activeTab) return;
    this.setData({
      activeTab: tab,
      checkins: [],
      offset: 0,
      hasMore: true
    });
    this.loadCheckins(true);
  },

  loadCheckins(reset = false) {
    if (this.data.loading) return;
    if (reset) {
      this.setData({ loading: true, error: false });
    }

    const offset = reset ? 0 : this.data.offset;
    const statusFilter = this.data.activeTab === 'all' ? null : this.data.activeTab;

    api.get('/api/my/checkins', {
      status_filter: statusFilter,
      limit: PAGE_SIZE,
      offset: offset
    })
      .then(data => {
        const newCheckins = reset ? data.checkins : [...this.data.checkins, ...data.checkins];
        this.setData({
          checkins: newCheckins,
          loading: false,
          loadingMore: false,
          error: false,
          offset: offset + data.checkins.length,
          hasMore: data.checkins.length === PAGE_SIZE
        });
      })
      .catch(err => {
        this.setData({
          loading: false,
          loadingMore: false,
          error: true
        });
      });
  },

  onViewCheckin(e) {
    const { id, status } = e.currentTarget.dataset;
    // All checkins go to preview page - the preview page handles different statuses
    wx.navigateTo({
      url: `/pages/preview/preview?checkin_id=${id}`
    });
  },

  onRetryLoad() {
    this.loadCheckins(true);
  },

  onLoadMore() {
    if (this.data.loadingMore || !this.data.hasMore) return;
    this.setData({ loadingMore: true });
    this.loadCheckins(false);
  },

  onGoTopics() {
    wx.switchTab({ url: '/pages/index/index' });
  }
});
