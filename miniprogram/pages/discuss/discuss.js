const api = require('../../utils/api');

Page({
  data: {
    checkinId: null,
    topic: '',
    messages: [],
    inputText: '',
    loading: false,
    draft: null,
    status: 'discussing',
    inputDisabled: false
  },

  onLoad(options) {
    this.setData({
      checkinId: parseInt(options.checkin_id || 0),
      topic: decodeURIComponent(options.topic || '')
    });

    if (!this.data.topic && this.data.checkinId) {
      api.get(`/api/checkin/${this.data.checkinId}`)
        .then(data => {
          const topic = data.topic || '';
          this.setData({ topic });
          this.addMessage('assistant', `我们来聊聊「${topic}」吧。你对这个话题有什么想说的？`);
        })
        .catch(() => {
          this.addMessage('assistant', '话题加载失败，请返回草稿箱重试。');
          this.setData({ inputDisabled: true });
        });
      return;
    }

    this.addMessage('assistant', `我们来聊聊「${this.data.topic}」吧。你对这个话题有什么想说的？`);
  },

  addMessage(role, content) {
    const messages = this.data.messages;
    messages.push({
      role,
      content,
      time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    });
    this.setData({ messages });
    // Scroll to bottom
    this.scrollToBottom();
  },

  scrollToBottom() {
    wx.createSelectorQuery()
      .select('.message-list')
      .boundingClientRect()
      .exec(() => {
        this.setData({ scrollTop: 99999 });
      });
  },

  onInputChange(e) {
    this.setData({ inputText: e.detail.value });
  },

  onSend() {
    const text = this.data.inputText.trim();
    if (!text || this.data.loading) return;

    // Show user message optimistically first
    this.addMessage('user', text);
    this.setData({ inputText: '', loading: true });

    api.post('/api/generate_content', {
      checkin_id: this.data.checkinId,
      message: text
    })
    .then(data => {
      this.setData({ loading: false, status: data.status });
      this.addMessage('assistant', data.reply);

      if (data.status === 'draft_ready' && data.draft) {
        this.setData({ draft: data.draft, inputDisabled: true });
        wx.setStorageSync('current_draft', data.draft);
        setTimeout(() => {
          wx.navigateTo({
            url: `/pages/preview/preview?checkin_id=${this.data.checkinId}&topic=${encodeURIComponent(this.data.topic)}`
          });
        }, 1000);
      }
    })
    .catch(err => {
      // Remove the user message that was added optimistically on failure
      this.setData({ loading: false });
      const messages = this.data.messages.slice(0, -1);
      this.setData({ messages });
      const detail = err.data?.detail || '消息发送失败，请重试';
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
    });
  }
});
