import asyncio
import json
import os
import sys

async def run_inspection():
    from playwright.async_api import async_playwright

    console_logs = []
    page_errors = []

    async with async_playwright() as p:
        # Launch Chromium with fake audio device so WebRTC microphone can publish
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--allow-file-access-from-files",
                "--autoplay-policy=no-user-gesture-required",
            ]
        )
        context = await browser.new_context(
            permissions=["microphone"],
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type.upper()}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        print("Navigating to http://localhost:8501...")
        await page.goto("http://localhost:8501", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # 1. Inspect top-level DOM
        title = await page.title()
        print(f"Page Title: {title}")

        # 2. Check for the LiveKit iframe
        frames = page.frames
        print(f"Total Frames: {len(frames)}")

        lk_frame = None
        for idx, f in enumerate(frames):
            try:
                btn = await f.query_selector("#lk-btn")
                if btn:
                    lk_frame = f
                    print(f"Found LiveKit component in Frame {idx} ({f.url})")
                    break
            except Exception:
                pass

        if not lk_frame:
            print("ERROR: LiveKit component frame with #lk-btn not found!")
            for idx, f in enumerate(frames):
                print(f"Frame {idx}: URL={f.url}")
        else:
            btn = await lk_frame.query_selector("#lk-btn")
            title_el = await lk_frame.query_selector("#lk-title")
            sub_el = await lk_frame.query_selector("#lk-sub")
            btn_text = await lk_frame.query_selector("#lk-btn-text")

            b_txt = await btn_text.inner_text() if btn_text else "None"
            t_txt = await title_el.inner_text() if title_el else "None"
            s_txt = await sub_el.inner_text() if sub_el else "None"

            print(f"Before click: Button='{b_txt}', Title='{t_txt}', Sub='{s_txt}'")

            print("Clicking Start LiveKit Voice button in iframe...")
            await btn.click()
            await asyncio.sleep(3)

            b_txt_3s = await btn_text.inner_text() if btn_text else "None"
            t_txt_3s = await title_el.inner_text() if title_el else "None"
            s_txt_3s = await sub_el.inner_text() if sub_el else "None"
            print(f"After click (3s): Button='{b_txt_3s}', Title='{t_txt_3s}', Sub='{s_txt_3s}'")

            await asyncio.sleep(4)
            b_txt_7s = await btn_text.inner_text() if btn_text else "None"
            t_txt_7s = await title_el.inner_text() if title_el else "None"
            s_txt_7s = await sub_el.inner_text() if sub_el else "None"
            print(f"After click (7s): Button='{b_txt_7s}', Title='{t_txt_7s}', Sub='{s_txt_7s}'")

        # Capture screenshot
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
