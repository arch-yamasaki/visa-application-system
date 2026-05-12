import { test, expect } from '@playwright/test'

test.describe('CaseListPage', () => {
  test('displays Cases heading and New Case button', async ({ page }) => {
    await page.goto('/?demo=true')
    await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible()
    await expect(page.getByRole('button', { name: '+ New Case' })).toBeVisible()
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
    // Wait for data to load, then check section headers exist
    await expect(page.locator('[data-field-row]').first()).toBeVisible()
    // Sections have known titles from fieldPaths (e.g. 案件情報, 申請内容)
    await expect(page.getByText('案件情報')).toBeVisible()
  })

  test('shows FieldRows inside sections', async ({ page }) => {
    const fieldRows = page.locator('[data-field-row]')
    await expect(fieldRows.first()).toBeVisible()
    const count = await fieldRows.count()
    expect(count).toBeGreaterThanOrEqual(1)
  })

  test('shows FlagBadge elements', async ({ page }) => {
    const badges = page.locator('span').filter({ hasText: /^(OK|Review|Missing|Error|Edited)$/ })
    await expect(badges.first()).toBeVisible()
  })

  test('has Confirm & Complete button', async ({ page }) => {
    // Wait for data to load first
    await expect(page.locator('[data-field-row]').first()).toBeVisible()
    // Button text: "確認して完了" or "Confirm & Complete"
    await expect(
      page.getByRole('button', { name: /Confirm & Complete|確認して完了/ })
    ).toBeVisible()
  })

  test('clicking a FieldRow activates it', async ({ page }) => {
    const firstRow = page.locator('[data-field-row]').first()
    await firstRow.click()
    // Active row gets blue background
    await expect(firstRow).toHaveClass(/bg-blue-100/)
  })
})

test.describe('UploadPage demo mode', () => {
  test('shows DropZone with drag & drop text and Browse button', async ({ page }) => {
    await page.goto('/cases/demo/upload?demo=true')
    await expect(page.locator('text=Drag & drop')).toBeVisible()
    await expect(page.locator('text=Browse Files')).toBeVisible()
  })
})

test.describe('Navigation', () => {
  test('redirects unknown paths to /', async ({ page }) => {
    await page.goto('/nonexistent-path?demo=true')
    // React Router Navigate strips query params on redirect
    await page.waitForURL(/^http:\/\/localhost:\d+\/(\?.*)?$/)
    await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible()
  })
})
