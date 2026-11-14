"""
消息采集器

从群聊/私聊消息中提取用户特征（时段、表情、词汇、消息长度、昵称）
与群级互动数据（@、共现、在场计数），写入存储；负责 v1→v2 数据迁移与用户退订。
"""
import re
import time
from datetime import datetime

try:
    import emoji as emoji_lib
    HAS_EMOJI_LIB = True
except ImportError:
    HAS_EMOJI_LIB = False


SCHEMA_VERSION = 2

_EMOJI_FALLBACK_PATTERN = (
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
    "]+"
)


class Collector:
    """消息特征与群级互动数据采集。"""

    _MAX_ACTIVE_USERS_PER_SCOPE = 200
    _EMOJI_KEEP_LIMIT = 500
    _EMOJI_TRIM_TO = 200
    _VOCAB_KEEP_LIMIT = 200
    _VOCAB_TRIM_TO = 100

    def __init__(self, sdk, config):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar.Collector")
        self.storage = sdk.storage
        self.config = config
        self._last_active = {}

    async def start(self):
        """
        启动采集器，执行数据迁移。

        :return: None
        """
        await self._migrate_if_needed()

    async def stop(self):
        """
        停止采集器。

        :return: None
        """
        self._last_active.clear()

    @staticmethod
    def _scope(platform, group_id):
        return f"sonar:{platform}:{group_id}"

    async def _is_optout(self, scope, user_id):
        optout = await self.storage.aget(f"{scope}:optout", [])
        return user_id in optout

    async def on_message(self, event):
        """
        处理一条消息事件，提取特征并持久化。

        :param event: 消息事件对象
        :return: None
        """
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
            if await self._is_optout(scope, user_id):
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
                await self._persist_presence(scope, user_id)
                await self._persist_group_user(scope, user_id, nickname, timestamp)
            return

        emojis = self._extract_emojis(text)
        words = self._extract_words(text)
        msg_len = len(text)
        mentions = event.get_mentions() or []

        await self._persist_profile(user_id, hour, msg_len, emojis, words, nickname, timestamp)

        if is_group and scope:
            await self._persist_presence(scope, user_id)
            await self._persist_group_user(scope, user_id, nickname, timestamp)
            await self._persist_groups_list(user_id, scope)

            if mentions:
                await self._persist_interact(scope, user_id, mentions)

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
                    await self._update_cooccurrence(scope)
                except Exception as e:
                    self.logger.error(f"Cooccurrence error: {e}")

    @staticmethod
    def _extract_emojis(text):
        found = []
        if HAS_EMOJI_LIB:
            for c in text:
                if c in emoji_lib.EMOJI_DATA and emoji_lib.EMOJI_DATA[c].get("status", 0) in (0, 1, 2):
                    found.append(c)
        else:
            emoji_pattern = re.compile(_EMOJI_FALLBACK_PATTERN, flags=re.UNICODE)
            for m in emoji_pattern.finditer(text):
                found.append(m.group())
        return found

    @staticmethod
    def _extract_words(text):
        words = []
        cn_chars = re.findall(r"[\u4e00-\u9fff]{2,}", text)
        for seg in cn_chars:
            for i in range(len(seg) - 1):
                words.append(seg[i : i + 2])
        en_words = re.findall(r"[a-zA-Z]{2,}", text)
        words.extend(w.lower() for w in en_words)
        return words

    async def _persist_profile(self, uid, hour, msg_len, emojis, words, nickname, timestamp):
        timing_key = f"sonar:profile:{uid}:timing"
        timing = await self.storage.aget(timing_key, {})
        hour_str = str(hour)
        timing[hour_str] = timing.get(hour_str, 0) + 1
        await self.storage.aset(timing_key, timing)

        if emojis:
            emoji_key = f"sonar:profile:{uid}:emoji"
            emoji_data = await self.storage.aget(emoji_key, {})
            for e in emojis:
                emoji_data[e] = emoji_data.get(e, 0) + 1
            if len(emoji_data) > self._EMOJI_KEEP_LIMIT:
                sorted_items = sorted(emoji_data.items(), key=lambda x: x[1], reverse=True)
                emoji_data = dict(sorted_items[:self._EMOJI_TRIM_TO])
            await self.storage.aset(emoji_key, emoji_data)

        if words:
            vocab_key = f"sonar:profile:{uid}:vocab"
            vocab_data = await self.storage.aget(vocab_key, {})
            for w in words:
                vocab_data[w] = vocab_data.get(w, 0) + 1
            if len(vocab_data) > self._VOCAB_KEEP_LIMIT:
                sorted_items = sorted(vocab_data.items(), key=lambda x: x[1], reverse=True)
                vocab_data = dict(sorted_items[:self._VOCAB_TRIM_TO])
            await self.storage.aset(vocab_key, vocab_data)

        length_key = f"sonar:profile:{uid}:length"
        length_data = await self.storage.aget(length_key, {"total": 0, "count": 0})
        length_data["total"] += msg_len
        length_data["count"] += 1
        await self.storage.aset(length_key, length_data)

        info_key = f"sonar:profile:{uid}:info"
        info = await self.storage.aget(info_key, {})
        if not info.get("nickname") and nickname:
            info["nickname"] = nickname
        if not info.get("first_seen"):
            info["first_seen"] = timestamp
        await self.storage.aset(info_key, info)

    async def _persist_presence(self, scope, uid):
        key = f"{scope}:presence:{uid}"
        current = await self.storage.aget(key, 0)
        await self.storage.aset(key, current + 1)

    async def _persist_group_user(self, scope, uid, nickname, timestamp):
        users_key = f"{scope}:users"
        users = await self.storage.aget(users_key, {})
        for uid_key in list(users.keys()):
            if not isinstance(users[uid_key], dict):
                users[uid_key] = {"nickname": "", "first_seen": users[uid_key]}
        if uid not in users:
            users[uid] = {"nickname": nickname, "first_seen": timestamp}
        elif nickname and not users[uid].get("nickname"):
            users[uid]["nickname"] = nickname
        await self.storage.aset(users_key, users)

    async def _persist_groups_list(self, uid, scope):
        groups_key = f"sonar:profile:{uid}:groups"
        groups = await self.storage.aget(groups_key, [])
        if scope not in groups:
            groups.append(scope)
            await self.storage.aset(groups_key, groups)

    async def _persist_interact(self, scope, uid, mentions):
        interact_key = f"{scope}:interact:{uid}"
        interact_data = await self.storage.aget(interact_key, {})
        for mentioned_id in mentions:
            if mentioned_id and mentioned_id != uid:
                interact_data[mentioned_id] = interact_data.get(mentioned_id, 0) + 1
        await self.storage.aset(interact_key, interact_data)

    async def _update_cooccurrence(self, scope):
        now = time.time()
        window = self.config.get("cooccur_window", 300)
        active = {}
        for uid, last_t in self._last_active.get(scope, {}).items():
            if now - last_t < window:
                active[uid] = last_t
        if len(active) < 2:
            return

        cooccur_key = f"{scope}:cooccur"
        cooccur = await self.storage.aget(cooccur_key, {})
        uids = list(active.keys())
        for i in range(len(uids)):
            for j in range(i + 1, len(uids)):
                pair = f"{uids[i]}|{uids[j]}"
                rpair = f"{uids[j]}|{uids[i]}"
                cooccur[pair] = cooccur.get(pair, 0) + 1
                cooccur[rpair] = cooccur.get(rpair, 0) + 1
        await self.storage.aset(cooccur_key, cooccur)

    async def delete_user_data(self, scope, user_id):
        """
        删除用户在指定 scope 的群级数据并加入退订名单。

        :param scope: 数据范围标识（sonar:platform:group_id）
        :param user_id: 用户 ID
        :return: None
        """
        await self.storage.adelete_multi([f"{scope}:presence:{user_id}", f"{scope}:interact:{user_id}"])

        users = await self.storage.aget(f"{scope}:users", {})
        users.pop(user_id, None)
        await self.storage.aset(f"{scope}:users", users)

        cooccur = await self.storage.aget(f"{scope}:cooccur", {})
        to_del = [k for k in cooccur if user_id in k.split("|")]
        for k in to_del:
            del cooccur[k]
        await self.storage.aset(f"{scope}:cooccur", cooccur)

        optout = await self.storage.aget(f"{scope}:optout", [])
        if user_id not in optout:
            optout.append(user_id)
        await self.storage.aset(f"{scope}:optout", optout)

        await self.storage.adelete(f"{scope}:cache")

        groups_key = f"sonar:profile:{user_id}:groups"
        groups = await self.storage.aget(groups_key, [])
        if scope in groups:
            groups.remove(scope)
            await self.storage.aset(groups_key, groups)

    async def delete_global_data(self, user_id):
        """
        删除用户的全部数据（含全局画像）。

        :param user_id: 用户 ID
        :return: None
        """
        groups = await self.storage.aget(f"sonar:profile:{user_id}:groups", [])
        for scope in groups:
            await self.storage.adelete_multi(
                [f"{scope}:presence:{user_id}", f"{scope}:interact:{user_id}"])

            users = await self.storage.aget(f"{scope}:users", {})
            users.pop(user_id, None)
            await self.storage.aset(f"{scope}:users", users)

            cooccur = await self.storage.aget(f"{scope}:cooccur", {})
            to_del = [k for k in cooccur if user_id in k.split("|")]
            for k in to_del:
                del cooccur[k]
            await self.storage.aset(f"{scope}:cooccur", cooccur)

            await self.storage.adelete(f"{scope}:cache")

        await self.storage.adelete_multi(
            [f"sonar:profile:{user_id}:{suffix}"
             for suffix in ["timing", "emoji", "vocab", "length", "info", "groups"]])

    async def rejoin_user(self, scope, user_id):
        """
        将用户移出退订名单。

        :param scope: 数据范围标识
        :param user_id: 用户 ID
        :return: None
        """
        optout = await self.storage.aget(f"{scope}:optout", [])
        if user_id in optout:
            optout.remove(user_id)
        await self.storage.aset(f"{scope}:optout", optout)

    async def get_all_scopes(self):
        """
        返回所有已采集的 scope 标识。

        :return: set[str]，scope 集合
        """
        all_keys = await self.storage.aget_all_keys()
        scopes = set()
        for k in all_keys:
            if k.startswith("sonar:") and k.endswith(":users"):
                parts = k.rsplit(":users", 1)[0]
                if parts.startswith("sonar:") and parts.count(":") >= 2:
                    rest = parts[6:]
                    scopes.add(rest)
        return scopes

    async def _migrate_if_needed(self):
        version = await self.storage.aget("sonar:schema_version", 1)
        if version >= SCHEMA_VERSION:
            return

        self.logger.info("开始迁移旧数据到新架构...")
        try:
            await self._migrate_v1_to_v2()
            await self.storage.aset("sonar:schema_version", SCHEMA_VERSION)
            self.logger.info("数据迁移完成")
        except Exception as e:
            self.logger.error(f"数据迁移失败: {e}")

    @staticmethod
    def _is_valid_emoji(char):
        if HAS_EMOJI_LIB:
            return char in emoji_lib.EMOJI_DATA and emoji_lib.EMOJI_DATA[char].get("status", 0) in (0, 1, 2)
        emoji_pattern = re.compile(_EMOJI_FALLBACK_PATTERN, flags=re.UNICODE)
        return bool(emoji_pattern.fullmatch(char))

    async def _migrate_v1_to_v2(self):
        all_keys = await self.storage.aget_all_keys()

        scopes = set()
        for k in all_keys:
            if k.startswith("sonar:") and k.endswith(":users"):
                parts = k.rsplit(":users", 1)[0]
                if parts.startswith("sonar:") and parts.count(":") >= 2:
                    scopes.add(parts)

        for scope in scopes:
            users = await self.storage.aget(f"{scope}:users", {})
            for uid in list(users.keys()):
                old_timing = await self.storage.aget(f"{scope}:timing:{uid}", {})
                if old_timing:
                    key = f"sonar:profile:{uid}:timing"
                    existing = await self.storage.aget(key, {})
                    for h, c in old_timing.items():
                        existing[h] = existing.get(h, 0) + c
                    await self.storage.aset(key, existing)

                old_emoji = await self.storage.aget(f"{scope}:emoji:{uid}", {})
                if old_emoji:
                    key = f"sonar:profile:{uid}:emoji"
                    existing = await self.storage.aget(key, {})
                    for e, c in old_emoji.items():
                        if self._is_valid_emoji(e):
                            existing[e] = existing.get(e, 0) + c
                    await self.storage.aset(key, existing)

                old_vocab = await self.storage.aget(f"{scope}:vocab:{uid}", {})
                if old_vocab:
                    key = f"sonar:profile:{uid}:vocab"
                    existing = await self.storage.aget(key, {})
                    for w, c in old_vocab.items():
                        existing[w] = existing.get(w, 0) + c
                    if len(existing) > self._VOCAB_KEEP_LIMIT:
                        top = sorted(existing.items(), key=lambda x: x[1], reverse=True)[:self._VOCAB_TRIM_TO]
                        existing = dict(top)
                    await self.storage.aset(key, existing)

                old_length = await self.storage.aget(f"{scope}:length:{uid}", {})
                if isinstance(old_length, dict) and old_length.get("count", 0) > 0:
                    key = f"sonar:profile:{uid}:length"
                    existing = await self.storage.aget(key, {"total": 0, "count": 0})
                    existing["total"] += old_length.get("total", 0)
                    existing["count"] += old_length.get("count", 0)
                    await self.storage.aset(key, existing)

                    await self.storage.aset(f"{scope}:presence:{uid}", old_length["count"])

                info_key = f"sonar:profile:{uid}:info"
                info = await self.storage.aget(info_key, {})
                user_data = users.get(uid, {})
                if isinstance(user_data, dict):
                    if not info.get("nickname") and user_data.get("nickname"):
                        info["nickname"] = user_data["nickname"]
                    if not info.get("first_seen") and user_data.get("first_seen"):
                        info["first_seen"] = user_data["first_seen"]
                if info:
                    await self.storage.aset(info_key, info)

                groups_key = f"sonar:profile:{uid}:groups"
                groups = await self.storage.aget(groups_key, [])
                if scope not in groups:
                    groups.append(scope)
                    await self.storage.aset(groups_key, groups)

        all_keys = await self.storage.aget_all_keys()
        for k in all_keys:
            if k.startswith("sonar:profile:") and k.endswith(":emoji"):
                data = await self.storage.aget(k, {})
                cleaned = {e: c for e, c in data.items() if self._is_valid_emoji(e)}
                if len(cleaned) != len(data):
                    await self.storage.aset(k, cleaned)

        for scope in scopes:
            users = await self.storage.aget(f"{scope}:users", {})
            for uid in list(users.keys()):
                await self.storage.adelete_multi(
                    [f"{scope}:{suffix}:{uid}" for suffix in ["timing", "emoji", "vocab", "length"]])
