
import logging
import sqlite3
import asyncio
from datetime import datetime, timezone

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import (
    Forbidden,
    RetryAfter,
    TelegramError,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ChatJoinRequestHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIGURATION
# =========================================================

BOT_TOKEN = "8225449385:AAGcVts1Z0GcdjdKm_nz603HdYgm8Pygazo"

# Bot owner / trusted bot managers (Telegram user IDs).
# These IDs can use bot-management commands.
ADMIN_IDS = {
    8485299821,
}

DB_NAME = "join_request_bot.db"

# How long to keep a voice-chat invitation notice, in seconds.
VC_NOTICE_DELETE_SECONDS = 5

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# =========================================================
# 10 NOTIFICATION DESIGNS
# =========================================================

DESIGNS = [
    {
        "name": "Classic",
        "text": (
            "🔔 <b>NEW JOIN REQUEST</b>\n\n"
            "👤 Name: {name}\n"
            "🆔 User ID: <code>{user_id}</code>\n"
            "🔗 Username: {username}\n"
            "💬 Group: {chat_title}\n\n"
            "Choose an action below."
        ),
    },
    {
        "name": "Premium",
        "text": (
            "╔══════ ✦ JOIN REQUEST ✦ ══════╗\n\n"
            "👑 <b>New member waiting for approval</b>\n\n"
            "🙍 <b>Name:</b> {name}\n"
            "🆔 <b>ID:</b> <code>{user_id}</code>\n"
            "🔗 <b>Username:</b> {username}\n"
            "🏠 <b>Group:</b> {chat_title}\n\n"
            "╚══════════════════════════════╝"
        ),
    },
    {
        "name": "Minimal",
        "text": (
            "📩 <b>Join request</b>\n\n"
            "{name}  |  <code>{user_id}</code>\n"
            "{username}\n"
            "Group: {chat_title}"
        ),
    },
    {
        "name": "Modern",
        "text": (
            "🚀 <b>MEMBER REQUEST RECEIVED</b>\n\n"
            "┌ 👤 {name}\n"
            "├ 🆔 <code>{user_id}</code>\n"
            "├ 🔗 {username}\n"
            "└ 🏠 {chat_title}\n\n"
            "⚙️ Select an action:"
        ),
    },
    {
        "name": "Security",
        "text": (
            "🛡️ <b>JOIN REQUEST SECURITY CHECK</b>\n\n"
            "A user is waiting to join the group.\n\n"
            "👤 {name}\n"
            "🆔 <code>{user_id}</code>\n"
            "🔗 {username}\n"
            "📍 {chat_title}\n\n"
            "Review the request before deciding."
        ),
    },
    {
        "name": "Emoji",
        "text": (
            "✨✨✨✨✨✨✨✨\n"
            "📨 <b>NEW REQUEST!</b>\n"
            "✨✨✨✨✨✨✨✨\n\n"
            "🙋 {name}\n"
            "🆔 <code>{user_id}</code>\n"
            "🔗 {username}\n"
            "🏡 {chat_title}\n\n"
            "👇 <b>Choose below</b>"
        ),
    },
    {
        "name": "Professional",
        "text": (
            "📋 <b>GROUP ACCESS REVIEW</b>\n\n"
            "Status: <b>Pending</b>\n"
            "Applicant: {name}\n"
            "Telegram ID: <code>{user_id}</code>\n"
            "Username: {username}\n"
            "Destination: {chat_title}\n\n"
            "Action is required from a group administrator."
        ),
    },
    {
        "name": "Neon",
        "text": (
            "⚡ <b>NEW ACCESS REQUEST</b> ⚡\n\n"
            "👤 <b>{name}</b>\n"
            "🆔 <code>{user_id}</code>\n"
            "🔗 {username}\n"
            "🌐 {chat_title}\n\n"
            "⚡ <i>Waiting for admin decision...</i>"
        ),
    },
    {
        "name": "Friendly",
        "text": (
            "👋 <b>Someone wants to join!</b>\n\n"
            "Say hello to: {name}\n"
            "Their ID: <code>{user_id}</code>\n"
            "Username: {username}\n"
            "Group: {chat_title}\n\n"
            "An admin can approve or decline below."
        ),
    },
    {
        "name": "Detailed",
        "text": (
            "🔎 <b>JOIN REQUEST DETAILS</b>\n\n"
            "• <b>Name:</b> {name}\n"
            "• <b>User ID:</b> <code>{user_id}</code>\n"
            "• <b>Username:</b> {username}\n"
            "• <b>Group:</b> {chat_title}\n"
            "• <b>Status:</b> Pending\n\n"
            "Select Accept or Decline to process this request."
        ),
    },
]


# =========================================================
# DATABASE
# =========================================================

def db_connection():
    conn = sqlite3.connect(DB_NAME, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT DEFAULT '',
                username TEXT DEFAULT '',
                started_at TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                chat_title TEXT DEFAULT '',
                user_id INTEGER,
                username TEXT DEFAULT '',
                action TEXT DEFAULT '',
                actor_id INTEGER DEFAULT 0,
                created_at TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            )
        """)

        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
            ("active_design", "0"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
            ("dm_template", ""),
        )


def get_setting(key, default=""):
    with db_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with db_connection() as conn:
        conn.execute("""
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, str(value)))


def save_user(user):
    if not user:
        return

    with db_connection() as conn:
        conn.execute("""
            INSERT INTO users(user_id, first_name, username, started_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name = excluded.first_name,
                username = excluded.username
        """, (
            user.id,
            user.first_name or "",
            user.username or "",
            datetime.now(timezone.utc).isoformat(),
        ))


def is_banned(user_id):
    with db_connection() as conn:
        row = conn.execute(
            "SELECT user_id FROM banned_users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row is not None


def ban_user(user_id, reason=""):
    with db_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO banned_users(user_id, reason, created_at)
            VALUES(?, ?, ?)
        """, (
            user_id,
            reason,
            datetime.now(timezone.utc).isoformat(),
        ))


def unban_user(user_id):
    with db_connection() as conn:
        cur = conn.execute(
            "DELETE FROM banned_users WHERE user_id = ?",
            (user_id,),
        )
        return cur.rowcount > 0


def log_action(chat_id, chat_title, user_id, username, action, actor_id=0):
    with db_connection() as conn:
        conn.execute("""
            INSERT INTO request_logs(
                chat_id, chat_title, user_id, username,
                action, actor_id, created_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?)
        """, (
            chat_id,
            chat_title or "",
            user_id,
            username or "",
            action,
            actor_id,
            datetime.now(timezone.utc).isoformat(),
        ))


# =========================================================
# HELPERS
# =========================================================

def is_bot_manager(user_id):
    return user_id in ADMIN_IDS


def username_text(user):
    if user.username:
        return "@" + user.username
    return "Not set"


def get_design_index():
    try:
        value = int(get_setting("active_design", "0"))
        return value % len(DESIGNS)
    except (TypeError, ValueError):
        return 0


def render_design(index, user, chat_title):
    design = DESIGNS[index]
    values = {
        "name": user.full_name or "Unknown",
        "user_id": user.id,
        "username": username_text(user),
        "chat_title": chat_title or "Unknown group",
    }
    return design["text"].format(**values)


def design_keyboard(index):
    previous_index = (index - 1) % len(DESIGNS)
    next_index = (index + 1) % len(DESIGNS)

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data=f"design_prev:{index}",
            ),
            InlineKeyboardButton(
                f"{index + 1}/{len(DESIGNS)}",
                callback_data="design_info",
            ),
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=f"design_next:{index}",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Use This Design",
                callback_data=f"design_use:{index}",
            ),
        ],
    ])


def request_keyboard(chat_id, user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Accept",
                callback_data=f"req_accept:{chat_id}:{user_id}",
            ),
            InlineKeyboardButton(
                "❌ Decline",
                callback_data=f"req_decline:{chat_id}:{user_id}",
            ),
        ],
    ])


async def safe_reply(update, text, **kwargs):
    if update.message:
        await update.message.reply_text(text, **kwargs)
    elif update.effective_message:
        await update.effective_message.reply_text(text, **kwargs)


async def is_group_admin(context, chat_id, user_id):
    """
    Allow any administrator or owner/creator.
    Do NOT require the clicking human admin to have can_invite_users.
    """
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except TelegramError:
        logger.exception(
            "Could not verify admin status for user %s in chat %s",
            user_id,
            chat_id,
        )
        return False


async def delete_later(context, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )
    except TelegramError:
        pass


# =========================================================
# START / HELP / USER REGISTRATION
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        save_user(user)

    text = (
        "👋 <b>Join Request Management Bot</b>\n\n"
        "Bot join requests manage karne aur admin notifications bhejne "
        "ke liye ready hai.\n\n"
        "Commands dekhne ke liye /help use karein."
    )

    if user and is_bot_manager(user.id):
        text += "\n\nAdmin panel: /panel"

    await safe_reply(update, text, parse_mode="HTML")


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        await safe_reply(
            update,
            f"Your Telegram user ID: <code>{user.id}</code>",
            parse_mode="HTML",
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>Bot Commands</b>\n\n"
        "/start - Start bot\n"
        "/myid - Show your Telegram ID\n"
        "/help - Show this help\n\n"
        "<b>Bot manager commands</b>\n"
        "/panel - Admin panel\n"
        "/stats - Statistics\n"
        "/design - Browse 10 designs\n"
        "/setdm YOUR MESSAGE - Set auto-DM template\n"
        "/testdm - Test your DM template\n"
        "/logs - Recent request logs\n"
        "/broadcast YOUR MESSAGE - Broadcast to started users\n"
        "/ban USER_ID - Add user to bot blocklist\n"
        "/unban USER_ID - Remove user from bot blocklist\n\n"
        "<b>Template placeholders</b>\n"
        "{name}, {username}, {user_id}"
    )
    await safe_reply(update, text, parse_mode="HTML")


# =========================================================
# ADMIN PANEL / STATS
# =========================================================

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_bot_manager(user.id):
        await safe_reply(update, "❌ You are not authorized.")
        return

    text = (
        "🛠️ <b>Admin Panel</b>\n\n"
        f"Active design: <b>{get_design_index() + 1}/"
        f"{len(DESIGNS)} — {DESIGNS[get_design_index()]['name']}</b>\n"
        f"Auto-DM: <b>{'Configured' if get_setting('dm_template') else 'Not configured'}</b>\n\n"
        "Use /help to view all commands."
    )
    await safe_reply(update, text, parse_mode="HTML")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_bot_manager(user.id):
        await safe_reply(update, "❌ You are not authorized.")
        return

    with db_connection() as conn:
        users_count = conn.execute(
            "SELECT COUNT(*) AS n FROM users"
        ).fetchone()["n"]

        requests_count = conn.execute(
            "SELECT COUNT(*) AS n FROM request_logs"
        ).fetchone()["n"]

        accepted_count = conn.execute(
            "SELECT COUNT(*) AS n FROM request_logs WHERE action = 'accepted'"
        ).fetchone()["n"]

        declined_count = conn.execute(
            "SELECT COUNT(*) AS n FROM request_logs WHERE action = 'declined'"
        ).fetchone()["n"]

        banned_count = conn.execute(
            "SELECT COUNT(*) AS n FROM banned_users"
        ).fetchone()["n"]

    text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Users who started bot: {users_count}\n"
        f"📝 Total logged actions: {requests_count}\n"
        f"✅ Accepted: {accepted_count}\n"
        f"❌ Declined: {declined_count}\n"
        f"🚫 Bot blocklist: {banned_count}"
    )
    await safe_reply(update, text, parse_mode="HTML")


# =========================================================
# DESIGN SELECTOR
# =========================================================

async def design_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_bot_manager(user.id):
        await safe_reply(update, "❌ You are not authorized.")
        return

    index = get_design_index()
    text = (
        f"🎨 <b>Notification Design {index + 1}/{len(DESIGNS)}</b>\n"
        f"Style: <b>{DESIGNS[index]['name']}</b>\n\n"
        "Use Next/Previous to browse all designs. "
        "Tap Use This Design to activate one."
    )

    await safe_reply(
        update,
        text,
        parse_mode="HTML",
        reply_markup=design_keyboard(index),
    )


async def design_callback(query, context, data):
    user = query.from_user
    if not is_bot_manager(user.id):
        await query.answer("Only bot managers can change designs.", show_alert=True)
        return

    if data == "design_info":
        await query.answer(f"{len(DESIGNS)} designs available.")
        return

    try:
        action, number = data.split(":")
        index = int(number) % len(DESIGNS)
    except (ValueError, TypeError):
        await query.answer("Invalid design.")
        return

    if action == "design_prev":
        index = (index - 1) % len(DESIGNS)
    elif action == "design_next":
        index = (index + 1) % len(DESIGNS)
    elif action == "design_use":
        set_setting("active_design", index)
        await query.answer(
            f"Design {index + 1} activated.",
            show_alert=True,
        )
        if query.message:
            await query.edit_message_text(
                f"✅ Active design: <b>{DESIGNS[index]['name']}</b>\n"
                f"Design {index + 1}/{len(DESIGNS)} will be used for "
                "new join-request notifications.",
                parse_mode="HTML",
            )
        return
    else:
        await query.answer("Unknown action.")
        return

    text = (
        f"🎨 <b>Notification Design {index + 1}/{len(DESIGNS)}</b>\n"
        f"Style: <b>{DESIGNS[index]['name']}</b>\n\n"
        "Browse with Previous/Next, or activate it."
    )

    await query.answer()
    if query.message:
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=design_keyboard(index),
        )


# =========================================================
# AUTO-DM TEMPLATE
# =========================================================

async def setdm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_bot_manager(user.id):
        await safe_reply(update, "❌ You are not authorized.")
        return

    template = " ".join(context.args).strip()
    if not template:
        await safe_reply(
            update,
            "Usage:\n"
            "/setdm Welcome {name}! Your ID is {user_id}. Username: {username}",
        )
        return

    # Validate placeholders before saving.
    try:
        template.format(
            name="Example",
            username="@example",
            user_id=12345,
        )
    except (KeyError, ValueError, IndexError) as exc:
        await safe_reply(update, f"❌ Invalid template: {exc}")
        return

    set_setting("dm_template", template)
    await safe_reply(update, "✅ Auto-DM template saved.")


async def testdm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_bot_manager(user.id):
        await safe_reply(update, "❌ You are not authorized.")
        return

    template = get_setting("dm_template")
    if not template:
        await safe_reply(
            update,
            "No auto-DM template set. Use /setdm YOUR MESSAGE",
        )
        return

    try:
        text = template.format(
            name=user.full_name or "Admin",
            username=username_text(user),
            user_id=user.id,
        )
        await context.bot.send_message(
            chat_id=user.id,
            text=text,
            parse_mode=None,
        )
        await safe_reply(update, "✅ Test message sent to your private chat.")
    except TelegramError as exc:
        await safe_reply(update, f"❌ Could not send test DM: {exc}")


async def send_join_dm(context, user):
    template = get_setting("dm_template")
    if not template:
        return

    try:
        text = template.format(
            name=user.full_name or "User",
            username=username_text(user),
            user_id=user.id,
        )
        await context.bot.send_message(
            chat_id=user.id,
            text=text,
            parse_mode=None,
        )
    except (Forbidden, TelegramError):
        # Telegram generally doesn't allow bots to start a private chat
        # with users who have not started the bot.
        logger.info("Auto-DM unavailable for user %s", user.id)


# =========================================================
# JOIN REQUEST HANDLER
# =========================================================

async def on_join_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    request = update.chat_join_request
    if not request:
        return

    chat = request.chat
    user = request.from_user

    save_user(user)

    # Automatically decline users on this bot's blocklist.
    if is_banned(user.id):
        try:
            await context.bot.decline_chat_join_request(
                chat_id=chat.id,
                user_id=user.id,
            )
            log_action(
                chat.id, chat.title, user.id, user.username,
                "declined_banned", 0,
            )
        except TelegramError:
            logger.exception("Could not decline blocked user")
        return

    # Send notification into the group so all group admins can see it.
    # Normal members cannot use the buttons: callback checks admin status.
    index = get_design_index()
    text = render_design(index, user, chat.title)

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            parse_mode="HTML",
            reply_markup=request_keyboard(chat.id, user.id),
        )
    except TelegramError:
        logger.exception(
            "Could not send join request notification to chat %s",
            chat.id,
        )

    log_action(
        chat.id, chat.title, user.id, user.username,
        "pending", 0,
    )

    # This may fail if the user has not opened the bot privately.
    await send_join_dm(context, user)


# =========================================================
# ACCEPT / DECLINE BUTTON CALLBACK
# =========================================================

async def request_callback(query, context, data):
    actor = query.from_user

    try:
        action, chat_id_text, user_id_text = data.split(":")
        chat_id = int(chat_id_text)
        user_id = int(user_id_text)
    except (ValueError, TypeError):
        await query.answer("Invalid request button.", show_alert=True)
        return

    # KEY RULE:
    # Any group admin/creator may click, including admins without
    # their own Invite Users / join-request approval permission.
    # Normal members are rejected.
    if not await is_group_admin(context, chat_id, actor.id):
        await query.answer(
            "❌ Only group admins can use these buttons.",
            show_alert=True,
        )
        return

    try:
        if action == "req_accept":
            await context.bot.approve_chat_join_request(
                chat_id=chat_id,
                user_id=user_id,
            )
            result = "accepted"
            response = "✅ Join request accepted."
            log_action(
                chat_id, "", user_id, "",
                "accepted", actor.id,
            )

        elif action == "req_decline":
            await context.bot.decline_chat_join_request(
                chat_id=chat_id,
                user_id=user_id,
            )
            result = "declined"
            response = "❌ Join request declined."
            log_action(
                chat_id, "", user_id, "",
                "declined", actor.id,
            )

        else:
            await query.answer("Unknown action.")
            return

    except TelegramError as exc:
        logger.exception("Join request action failed")
        await query.answer(
            "Action failed. Check that the bot is an admin with "
            "permission to invite users and that the request is still pending.",
            show_alert=True,
        )
        return

    await query.answer(response, show_alert=True)

    if query.message:
        old_text = query.message.text_html or query.message.text or ""
        try:
            await query.edit_message_text(
                old_text + f"\n\n<b>Status:</b> {result.title()}\n"
                f"<b>By admin ID:</b> <code>{actor.id}</code>",
                parse_mode="HTML",
                reply_markup=None,
            )
        except TelegramError:
            pass


# =========================================================
# RECENT LOGS
# =========================================================

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_bot_manager(user.id):
        await safe_reply(update, "❌ You are not authorized.")
        return

    with db_connection() as conn:
        rows = conn.execute("""
            SELECT chat_title, user_id, username, action, actor_id, created_at
            FROM request_logs
            ORDER BY id DESC
            LIMIT 15
        """).fetchall()

    if not rows:
        await safe_reply(update, "No request logs yet.")
        return

    lines = ["📜 <b>Recent Request Logs</b>\n"]
    for row in rows:
        lines.append(
            f"• <b>{row['action']}</b> | "
            f"{row['chat_title'] or 'Group'} | "
            f"<code>{row['user_id']}</code> | "
            f"{row['username'] or 'No username'} | "
            f"Actor: <code>{row['actor_id']}</code>\n"
            f"  <i>{row['created_at']}</i>"
        )

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:3900] + "\n…"

    await safe_reply(update, text, parse_mode="HTML")


# =========================================================
# BROADCAST
# =========================================================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_bot_manager(user.id):
        await safe_reply(update, "❌ You are not authorized.")
        return

    message = " ".join(context.args).strip()
    if not message:
        await safe_reply(update, "Usage: /broadcast Your message")
        return

    with db_connection() as conn:
        rows = conn.execute(
            "SELECT user_id FROM users"
        ).fetchall()

    success = 0
    failed = 0

    status_message = await update.effective_message.reply_text(
        "📣 Broadcast started..."
    )

    for row in rows:
        target_id = row["user_id"]
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=message,
            )
            success += 1
        except RetryAfter as exc:
            wait_seconds = getattr(exc, "retry_after", 1)
            await asyncio.sleep(float(wait_seconds))
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=message,
                )
                success += 1
            except TelegramError:
                failed += 1
        except TelegramError:
            failed += 1

        await asyncio.sleep(0.05)

    await status_message.edit_text(
        f"📣 <b>Broadcast finished</b>\n\n"
        f"✅ Sent: {success}\n"
        f"❌ Failed: {failed}",
        parse_mode="HTML",
    )


# =========================================================
# BOT BLOCKLIST COMMANDS
# =========================================================

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_bot_manager(user.id):
        await safe_reply(update, "❌ You are not authorized.")
        return

    if not context.args:
        await safe_reply(update, "Usage: /ban USER_ID [reason]")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "❌ User ID must be a number.")
        return

    reason = " ".join(context.args[1:]).strip()
    ban_user(target_id, reason)
    await safe_reply(
        update,
        f"🚫 User <code>{target_id}</code> added to the bot blocklist.",
        parse_mode="HTML",
    )


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_bot_manager(user.id):
        await safe_reply(update, "❌ You are not authorized.")
        return

    if not context.args:
        await safe_reply(update, "Usage: /unban USER_ID")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "❌ User ID must be a number.")
        return

    removed = unban_user(target_id)
    if removed:
        await safe_reply(
            update,
            f"✅ User <code>{target_id}</code> removed from the bot blocklist.",
            parse_mode="HTML",
        )
    else:
        await safe_reply(update, "User was not on the bot blocklist.")


# =========================================================
# OPTIONAL: VOICE CHAT INVITATION NOTICE
# =========================================================

async def service_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    if not message:
        return

    invited = getattr(message, "video_chat_participants_invited", None)
    if not invited:
        return

    names = []
    for participant in invited.users:
        names.append(
            f"• {participant.full_name} "
            f"(<code>{participant.id}</code>)"
        )

    text = (
        "🎙️ <b>Voice/Video Chat Invitation</b>\n\n"
        + "\n".join(names)
    )

    try:
        notice = await message.reply_text(
            text,
            parse_mode="HTML",
        )
        asyncio.create_task(
            delete_later(
                context,
                notice.chat_id,
                notice.message_id,
                VC_NOTICE_DELETE_SECONDS,
            )
        )
    except TelegramError:
        logger.exception("Could not send voice-chat invitation notice")


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callback_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data

    if data.startswith("design_"):
        await design_callback(query, context, data)
        return

    if data.startswith("req_accept:") or data.startswith("req_decline:"):
        await request_callback(query, context, data)
        return

    await query.answer("Unknown button.")


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "Unhandled error while processing update",
        exc_info=context.error,
    )


# =========================================================
# MAIN
# =========================================================

def main():
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError(
            "Please put your Telegram bot token in BOT_TOKEN."
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("help", help_command))

    # Bot-manager commands
    app.add_handler(CommandHandler("panel", panel))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("design", design_command))
    app.add_handler(CommandHandler("setdm", setdm))
    app.add_handler(CommandHandler("testdm", testdm))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))

    # Join request updates
    app.add_handler(ChatJoinRequestHandler(on_join_request))

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(callback_router))

    # Optional voice/video chat invitation notices
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.VIDEO_CHAT_PARTICIPANTS_INVITED,
            service_message_handler,
        )
    )

    app.add_error_handler(error_handler)

    logger.info("Join Request Management Bot is starting...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
