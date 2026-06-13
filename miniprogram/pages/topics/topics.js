const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    topics: [],
    loading: false,
    generating: false,
    apiKeyConfigured: false,
    selectedTopicId: null,
    emptyState: false,
    loadError: false,
  },

  onLoad() {
    auth.ensureLoggedIn().then(() => {
      this.loadTopics();
      this.loadApiKeyStatus();
    }).catch(err => {
      wx.showToast({ title: '请先登录', icon: 'none' });
    });
  },

  loadTopics() {
    this.setData({ loading: true });
    api.get('/api/hot_topics/today')
      .then(data => {
        this.setData({
          topics: data.topics,
          loading: false,
          emptyState: !data.topics || data.topics.length === 0,
        });
      })
      .catch(err => {
        this.setData({ loading: false, loadError: true, emptyState: true });
        const msg = err.data?.detail || '获取选题失败';
        wx.showToast({ title: msg, icon: 'none' });
      });
  },

  loadApiKeyStatus() {
    api.get('/api/user/api_key/status')
      .then(data => {
        this.setData({ apiKeyConfigured: !!data.configured });
      })
      .catch(() => {
        this.setData({ apiKeyConfigured: false });
      });
  },

  onSelectTopic(e) {
    const selected = this.data.topics.find(item => item.id === e.detail.id) || null;
    this.setData({
      selectedTopicId: selected ? selected.id : null,
    });
  },

  onConfirmTopic() {
    const selected = this.data.topics.find(item => item.id === this.data.selectedTopicId);
    if (!selected || this.data.generating) {
      wx.showToast({ title: '请选择一个热点', icon: 'none' });
      return;
    }
    if (!this.data.apiKeyConfigured) {
      wx.showModal({
        title: '需要配置 API Key',
        content: 'AI 起稿需要先在设置页保存 DeepSeek API Key。',
        confirmText: '去设置',
        success: (res) => {
          if (res.confirm) {
            wx.navigateTo({ url: '/pages/settings/settings' });
          }
        }
      });
      return;
    }

    this.setData({ generating: true });

    api.post('/api/select_topic', { topic: selected.title, hot_topic_id: selected.id })
      .then(data => {
        return api.post('/api/quick_generate', {
          topic_id: selected.id,
          checkin_id: data.checkin_id,
          hot_topic: selected.title,
          angle: selected.ai_angle || '围绕这条热点给出一个能引发讨论的明确判断',
          platform: 'xiaohongshu'
        }).then(result => ({ checkinId: data.checkin_id, result }));
      })
      .then(({ checkinId, result }) => {
        wx.setStorageSync('current_draft', result.content);
        wx.navigateTo({
          url: `/pages/preview/preview?checkin_id=${checkinId}&topic=${encodeURIComponent(selected.title)}`
        });
      })
      .catch(err => {
        const detail = err.data?.detail || '生成失败';
        if (detail.includes('API Key')) {
          wx.showModal({
            title: '需要配置 API Key',
            content: detail,
            confirmText: '去设置',
            success: (res) => {
              if (res.confirm) wx.navigateTo({ url: '/pages/settings/settings' });
            }
          });
        } else {
          wx.showToast({ title: detail, icon: 'none' });
        }
      })
      .finally(() => {
        this.setData({ generating: false });
      });
  },

  onRetryLoad() {
    this.loadTopics();
  }
});
