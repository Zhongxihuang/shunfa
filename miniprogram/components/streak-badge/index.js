Component({
  properties: {
    streak: { type: Number, value: 0 },
    longestStreak: { type: Number, value: 0 }
  },
  computed: {
    badgeClass() {
      const s = this.properties.streak;
      if (s >= 30) return 'badge-legendary';
      if (s >= 7) return 'badge-epic';
      if (s >= 3) return 'badge-rare';
      return 'badge-normal';
    }
  }
});
