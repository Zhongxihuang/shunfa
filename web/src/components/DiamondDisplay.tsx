interface Props {
  diamonds: number;
}

export default function DiamondDisplay({ diamonds }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-3xl">💎</span>
      <div>
        <div className="text-2xl font-bold text-gray-800">{diamonds}</div>
        <div className="text-xs text-gray-500">钻石</div>
      </div>
    </div>
  );
}
