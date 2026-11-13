import { expect, test } from '@playwright/test'

// These tests hit the real FastAPI backend, which talks to the real Steam API.

test('search -> detail -> reviews with filters and pagination', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Steam 게임')

  const box = page.getByRole('searchbox', { name: '게임 검색' })
  await box.fill('elden ring')
  // autocomplete shows the game
  const option = page.getByRole('option', { name: /ELDEN RING/ }).first()
  await expect(option).toBeVisible({ timeout: 20_000 })
  await box.press('Enter')

  await expect(page).toHaveURL(/\/search\?q=elden/)
  const card = page.locator('a.card', { hasText: /^ELDEN RING/ }).first()
  await expect(card).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText(/개$/).first()).toBeVisible()
  await card.click()

  // detail page
  await expect(page).toHaveURL(/\/game\/1245620/)
  await expect(page.getByRole('heading', { level: 1 })).toContainText('ELDEN RING', { timeout: 30_000 })
  await expect(page.getByRole('link', { name: /Steam 상점/ })).toHaveAttribute('href', 'https://store.steampowered.com/app/1245620')
  await expect(page.locator('.irow', { hasText: '개발사' })).toContainText('FromSoftware')
  await expect(page.locator('.sumbar')).toContainText('Steam 전체 리뷰')
  await expect(page.locator('.sample-note')).toContainText('표본')
  await expect(page.locator('.recharts-surface').first()).toBeVisible({ timeout: 40_000 })

  // reviews: default korean/helpful
  const reviews = page.locator('article.review')
  await expect(reviews.first()).toBeVisible({ timeout: 30_000 })
  const firstBefore = await reviews.first().innerText()
  expect(await reviews.count()).toBeGreaterThan(5)
  await expect(reviews.first().locator('.lang')).toContainText('한국어')

  // filter: negative only, english
  await page.locator('.rfilters label', { hasText: '언어' }).locator('select').selectOption('english')
  await page.locator('.rfilters label', { hasText: '평가' }).locator('select').selectOption('negative')
  await expect(page.locator('article.review.up')).toHaveCount(0, { timeout: 30_000 })
  await expect(page.locator('article.review.down').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.locator('article.review .lang').first()).toContainText('영어')

  // sort recent + pagination
  await page.locator('.rfilters label', { hasText: '정렬' }).locator('select').selectOption('recent')
  await page.locator('.rfilters label', { hasText: '평가' }).locator('select').selectOption('all')
  await expect(reviews.first()).toBeVisible({ timeout: 30_000 })
  const p1 = await reviews.first().innerText()
  await page.getByRole('button', { name: '다음 →' }).last().click()
  await expect(page.getByText('2 페이지')).toBeVisible({ timeout: 30_000 })
  await expect.poll(async () => reviews.first().innerText()).not.toBe(p1)
  await page.getByRole('button', { name: '← 이전' }).last().click()
  await expect(page.getByText('1 페이지')).toBeVisible()
  expect(firstBefore.length).toBeGreaterThan(0)

  // "load more" mode accumulates
  await page.locator('.rfilters label', { hasText: '보기 방식' }).locator('select').selectOption('more')
  await expect(reviews.first()).toBeVisible({ timeout: 30_000 })
  const n1 = await reviews.count()
  await page.getByRole('button', { name: /리뷰 더 불러오기/ }).click()
  await expect.poll(async () => reviews.count(), { timeout: 30_000 }).toBeGreaterThan(n1)
})

test('search filters + sort update results', async ({ page }) => {
  await page.goto('/search?sort=reviews')
  await expect(page.locator('a.card').first()).toBeVisible({ timeout: 20_000 })
  await page.getByRole('button', { name: 'RPG' }).click()
  await expect(page).toHaveURL(/genre=122/)
  await expect(page.locator('a.card').first()).toBeVisible()
  await page.locator('select[name=price]').selectOption('free')
  await expect(page).toHaveURL(/price=free/)
})

test('empty result and unknown game', async ({ page }) => {
  await page.goto('/search?q=zzqxjvk9')
  await expect(page.getByText('검색 결과가 없습니다')).toBeVisible({ timeout: 30_000 })
  await page.goto('/game/99999991')
  await expect(page.getByRole('heading', { name: '찾을 수 없습니다' })).toBeVisible({ timeout: 30_000 })
})

test('network failure shows friendly error', async ({ page }) => {
  await page.route('**/api/games/search**', (r) => r.abort())
  await page.goto('/search?q=hades')
  await expect(page.getByRole('alert')).toContainText('서버에 연결할 수 없습니다', { timeout: 20_000 })
})

test.describe('mobile', () => {
  test.use({ viewport: { width: 390, height: 800 } })
  test('no horizontal overflow on home, search and detail', async ({ page }) => {
    for (const url of ['/', '/search?q=hades', '/game/1245620']) {
      await page.goto(url)
      await page.waitForLoadState('networkidle')
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      expect(overflow, url).toBeLessThanOrEqual(1)
    }
  })
})

test('home carousel and tabs', async ({ page }) => {
  await page.goto('/')
  const stage = page.locator('.cx-top .dim')
  await expect(stage).toContainText('STAGE 01', { timeout: 20_000 })
  await page.getByRole('button', { name: '다음 게임' }).click()
  await expect(stage).toContainText('STAGE 02')
  await page.locator('.carousel').focus()
  await page.keyboard.press('ArrowLeft')
  await expect(stage).toContainText('STAGE 01')
  for (const name of ['신작', '할인 중', '출시 예정']) {
    await page.getByRole('tab', { name, exact: true }).click()
    await expect(page.locator('.grid a.card').first()).toBeVisible({ timeout: 30_000 })
  }
  await page.getByRole('button', { name: /PRESS START/ }).click()
  await expect(page).toHaveURL(/\/game\/\d+/)
})

test('genre chips on every tab, topbar search after scroll, menu, steam login link', async ({ page }) => {
  await page.goto('/?tab=new')
  await expect(page.getByRole('tab', { name: '신작', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.grid a.card').first()).toBeVisible({ timeout: 30_000 })
  await page.locator('.chips').getByRole('button', { name: 'RPG' }).click()
  await expect(page.locator('.grid a.card .tags').first()).toContainText('RPG', { timeout: 30_000 })
  await expect(page.locator('.grid a.card').first()).toBeVisible()

  // topbar search is always available (even after scrolling) and works
  await page.evaluate(() => window.scrollTo(0, 1500))
  const box = page.locator('.topsearch').getByRole('searchbox')
  await expect(box).toBeVisible()
  await box.fill('hades')
  await box.press('Enter')
  await expect(page).toHaveURL(/\/search\?q=hades/)

  // inline top navigation (desktop)
  await page.locator('.topnav').getByRole('link', { name: '할인 중' }).click()
  await expect(page).toHaveURL(/tab=sale/)
  await expect(page.getByRole('tab', { name: '할인 중', exact: true })).toHaveAttribute('aria-selected', 'true')

  // login button points at our OpenID start endpoint (we do not complete a real Steam login in tests)
  await expect(page.getByRole('link', { name: /Steam 로그인/ })).toHaveAttribute('href', /\/api\/auth\/steam\/login\?next=/)
  const res = await page.request.get('/api/auth/steam/login?next=/', { maxRedirects: 0 })
  expect(res.status()).toBe(302)
  expect(res.headers()['location']).toContain('https://steamcommunity.com/openid/login')
})


test('portal home sections render with real data', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('.promo')).toHaveCount(3, { timeout: 30_000 })
  await expect(page.locator('.ranklist li').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.getByRole('heading', { name: /인기 게임 TOP5/ })).toBeVisible()
  await expect(page.locator('.feed li').first()).toBeVisible({ timeout: 40_000 })
  await expect(page.locator('.trailer-card').first()).toBeVisible()
  await expect(page.locator('.daytab')).toHaveCount(7)
  // recently viewed is recorded after visiting a game
  await page.locator('.promo').first().click()
  await expect(page).toHaveURL(/\/game\/\d+/)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 30_000 })
  await expect.poll(() => page.evaluate(() => localStorage.getItem('gl_recent'))).toContain('appid')
  await page.goto('/')
  await expect(page.locator('.recent li').first()).toBeVisible()
})

test.describe('mobile menu', () => {
  test.use({ viewport: { width: 390, height: 800 } })
  test('MENU button navigates on small screens', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.topnav')).toBeHidden()
    await page.getByRole('button', { name: '메뉴' }).click()
    await page.getByRole('link', { name: /신작/ }).first().click()
    await expect(page).toHaveURL(/tab=new/)
  })
})
