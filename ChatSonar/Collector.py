import re
import time
import asyncio
from collections import Counter
from datetime import datetime

try:
    import emoji as emoji_lib
    HAS_EMOJI_LIB = True
except ImportError:
    HAS_EMOJI_LIB = False


SCHEMA_VERSION = 2


class Collector:
    _MAX_ACTIVE_USERS_PER_SCOPE = 200

    def __init__(self, sdk, config):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar.Collector")
        self.storage = sdk.storage
        self.config = config
        self._last_active = {}

    async def start(self):
        self._migrate_if_needed()

    async def stop(self):
        pass

    def _scope(self, platform, group_id):
        return f"sonar:{platform}:{group_id}"

    def _is_optout(self, scope, user_id):
        optout = self.storage.get(f"{scope}:optout", [])
        return user_id in optout

    async def on_message(self, event):
        platform = event.get_platform()
        detail_type = event.get_detail_type()
        if detail_type not in ("group", "private"):
            return

        is_group = detail_type == "group"
        is_command = False
        if hasattr(event, 'is_command') and callable(event.is_command):
            try:
                is_command = event.is_command()
            except Exception:
                text = event.get_text() or ""
                is_command = text.startswith("/")

        user_id = event.get_user_id()
        if not user_id:
            return

        group_id = None
        scope = None
        if is_group:
            group_id = event.get_group_id()
            if not group_id:
                return
            scope = self._scope(platform, group_id)
            if self._is_optout(scope, user_id):
                return

        text = event.get_text() or ""
        event_time = event.get_time()
        if event_time and event_time > 0:
            if event_time > 1e12:
                event_time = int(event_time / 1000)
            utc_offset = self.config.get("utc_offset", 8)
            hour = int((event_time / 3600 + utc_offset) % 24)
        else:
            hour = datetime.now().hour

        nickname = event.get_user_nickname() or ""
        timestamp = time.time()

        if is_command:
            if scope:
                self._persist_presence(scope, user_id)
                self._persist_group_user(scope, user_id, nickname, timestamp)
            return

        emojis = self._extract_emojis(text)
        words = self._extract_words(text)
        msg_len = len(text)
        mentions = event.get_mentions() or []

        self._persist_profile(user_id, hour, msg_len, emojis, words, nickname, timestamp)

        if is_group and scope:
            self._persist_presence(scope, user_id)
            self._persist_group_user(scope, user_id, nickname, timestamp)
            self._persist_groups_list(user_id, scope)

            if mentions:
                self._persist_interact(scope, user_id, mentions)

            now = time.time()
            window = self.config.get("cooccur_window", 300)
            scope_active = self._last_active.get(scope)
            if scope_active is None:
                scope_active = {}
                self._last_active[scope] = scope_active
            scope_active[user_id] = now
            if len(scope_active) > self._MAX_ACTIVE_USERS_PER_SCOPE:
                expired = [uid for uid, t in scope_active.items() if now - t >= window]
                for uid in expired:
                    del scope_active[uid]
                if len(scope_active) > self._MAX_ACTIVE_USERS_PER_SCOPE:
                    sorted_users = sorted(scope_active.items(), key=lambda x: x[1])
                    for uid, _ in sorted_users[:len(scope_active) - self._MAX_ACTIVE_USERS_PER_SCOPE]:
                        del scope_active[uid]
            if len(scope_active) >= 2:
                try:
                    self._update_cooccurrence(scope)
                except Exception as e:
                    self.logger.error(f"Cooccurrence error: {e}")

    def _extract_emojis(self, text):
        found = []
        if HAS_EMOJI_LIB:
            for c in text:
                if c in emoji_lib.EMOJI_DATA and emoji_lib.EMOJI_DATA[c].get("status", 0) in (0, 1, 2):
                    found.append(c)
        else:
            emoji_pattern = re.compile(
                "["
                "\U0001F600-\U0001F64F"
                "\U0001F300-\U0001F5FF"
                "\U0001F680-\U0001F6FF"
                "\U0001F1E0-\U0001F1FF"
                "\U00002702-\U000027B0"
                "\U000024C2-\U0001F251"
                "\U0001f926-\U0001f937"
                "\u2640-\u2642"
                "\u2600-\u2B55"
                "]+",
                flags=re.UNICODE,
            )
            for m in emoji_pattern.finditer(text):
                found.append(m.group())
        return found

    def _extract_words(self, text):
        words = []
        cn_chars = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        for seg in cn_chars:
            for i in range(len(seg) - 1):
                words.append(seg[i : i + 2])
        en_words = re.findall(r"[a-zA-Z]{2,}", text)
        words.extend(w.lower() for w in en_words)
        return words

    def _persist_profile(self, uid, hour, msg_len, emojis, words, nickname, timestamp):
        timing_key = f"sonar:profile:{uid}:timing"
        timing = self.storage.get(timing_key, {})
        hour_str = str(hour)
        timing[hour_str] = timing.get(hour_str, 0) + 1
        self.storage.set(timing_key, timing)

        if emojis:
            emoji_key = f"sonar:profile:{uid}:emoji"
            emoji_data = self.storage.get(emoji_key, {})
            for e in emojis:
                emoji_data[e] = emoji_data.get(e, 0) + 1
            if len(emoji_data) > 500:
                sorted_items = sorted(emoji_data.items(), key=lambda x: x[1], reverse=True)
                emoji_data = dict(sorted_items[:200])
            self.storage.set(emoji_key, emoji_data)

        if words:
            vocab_key = f"sonar:profile:{uid}:vocab"
            vocab_data = self.storage.get(vocab_key, {})
            for w in words:
                vocab_data[w] = vocab_data.get(w, 0) + 1
            if len(vocab_data) > 200:
                sorted_items = sorted(vocab_data.items(), key=lambda x: x[1], reverse=True)
                vocab_data = dict(sorted_items[:100])
            self.storage.set(vocab_key, vocab_data)

        length_key = f"sonar:profile:{uid}:length"
        length_data = self.storage.get(length_key, {"total": 0, "count": 0})
        length_data["total"] += msg_len
        length_data["count"] += 1
        self.storage.set(length_key, length_data)

        info_key = f"sonar:profile:{uid}:info"
        info = self.storage.get(info_key, {})
        if not info.get("nickname") and nickname:
            info["nickname"] = nickname
        if not info.get("first_seen"):
            info["first_seen"] = timestamp
        self.storage.set(info_key, info)

    def _persist_presence(self, scope, uid):
        key = f"{scope}:presence:{uid}"
        current = self.storage.get(key, 0)
        self.storage.set(key, current + 1)

    def _persist_group_user(self, scope, uid, nickname, timestamp):
        users_key = f"{scope}:users"
        users = self.storage.get(users_key, {})
        for uid_key in list(users.keys()):
            if not isinstance(users[uid_key], dict):
                users[uid_key] = {"nickname": "", "first_seen": users[uid_key]}
        if uid not in users:
            users[uid] = {"nickname": nickname, "first_seen": timestamp}
        elif nickname and not users[uid].get("nickname"):
            users[uid]["nickname"] = nickname
        self.storage.set(users_key, users)

    def _persist_groups_list(self, uid, scope):
        groups_key = f"sonar:profile:{uid}:groups"
        groups = self.storage.get(groups_key, [])
        if scope not in groups:
            groups.append(scope)
            self.storage.set(groups_key, groups)

    def _persist_interact(self, scope, uid, mentions):
        interact_key = f"{scope}:interact:{uid}"
        interact_data = self.storage.get(interact_key, {})
        for mentioned_id in mentions:
            if mentioned_id and mentioned_id != uid:
                interact_data[mentioned_id] = interact_data.get(mentioned_id, 0) + 1
        self.storage.set(interact_key, interact_data)

    def _update_cooccurrence(self, scope):
        now = time.time()
        window = self.config.get("cooccur_window", 300)
        active = {}
        for uid, last_t in self._last_active.get(scope, {}).items():
            if now - last_t < window:
                active[uid] = last_t
        if len(active) < 2:
            return

        cooccur_key = f"{scope}:cooccur"
        cooccur = self.storage.get(cooccur_key, {})
        uids = list(active.keys())
        for i in range(len(uids)):
            for j in range(i + 1, len(uids)):
                pair = f"{uids[i]}|{uids[j]}"
                rpair = f"{uids[j]}|{uids[i]}"
                cooccur[pair] = cooccur.get(pair, 0) + 1
                cooccur[rpair] = cooccur.get(rpair, 0) + 1
        self.storage.set(cooccur_key, cooccur)

    def delete_user_data(self, scope, user_id):
        for suffix in ["presence", "interact"]:
            self.storage.delete(f"{scope}:{suffix}:{user_id}")

        users = self.storage.get(f"{scope}:users", {})
        users.pop(user_id, None)
        self.storage.set(f"{scope}:users", users)

        cooccur = self.storage.get(f"{scope}:cooccur", {})
        to_del = [k for k in cooccur if user_id in k.split("|")]
        for k in to_del:
            del cooccur[k]
        self.storage.set(f"{scope}:cooccur", cooccur)

        optout = self.storage.get(f"{scope}:optout", [])
        if user_id not in optout:
            optout.append(user_id)
        self.storage.set(f"{scope}:optout", optout)

        self.storage.delete(f"{scope}:cache")

        groups_key = f"sonar:profile:{user_id}:groups"
        groups = self.storage.get(groups_key, [])
        if scope in groups:
            groups.remove(scope)
            self.storage.set(groups_key, groups)

    def delete_global_data(self, user_id):
        groups = self.storage.get(f"sonar:profile:{user_id}:groups", [])
        for scope in groups:
            for suffix in ["presence", "interact"]:
                self.storage.delete(f"{scope}:{suffix}:{user_id}")

            users = self.storage.get(f"{scope}:users", {})
            users.pop(user_id, None)
            self.storage.set(f"{scope}:users", users)

            cooccur = self.storage.get(f"{scope}:cooccur", {})
            to_del = [k for k in cooccur if user_id in k.split("|")]
            for k in to_del:
                del cooccur[k]
            self.storage.set(f"{scope}:cooccur", cooccur)

            self.storage.delete(f"{scope}:cache")

        for suffix in ["timing", "emoji", "vocab", "length", "info", "groups"]:
            self.storage.delete(f"sonar:profile:{user_id}:{suffix}")

    def rejoin_user(self, scope, user_id):
        optout = self.storage.get(f"{scope}:optout", [])
        if user_id in optout:
            optout.remove(user_id)
        self.storage.set(f"{scope}:optout", optout)

    def get_all_scopes(self):
        all_keys = self.storage.keys()
        scopes = set()
        for k in all_keys:
            if k.startswith("sonar:") and k.endswith(":users"):
                parts = k.rsplit(":users", 1)[0]
                if parts.startswith("sonar:") and parts.count(":") >= 2:
                    rest = parts[6:]
                    scopes.add(rest)
        return scopes

    def _migrate_if_needed(self):
        version = self.storage.get("sonar:schema_version", 1)
        if version >= SCHEMA_VERSION:
            return

        self.logger.info("开始迁移旧数据到新架构...")
        try:
            self._migrate_v1_to_v2()
            self.storage.set("sonar:schema_version", SCHEMA_VERSION)
            self.logger.info("数据迁移完成")
        except Exception as e:
            self.logger.error(f"数据迁移失败: {e}")

    def _is_valid_emoji(self, char):
        if HAS_EMOJI_LIB:
            return char in emoji_lib.EMOJI_DATA and emoji_lib.EMOJI_DATA[char].get("status", 0) in (0, 1, 2)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001f926-\U0001f937"
            "\u2640-\u2642"
            "\u2600-\u2B55"
            "]+",
            flags=re.UNICODE,
        )
        return bool(emoji_pattern.fullmatch(char))

    def _migrate_v1_to_v2(self):
        all_keys = self.storage.keys()

        scopes = set()
        for k in all_keys:
            if k.startswith("sonar:") and k.endswith(":users"):
                parts = k.rsplit(":users", 1)[0]
                if parts.startswith("sonar:") and parts.count(":") >= 2:
                    scopes.add(parts)

        for scope in scopes:
            users = self.storage.get(f"{scope}:users", {})
            for uid in list(users.keys()):
                old_timing = self.storage.get(f"{scope}:timing:{uid}", {})
                if old_timing:
                    key = f"sonar:profile:{uid}:timing"
                    existing = self.storage.get(key, {})
                    for h, c in old_timing.items():
                        existing[h] = existing.get(h, 0) + c
                    self.storage.set(key, existing)

                old_emoji = self.storage.get(f"{scope}:emoji:{uid}", {})
                if old_emoji:
                    key = f"sonar:profile:{uid}:emoji"
                    existing = self.storage.get(key, {})
                    for e, c in old_emoji.items():
                        if self._is_valid_emoji(e):
                            existing[e] = existing.get(e, 0) + c
                    self.storage.set(key, existing)

                old_vocab = self.storage.get(f"{scope}:vocab:{uid}", {})
                if old_vocab:
                    key = f"sonar:profile:{uid}:vocab"
                    existing = self.storage.get(key, {})
                    for w, c in old_vocab.items():
                        existing[w] = existing.get(w, 0) + c
                    if len(existing) > 200:
                        top = sorted(existing.items(), key=lambda x: x[1], reverse=True)[:100]
                        existing = dict(top)
                    self.storage.set(key, existing)

                old_length = self.storage.get(f"{scope}:length:{uid}", {})
                if isinstance(old_length, dict) and old_length.get("count", 0) > 0:
                    key = f"sonar:profile:{uid}:length"
                    existing = self.storage.get(key, {"total": 0, "count": 0})
                    existing["total"] += old_length.get("total", 0)
                    existing["count"] += old_length.get("count", 0)
                    self.storage.set(key, existing)

                    self.storage.set(f"{scope}:presence:{uid}", old_length["count"])

                info_key = f"sonar:profile:{uid}:info"
                info = self.storage.get(info_key, {})
                user_data = users.get(uid, {})
                if isinstance(user_data, dict):
                    if not info.get("nickname") and user_data.get("nickname"):
                        info["nickname"] = user_data["nickname"]
                    if not info.get("first_seen") and user_data.get("first_seen"):
                        info["first_seen"] = user_data["first_seen"]
                if info:
                    self.storage.set(info_key, info)

                groups_key = f"sonar:profile:{uid}:groups"
                groups = self.storage.get(groups_key, [])
                if scope not in groups:
                    groups.append(scope)
                    self.storage.set(groups_key, groups)

        all_keys = self.storage.keys()
        for k in all_keys:
            if k.startswith("sonar:profile:") and k.endswith(":emoji"):
                data = self.storage.get(k, {})
                cleaned = {e: c for e, c in data.items() if self._is_valid_emoji(e)}
                if len(cleaned) != len(data):
                    self.storage.set(k, cleaned)

        for scope in scopes:
            users = self.storage.get(f"{scope}:users", {})
            for uid in list(users.keys()):
                for suffix in ["timing", "emoji", "vocab", "length"]:
                    self.storage.delete(f"{scope}:{suffix}:{uid}")
