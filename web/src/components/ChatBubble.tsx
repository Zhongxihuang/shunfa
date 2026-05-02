interface Props {
  role: 'user' | 'assistant';
  content: string;
  time: string;
}

export default function ChatBubble({ role, content, time }: Props) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div className={`max-w-[75%] ${isUser ? 'items-end' : 'items-start'} flex flex-col gap-1`}>
        <div
          className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
            isUser
              ? 'bg-primary text-white rounded-br-sm'
              : 'bg-white text-gray-800 rounded-bl-sm shadow-sm'
          }`}
        >
          {content}
        </div>
        <span className="text-xs text-gray-400">{time}</span>
      </div>
    </div>
  );
}
