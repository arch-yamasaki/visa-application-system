import { test, expect } from '@playwright/test'

test.describe('CaseListPage', () => {
  test('displays heading and new case button in Japanese', async ({ page }) => {
    await page.goto('/?demo=true')
    await expect(page.getByRole('heading', { name: '案件一覧' })).toBeVisible()
    await expect(page.getByRole('button', { name: '+ 新規案件' })).toBeVisible()
    await expect(page.getByText('抽出済み')).toBeVisible()
  })

  test('copies case_id without opening the case', async ({ page }) => {
    await page.goto('/?demo=true')
    await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], {
      origin: new URL(page.url()).origin,
    })

    await page.getByRole('button', { name: 'demo-gijinkoku-001 をコピー' }).click()

    await expect(page).toHaveURL(/\?demo=true/)
    await expect(page.getByText('コピー済')).toBeVisible()
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe('demo-gijinkoku-001')
  })
})

test.describe('ReviewPage demo mode', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/cases/demo/review?demo=true')
  })

  test('shows ReviewBanner with case_id', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'demo-gijinkoku-001 をコピー' })).toBeVisible()
    await expect(page.getByText('抽出済み')).toBeVisible()
  })

  test('shows at least one FieldSection', async ({ page }) => {
    await expect(page.locator('[data-field-row]').first()).toBeVisible()
    await expect(page.getByText('身分事項')).toBeVisible()
  })

  test('shows FieldRows inside sections', async ({ page }) => {
    const fieldRows = page.locator('[data-field-row]')
    await expect(fieldRows.first()).toBeVisible()
    const count = await fieldRows.count()
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('does not show review progress controls', async ({ page }) => {
    await expect(page.locator('[data-field-row]').first()).toBeVisible()
    await expect(page.getByText('確認済:')).not.toBeVisible()
    await expect(page.getByText('要対応')).not.toBeVisible()
    await expect(page.getByText('編集済')).not.toBeVisible()
    await expect(page.getByText('要レビュー')).not.toBeVisible()
    await expect(page.getByRole('button', { name: '全て確認済み' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: '確認して完了' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: '保存' })).toBeVisible()
  })

  test('clicking a FieldRow activates it', async ({ page }) => {
    const firstRow = page.locator('[data-field-row]').first()
    await firstRow.click()
    await expect(firstRow).toHaveClass(/bg-blue-100/)
  })

  test('inline edit: double-click to edit, save updates value', async ({ page }) => {
    const firstRow = page.locator('[data-field-row]').first()
    await expect(firstRow).toBeVisible()

    // Double-click to enter edit mode
    await firstRow.dblclick()

    // Edit input should appear
    const input = firstRow.locator('input')
    await expect(input).toBeVisible()

    // Clear and type new value
    await input.fill('テスト編集値')

    // Click save button
    await firstRow.getByRole('button', { name: '保存' }).click()

    // Input should disappear and new value should be displayed
    await expect(input).not.toBeVisible()
    await expect(firstRow.getByText('テスト編集値')).toBeVisible()

    await expect(firstRow.locator('span').filter({ hasText: '編集済' })).not.toBeVisible()
  })

  test('keyboard: Enter to edit, Escape to cancel', async ({ page }) => {
    const firstRow = page.locator('[data-field-row]').first()
    await expect(firstRow).toBeVisible()

    // Focus the row
    await firstRow.focus()

    // Press Enter to start editing
    await page.keyboard.press('Enter')
    const input = firstRow.locator('input')
    await expect(input).toBeVisible()

    // Press Escape to cancel
    await page.keyboard.press('Escape')
    await expect(input).not.toBeVisible()
  })
})

test.describe('Demo mode navigation', () => {
  test('case list → click case → review page preserves demo mode', async ({ page }) => {
    await page.goto('/?demo=true')
    await expect(page.getByRole('heading', { name: '案件一覧' })).toBeVisible()

    // Click the demo case card outside the copyable case_id control
    await page.getByText('NGUYEN VAN DEMO').click()

    // Should navigate to review page with demo=true
    await expect(page).toHaveURL(/\/cases\/demo-gijinkoku-001\/review\?demo=true/)
    await expect(page.getByText('demo-gijinkoku-001').first()).toBeVisible()
    await expect(page.locator('[data-field-row]').first()).toBeVisible()

    // Go back and verify demo mode is maintained
    await page.goBack()
    await expect(page).toHaveURL(/\?demo=true/)
    await expect(page.getByRole('heading', { name: '案件一覧' })).toBeVisible()
    await expect(page.getByText('demo-gijinkoku-001')).toBeVisible()
  })
})

test.describe('UploadPage demo mode', () => {
  test('shows DropZone with Japanese text', async ({ page }) => {
    await page.goto('/cases/demo/upload?demo=true')
    await expect(page.getByText('ここにファイルをドラッグ＆ドロップ')).toBeVisible()
    await expect(page.getByText('ファイルを選択')).toBeVisible()
  })
})

test.describe('UploadPage backend selection', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/cases/demo/upload?demo=true')
  })

  test('shows extraction engine and pattern selectors', async ({ page }) => {
    await expect(page.getByText('抽出エンジン')).toBeVisible()
    await expect(page.getByText('抽出方式')).toBeVisible()
  })

  test('default backend is Gemini', async ({ page }) => {
    const backendSelect = page.locator('select').first()
    await expect(backendSelect).toHaveValue('gemini')
  })

  test('default pattern is auto', async ({ page }) => {
    const patternSelect = page.locator('select').nth(1)
    await expect(patternSelect).toHaveValue('auto')
  })

  test('can switch backend to Codex', async ({ page }) => {
    const backendSelect = page.locator('select').first()
    await backendSelect.selectOption('codex')
    await expect(backendSelect).toHaveValue('codex')
  })

  test('can switch pattern to text_only', async ({ page }) => {
    const patternSelect = page.locator('select').nth(1)
    await patternSelect.selectOption('text_only')
    await expect(patternSelect).toHaveValue('text_only')
  })
})

test.describe('Navigation', () => {
  test('redirects unknown paths to /', async ({ page }) => {
    await page.goto('/nonexistent-path?demo=true')
    await page.waitForURL(/^http:\/\/(localhost|127\.0\.0\.1):\d+\/(\?.*)?$/)
    await expect(page.getByRole('heading', { name: '案件一覧' })).toBeVisible()
  })
})
