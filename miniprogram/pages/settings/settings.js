const api = require('../../utils/api');
const auth = require('../../utils/auth');
const app = getApp();

Page({
  data: {
    reminderEnabled: false,
    reminderTime: '21:00',
    wechatPushConfigured: false,
    apiKeyConfigured: false,
    apiKeyPreview: '',
    apiKeyInput: '',
    showApiKeyInput: false,
    apiKeySaving: false,
    loading: false,
    saving: false
  },

  onLoad() {
    auth.ensureLoggedIn().then(() => {
      this.loadReminderStatus();
      this.loadApiKeyStatus();
    });
  },

  loadReminderStatus() {
    this.setData({ loading: true });
    api.get('/api/reminder_status')
      .then(data => {
        this.setData({
          reminderEnabled: data.reminder_enabled,
          reminderTime: data.reminder_time || '21:00',
          wechatPushConfigured: !!data.wechat_push_configured,
          loading: false
        });
      })
      .catch(() => {
        this.setData({ loading: false });
      });
  },

  loadApiKeyStatus() {
    api.get('/api/user/api_key/status')
      .then(data => {
        this.setData({
          apiKeyConfigured: !!data.configured,
          apiKeyPreview: data.preview || ''
        });
      })
      .catch(() => {
        this.setData({ apiKeyConfigured: false, apiKeyPreview: '' });
      });
  },

  onApiKeyInput(e) {
    this.setData({ apiKeyInput: e.detail.value });
  },

  onShowApiKeyInput() {
    this.setData({ showApiKeyInput: true, apiKeyInput: '' });
  },

  onCancelApiKeyInput() {
    this.setData({ showApiKeyInput: false, apiKeyInput: '' });
  },

  onSaveApiKey() {
    const key = (this.data.apiKeyInput || '').trim();
    if (!key) {
      wx.showToast({ title: '请输入 API Key', icon: 'none' });
      return;
    }
    if (!key.startsWith('sk-') || key.length < 10) {
      wx.showToast({ title: 'Key 格式应以 sk- 开头', icon: 'none' });
      return;
    }
    this.setData({ apiKeySaving: true });
    api.post('/api/user/api_key', { api_key: key })
      .then(data => {
        this.setData({
          apiKeyConfigured: true,
          apiKeyPreview: data.preview || '',
          apiKeyInput: '',
          showApiKeyInput: false,
          apiKeySaving: false
        });
        wx.showToast({ title: 'Key 已保存', icon: 'success' });
      })
      .catch(err => {
        this.setData({ apiKeySaving: false });
        wx.showToast({ title: err.data?.detail || 'Key 保存失败', icon: 'none' });
      });
  },

  onDeleteApiKey() {
    wx.showModal({
      title: '移除 API Key',
      content: '移除后将无法使用 AI 生成、讨论和质量提示。',
      confirmText: '移除',
      confirmColor: '#b56a5b',
      success: (res) => {
        if (!res.confirm) return;
        api.delete('/api/user/api_key')
          .then(() => {
            this.setData({
              apiKeyConfigured: false,
              apiKeyPreview: '',
              apiKeyInput: '',
              showApiKeyInput: false
            });
            wx.showToast({ title: '已移除', icon: 'success' });
          })
          .catch(err => {
            wx.showToast({ title: err.data?.detail || '移除失败', icon: 'none' });
          });
      }
    });
  },

  onToggleReminder(e) {
    this.setData({ reminderEnabled: e.detail.value });
  },

  onTimeChange(e) {
    this.setData({ reminderTime: e.detail.value });
  },

  onSave() {
    if (this.data.saving) return;
    this.setData({ saving: true });

    const finishSave = () => api.post('/api/reminder', {
      reminder_enabled: this.data.reminderEnabled,
      reminder_time: this.data.reminderEnabled ? this.data.reminderTime : null
    });

    const maybeSubscribe = () => {
      const templateId = app.globalData.reminderTemplateId;
      if (!this.data.reminderEnabled || !templateId) {
        return Promise.resolve();
      }
      return new Promise((resolve, reject) => {
        wx.requestSubscribeMessage({
          tmplIds: [templateId],
          success: (res) => {
            const status = res[templateId];
            if (status === 'accept') {
              resolve();
              return;
            }
            reject(new Error(status || 'subscribe_rejected'));
          },
          fail: reject
        });
      });
    };

    maybeSubscribe()
    .then(() => finishSave())
    .then(() => {
      this.setData({ saving: false });
      wx.showToast({ title: '设置已保存', icon: 'success' });
    })
    .catch((err) => {
      this.setData({ saving: false });
      const errMsg = err && err.message ? err.message : '';
      const isSubscribeError = !!(
        err &&
        (errMsg === 'subscribe_rejected' || errMsg === 'ban' || errMsg === 'reject' ||
         errMsg === 'TEMPLATE_TYPE_BAN' || errMsg === 'service_not_subscribe' ||
         errMsg === 'miniprogram_not_subscribe' ||
         errMsg.includes('cancel') || errMsg.includes('fail') || errMsg.includes('auth'))
      );
      if (isSubscribeError && this.data.reminderEnabled && app.globalData.reminderTemplateId) {
        this.setData({ reminderEnabled: false });
      }
      if (isSubscribeError) {
        let tip = '未完成订阅授权';
        if (errMsg.includes('cancel')) {
          tip = '用户取消授权';
        } else if (errMsg.includes('TEMPLATE_TYPE_BAN') || errMsg.includes('ban')) {
          tip = '订阅消息模板已失效';
        } else if (errMsg.includes('reject')) {
          tip = '用户拒绝了授权';
        } else if (errMsg.includes('auth')) {
          tip = '未获得授权权限';
        }
        wx.showToast({ title: tip, icon: 'none' });
        return;
      }
      wx.showToast({ title: err.data && err.data.detail || '保存失败', icon: 'none' });
    });
  }
});
