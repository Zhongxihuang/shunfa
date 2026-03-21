Component({
  properties: {
    topic:    { type: String,  value: '' },
    index:    { type: Number,  value: 0 },   // 1-based 序号
    selected: { type: Boolean, value: false }
  },

  methods: {
    onTap() {
      this.triggerEvent('select', { topic: this.properties.topic });
    }
  }
});
