import logging
import os
import re
from io import BytesIO
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")

URL_PATTERN = re.compile(r'^https?://', re.IGNORECASE)


def normalize_url(text: str) -> str:
    text = text.strip()
    if not URL_PATTERN.match(text):
        text = "https://" + text
    return text


async def capture_screenshot(url: str, full_page: bool = False) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(url, wait_until="networkidle", timeout=20000)
            screenshot_bytes = await page.screenshot(full_page=full_page, type="png")
            return screenshot_bytes
        finally:
            await browser.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 *WebShot Bot*\n\n"
        "Send me any webpage URL and I'll capture a screenshot of it.\n\n"
        "By default I capture the visible viewport. Use `/full <url>` for a full-page "
        "(scrolled) screenshot.\n\n"
        "Example: `example.com` or `/full example.com`",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Usage:\n"
        "• Send a URL directly → viewport screenshot\n"
        "• `/full <url>` → full-page screenshot\n\n"
        "The `https://` prefix is optional — I'll add it automatically.",
        parse_mode="Markdown"
    )


async def full_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Usage: `/full example.com`", parse_mode="Markdown")
        return

    url = normalize_url(args[0])
    await process_screenshot(update, url, full_page=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if " " in text or "." not in text:
        await update.message.reply_text("⚠️ Please send a single valid URL, e.g. `example.com`", parse_mode="Markdown")
        return

    url = normalize_url(text)
    await process_screenshot(update, url, full_page=False)


async def process_screenshot(update: Update, url: str, full_page: bool):
    status_msg = await update.message.reply_text(f"📸 Capturing `{url}`...", parse_mode="Markdown")

    try:
        screenshot_bytes = await capture_screenshot(url, full_page=full_page)
        photo_file = BytesIO(screenshot_bytes)
        photo_file.name = "screenshot.png"

        await update.message.reply_document(
            document=photo_file,
            filename="screenshot.png",
            caption=f"✅ Screenshot of `{url}`",
            parse_mode="Markdown"
        )
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Screenshot error for {url}: {e}")
        error_text = str(e)
        if "timeout" in error_text.lower():
            reply = f"❌ Timed out loading `{url}`. The page may be too slow or unreachable."
        elif "net::" in error_text:
            reply = f"❌ Couldn't reach `{url}`. Check the URL is correct and publicly accessible."
        else:
            reply = f"❌ Failed to capture `{url}`.\nError: {error_text[:200]}"
        await status_msg.edit_text(reply, parse_mode="Markdown")


def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("full", full_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("WebShotBot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
