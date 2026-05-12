import { test, expect } from '@playwright/test'

test.describe('CaseListPage', () => {
  test('displays heading and new case button in Japanese', async ({ page }) => {
    await page.goto('/?demo=true')
    await expect(page.getByRole('heading', { name: '案件一覧' })).toBeVisible()
    await expect(page.getByRole('button', { name: '+ 新規案件' })).toBeVisible()
  })
})

test.describe('ReviewPage demo mode', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/cases/demo/review?demo=true')
  })

  test('shows ReviewBanner with case_id', async ({ page }) => {
    await expect(page.getByText('demo-gijinkoku-001').first()).toBeVisible()
  })

  test('shows at least one FieldSection', async ({ page }) => {
    await expect(page.locator('[data-field-row]').first()).toBeVisible()
    await expect(page.getByText('案件情報')).toBeVisible()
  })

  test('shows FieldRows inside sections', async ({ page }) => {
    const fieldRows = page.locator('[data-field-row]')
    await expect(fieldRows.first()).toBeVisible()
    const count = await fieldRows.count()
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('shows FlagBadge elements in Japanese', async ({ page }) => {
    const badges = page.locator('span').filter({ hasText: /^(OK|要確認|不足|エラー|編集済)$/ })
    await expect(badges.first()).toBeVisible()
  })

  test('has confirm button', async ({ page }) => {
    await expect(page.locator('[data-field-row]').first()).toBeVisible()
    await expect(
      page.getByRole('button', { name: '確認して完了' })
    ).toBeVisible()
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

    // Badge should change to 編集済
    await expect(firstRow.locator('span').filter({ hasText: '編集済' })).toBeVisible()
  })

  test('mark all reviewed: button click changes to confirmed', async ({ page }) => {
    await expect(page.locator('[data-field-row]').first()).toBeVisible()

    // Find a section with "全て確認済み" button
    const markAllButton = page.getByRole('button', { name: '全て確認済み' }).first()
    await expect(markAllButton).toBeVisible()

    // Click it
    await markAllButton.click()

    // The button should disappear and "確認完了" text should appear in that section
    await expect(page.getByText('確認完了').first()).toBeVisible()
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

test.describe('UploadPage demo mode', () => {
  test('shows DropZone with Japanese text', async ({ page }) => {
    await page.goto('/cases/demo/upload?demo=true')
    await expect(page.getByText('ここにファイルをドラッグ＆ドロップ')).toBeVisible()
    await expect(page.getByText('ファイルを選択')).toBeVisible()
  })
})

test.describe('Navigation', () => {
  test('redirects unknown paths to /', async ({ page }) => {
    await page.goto('/nonexistent-path?demo=true')
    await page.waitForURL(/^http:\/\/localhost:\d+\/(\?.*)?$/)
    await expect(page.getByRole('heading', { name: '案件一覧' })).toBeVisible()
  })
})
