const api = require('../../utils/api');

Page({
  data: {
    checkinId: null,
    content: '',
    originalDraft: '',
    submitting: false
  },

  onLoad(options) {
    const draft = decodeURIComponent(options.draft || '');
    this.setData({
      checkinId: parseInt(options.checkin_id),
      content: draft,
      originalDraft: draft
    });
  },

  onContentChange(e) {
    this.setData({ content: e.detail.value });
  },

  onRegenerate() {
    // Go back to discuss page to continue the conversation
    wx.navigateBack();
  },

  onConfirm() {
    if (this.data.submitting) return;

    const content = this.data.content.trim();
    if (!content) {
      wx.showToast({ title: '内容不能为空', icon: 'none' });
      return;
    }

    this.setData({ submitting: true });

    api.post('/api/confirm_content', {
      checkin_id: this.data.checkinId,
      content: content
    })
    .then(() => {
      return api.post('/api/confirm_publish', {
        checkin_id: this.data.checkinId
      });
    })
    .then(data => {
      this.setData({ submitting: false });
      wx.showToast({ title: data.message || '发布成功！', icon: 'success' });
      setTimeout(() => {
        wx.switchTab({ url: '/pages/index/index' });
      }, 1500);
    })
    .catch(err => {
      this.setData({ submitting: false });
      wx.showToast({ title: err.data && err.data.detail || '操作失败', icon: 'none' });
    });
  }
});
