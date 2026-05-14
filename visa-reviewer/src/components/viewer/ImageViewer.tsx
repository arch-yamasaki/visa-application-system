interface Props {
  url: string
}

export default function ImageViewer({ url }: Props) {
  return (
    <div className="p-4 flex justify-center">
      <img
        src={url}
        alt="書類"
        className="max-w-full shadow-lg"
      />
    </div>
  )
}
