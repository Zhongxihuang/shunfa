Component({
  properties: {
    topicId: { type: Number, value: 0 },
    topic: { type: String, value: '' },
    summary: { type: String, value: '' },
    source: { type: String, value: '' },
    url: { type: String, value: '' },
    index: { type: Number, value: 0 },
    selected: { type: Boolean, value: false }
  },

  methods: {
    onTap() {
      this.triggerEvent('select', {
        id: this.properties.topicId,
        topic: this.properties.topic,
        summary: this.properties.summary,
        source: this.properties.source,
        url: this.properties.url,
      });
    },

    onCopyLink() {
      if (!this.properties.url) return;
      wx.setClipboardData({
        data: this.properties.url,
      });
    }
  }
});
