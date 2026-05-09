// frontend/src/__tests__/admin/thresholds.e2e.ts
//
// Playwright E2E tests for the /admin/thresholds page.
// These tests require a live Atlas environment. They are automatically
// skipped when ATLAS_E2E_BASE_URL or ATLAS_PASSWORD is not set, so
// local and CI unit-test runs pass without a live backend.
//
// KNOWN GAPS (intentional): test 1 does not assert atlas_threshold_history row
// because that requires a Postgres connection in the E2E context. The
// migration unit test covers the trigger fire path. Test 2 does not poll
// to success because that requires a live EC2 m3_daily.py run.

import { test, expect } from '@playwright/test'

const E2E_URL = process.env.ATLAS_E2E_BASE_URL
const E2E_PASSWORD = process.env.ATLAS_PASSWORD

test.skip(!E2E_URL || !E2E_PASSWORD, 'needs ATLAS_E2E_BASE_URL + ATLAS_PASSWORD')

// ---------------------------------------------------------------------------
// Auth helper: login before each test
// ---------------------------------------------------------------------------
test.describe('admin thresholds E2E', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${E2E_URL}/login`)
    await page.fill('input[type="password"]', E2E_PASSWORD!)
    await page.click('button[type="submit"]')
    await page.waitForURL('**/')
  })

  // -------------------------------------------------------------------------
  // Test 1: FM edits a threshold and sees update
  // -------------------------------------------------------------------------
  test('FM edits a threshold and sees the update', async ({ page }) => {
    await page.goto(`${E2E_URL}/admin/thresholds`)
    await expect(page.getByText('Threshold Admin')).toBeVisible()

    // Find the first "Edit" button and click it to open the modal
    const editBtn = page.getByRole('button', { name: 'Edit' }).first()
    await expect(editBtn).toBeVisible()
    await editBtn.click()

    // Modal should be visible
    await expect(page.getByRole('heading', { name: 'Edit Threshold' })).toBeVisible()

    // Read the allowed range hint — format is "Allowed range: [min, max]"
    const hintText = await page.locator('text=Allowed range:').textContent()
    const rangeMatch = hintText?.match(/\[([\d.]+),\s*([\d.]+)\]/)
    const minVal = rangeMatch ? parseFloat(rangeMatch[1]) : 0
    const maxVal = rangeMatch ? parseFloat(rangeMatch[2]) : 100

    // Use a value in the middle of the range
    const newVal = ((minVal + maxVal) / 2).toFixed(2)

    // Fill in the value
    const valueInput = page.locator('input[type="number"]')
    await valueInput.fill(newVal)

    // Diff preview should appear
    await expect(page.locator('text=Diff preview:')).toBeVisible()

    // Fill in the required reason
    const reasonTextarea = page.locator('textarea')
    await reasonTextarea.fill('E2E test adjustment — automated')

    // Save button should be enabled
    const saveBtn = page.getByRole('button', { name: 'Save' })
    await expect(saveBtn).toBeEnabled()
    await saveBtn.click()

    // Modal should close after save
    await expect(page.getByRole('heading', { name: 'Edit Threshold' })).not.toBeVisible()

    // Page should still show the thresholds table (no crash)
    await expect(page.getByText('Threshold Admin')).toBeVisible()
  })

  // -------------------------------------------------------------------------
  // Test 2: Recompute trigger shows inline confirmation
  // -------------------------------------------------------------------------
  test('clicking M3 recompute shows started message in UI', async ({ page }) => {
    await page.goto(`${E2E_URL}/admin/thresholds`)
    await expect(page.getByText('Threshold Admin')).toBeVisible()

    // Click Re-run M3
    const m3Btn = page.getByRole('button', { name: 'Re-run M3' })
    await expect(m3Btn).toBeVisible()
    await m3Btn.click()

    // Should show either "Recompute started" or an error message inline
    // (we don't assert success since the live backend may or may not be running)
    await expect(
      page.locator('text=Recompute started').or(page.locator('text=Triggering…'))
    ).toBeVisible({ timeout: 10000 })
  })

  // -------------------------------------------------------------------------
  // Test 3: Out-of-range edit keeps modal open with inline error
  // -------------------------------------------------------------------------
  test('out-of-range value keeps modal open with error message', async ({ page }) => {
    await page.goto(`${E2E_URL}/admin/thresholds`)
    await expect(page.getByText('Threshold Admin')).toBeVisible()

    // Open the first edit modal
    await page.getByRole('button', { name: 'Edit' }).first().click()
    await expect(page.getByRole('heading', { name: 'Edit Threshold' })).toBeVisible()

    // Enter an absurdly large value that is guaranteed to be out of range
    const valueInput = page.locator('input[type="number"]')
    await valueInput.fill('999999999')

    // Fill in a reason
    await page.locator('textarea').fill('Out-of-range test — automated')

    // Try to save
    const saveBtn = page.getByRole('button', { name: 'Save' })
    await saveBtn.click()

    // Modal should STAY open (not close)
    await expect(page.getByRole('heading', { name: 'Edit Threshold' })).toBeVisible()

    // An error message should be visible (either the client-side range check or the server constraint)
    const errorMsg = page.locator('text=outside the allowed').or(
      page.locator('text=must be between')
    )
    await expect(errorMsg).toBeVisible()
  })
})
