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


class Collector:
    def __init__(self, sdk, config):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar.Collector")
        self.storage = sdk.storage
        self.config = config
        self._last_active = {}

    async def start(self):
        pass

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

        group_id = event.get_group_id() if detail_type == "group" else f"dm_{event.get_user_id()}"
        if not group_id:
            return

        scope = self._scope(platform, group_id)
        user_id = event.get_user_id()
        if not user_id:
            return

        if self._is_optout(scope, user_id):
            return

        text = event.get_text() or ""
        msg_len = len(text)
        event_time = event.get_time()
        if event_time and event_time > 0:
            if event_time > 1e12:
                event_time = int(event_time / 1000)
            utc_offset = self.config.get("utc_offset", 8)
            hour = int((event_time / 3600 + utc_offset) % 24)
        else:
            hour = datetime.now().hour
        emojis = self._extract_emojis(text)
        words = self._extract_words(text)
        mentions = event.get_mentions() or []
        timestamp = time.time()
        nickname = event.get_user_nickname() or ""

        record = {
            "scope": scope,
            "user_id": user_id,
            "nickname": nickname,
            "hour": hour,
            "msg_len": msg_len,
            "emojis": emojis,
            "words": words,
            "mentions": mentions,
            "timestamp": timestamp,
        }

        try:
            self._persist(record)
        except Exception as e:
            self.logger.error(f"Persist error: {e}")

        self._last_active.setdefault(scope, {})
        self._last_active[scope][user_id] = time.time()
        if len(self._last_active.get(scope, {})) >= 2:
            try:
                self._update_cooccurrence(scope)
            except Exception as e:
                self.logger.error(f"Cooccurrence error: {e}")

    def _extract_emojis(self, text):
        found = []
        if HAS_EMOJI_LIB:
            found = [c for c in text if c in emoji_lib.EMOJI_DATA]
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
                "\U00010000-\U0010ffff"
                "\u2640-\u2642"
                "\u2600-\u2B55"
                "\u200d"
                "\u23cf"
                "\u23e9"
                "\u231a"
                "\ufe0f"
                "\u3030"
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

    def _persist(self, rec):
        scope = rec["scope"]
        uid = rec["user_id"]
        ts = rec["timestamp"]

        timing_key = f"{scope}:timing:{uid}"
        timing = self.storage.get(timing_key, {})
        hour_str = str(rec["hour"])
        timing[hour_str] = timing.get(hour_str, 0) + 1
        self.storage.set(timing_key, timing)

        if rec["emojis"]:
            emoji_key = f"{scope}:emoji:{uid}"
            emoji_data = self.storage.get(emoji_key, {})
            for e in rec["emojis"]:
                emoji_data[e] = emoji_data.get(e, 0) + 1
            self.storage.set(emoji_key, emoji_data)

        if rec["words"]:
            vocab_key = f"{scope}:vocab:{uid}"
            vocab_data = self.storage.get(vocab_key, {})
            for w in rec["words"]:
                vocab_data[w] = vocab_data.get(w, 0) + 1
            if len(vocab_data) > 200:
                sorted_items = sorted(vocab_data.items(), key=lambda x: x[1], reverse=True)
                vocab_data = dict(sorted_items[:100])
            self.storage.set(vocab_key, vocab_data)

        length_key = f"{scope}:length:{uid}"
        length_data = self.storage.get(length_key, {"total": 0, "count": 0})
        length_data["total"] += rec["msg_len"]
        length_data["count"] += 1
        self.storage.set(length_key, length_data)

        if rec["mentions"]:
            interact_key = f"{scope}:interact:{uid}"
            interact_data = self.storage.get(interact_key, {})
            for mentioned_id in rec["mentions"]:
                if mentioned_id and mentioned_id != uid:
                    interact_data[mentioned_id] = interact_data.get(mentioned_id, 0) + 1
            self.storage.set(interact_key, interact_data)

        users_key = f"{scope}:users"
        users = self.storage.get(users_key, {})
        for uid_key in list(users.keys()):
            if not isinstance(users[uid_key], dict):
                users[uid_key] = {"nickname": "", "first_seen": users[uid_key]}
        if uid not in users:
            users[uid] = {"nickname": rec.get("nickname", ""), "first_seen": ts}
        elif rec.get("nickname"):
            if not users[uid].get("nickname"):
                users[uid]["nickname"] = rec["nickname"]
        self.storage.set(users_key, users)

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
        suffixes = ["timing", "emoji", "vocab", "length", "interact"]
        for s in suffixes:
            self.storage.delete(f"{scope}:{s}:{user_id}")

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

        cache_key = f"{scope}:cache"
        self.storage.delete(cache_key)

    def rejoin_user(self, scope, user_id):
        optout = self.storage.get(f"{scope}:optout", [])
        if user_id in optout:
            optout.remove(user_id)
        self.storage.set(f"{scope}:optout", optout)

    def get_all_scopes(self):
        all_keys = self.storage.keys()
        scopes = set()
        for k in all_keys:
            if k.startswith("sonar:") and ":users" in k:
                parts = k.split(":")
                if len(parts) >= 3:
                    scopes.add(f"{parts[1]}:{parts[2]}")
        return scopes
