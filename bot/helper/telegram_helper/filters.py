from pyrogram.filters import create
from bot import OWNER_ID, config_dict, user_data


class CustomFilters:
    async def custom_owner_filter(self, client, update):
        uid = update.from_user.id or update.sender_chat.id
        return uid == OWNER_ID

    owner_filter = create(custom_owner_filter)

    async def custom_chat_filter(self, client, update):
        chat_id = update.chat.id
        thread_id = update.message_thread_id if update.topic_message else None
        return bool(
            chat_id in user_data
            and user_data[chat_id].get("is_auth", False)
            and (
                thread_id is None
                or thread_id in user_data[chat_id].get("thread_ids", [])
            )
        )

    chat_filter = create(custom_chat_filter)

    async def custom_user_filter(self, client, update):
        uid = update.from_user.id or update.sender_chat.id
        chat_id = update.chat.id
        thread_id = update.message_thread_id if update.topic_message else None
        return bool(
            uid == OWNER_ID
            or (
                uid in user_data
                and (
                    user_data[uid].get("is_auth", False)
                    or user_data[uid].get("is_sudo", False)
                )
            )
            or (
                chat_id in user_data
                and user_data[chat_id].get("is_auth", False)
                and (
                    thread_id is None
                    or thread_id in user_data[chat_id].get("thread_ids", [])
                )
            )
        )

    user_filter = create(custom_user_filter)

    async def custom_sudo_filter(self, client, update):
        uid = update.from_user.id or update.sender_chat.id
        return bool(uid == OWNER_ID or uid in user_data and user_data[uid].get("is_sudo"))

    sudo_filter = create(custom_sudo_filter)

    async def custom_user_callback_filter(self, client, query):
        uid = query.from_user.id
        original = query.message.reply_to_message
        if not original or not original.from_user or original.from_user.id != uid:
            return False
        return await CustomFilters.user_filter(client, original)

    user_callback_filter = create(custom_user_callback_filter)

    async def custom_rclone_callback_filter(self, client, query):
        if not await CustomFilters.user_callback_filter(client, query):
            return False
        uid = query.from_user.id
        return bool(config_dict["MULTI_RCLONE_CONFIG"] or uid == OWNER_ID
                    or user_data.get(uid, {}).get("is_sudo"))

    rclone_callback_filter = create(custom_rclone_callback_filter)

