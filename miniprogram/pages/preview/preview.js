const api = require('../../utils/api');

Page({
  data: {
    checkinId: null,
    topic: '',
    topicSource: '',
    topicUrl: '',
    topicSummary: '',
    content: '',
    originalDraft: '',
    step: 'preview',  // 'preview' | 'quality_check' | 'quality_result' | 'publishing'
    qualityPass: null,
    qualityIssues: [],
    submitting: false,
    feedbackSent: false
  },

  onLoad(options) {
    const checkinId = parseInt(options.checkin_id || 0);
    const draft = wx.getStorageSync('current_draft') || '';
    const topicFromUrl = decodeURIComponent(options.topic || '');

    this.setData({
      checkinId,
      content: draft,
      originalDraft: draft,
      topic: topicFromUrl  // temporary; will be replaced by API if available
    });

    // Fetch topic from API (authoritative source)
    api.get(`/api/checkin/${checkinId}`)
      .then(data => {
        this.setData({
          topic: data.topic || topicFromUrl,
          topicSource: data.topic_source || '',
          topicUrl: data.topic_url || '',
          topicSummary: data.topic_summary || '',
          content: data.content || draft,
          originalDraft: data.content || draft,
          feedbackSent: data.content_feedback === 'down'
        });
      })
      .catch(() => {
        // Fall back to URL topic which is already set
      });
  },

  onContentChange(e) {
    this.setData({ content: e.detail.value });
  },

  onRegenerate() {
    wx.navigateBack();
  },

  onCopySourceLink() {
    if (!this.data.topicUrl) return;
    wx.setClipboardData({
      data: this.data.topicUrl,
      success: () => wx.showToast({ title: '链接已复制', icon: 'none' })
    });
  },

  // Step 1: Quality check
  onCheckQuality() {
    const content = this.data.content.trim();
    if (!content) {
      wx.showToast({ title: '内容不能为空', icon: 'none' });
      return;
    }

    this.setData({ step: 'quality_check', submitting: true });

    api.post('/api/confirm_content', {
      checkin_id: this.data.checkinId,
      content: content
    })
    .then(data => {
      // Update topic from API response if changed
      if (data.topic) {
        this.setData({ topic: data.topic });
      }
      this.setData({
        submitting: false,
        qualityPass: data.content_approved,
        qualityIssues: data.quality_issues || [],
        step: 'quality_result'
      });
    })
    .catch(err => {
      this.setData({ submitting: false, step: 'preview' });
      wx.showToast({ title: err.data && err.data.detail || '检查失败', icon: 'none' });
    });
  },

  // Step 2: Actually publish
  onPublish() {
    if (this.data.submitting) return;
    this.setData({ step: 'publishing', submitting: true });

    api.post('/api/confirm_publish', {
      checkin_id: this.data.checkinId
    })
    .then(data => {
      this.setData({ submitting: false });
      wx.showToast({ title: data.message || '发布成功！', icon: 'success' });
      setTimeout(() => {
        wx.switchTab({ url: '/pages/index/index' });
      }, 1500);
    })
    .catch(err => {
      this.setData({ submitting: false, step: 'quality_result' });
      wx.showToast({ title: err.data && err.data.detail || '发布失败', icon: 'none' });
    });
  },

  onSendFeedback() {
    if (this.data.feedbackSent || !this.data.checkinId) return;
    api.post('/api/content_feedback', {
      checkin_id: this.data.checkinId,
      feedback: 'down'
    })
    .then(() => {
      this.setData({ feedbackSent: true });
      wx.showToast({ title: '已记录反馈', icon: 'success' });
    })
    .catch(() => {
      wx.showToast({ title: '反馈发送失败', icon: 'none' });
    });
  },

  // Go back to edit
  onBackToEdit() {
    this.setData({ step: 'preview', qualityPass: null, qualityIssues: [] });
  }
});
