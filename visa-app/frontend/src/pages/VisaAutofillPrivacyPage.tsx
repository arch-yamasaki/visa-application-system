const POLICY_UPDATED_AT = '2026年8月15日'

export default function VisaAutofillPrivacyPage() {
  return (
    <article className="mx-auto max-w-3xl px-6 py-10 text-sm leading-7 text-gray-700">
      <h1 className="text-2xl font-semibold text-gray-900">
        Visa Application Autofill プライバシーポリシー
      </h1>
      <p className="mt-2 text-xs text-gray-500">最終更新日: {POLICY_UPDATED_AT}</p>

      <p className="mt-8">
        本ポリシーは、Chrome拡張機能「Visa Application Autofill」（以下「本拡張機能」）における
        利用者情報の取扱いを説明するものです。本拡張機能の単一の目的は、利用者が所属組織の
        visa-appに保存された在留資格申請情報を読み込み、出入国在留管理庁の在留申請オンライン
        システム（RASENS）の申請フォームへ入力する作業を補助することです。
      </p>

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-gray-900">1. 取り扱う情報</h2>
        <ul className="mt-3 list-disc space-y-2 pl-6">
          <li>
            認証情報: メールアドレス、認証トークン、およびメール・パスワードログイン時に入力された
            パスワード。パスワードはFirebase Authenticationへ直接送信され、本拡張機能には保存されません。
          </li>
          <li>
            案件情報: 案件ID、申請人氏名、所属先、案件の処理状態など、所属組織の案件一覧を表示するための情報。
          </li>
          <li>
            申請フォーム情報: 氏名、住所、連絡先、生年月日、国籍・地域、旅券情報、学歴・職歴、勤務先・雇用条件、
            取次者情報その他、在留資格申請フォームへ入力するためにvisa-appから取得する情報。
          </li>
          <li>
            ローカル設定: 選択中の案件ID、ログイン状態、および読み込んだ入力行。本拡張機能は、利用者の操作により
            RASENSの対象申請画面を検知しますが、一般的な閲覧履歴の収集や追跡は行いません。
          </li>
        </ul>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-gray-900">2. 利用目的と処理</h2>
        <ul className="mt-3 list-disc space-y-2 pl-6">
          <li>利用者を認証し、所属組織に紐づく案件だけを表示するため。</li>
          <li>選択された案件の申請データをvisa-appから取得し、利用者の端末内に一時保存するため。</li>
          <li>利用者が「一括入力」または「ゆっくり入力」を実行したとき、RASENSの対象フォームへ値を入力するため。</li>
          <li>ログイン状態の維持、認証トークンの更新、および入力結果の表示に必要な範囲で処理するため。</li>
        </ul>
        <p className="mt-3">
          本拡張機能はRASENSの最終送信を行いません。申請内容の確認と最終送信は利用者自身が行います。
        </p>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-gray-900">3. 保存と保持期間</h2>
        <p className="mt-3">
          認証トークン、メールアドレス、選択中の案件ID、および読み込んだ入力行は、Chromeの
          <code className="mx-1 rounded bg-gray-100 px-1 py-0.5">storage.local</code>
          に保存されます。入力行は別案件の読込またはログアウトにより置き換え・削除され、認証情報はログアウトまたは
          本拡張機能の削除により削除されます。visa-app側の案件情報は、利用者の所属組織に適用される運用・保持方針に従います。
        </p>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-gray-900">4. 外部サービスおよび情報の共有</h2>
        <p className="mt-3">本拡張機能は、機能提供に必要な範囲で次のサービスと通信します。</p>
        <ul className="mt-3 list-disc space-y-2 pl-6">
          <li>Google Firebase Authentication: メール・パスワードまたはGoogleアカウントによる認証。</li>
          <li>visa-app: 所属組織の案件一覧および選択案件の申請フォーム情報の取得。</li>
          <li>出入国在留管理庁 RASENS: 利用者が開いている対象申請フォームへのローカルな入力補助。</li>
        </ul>
        <p className="mt-3">
          法令に基づく場合、セキュリティ上必要な場合、または利用者が個別に同意した場合を除き、
          広告、データ販売、信用判断その他、本拡張機能の単一目的と無関係な用途で情報を第三者へ提供しません。
        </p>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-gray-900">5. セキュリティとリモートコード</h2>
        <p className="mt-3">
          外部サービスとの通信にはHTTPSを使用し、visa-appでは認証と組織単位のアクセス制御を行います。
          本拡張機能は、外部から取得したJavaScript、WebAssemblyその他の実行コードを読み込んだり実行したりしません。
          実行されるコードはChrome Web Storeへ提出するパッケージに含まれるものだけです。
        </p>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-gray-900">6. Chrome Web Store User Data Policyへの準拠</h2>
        <p className="mt-3">
          Google APIから取得する情報を含む利用者情報の取扱いは、Chrome Web Store User Data Policyの
          Limited Use要件に従います。本拡張機能の単一目的の提供・改善に必要な範囲に利用を限定し、
          パーソナライズ広告、データ販売、または目的外の人による閲覧には利用しません。
        </p>
      </section>

      <section className="mt-8">
        <h2 className="text-lg font-semibold text-gray-900">7. 利用者の選択とお問い合わせ</h2>
        <p className="mt-3">
          利用者はログアウトまたは本拡張機能の削除により、端末内に保存された情報を削除できます。
          visa-appに保存された案件情報の確認、訂正、削除、または本ポリシーに関するお問い合わせは、
          所属組織の管理者または
          <a className="mx-1 text-blue-700 underline" href="mailto:y_yamasaki@genbaai.com">
            y_yamasaki@genbaai.com
          </a>
          までご連絡ください。
        </p>
      </section>
    </article>
  )
}
