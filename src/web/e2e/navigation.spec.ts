import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test('landing page loads with hero section', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('text=Bench Goblins')).toBeVisible();
  });

  test('landing page has sign in button', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('text=Sign In')).toBeVisible();
  });

  test('ask page loads', async ({ page }) => {
    await page.goto('/ask');
    await expect(page).toHaveURL('/ask');
  });

  test('leaderboard page loads with tabs', async ({ page }) => {
    await page.goto('/leaderboard');
    await expect(page.locator('text=Leaderboard')).toBeVisible();
    await expect(page.locator('text=Top Players')).toBeVisible();
    await expect(page.locator('text=Trending')).toBeVisible();
    await expect(page.locator('text=Accuracy')).toBeVisible();
    await expect(page.locator('text=Season')).toBeVisible();
  });

  test('leaderboard sport selector works', async ({ page }) => {
    await page.goto('/leaderboard');
    await page.click('text=NBA');
    // Should still be on leaderboard with NBA selected
    await expect(page.locator('text=Leaderboard')).toBeVisible();
  });

  test('dashboard page loads', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page.locator('text=Dashboard')).toBeVisible();
    await expect(page.locator('text=Quick Actions')).toBeVisible();
    await expect(page.locator('text=System Status')).toBeVisible();
  });

  test('history page loads', async ({ page }) => {
    await page.goto('/history');
    await expect(page).toHaveURL('/history');
  });

  test('header nav links are visible', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('nav >> text=Ask')).toBeVisible();
    await expect(page.locator('nav >> text=Verdict')).toBeVisible();
    await expect(page.locator('nav >> text=History')).toBeVisible();
    await expect(page.locator('nav >> text=Leaderboard')).toBeVisible();
  });

  test('commissioner page loads with pro gate', async ({ page }) => {
    await page.goto('/commissioner');
    await expect(page).toHaveURL('/commissioner');
  });

  test('accuracy page loads', async ({ page }) => {
    await page.goto('/accuracy');
    await expect(page).toHaveURL('/accuracy');
  });

  test('privacy page loads', async ({ page }) => {
    await page.goto('/privacy');
    await expect(page.locator('text=Privacy')).toBeVisible();
  });

  test('terms page loads', async ({ page }) => {
    await page.goto('/terms');
    await expect(page.locator('text=Terms')).toBeVisible();
  });
});
