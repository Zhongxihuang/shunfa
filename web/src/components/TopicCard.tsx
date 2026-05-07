interface Props {
  topic: string;
  index: number;
  selected: boolean;
  onSelect: (topic: string) => void;
}

export default function TopicCard({ topic, index, selected, onSelect }: Props) {
  return (
    <button
      onClick={() => onSelect(topic)}
      className={`w-full rounded-2xl border p-4 text-left transition-all duration-150 ${
        selected
          ? 'border-primary bg-primary/5 shadow-md shadow-primary/10'
          : 'border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]'
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary-dark">
          {index + 1}
        </span>
        <span className="text-sm leading-relaxed text-[var(--ink)]">{topic}</span>
      </div>
      {selected && (
        <div className="mt-2 flex justify-end">
          <span className="text-xs font-medium text-primary-dark">已选择</span>
        </div>
      )}
    </button>
  );
}
