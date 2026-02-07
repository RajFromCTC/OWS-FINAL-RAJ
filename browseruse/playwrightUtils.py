async def _focus_chart_for_hotkeys(page):

    for _ in range(3):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(150)

    vp = page.viewport_size or {"width": 1280, "height": 720}
    x = int(vp["width"] * 0.50)
    y = int(vp["height"] * 0.30)


    await page.mouse.click(x, y)
    await page.wait_for_timeout(200)


def _interval_to_tv_typing(interval: str) -> str:
    iv = str(interval).strip()
    iv_l = iv.lower()

    if iv_l == "1h":
        return "60"
    if iv_l == "4h":
        return "240"
    if iv_l in ["1d", "d"]:
        return "1D"
    if iv_l in ["1w", "w"]:
        return "1W"
    if iv_l in ["1m", "m"]:
        return "1M"

    if iv_l.endswith("m") and iv_l[:-1].isdigit():
        return iv_l[:-1]

    return iv

async def ensure_single_layout(page):
    """
    Ensures the TradingView chart layout is set to a single chart.
    """
    logger_name = "ensure_single_layout"
    try:
        # Check if the layout button exists
        layout_button = page.locator("button[data-name='header-toolbar-chart-layouts']")
        if await layout_button.count() == 0:
            return
            
        # Check if we are already in single layout
        # Usually, the button has a 'title' or 'aria-label' that mentions the layout.
        # Or we can just click and select 'Single' to be sure.
        
        await layout_button.click()
        await page.wait_for_timeout(1000)
        
        # The single layout is usually the first option in the popup menu.
        # Selector for the popup menu item for single layout:
        single_layout_option = page.locator("[data-name='menu-inner'] div[data-value='s'], [data-name='menu-inner'] div:has-text('1 chart')").first
        
        if await single_layout_option.is_visible():
            await single_layout_option.click()
            await page.wait_for_timeout(2000) # Wait for layout change
            print("[INFO] Layout reset to single chart.")
        else:
            # If we can't find the specific option, press Escape to close menu
            await page.keyboard.press("Escape")
            
    except Exception as e:
        print(f"[WARN] Failed to set single layout: {e}")

async def set_timeframe_by_typing(page, interval: str):

    tf = _interval_to_tv_typing(interval)

    await _focus_chart_for_hotkeys(page)

    await page.keyboard.type(tf, delay=60)
    await page.keyboard.press("Enter")

    await page.wait_for_timeout(2500)
