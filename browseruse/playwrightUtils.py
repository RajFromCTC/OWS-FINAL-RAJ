async def _focus_chart_for_hotkeys(page):

    for _ in range(3):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(150)

    vp = page.viewport_size or {"width": 1280, "height": 720}
    x = int(vp["width"] * 0.50)
    y = int(vp["height"] * 0.30)


    await page.mouse.click(x, y)
    await page.wait_for_timeout(200)


async def set_timeframe_by_typing(page, interval: str):

    tf = _interval_to_tv_typing(interval)

    await _focus_chart_for_hotkeys(page)

    await page.keyboard.type(tf, delay=60)
    await page.keyboard.press("Enter")

    await page.wait_for_timeout(2500)
