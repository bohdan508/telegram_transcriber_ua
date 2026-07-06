"""Telegram bot that transcribes Ukrainian voice messages to text, fully locally.

Runs faster-whisper (CTranslate2) on CPU — designed for a Raspberry Pi 5 (4 GB).
See CLAUDE.md for the design rationale and model-choice notes.
"""

import asyncio
import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from faster_whisper import WhisperModel
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("voice-text")

# --- Config (all via env; see .env.example) ----------------------------------
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "Yehor/whisper-small-ukrainian")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "uk")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_CPU_THREADS = int(os.getenv("WHISPER_CPU_THREADS", "4"))
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))

_allowed = os.getenv("ALLOWED_USER_IDS", "").strip()
ALLOWED_USER_IDS = {int(x) for x in _allowed.split(",") if x.strip()} if _allowed else set()

# --- Model: load once at startup, keep resident ------------------------------
log.info("Loading Whisper model %r (compute_type=%s)...", WHISPER_MODEL, WHISPER_COMPUTE_TYPE)
model = WhisperModel(
    WHISPER_MODEL,
    device="cpu",
    compute_type=WHISPER_COMPUTE_TYPE,
    cpu_threads=WHISPER_CPU_THREADS,
)
log.info("Model loaded.")

# Single worker => transcriptions run one at a time (CPU-bound, saturates cores).
_executor = ThreadPoolExecutor(max_workers=1)


def _transcribe(path: str) -> str:
    """Blocking transcription. Runs in the executor thread, not the event loop."""
    segments, _info = model.transcribe(
        path,
        language=WHISPER_LANGUAGE,
        beam_size=WHISPER_BEAM_SIZE,
        vad_filter=True,                 # skip silence -> faster, cleaner
        condition_on_previous_text=False,  # short clips need no prior context
    )
    return " ".join(s.text.strip() for s in segments).strip()


def _is_allowed(update: Update) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    user = update.effective_user
    return bool(user and user.id in ALLOWED_USER_IDS)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привіт! Надішли мені голосове повідомлення, і я перетворю його на текст. 🎙"
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update):
        await update.message.reply_text("Вибач, цей бот доступний лише обраним користувачам.")
        return

    msg = update.message
    # voice note, uploaded audio, or a video note ("circle"). Whisper decodes
    # audio via ffmpeg, so the video-note MP4 container works like the rest.
    media = msg.voice or msg.audio or msg.video_note
    if media is None:
        return

    placeholder = await msg.reply_text("🎙 Розпізнаю...")

    tmp_path = None
    try:
        # Download the media file to a temp path (ffmpeg sniffs the real format,
        # so the suffix is cosmetic; pick the right one anyway).
        tg_file = await context.bot.get_file(media.file_id)
        suffix = ".mp4" if msg.video_note else ".oga"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        await tg_file.download_to_drive(tmp_path)

        # Run blocking transcription off the event loop, serialized via executor.
        loop = asyncio.get_running_loop()
        t0 = time.monotonic()
        text = await loop.run_in_executor(_executor, _transcribe, tmp_path)
        dt = time.monotonic() - t0
        log.info("Transcribed %.1fs audio in %.1fs (user=%s)",
                 media.duration or 0, dt, update.effective_user.id if update.effective_user else "?")

        await placeholder.edit_text(text or "🤷 Не вдалося розпізнати мовлення.")
    except Exception:
        log.exception("Transcription failed")
        await placeholder.edit_text("⚠️ Сталася помилка під час розпізнавання.")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def main() -> None:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(
        MessageHandler(filters.VOICE | filters.AUDIO | filters.VIDEO_NOTE, handle_voice)
    )

    log.info("Bot starting (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
