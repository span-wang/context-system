type LoadStateProps = {
  loading: boolean;
  error: string;
  empty?: boolean;
  emptyLabel?: string;
};

export function LoadState({ loading, error, empty = false, emptyLabel = "暂无数据" }: LoadStateProps) {
  if (loading) {
    return <div className="empty compact">正在加载...</div>;
  }
  if (error) {
    return <div className="errorPanel">{error}</div>;
  }
  if (empty) {
    return <div className="empty compact">{emptyLabel}</div>;
  }
  return null;
}
