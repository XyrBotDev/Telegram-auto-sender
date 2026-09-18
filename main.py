# 1. Sabse pehle asyncio aur loop setup (IMPORTANT)
import asyncio

try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# 2. Ab baaki modules import karein
import os
import json
import logging
import threading
from flask import Flask

# 3. PYROGRAM KO AB IMPORT KAREIN (Taki use loop mil jaye)
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
INTERVAL = int(os.environ.get("INTERVAL", "300"))          
DELAY = int(os.environ.get("DELAY_BETWEEN_GROUPS", "8"))   
PORT = int(os.environ.get("PORT", "8080"))                 
BLACKLIST_FILE = "blacklist.json"
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AutoSender")

# ---- Flask Server (Render ke liye) ----
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "✅ Bot is Running!", 200

def start_flask():
    web_app.run(host="0.0.0.0", port=PORT)

# ---- Blacklist System ----
def load_blacklist():
    try:
        if os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, "r") as f:
                return set(json.load(f))
    except: pass
    return set()

def save_blacklist(bl):
    try:
        with open(BLACKLIST_FILE, "w") as f:
            json.dump(list(bl), f)
    except: pass

blacklist = load_blacklist()
sent_messages = {}

# ---- Helper Functions ----
async def check_deleted(app):
    global blacklist
    deleted = []
    for chat_id, msg_id in list(sent_messages.items()):
        try:
            msg = await app.get_messages(chat_id, msg_id)
            if not msg or msg.empty:
                deleted.append(chat_id)
        except:
            deleted.append(chat_id)

    for chat_id in deleted:
        blacklist.add(chat_id)
        sent_messages.pop(chat_id, None)
        logger.warning(f"⛔ Blacklisted {chat_id} (Deleted)")
    if deleted: save_blacklist(blacklist)

async def send_cycle(app):
    await check_deleted(app)
    groups = []
    async for dialog in app.get_dialogs():
        if dialog.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            groups.append(dialog.chat.id)
    
    active = [g for g in groups if g not in blacklist]
    logger.info(f"🚀 Sending to {len(active)} groups...")

    for chat_id in active:
        try:
            msg = await app.send_message(chat_id, MESSAGE)
            sent_messages[chat_id] = msg.id
            await asyncio.sleep(DELAY)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except (ChatWriteForbidden, ChatAdminRequired, UserBannedInChannel):
            blacklist.add(chat_id)
            save_blacklist(blacklist)
        except Exception as e:
            logger.error(f"Error {chat_id}: {e}")

# ---- Main Engine ----
async def main():
    app = Client(
        "auto_sender",
        session_string=SESSION_STRING,
        api_id=API_ID,
        api_hash=API_HASH
    )
    
    async with app:
        logger.info("✅ Logged in!")
        while True:
            await send_cycle(app)
            logger.info(f"💤 Sleeping for {INTERVAL}s")
            await asyncio.sleep(INTERVAL)

if __name__ == "__main__":
    # Flask ko thread me chalayein
    threading.Thread(target=start_flask, daemon=True).start()
    
    # Event loop ke sath run karein
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
