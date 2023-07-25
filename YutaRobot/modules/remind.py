import asyncio
import html
import io
import re
import time

from GabiBraunRobot import DRAGONS, REMINDER_LIMIT, dispatcher
from GabiBraunRobot.modules.connection import connected
from GabiBraunRobot.modules.helper_funcs.chat_status import user_admin
from GabiBraunRobot.modules.helper_funcs.extraction import extract_text
from GabiBraunRobot.modules.helper_funcs.string_handling import (
    extract_time_seconds, markdown_to_html,
)
from GabiBraunRobot.modules.log_channel import loggable
from GabiBraunRobot.modules.ping import get_readable_time
from GabiBraunRobot.modules.sql import remind_sql as sql
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, ParseMode,
    Update,
)
from telegram.ext import (
    CallbackContext, CallbackQueryHandler,
    CommandHandler,
)
from telegram.utils.helpers import mention_html

html_tags = re.compile('<.*?>')

@user_admin
@loggable
def remind(update: Update, context: CallbackContext):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    args = msg.text.split(None, 2)
    is_replied = False

    conn = connected(context.bot, update, chat, user.id, need_admin=True)
    if conn is not False:
        chat_id = conn
        chat_title = dispatcher.bot.getChat(conn).title
    else:
        chat_id = chat.id
        chat_title = "your private chat" if chat.type == "private" else chat.title

    if len(args) != 3:
        if (
            len(args) != 2 or
            (not msg.reply_to_message) or (not extract_text(msg.reply_to_message))
        ):
            msg.reply_text(
                "Incorrect format\nFormat: `/remind 20m message here`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        is_replied = True

    duration = ""
    text = ""
    if is_replied:
        text = extract_text(msg.reply_to_message)
        duration = args[1]
    else:
        duration, text = args[1:]

    when = extract_time_seconds(msg, duration)
    if not when or when == "":
        return
    if int(when) > 63072000:
        msg.reply_text("Max remind time is limtied to 2 years!")
        return
    if int(when) < 30:
        msg.reply_text("Your reminder needs to be more than 30 seconds!")
        return

    t = (round(time.time()) + when)
    chat_limit = sql.num_reminds_in_chat(chat_id)
    if chat_limit >= REMINDER_LIMIT:
        msg.reply_text(f"You can set {REMINDER_LIMIT} reminders in a chat.")
        return

    sql.set_remind(chat_id, t, text[:512], user.id)

    confirmation = f"Noted! I'll remind you after {args[1]}.\nThis reminder's timestamp is <code>{t}</code>."
    if len(text) > 512:
        confirmation += "\n<b>Note</b>: Reminder was over 512 characters and was truncated."

    msg.reply_text(confirmation, parse_mode=ParseMode.HTML)

    return (
        f"<b>{html.escape(chat_title)}:</b>\n"
        f"#REMINDER\n"
        f"<b>Admin</b>: {mention_html(user.id, user.first_name)}\n"
        f"<b>Time left</b>: {duration}\n"
        "<b>Message</b>: {}{}".format(re.sub(html_tags, '', text[:20]), "...." if len(text) > 20 else "")
    )

@user_admin
def reminders(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message

    conn = connected(context.bot, update, chat, user.id, need_admin=True)
    if conn is not False:
        chat_id = conn
        chat_title = dispatcher.bot.getChat(conn).title
    else:
        chat_id = chat.id
        chat_title = "your private chat" if chat.type == "private" else chat.title

    reminders = sql.get_reminds_in_chat(chat_id)
    if len(reminders) < 1:
        return msg.reply_text(f"There are no reminders in {chat_title} yet.")
    text = f"Reminders in {chat_title} are:\n"
    for reminder in reminders:
        user = context.bot.get_chat(reminder.user_id)
        text += ("\n• {}\n  <b>By</b>: {}\n  <b>Time left</b>: {}\n  <b>Time stamp</b>: <code>{}</code>").format(reminder.remind_message, (mention_html(user.id, user.first_name) if not user.username else "@"+user.username), get_readable_time(reminder.time_seconds-round(time.time())), reminder.time_seconds)
    text += "\n\n<b>Note</b>: You can clear a particular reminder with its time stamp."
    if len(text) > 4096:
        text = re.sub(html_tags, '', text)
        with io.BytesIO(str.encode(text)) as file:
            file.name = f"reminders_{chat_id}.txt"
            dispatcher.bot.send_document(
                chat_id=update.effective_chat.id, 
                document=file, 
                caption="Click to get the list of all reminders in this chat.", 
                reply_to_message_id=msg.message_id
            )
        return
    msg.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

@user_admin
@loggable
def clearreminder(update: Update, context: CallbackContext):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    args = context.args

    conn = connected(context.bot, update, chat, user.id, need_admin=True)
    if conn is not False:
        chat_id = conn
        chat_title = dispatcher.bot.getChat(conn).title
    else:
        chat_id = chat.id
        chat_title = "your private chat" if chat.type == "private" else chat.title

    if len(args) >= 1:
        timestamp = args[0]
        try:
            timestamp = int(timestamp)
        except:
            timestamp = 0

        remind = sql.get_remind_in_chat(chat_id, timestamp)
        if not remind:
            msg.reply_text("This time stamp doesn't seem to be valid.")
            return

        sql.rem_remind(chat_id, timestamp, remind.remind_message, remind.user_id)
        msg.reply_text("I've deleted this reminder.")
        return (
            f"<b>{html.escape(chat_title)}:</b>\n"
            f"#REMINDER_DELETED\n"
            f"<b>Admin</b>: {mention_html(user.id, user.first_name)}\n"
            f"<b>Reminder by</b>: <code>{remind.user_id}</code>\n"
            f"<b>Time stamp</b>: <code>{timestamp}</code>\n"
            "<b>Message</b>: {}{}".format(re.sub(html_tags, '', remind.remind_message[:20]), "...." if len(remind.remind_message) > 20 else "")
        )
    else:
        msg.reply_text("You need to provide me the timestamp of the reminder.\n<b>Note</b>: You can see timestamps via /reminders command.", parse_mode=ParseMode.HTML)
        return

@user_admin
def clearallreminders(update: Update, context: CallbackContext):
    real_chat = chat = update.effective_chat
    user = update.effective_user

    conn = connected(context.bot, update, chat, user.id, need_admin=True)
    if conn is not False:
        chat_id = conn
        chat = dispatcher.bot.getChat(conn)
    else:
        chat_id = chat.id

    member = chat.get_member(user.id)
    if chat.type != "private" and member.status != "creator" and member.user.id not in DRAGONS:
        return update.effective_message.reply_text("Only group owner can do this!")

    context.bot.send_message(
        chat_id=real_chat.id,
        text="Are you sure you want to delete all reminders?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(text="Yes", callback_data="clearremind_yes"),
            InlineKeyboardButton(text="No", callback_data="clearremind_no"),
        ]]),
    )

@user_admin
@loggable
def clearallremindersbtn(update: Update, context: CallbackContext):
    query = update.callback_query
    chat = update.effective_chat
    user = update.effective_user

    conn = connected(context.bot, update, chat, user.id, need_admin=True)
    if conn is not False:
        chat_id = conn
        chat_title = dispatcher.bot.getChat(conn).title
    else:
        chat_id = chat.id
        chat_title = "your private chat" if chat.type == "private" else chat.title

    option = query.data.split("_")[1]
    member = context.bot.get_chat_member(chat_id, user.id)
    if chat.type != "private" and member.status != "creator" and member.user.id not in DRAGONS:
        return query.answer("Only group owner can do this!")
    if option == "no":
        query.message.edit_text("No reminders were deleted!")
    elif option == "yes":
        reminders = sql.get_reminds_in_chat(chat_id)
        for r in reminders:
            try:
                sql.rem_remind(r.chat_id, r.time_seconds, r.remind_message, r.user_id)
            except:
                pass
        query.message.edit_text("I have deleted all reminders.")
    context.bot.answer_callback_query(query.id)
    return (
            f"<b>{html.escape(chat_title)}:</b>\n"
            f"#ALL_REMINDERS_DELETED"
    )


async def check_reminds():
    while True:
        t = round(time.time())
        if t in sql.REMINDERS:
            r = sql.REMINDERS[t]
            for a in r:
                try:
                    user = dispatcher.bot.get_chat(a["user_id"])
                    text = "{}'s reminder:\n{}".format(mention_html(user.id, user.first_name), markdown_to_html(a["message"]))
                    dispatcher.bot.send_message(a["chat_id"], text, parse_mode=ParseMode.HTML)
                    sql.rem_remind(a["chat_id"], t, a["message"], a["user_id"])
                except:
                    continue
        await asyncio.sleep(1)

#starts the reminder
asyncio.get_event_loop().create_task(check_reminds())


REMIND_HANDLER = CommandHandler(["remind", "reminder"], remind, run_async=True)
REMINDERS_HANDLER = CommandHandler(["reminds", "reminders"], reminders, run_async=True)
CLEARREMINDER_HANDLER = CommandHandler(["clearreminder", "clearremind"], clearreminder, run_async=True)
CLEARALLREMINDERS_HANDLER = CommandHandler(["clearallreminders", "clearallreminds"], clearallreminders, run_async=True)
CLEARALLREMINDERSBTN_HANDLER = CallbackQueryHandler(clearallremindersbtn, pattern=r"clearremind_", run_async=True)

dispatcher.add_handler(REMIND_HANDLER)
dispatcher.add_handler(REMINDERS_HANDLER)
dispatcher.add_handler(CLEARREMINDER_HANDLER)
dispatcher.add_handler(CLEARALLREMINDERS_HANDLER)
dispatcher.add_handler(CLEARALLREMINDERSBTN_HANDLER)

__mod_name__ = "ʀᴇᴍɪɴᴅᴇʀꜱ"
__help__ = """
This module lets you setup upto 20 reminders per group/pm.
The usage is as follows

*Commands*:
 • `/remind <time> <text>`*:* Sets a reminder for given time, usage is same like a mute command
 • `/reminders`*:* Lists all the reminders for current chat
 • `/clearreminder <timestampID>`*:* Removes the reminder of the given timestamp ID from the list
 • `/clearallreminders`*:* Cleans all saved reminders (owner only)

*TimestampID:* An ID number listed under each reminder, used to remove a reminder
*Time:* 1d or 1h or 1m or 30s

*Notes:*
 • You can only supply one time variable, be it day(s), hour(s), minute(s) or seconds
 • The shortest reminder can be 30 seconds
 • Reminders are limited to 512 chracters per reminder
 • Only group admins can setup reminders

*Example:*
`/remind 2h You need to sleep!`
This will print a reminder with the text after 2 hours

`/clearreminder 1631378953`
Removes the reminder of the said timestamp ID
"""