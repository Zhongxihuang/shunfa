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
      className={`w-full text-left p-4 rounded-xl border-2 transition-all duration-150 bg-white ${
        selected
          ? 'border-primary shadow-md shadow-primary/20'
          : 'border-gray-200 hover:border-gray-300'
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
          {index + 1}
        </span>
        <span className="text-gray-800 text-sm leading-relaxed">{topic}</span>
      </div>
      {selected && (
        <div className="mt-2 flex justify-end">
          <span className="text-primary text-xs font-medium">已选择 ✓</span>
        </div>
      )}
    </button>
  );
}
