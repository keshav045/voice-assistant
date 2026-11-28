import asyncio
import os


async def run_inspection():
    from playwright.async_api import async_playwright

    console_logs = []
    page_errors = []
    target_url = os.environ.get("NEXUS_UI_URL", "http://localhost:8000")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )
        context = await browser.new_context(
            permissions=["microphone"],
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type.upper()}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        print(f"Navigating to {target_url}...")
        await page.goto(target_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1.5)

        title = await page.title()
        print(f"Page Title: {title}")

        connect_btn = await page.query_selector("#livekit-connect-btn")
        status_pill = await page.query_selector("#livekit-status-pill")
        btn_label = await page.query_selector("#livekit-connect-btn-label")

        if not connect_btn:
            print("ERROR: #livekit-connect-btn not found on page!")
        else:
            b_txt = await btn_label.inner_text() if btn_label else "None"
            s_txt = await status_pill.inner_text() if status_pill else "None"
            print(f"Found #livekit-connect-btn: label='{b_txt}', status='{s_txt}'")

        await page.screenshot(path="dom_inspection_screenshot.png")
        print("Saved screenshot to dom_inspection_screenshot.png")

        print("\n--- Browser Console Logs ---")
        for log in console_logs:
            print(log)

        if page_errors:
            print("\n--- Uncaught Page Errors ---")
            for err in page_errors:
                print(err)
        else:
            print("\nNo uncaught page errors.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_inspection())
