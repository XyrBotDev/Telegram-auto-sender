import os
import json
import asyncio
import logging
from pyrogram import Client
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
INTERVAL = int(os.environ.get("INTERVAL", "300"))          # 5 min = 300 sec
DELAY = int(os.environ.get("DELAY_BETWEEN_GROUPS", "8"))   # Har group ke beech delay
BLACKLIST_FILE = "blacklist.json"
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AutoSender")

# Pyrogram Client (Session String se)
app = Client(
    name="auto_sender",
    session_string=SESSION_STRING,
    api_id=API_ID,
    api_hash=API_HASH
)

# ---- Blacklist System ----
def load_blacklist() -> set:
    try:
        with open(BLACKLIST_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_blacklist(bl: set):
    with open(BLACKLIST_FILE, "w") as f:
        json.dump(list(bl), f)

blacklist = load_blacklist()
sent_messages = {}  # {chat_id: message_id}


# ---- Step 1: Check Deleted Messages ----
async def check_deleted():
    """Pichle cycle me bheje messages check karo — agar delete hue to blacklist"""
    global blacklist
    deleted = []

    for chat_id, msg_id in list(sent_messages.items()):
        try:
            msg = await app.get_messages(chat_id, msg_id)
            if msg.empty:  # Message delete ho chuka hai
                deleted.append(chat_id)
        except Exception:
            deleted.append(chat_id)

    for chat_id in deleted:
        blacklist.add(chat_id)
        sent_messages.pop(chat_id, None)
        logger.warning(f"⛔ BLACKLISTED {chat_id} — message deleted by admin/bot")

    if deleted:
        save_blacklist(blacklist)
        logger.info(f"📝 Blacklist updated. Total: {len(blacklist)}")


# ---- Step 2: Fetch All Groups (Dynamic) ----
async def get_all_groups() -> list:
    """Saare groups ki fresh list (naye groups bhi include honge)"""
    groups = []
    async for dialog in app.get_dialogs():
        chat = dialog.chat
        if chat.type in ("group", "supergroup"):
            groups.append(chat.id)
    return groups


# ---- Step 3: Send to All Active Groups ----
async def send_cycle():
    global blacklist

    # Pehle deleted messages check karo
    await check_deleted()

    # Fresh group list lao
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
            logger.warning(f"  ⏳ FloodWait {e.value}s — waiting...")
            await asyncio.sleep(e.value)
            # Retry this group
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
            logger.warning(f"  ⛔ BLACKLISTED {chat_id} — no permission")

        except RPCError as e:
            logger.error(f"  ❌ RPC Error {chat_id}: {e}")
            failed += 1

        except Exception as e:
            logger.error(f"  ❌ Error {chat_id}: {e}")
            failed += 1

        # Rate limit se bachne ke liye delay
        await asyncio.sleep(DELAY)

    save_blacklist(blacklist)
    logger.info(f"\n📈 Cycle Complete | ✅ {success} Sent | ❌ {failed} Failed\n")


# ---- Main Loop ----
async def main():
    me = await app.get_me()
    logger.info(f"🔐 Logged in as: {me.first_name} (@{me.username})")
    logger.info(f"⏱️  Interval: {INTERVAL}s | Delay: {DELAY}s\n")

    while True:
        try:
            await send_cycle()
        except Exception as e:
            logger.error(f"💥 Critical: {e}")

        logger.info(f"💤 Sleeping {INTERVAL}s until next cycle...\n")
        await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    app.run(main())
