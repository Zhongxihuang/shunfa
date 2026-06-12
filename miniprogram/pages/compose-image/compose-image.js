const api = require('../../utils/api');

function formatTagsForCopy(tags) {
  // Storage is `["机器学习", "AI", ...]`; users want `#机器学习 #AI` for paste
  // into 小红书. This is the only place that format is decided.
  if (!tags || !tags.length) return '';
  return tags.map((t) => (t.startsWith('#') ? t : '#' + t)).join(' ');
}

function buildAllCopy(title, tags) {
  // Compose the full post body the user will paste into 小红书's
  // caption field. Empty title or no tags is OK — we just skip the line.
  const tagLine = formatTagsForCopy(tags);
  const titleLine = (title || '').trim();
  if (titleLine && tagLine) return `${titleLine}\n\n${tagLine}`;
  return titleLine || tagLine;
}

Page({
  data: {
    rawText: '',
    coverTitle: '',
    template: 'a',
    templates: [
      { id: 'a', name: '暖纸编辑' },
      { id: 'b', name: '瑞士现代' },
      { id: 'c', name: '撞色高定' }
    ],
    jobId: null,
    pages: [],
    pageCount: 0,
    overflow: false,
    images: [],
    previewing: false,
    rendering: false,
    // AI-generated Xiaohongshu-style copy. Populated by POST /api/image_jobs
    // and persisted on the job, so they survive template re-renders.
    aiTitle: '',
    aiTags: [],
    aiTagsFormatted: '',
    hasAiCopy: false
  },

  onTextInput(e) {
    this.setData({ rawText: e.detail.value });
  },

  onCoverInput(e) {
    this.setData({ coverTitle: e.detail.value });
  },

  onPickTemplate(e) {
    this.setData({ template: e.currentTarget.dataset.id, images: [] });
  },

  onPreview() {
    const rawText = this.data.rawText.trim();
    if (!rawText) {
      wx.showToast({ title: '请先粘贴正文', icon: 'none' });
      return;
    }
    this.setData({ previewing: true });
    api.post('/api/image_jobs', {
      raw_text: rawText,
      template: this.data.template,
      cover_title: this.data.coverTitle.trim() || null
    }).then((res) => {
      const aiTitle = res.ai_title || '';
      const aiTags = res.ai_tags || [];
      this.setData({
        jobId: res.job_id,
        pages: res.pages,
        pageCount: res.page_count,
        overflow: res.overflow,
        images: [],
        aiTitle,
        aiTags,
        aiTagsFormatted: formatTagsForCopy(aiTags),
        hasAiCopy: !!(aiTitle || aiTags.length),
        previewing: false
      });
    }).catch(() => {
      this.setData({ previewing: false });
      wx.showToast({ title: '生成失败，请重试', icon: 'none' });
    });
  },

  onRender() {
    if (!this.data.jobId) return;
    this.setData({ rendering: true });
    api.post(`/api/image_jobs/${this.data.jobId}/render`, {
      template: this.data.template
    }).then((res) => {
      const images = (res.images || []).map((b64) => `data:image/png;base64,${b64}`);
      this.setData({ images, rendering: false });
    }).catch(() => {
      this.setData({ rendering: false });
      wx.showToast({ title: '渲染失败，请重试', icon: 'none' });
    });
  },

  onSaveImage(e) {
    const src = e.currentTarget.dataset.src;
    // base64 data URI -> write to a temp file -> save to album
    const fsm = wx.getFileSystemManager();
    const filePath = `${wx.env.USER_DATA_PATH}/card_${Date.now()}.png`;
    const base64 = src.replace(/^data:image\/png;base64,/, '');
    try {
      fsm.writeFileSync(filePath, base64, 'base64');
    } catch (err) {
      wx.showToast({ title: '保存失败', icon: 'none' });
      return;
    }
    wx.saveImageToPhotosAlbum({
      filePath,
      success: () => wx.showToast({ title: '已保存到相册', icon: 'success' }),
      fail: (err) => {
        if (err.errMsg && err.errMsg.indexOf('auth deny') !== -1) {
          wx.showModal({
            title: '需要相册权限',
            content: '请在设置中允许保存图片到相册',
            confirmText: '去设置',
            success: (r) => { if (r.confirm) wx.openSetting(); }
          });
        } else {
          wx.showToast({ title: '保存失败', icon: 'none' });
        }
      }
    });
  },

  // ── AI 文案复制 ──────────────────────────────────────────────────────
  // Three flavours so the user can pick the granularity that matches where
  // they're pasting. All three go through the same wx.setClipboardData;
  // the only difference is what we hand it.

  onCopyTitle() {
    const title = (this.data.aiTitle || '').trim();
    if (!title) {
      wx.showToast({ title: 'AI 还没生成标题', icon: 'none' });
      return;
    }
    wx.setClipboardData({
      data: title,
      success: () => wx.showToast({ title: '标题已复制', icon: 'success' })
    });
  },

  onCopyTags() {
    const formatted = this.data.aiTagsFormatted;
    if (!formatted) {
      wx.showToast({ title: 'AI 还没生成标签', icon: 'none' });
      return;
    }
    wx.setClipboardData({
      data: formatted,
      success: () => wx.showToast({ title: '标签已复制', icon: 'success' })
    });
  },

  onCopyAll() {
    const all = buildAllCopy(this.data.aiTitle, this.data.aiTags);
    if (!all) {
      wx.showToast({ title: 'AI 还没生成文案', icon: 'none' });
      return;
    }
    wx.setClipboardData({
      data: all,
      success: () => wx.showToast({ title: '标题+标签已复制', icon: 'success' })
    });
  }
});
