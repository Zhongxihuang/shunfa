export interface CheckinItem {
  id: number;
  date: string;
  topic: string;
  topic_source?: string | null;
  content?: string | null;
  status: string;
  points_earned?: number;
  created_at?: string;
}

export interface CheckinsResponse {
  checkins: CheckinItem[];
  total: number;
  draft_count: number;
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    topic_selected: '待讨论',
    discussing: '讨论中',
    draft_ready: '待发布',
    pending: '待确认',
    completed: '已发布',
    draft: '草稿',
  };
  return labels[status] ?? status;
}

export function continueHref(item: CheckinItem): string {
  if (item.status === 'topic_selected' || item.status === 'discussing') {
    return `/discuss?checkin_id=${item.id}&topic=${encodeURIComponent(item.topic)}`;
  }
  return `/preview?checkin_id=${item.id}`;
}
