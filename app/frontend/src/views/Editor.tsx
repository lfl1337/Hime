export function Editor() {
  return (
    <div className="flex items-center justify-center h-full">
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-10 text-center max-w-md">
        <div className="text-4xl mb-4">編</div>
        <h2 className="text-lg font-semibold text-zinc-200 mb-2">
          Translation Editor
        </h2>
        <p className="text-sm text-zinc-500">
          Review and edit saved translations before exporting.
        </p>
      </div>
    </div>
  )
}
