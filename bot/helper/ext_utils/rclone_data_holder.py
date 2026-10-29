from bot import local_storage


rclone_dict = {}
PERSISTENT_KEYS = {"MIRROR_SELECT_REMOTE", "MIRROR_SELECT_BASE_DIR"}


def get_rclone_data(key, user_id):
    value_dict = rclone_dict.get(user_id, {})
    return value_dict.get(key, "")


def update_rclone_data(key, value, user_id):
    if local_storage and key in PERSISTENT_KEYS:
        local_storage.patch("rclone", user_id, {key: value})
    if user_id in rclone_dict:
        rclone_dict[user_id][key] = value
    else:
        rclone_dict[user_id] = {key: value}
