const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    topics: [],
    refreshCount: 0,
    maxRefreshes: 3,
    loading: false,
    selectedTopic: null,
    customTopic: '',
    showCustomInput: false
  },

  onLoad() {
    auth.ensureLoggedIn().then(() => {
      this.loadTopics();
    }).catch(err => {
      wx.showToast({ title: '请先登录', icon: 'none' });
    });
  },

  loadTopics() {
    this.setData({ loading: true });
    api.post('/api/daily_topics')
      .then(data => {
        this.setData({
          topics: data.topics,
          refreshCount: data.refresh_count,
          maxRefreshes: data.max_refreshes,
          loading: false
        });
      })
      .catch(err => {
        this.setData({ loading: false });
        const msg = err.data?.detail || '获取选题失败';
        wx.showToast({ title: msg, icon: 'none' });
      });
  },

  onRefresh() {
    if (this.data.refreshCount >= this.data.maxRefreshes) {
      wx.showToast({ title: '今日换题次数已用完', icon: 'none' });
      return;
    }
    this.loadTopics();
  },

  onSelectTopic(e) {
    const topic = e.currentTarget.dataset.topic;
    this.setData({ selectedTopic: topic });
  },

  onConfirmTopic() {
    const topic = this.data.selectedTopic || this.data.customTopic.trim();
    if (!topic) {
      wx.showToast({ title: '请选择或输入一个选题', icon: 'none' });
      return;
    }

    api.post('/api/select_topic', { topic })
      .then(data => {
        wx.navigateTo({
          url: `/pages/discuss/discuss?checkin_id=${data.checkin_id}&topic=${encodeURIComponent(topic)}`
        });
      })
      .catch(err => {
        wx.showToast({ title: err.data?.detail || '选题失败', icon: 'none' });
      });
  },

  onCustomInput(e) {
    this.setData({ customTopic: e.detail.value });
  },

  onToggleCustomInput() {
    this.setData({ showCustomInput: !this.data.showCustomInput });
  }
});
