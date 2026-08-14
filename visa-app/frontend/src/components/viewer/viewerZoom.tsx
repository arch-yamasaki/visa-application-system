interface ToolbarProps {
  zoomPercent: number
  onZoomIn: () => void
  onZoomOut: () => void
  onFitWidth: () => void
  onResetZoom: () => void
  page?: number
  numPages?: number
  onPrevPage?: () => void
  onNextPage?: () => void
}

export function ViewerToolbar({
  zoomPercent,
  onZoomIn,
  onZoomOut,
  onFitWidth,
  onResetZoom,
  page,
  numPages,
  onPrevPage,
  onNextPage,
}: ToolbarProps) {
  const btn =
    'px-2 py-1 text-xs bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-30 disabled:hover:bg-white'
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-1.5 border-b border-gray-200 bg-gray-50 select-none">
      <div className="flex items-center gap-2">
        {numPages !== undefined && page !== undefined && (
          <>
            <button className={btn} onClick={onPrevPage} disabled={page <= 1}>
              前へ
            </button>
            <span className="text-xs text-gray-500 tabular-nums">
              {page} / {numPages}
            </span>
            <button className={btn} onClick={onNextPage} disabled={page >= numPages}>
              次へ
            </button>
          </>
        )}
      </div>
      <div className="flex items-center gap-1">
        <button className={btn} onClick={onZoomOut} title="縮小" aria-label="縮小">
          −
        </button>
        <button
          className="w-14 py-1 text-xs text-gray-600 tabular-nums text-center bg-white border border-gray-300 rounded hover:bg-gray-50"
          onClick={onResetZoom}
          title="100%に戻す"
        >
          {zoomPercent}%
        </button>
        <button className={btn} onClick={onZoomIn} title="拡大" aria-label="拡大">
          ＋
        </button>
        <button className={`${btn} ml-1`} onClick={onFitWidth} title="幅に合わせる">
          幅に合わせる
        </button>
      </div>
    </div>
  )
}
