const api = require('../../utils/api');
const auth = require('../../utils/auth');
const app = getApp();

Page({
  data: {
    reminderEnabled: false,
    reminderTime: '21:00',
    wechatPushConfigured: false,
    loading: false,
    saving: false
  },

  onLoad() {
    auth.ensureLoggedIn().then(() => {
      this.loadReminderStatus();
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
