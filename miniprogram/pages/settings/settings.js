const api = require('../../utils/api');
const auth = require('../../utils/auth');

Page({
  data: {
    reminderEnabled: false,
    reminderTime: '21:00',
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

    api.post('/api/reminder', {
      reminder_enabled: this.data.reminderEnabled,
      reminder_time: this.data.reminderEnabled ? this.data.reminderTime : null
    })
    .then(() => {
      this.setData({ saving: false });
      wx.showToast({ title: '设置已保存', icon: 'success' });
    })
    .catch(err => {
      this.setData({ saving: false });
      wx.showToast({ title: err.data && err.data.detail || '保存失败', icon: 'none' });
    });
  }
});
