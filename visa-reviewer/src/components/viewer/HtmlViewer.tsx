interface Props {
  url: string
}

export default function HtmlViewer({ url }: Props) {
  return (
    <iframe
      src={url}
      className="w-full h-full border-0"
      title="Document preview"
    />
  )
}
