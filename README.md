# voice-text

Telegram bot that transcribes **Ukrainian voice messages to text**, running
**fully locally** on a **Raspberry Pi 5 (4 GB)** with `faster-whisper`.

Send the bot a voice message → it replies with the transcribed text. No cloud
STT, no per-request cost. See [CLAUDE.md](CLAUDE.md) for design details.

## Setup

### 1. System packages (on the Pi)
Raspberry Pi OS **64-bit** (Lite is fine — headless is preferred).

```bash
sudo apt update && sudo apt install -y ffmpeg python3-venv git
```

### 2. Get the code + dependencies

```bash
git clone <your-repo-url> voice-text && cd voice-text
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env: paste your TELEGRAM_BOT_TOKEN from @BotFather.
```

### 4. Run

```bash
.venv/bin/python bot.py
```

First run downloads the model from Hugging Face (cached afterwards), so the
first start is slower. Then message your bot a voice note.

## Choosing / swapping the model

The model is set by `WHISPER_MODEL` in `.env` — change that one value to A/B test:

- `Yehor/whisper-small-ukrainian` (default) — Ukrainian fine-tune, small & fast
- `large-v3-turbo` — generic but strong; more RAM
- `small` — generic baseline

### If the model needs conversion to CTranslate2

`faster-whisper` needs models in CTranslate2 format. If `WHISPER_MODEL` fails to
load with a format error, convert it once (do this on a dev machine, then copy
the output folder to the Pi):

```bash
pip install ctranslate2 transformers torch
ct2-transformers-converter \
  --model Yehor/whisper-small-ukrainian \
  --output_dir whisper-uk-ct2 \
  --copy_files tokenizer.json preprocessor_config.json \
  --quantization int8
```

Then set `WHISPER_MODEL=whisper-uk-ct2` (the output dir) in `.env`.

## Run on boot (systemd)

Edit `voice-text-bot.service` so `User`, `WorkingDirectory`, `EnvironmentFile`,
and `ExecStart` paths match your Pi, then:

```bash
sudo cp voice-text-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now voice-text-bot
journalctl -u voice-text-bot -f   # watch logs
```

## Notes

- Transcriptions run **one at a time** (CPU-bound). Concurrent voice messages
  queue automatically.
- Restrict access with `ALLOWED_USER_IDS` in `.env` so randoms can't use your Pi.
