const { LEVEL_THRESHOLDS, LEVEL_NAMES } = require('../../constants/levels');

Component({
  properties: {
    level: { type: Number, value: 1 },
    points: { type: Number, value: 0 }
  },
  data: {
    nextLevelPoints: 100,
    progressPercent: 0,
    levelName: '新手'
  },
  observers: {
    'level, points': function(level, points) {
      const currentThreshold = LEVEL_THRESHOLDS[level - 1] || 0;
      const nextThreshold = LEVEL_THRESHOLDS[level] || LEVEL_THRESHOLDS[LEVEL_THRESHOLDS.length - 1];
      const progressPercent = nextThreshold === currentThreshold ? 100 :
        Math.min(100, Math.floor((points - currentThreshold) / (nextThreshold - currentThreshold) * 100));
      const levelName = LEVEL_NAMES[level - 1] || '传奇';
      this.setData({ nextLevelPoints: nextThreshold, progressPercent, levelName });
    }
  }
});
