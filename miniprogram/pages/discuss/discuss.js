const api = require('../../utils/api');

Page({
  data: {
    checkinId: null,
    topic: '',
    messages: [],
    inputText: '',
    loading: false,
    draft: null,
    status: 'discussing'
  },

  onLoad(options) {
    this.setData({
      checkinId: parseInt(options.checkin_id),
      topic: decodeURIComponent(options.topic || '')
    });

    // Add welcome message
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
        this.setData({ draft: data.draft });
        wx.setStorageSync('current_draft', data.draft);
        setTimeout(() => {
          wx.navigateTo({
            url: `/pages/preview/preview?checkin_id=${this.data.checkinId}`
          });
        }, 1000);
      }
    })
    .catch(err => {
      this.setData({ loading: false });
      this.addMessage('assistant', '抱歉，出了点问题，请重试～');
    });
  }
});
