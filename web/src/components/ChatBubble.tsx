interface Props {
  role: 'user' | 'assistant';
  content: string;
  time: string;
}

export default function ChatBubble({ role, content, time }: Props) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div className={`max-w-[75%] ${isUser ? 'items-end' : 'items-start'} sf-fade flex flex-col gap-1`}>
        <div
          className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? 'rounded-br-sm bg-[var(--ink)] text-[#fcfbf8]'
              : 'rounded-bl-sm border border-[var(--border)] bg-[var(--surface-strong)] text-[var(--ink)] shadow-[var(--shadow-soft)]'
          }`}
        >
          {content}
        </div>
        <span className="text-xs text-[var(--ink-muted)]">{time}</span>
      </div>
    </div>
  );
}
