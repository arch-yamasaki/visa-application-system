import { useEffect, useState } from 'react'
import { apiClient, type OrgSettings } from '../api/client'

const emptySettings: OrgSettings = {
  org_id: '',
  intermediary: {
    name: '',
    postal_code: '',
    address: '',
    organization: '',
    phone: '',
  },
  receiving_method: {
    method: 'メール Email',
    notification_email: '',
  },
  updated_at: null,
  updated_by_uid: null,
  can_update: false,
}

type IntermediaryKey = keyof OrgSettings['intermediary']

const intermediaryFields: Array<{ key: IntermediaryKey; label: string; placeholder: string }> = [
  { key: 'name', label: '取次者 氏名', placeholder: '例: 行政　太郎' },
  { key: 'postal_code', label: '取次者 郵便番号', placeholder: '例: 6310855' },
  { key: 'address', label: '取次者 住所', placeholder: '例: 奈良県奈良市...' },
  { key: 'organization', label: '取次者 所属機関等', placeholder: '例: 行政書士事務所' },
  { key: 'phone', label: '取次者 電話番号', placeholder: '例: 0742405620' },
]

function normalizeDigits(value: string): string {
  return value.normalize('NFKC').replace(/[^0-9]/g, '')
}

export default function OrgSettingsPage() {
  const [settings, setSettings] = useState<OrgSettings>(emptySettings)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    apiClient.getOrgSettings()
      .then(setSettings)
      .catch((err) => setError((err as Error).message))
      .finally(() => setLoading(false))
  }, [])

  const updateIntermediary = (key: IntermediaryKey, value: string) => {
    setSettings((current) => ({
      ...current,
      intermediary: { ...current.intermediary, [key]: value },
    }))
    setSaved(false)
  }

  const updateEmail = (value: string) => {
    setSettings((current) => ({
      ...current,
      receiving_method: {
        ...current.receiving_method,
        notification_email: value.trim().toLowerCase(),
      },
    }))
    setSaved(false)
  }

  const handleSave = async () => {
    const missing = intermediaryFields
      .filter((field) => !settings.intermediary[field.key].trim())
      .map((field) => field.label)
    if (!settings.receiving_method.notification_email.trim()) {
      missing.push('通知送信用メールアドレス')
    }
    if (missing.length > 0) {
      setError(`未入力: ${missing.join(', ')}`)
      return
    }
    if (!/^[0-9]+$/.test(settings.intermediary.postal_code)) {
      setError('取次者 郵便番号は半角数字のみで入力してください。')
      return
    }
    if (!/^[0-9]+$/.test(settings.intermediary.phone)) {
      setError('取次者 電話番号は半角数字のみで入力してください。')
      return
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(settings.receiving_method.notification_email)) {
      setError('通知送信用メールアドレスの形式を確認してください。')
      return
    }

    setSaving(true)
    setError('')
    try {
      const updated = await apiClient.updateOrgSettings({
        intermediary: settings.intermediary,
        receiving_method: settings.receiving_method,
      })
      setSettings(updated)
      setSaved(true)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="max-w-3xl mx-auto p-6 text-sm text-gray-500">読込中...</div>
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <div className="mb-6">
        <p className="text-xs text-gray-500 mb-1">組織: {settings.org_id}</p>
        <h2 className="text-xl font-semibold text-gray-800">組織設定</h2>
      </div>

      {!settings.can_update && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          member権限のため閲覧のみです。変更はadminに依頼してください。
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {saved && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          保存しました。
        </div>
      )}

      <div className="space-y-6">
        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-800 mb-4">取次者</h3>
          <div className="grid gap-4">
            {intermediaryFields.map((field) => (
              <label key={field.key} className="block">
                <span className="block text-xs font-medium text-gray-600 mb-1">{field.label}</span>
                <input
                  value={settings.intermediary[field.key]}
                  onChange={(event) => updateIntermediary(
                    field.key,
                    field.key === 'postal_code' || field.key === 'phone'
                      ? normalizeDigits(event.target.value)
                      : event.target.value,
                  )}
                  disabled={!settings.can_update || saving}
                  inputMode={field.key === 'postal_code' || field.key === 'phone' ? 'numeric' : undefined}
                  placeholder={field.placeholder}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                />
              </label>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h3 className="text-sm font-semibold text-gray-800 mb-4">受領方法等</h3>
          <div className="grid gap-4">
            <label className="block">
              <span className="block text-xs font-medium text-gray-600 mb-1">在留資格認定証明書の受領方法</span>
              <input
                value="メール Email"
                disabled
                className="w-full rounded-md border border-gray-300 bg-gray-100 px-3 py-2 text-sm text-gray-500"
              />
            </label>
            <label className="block">
              <span className="block text-xs font-medium text-gray-600 mb-1">通知送信用メールアドレス</span>
              <input
                type="email"
                value={settings.receiving_method.notification_email}
                onChange={(event) => updateEmail(event.target.value)}
                disabled={!settings.can_update || saving}
                placeholder="example@example.com"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm disabled:bg-gray-100 disabled:text-gray-500"
              />
            </label>
          </div>
        </section>
      </div>

      <div className="mt-6 flex items-center justify-end gap-3">
        {settings.updated_at && (
          <span className="text-xs text-gray-400">
            最終更新: {new Date(settings.updated_at).toLocaleString('ja-JP')}
          </span>
        )}
        <button
          onClick={() => void handleSave()}
          disabled={!settings.can_update || saving}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
        >
          {saving ? '保存中...' : '保存'}
        </button>
      </div>
    </div>
  )
}
