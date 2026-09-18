import os
import json
import asyncio
import logging
import threading
from flask import Flask
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import (
    FloodWait, PeerFlood, UserBannedInChannel,
    ChatWriteForbidden, ChatAdminRequired,
    UserNotParticipant, ChannelPrivate, RPCError
)

# ===================== CONFIGURATION =====================
SESSION_STRING = os.environ.get("SESSION_STRING", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
MESSAGE = os.environ.get("MESSAGE", "Hello! Ye automated message hai. ⚡")
INTERVAL = int(os.environ.get("INTERVAL", "300"))          # 5 minutes = 300 sec
DELAY = int(os.environ.get("DELAY_BETWEEN_GROUPS", "8"))   # Har message ke beech delay
PORT = int(os.environ.get("PORT", "8080"))                 # Render port
BLACKLIST_FILE = "blacklist.json"
# =========================================================

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AutoSender")

# ---- 1. Event Loop Fix (Python 3.10+ Error Remover) ----
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ---- 2. Flask Server Setup (Render 24/7 Support) ----
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "<h3>✅ Telegram Auto Sender Web Service is Running 24/7!</h3>", 200

@web_app.route("/health")
def health():
    return {"status": "ok", "blacklisted_groups": len(blacklist)}, 200

def start_flask():
    logger.info(f"🌐 Starting Flask server on port {PORT}...")
    web_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


# ---- 3. Pyrogram Client Setup ----
app = Client(
    name="auto_sender",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH
)

# ---- 4. Blacklist Storage System ----
def load_blacklist() -> set:
    try:
        with open(BLACKLIST_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_blacklist(bl: set):
    try:
        with open(BLACKLIST_FILE, "w") as f:
            json.dump(list(bl), f)
    except Exception as e:
        logger.error(f"Blacklist save error: {e}")

blacklist = load_blacklist()
sent_messages = {}  # {chat_id: message_id}


# ---- Step 1: Check Deleted Messages ----
async def check_deleted():
    """Pichle cycle ke messages check karo — delete hua to blacklist"""
    global blacklist
    deleted = []

    for chat_id, msg_id in list(sent_messages.items()):
        try:
            msg = await app.get_messages(chat_id, msg_id)
            # Agar message delete ho chuka hai (None ya empty)
            if not msg or getattr(msg, "empty", False):
                deleted.append(chat_id)
        except Exception:
            deleted.append(chat_id)

    for chat_id in deleted:
        blacklist.add(chat_id)
        sent_messages.pop(chat_id, None)
        logger.warning(f"⛔ BLACKLISTED {chat_id} — msg was deleted by admin/bot!")

    if deleted:
        save_blacklist(blacklist)
        logger.info(f"📝 Blacklist updated! Total blacklisted: {len(blacklist)}")


# ---- Step 2: Dynamic Group Fetching ----
async def get_all_groups() -> list:
    """Naye aur purane saare joined groups dynamic uthayega"""
    groups = []
    try:
        async for dialog in app.get_dialogs():
            chat = dialog.chat
            if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                groups.append(chat.id)
    except Exception as e:
        logger.error(f"Error fetching dialogs: {e}")
    return groups


# ---- Step 3: Broadcast Engine ----
async def send_cycle():
    global blacklist

    # 1. Pehle deleted check karo
    await check_deleted()

    # 2. Saare groups fresh lao
    all_groups = await get_all_groups()
    active = [g for g in all_groups if g not in blacklist]

    logger.info("=" * 50)
    logger.info(f"📊 Total Groups: {len(all_groups)}")
    logger.info(f"⛔ Blacklisted:  {len(blacklist)}")
    logger.info(f"✅ Sending to:   {len(active)}")
    logger.info("=" * 50)

    success, failed = 0, 0

    for chat_id in active:
        try:
            msg = await app.send_message(chat_id, MESSAGE)
            sent_messages[chat_id] = msg.id
            success += 1
            logger.info(f"  ✅ Sent → {chat_id}")

        except FloodWait as e:
            logger.warning(f"  ⏳ FloodWait: {e.value}s ruk rahe hain...")
            await asyncio.sleep(e.value)
            try:
                msg = await app.send_message(chat_id, MESSAGE)
                sent_messages[chat_id] = msg.id
                success += 1
            except Exception:
                failed += 1

        except (ChatWriteForbidden, ChatAdminRequired,
                UserBannedInChannel, UserNotParticipant,
                ChannelPrivate, PeerFlood):
            blacklist.add(chat_id)
            logger.warning(f"  ⛔ BLACKLISTED {chat_id} — no permissions/banned")

        except RPCError as e:
            logger.error(f"  ❌ RPC Error {chat_id}: {e}")
            failed += 1

        except Exception as e:
            logger.error(f"  ❌ Error {chat_id}: {e}")
            failed += 1

        # Telegram rate limit delay
        await asyncio.sleep(DELAY)

    save_blacklist(blacklist)
    logger.info(f"📈 Cycle Finished | ✅ {success} Sent | ❌ {failed} Failed\n")


# ---- Main Async Loop ----
async def main():
    async with app:
        me = await app.get_me()
        logger.info(f"🔐 Connected as: {me.first_name} (@{me.username})")
        logger.info(f"⏱️ Interval: {INTERVAL}s | Delay: {DELAY}s\n")

        while True:
            try:
                await send_cycle()
            except Exception as e:
                logger.error(f"💥 Exception in loop: {e}")

            logger.info(f"💤 Next cycle in {INTERVAL} seconds...\n")
            await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    # 1. Flask Web Server background thread me start karo
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # 2. Main Telegram Event Loop Run karo
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Bot stopped manually.")
    finally:
        loop.close()
