"""
社交距离分析器

基于用户特征向量（时段/表情/词汇）与互动数据（@、共现）计算用户间
加权距离，输出距离矩阵、岛屿群落（连通分量）、平行自我匹配与个人画像。
"""
import math
import time
from collections import defaultdict


class Analyzer:
    """距离矩阵、岛屿检测与用户画像计算。"""

    def __init__(self, sdk, config):
        self.sdk = sdk
        self.logger = sdk.logger.get_child("ChatSonar.Analyzer")
        self.storage = sdk.storage
        self.config = config

    def _default_weights(self):
        return self.config.get("weights", {
            "timing": 0.20,
            "emoji": 0.15,
            "vocab": 0.20,
            "interaction": 0.30,
            "cooccurrence": 0.15,
        })

    def _min_messages(self):
        return self.config.get("min_messages", 5)

    def _distance_threshold(self):
        return self.config.get("distance_threshold", 0.6)

    async def _get_users(self, scope):
        users = await self.storage.aget(f"{scope}:users", {})
        return list(users.keys())

    async def _get_global_count(self, uid):
        length_data = await self.storage.aget(f"sonar:profile:{uid}:length", {"count": 0})
        return length_data.get("count", 0)

    async def _get_presence(self, scope, uid):
        return await self.storage.aget(f"{scope}:presence:{uid}", 0)

    async def _eligible_users(self, scope):
        users = await self._get_users(scope)
        min_msg = self._min_messages()
        eligible = []
        for u in users:
            if await self._get_global_count(u) >= min_msg:
                eligible.append(u)
        return eligible

    async def _get_profile(self, uid):
        keys = [f"sonar:profile:{uid}:{suffix}" for suffix in ("timing", "emoji", "vocab", "length")]
        values = await self.storage.aget_multi(keys)
        return {
            "timing": values.get(keys[0], {}),
            "emoji": values.get(keys[1], {}),
            "vocab": values.get(keys[2], {}),
            "length": values.get(keys[3], {"total": 0, "count": 0}),
        }

    async def _load_scope_snapshot(self, scope, profile_cache=None):
        users = await self._get_users(scope)
        profiles = {}
        interact = {}
        presence = {}
        for uid in users:
            if profile_cache is not None and uid in profile_cache:
                profiles[uid] = profile_cache[uid]
            else:
                prof = await self._get_profile(uid)
                profiles[uid] = prof
                if profile_cache is not None:
                    profile_cache[uid] = prof
            interact[uid] = await self.storage.aget(f"{scope}:interact:{uid}", {})
            presence[uid] = await self.storage.aget(f"{scope}:presence:{uid}", 0)
        cooccur = await self.storage.aget(f"{scope}:cooccur", {}) if users else {}
        return {
            "users": users,
            "profiles": profiles,
            "interact": interact,
            "presence": presence,
            "cooccur": cooccur,
        }

    async def get_snapshot(self, scope):
        """
        返回指定 scope 的全量数据快照。

        :param scope: 数据范围标识（sonar:platform:group_id）
        :return: dict，含 users/profiles/interact/presence/cooccur
        """
        return await self._load_scope_snapshot(scope)

    async def _all_scopes(self):
        all_keys = await self.storage.aget_all_keys()
        scopes = set()
        for k in all_keys:
            if k.startswith("sonar:") and k.endswith(":users"):
                parts = k.rsplit(":users", 1)[0]
                if parts.startswith("sonar:") and parts.count(":") >= 2:
                    scopes.add(parts)
        return scopes

    @staticmethod
    def _cosine_or_neutral(a, b):
        if not a and not b:
            return 0.5
        return Analyzer.cosine_sim(a, b)

    @staticmethod
    def _behavior_sim(t, e, v):
        return t * 0.35 + e * 0.25 + v * 0.40

    def detail_from_snapshot(self, snap, uid):
        """
        从数据快照中提取用户画像，不产生存储读取。

        :param snap: get_snapshot 返回的快照 dict
        :param uid: 用户 ID
        :return: dict 用户画像，用户不在快照中时返回 None
        """
        prof = snap["profiles"].get(uid)
        if prof is None:
            return None
        timing = prof["timing"]
        emoji = prof["emoji"]
        vocab = prof["vocab"]
        length = prof["length"]
        active = sorted(timing.items(), key=lambda x: x[1], reverse=True)
        peak = [h for h, _ in active[:3]]
        count = length.get("count", 0)
        avg = round(length["total"] / count, 1) if count > 0 else 0
        interact = snap["interact"].get(uid, {})
        return {
            "message_count": count,
            "avg_length": avg,
            "peak_hours": peak,
            "top_emoji": sorted(emoji.items(), key=lambda x: x[1], reverse=True)[:5],
            "top_vocab": sorted(vocab.items(), key=lambda x: x[1], reverse=True)[:5],
            "interact_count": sum(interact.values()),
            "interact_targets": len(interact),
            "presence": snap["presence"].get(uid, 0),
        }

    @staticmethod
    def jaccard(set_a, set_b):
        """
        计算 Jaccard 相似度。

        :param set_a: 集合 A
        :param set_b: 集合 B
        :return: float 相似度（0.0 ~ 1.0）
        """
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        a = set(set_a)
        b = set(set_b)
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def cosine_sim(dict_a, dict_b):
        """
        计算稀疏向量的余弦相似度。

        :param dict_a: 稀疏向量 A（key -> count）
        :param dict_b: 稀疏向量 B（key -> count）
        :return: float 相似度（0.0 ~ 1.0）
        """
        if not dict_a or not dict_b:
            return 0.0
        all_keys = set(dict_a.keys()) | set(dict_b.keys())
        dot = sum(dict_a.get(k, 0) * dict_b.get(k, 0) for k in all_keys)
        norm_a = math.sqrt(sum(v ** 2 for v in dict_a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in dict_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def timing_similarity(self, uid_a, uid_b):
        ta = await self.storage.aget(f"sonar:profile:{uid_a}:timing", {})
        tb = await self.storage.aget(f"sonar:profile:{uid_b}:timing", {})
        if not ta and not tb:
            return 0.5
        all_hours = set(range(24))
        vec_a = {h: ta.get(str(h), 0) for h in all_hours}
        vec_b = {h: tb.get(str(h), 0) for h in all_hours}
        return self.cosine_sim(vec_a, vec_b)

    async def emoji_similarity(self, uid_a, uid_b):
        ea = await self.storage.aget(f"sonar:profile:{uid_a}:emoji", {})
        eb = await self.storage.aget(f"sonar:profile:{uid_b}:emoji", {})
        if not ea and not eb:
            return 0.5
        return self.cosine_sim(ea, eb)

    async def vocab_similarity(self, uid_a, uid_b):
        va = await self.storage.aget(f"sonar:profile:{uid_a}:vocab", {})
        vb = await self.storage.aget(f"sonar:profile:{uid_b}:vocab", {})
        if not va and not vb:
            return 0.5
        return self.cosine_sim(va, vb)

    async def interaction_score(self, scope, uid_a, uid_b, max_interact=100.0):
        ia = await self.storage.aget(f"{scope}:interact:{uid_a}", {})
        ib = await self.storage.aget(f"{scope}:interact:{uid_b}", {})
        a_to_b = ia.get(uid_b, 0)
        b_to_a = ib.get(uid_a, 0)
        total = a_to_b + b_to_a
        if total == 0:
            return 0.0
        return min(total / max_interact, 1.0)

    async def cooccurrence_score(self, scope, uid_a, uid_b, max_cooccur=50.0):
        cooccur = await self.storage.aget(f"{scope}:cooccur", {})
        pair = f"{uid_a}|{uid_b}"
        val = cooccur.get(pair, 0)
        if val == 0:
            return 0.0
        return min(val / max_cooccur, 1.0)

    async def compute_pair_distance(self, scope, uid_a, uid_b, weights=None, max_interact=100.0, max_cooccur=50.0):
        """
        计算两个用户在指定 scope 下的加权综合距离。

        :param scope: 数据范围标识
        :param uid_a: 用户 A ID
        :param uid_b: 用户 B ID
        :param weights: [dict] 各维度权重（默认: 配置 weights）
        :param max_interact: [float] 互动计分归一化上限 (默认: 100.0)
        :param max_cooccur: [float] 共现计分归一化上限 (默认: 50.0)
        :return: tuple(float 综合距离, dict 各维度得分)
        """
        if weights is None:
            weights = self._default_weights()

        scores = {
            "timing": await self.timing_similarity(uid_a, uid_b),
            "emoji": await self.emoji_similarity(uid_a, uid_b),
            "vocab": await self.vocab_similarity(uid_a, uid_b),
            "interaction": await self.interaction_score(scope, uid_a, uid_b, max_interact),
            "cooccurrence": await self.cooccurrence_score(scope, uid_a, uid_b, max_cooccur),
        }

        total_w = sum(weights.values())
        distance = 0.0
        for dim, w in weights.items():
            nw = w / total_w if total_w > 0 else 0
            distance += nw * (1.0 - scores.get(dim, 0))

        return distance, scores

    async def compute_distance_matrix(self, scope, force=False):
        """
        计算指定 scope 的全量距离矩阵，结果按 update_interval 缓存。

        :param scope: 数据范围标识
        :param force: [bool] 跳过缓存强制重算 (默认: False)
        :return: dict（timestamp/users/matrix/scores），活跃用户不足时返回 None
        """
        cache_key = f"{scope}:cache"
        if not force:
            cached = await self.storage.aget(cache_key)
            if cached:
                interval = self.config.get("update_interval", 3600)
                if time.time() - cached.get("timestamp", 0) < interval:
                    return cached

        snap = await self._load_scope_snapshot(scope)
        min_msg = self._min_messages()
        users = [u for u in snap["users"]
                 if snap["profiles"][u]["length"].get("count", 0) >= min_msg]
        if len(users) < 2:
            return None

        weights = self._default_weights()
        total_w = sum(weights.values()) or 1.0
        profiles = snap["profiles"]
        interact = snap["interact"]
        cooccur = snap["cooccur"]

        max_interact = 1.0
        for ia in interact.values():
            if ia:
                m = max(ia.values())
                if m > max_interact:
                    max_interact = m
        max_cooccur = max(max(cooccur.values(), default=0), 1)

        cos = self._cosine_or_neutral
        matrix = {}
        scores_map = {}
        nu = len(users)
        for i in range(nu):
            ua = users[i]
            pa = profiles[ua]
            ia = interact[ua]
            ta, ea, va = pa["timing"], pa["emoji"], pa["vocab"]
            for j in range(i + 1, nu):
                ub = users[j]
                pb = profiles[ub]
                scores = {
                    "timing": cos(ta, pb["timing"]),
                    "emoji": cos(ea, pb["emoji"]),
                    "vocab": cos(va, pb["vocab"]),
                }
                a_to_b = ia.get(ub, 0)
                b_to_a = interact[ub].get(ua, 0)
                ti = a_to_b + b_to_a
                scores["interaction"] = min(ti / max_interact, 1.0) if ti else 0.0
                co = cooccur.get(f"{ua}|{ub}", 0)
                scores["cooccurrence"] = min(co / max_cooccur, 1.0) if co else 0.0

                dist = 0.0
                for dim, w in weights.items():
                    dist += (w / total_w) * (1.0 - scores.get(dim, 0))
                key = f"{ua}|{ub}"
                matrix[key] = dist
                matrix[f"{ub}|{ua}"] = dist
                scores_map[key] = scores
                scores_map[f"{ub}|{ua}"] = scores

        result = {
            "timestamp": time.time(),
            "users": users,
            "matrix": matrix,
            "scores": scores_map,
        }
        await self.storage.aset(cache_key, result)
        return result

    async def detect_islands(self, scope, data=None, threshold=None):
        """
        以距离阈值做并查集连通分量检测，返回社交岛屿列表。

        :param scope: 数据范围标识
        :param data: [dict] 既有距离矩阵结果；None 时自行计算 (默认: None)
        :param threshold: [float] 连通距离阈值；None 时取配置 (默认: None)
        :return: list[dict]，每项含 members/avg_distance/size，按 size 降序
        """
        if threshold is None:
            threshold = self._distance_threshold()
        if data is None:
            data = await self.compute_distance_matrix(scope)
        if not data:
            return []

        users = data["users"]
        matrix = data["matrix"]

        parent = {u: u for u in users}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(len(users)):
            for j in range(i + 1, len(users)):
                key = f"{users[i]}|{users[j]}"
                dist = matrix.get(key, 1.0)
                if dist < threshold:
                    union(users[i], users[j])

        groups = defaultdict(list)
        for u in users:
            groups[find(u)].append(u)

        islands = []
        for root, members in groups.items():
            avg_dist = 0.0
            count = 0
            for mi in range(len(members)):
                for mj in range(mi + 1, len(members)):
                    key = f"{members[mi]}|{members[mj]}"
                    avg_dist += matrix.get(key, 1.0)
                    count += 1
            avg_dist = avg_dist / count if count > 0 else 0.0

            islands.append({
                "members": members,
                "avg_distance": round(avg_dist, 3),
                "size": len(members),
            })

        islands.sort(key=lambda x: x["size"], reverse=True)
        return islands

    async def find_parallel_universe(self, scope, user_id):
        """
        在本群与全部跨群范围中寻找与目标用户无互动且行为最相似的用户。

        :param scope: 当前数据范围标识；空值时仅做跨群匹配
        :param user_id: 用户 ID
        :return: dict，含 local（本群匹配或 None）与 cross_scope（最多 3 项列表）
        """
        profile_cache = {}
        local = None
        if scope:
            local = await self._find_parallel_in_scope(scope, user_id, profile_cache)

        cross = []
        for other_scope in await self._all_scopes():
            if other_scope == scope:
                continue
            match = await self._find_parallel_in_scope(other_scope, user_id, profile_cache)
            if match:
                match["scope"] = other_scope
                cross.append(match)

        seen = {}
        for item in cross:
            uid = item["user_id"]
            if uid not in seen or item["similarity"] > seen[uid]["similarity"]:
                seen[uid] = item
        top_cross = sorted(seen.values(), key=lambda x: x["similarity"], reverse=True)[:3]

        return {
            "local": local,
            "cross_scope": top_cross,
        }

    async def _find_parallel_in_scope(self, scope, user_id, profile_cache=None):
        snap = await self._load_scope_snapshot(scope, profile_cache)
        users = snap["users"]
        if user_id not in users:
            return None

        my_interact = snap["interact"].get(user_id, {})
        cooccur = snap["cooccur"]
        my_prof = snap["profiles"][user_id]
        my_timing = my_prof["timing"]
        my_emoji = my_prof["emoji"]
        my_vocab = my_prof["vocab"]
        cos = self._cosine_or_neutral

        best = None
        best_sim = -1.0
        for other in users:
            if other == user_id:
                continue
            if my_interact.get(other, 0) > 0:
                continue
            if snap["interact"].get(other, {}).get(user_id, 0) > 0:
                continue
            if (cooccur.get(f"{user_id}|{other}", 0) > 0
                    or cooccur.get(f"{other}|{user_id}", 0) > 0):
                continue

            op = snap["profiles"][other]
            t = cos(my_timing, op["timing"])
            e = cos(my_emoji, op["emoji"])
            v = cos(my_vocab, op["vocab"])
            sim = self._behavior_sim(t, e, v)

            if sim > best_sim:
                best_sim = sim
                best = {
                    "user_id": other,
                    "similarity": round(sim, 3),
                    "scores": {"timing": t, "emoji": e, "vocab": v},
                }

        return best

    async def get_user_distances(self, scope, user_id):
        """
        返回指定用户与本群全部其他用户的距离与得分。

        :param scope: 数据范围标识
        :param user_id: 用户 ID
        :return: dict（uid -> {distance, scores}），按距离升序；无数据时返回 None
        """
        data = await self.compute_distance_matrix(scope)
        if not data or user_id not in data["users"]:
            return None

        users = data["users"]
        matrix = data["matrix"]
        scores_map = data["scores"]

        distances = {}
        for other in users:
            if other == user_id:
                continue
            key = f"{user_id}|{other}"
            distances[other] = {
                "distance": round(matrix.get(key, 1.0), 3),
                "scores": scores_map.get(key, {}),
            }

        sorted_distances = dict(
            sorted(distances.items(), key=lambda x: x[1]["distance"])
        )
        return sorted_distances

    async def get_user_detail(self, scope_or_uid, uid=None):
        """
        返回用户画像详情；传入 scope 时附带该群互动统计，否则聚合全局群组。

        :param scope_or_uid: 数据范围标识（uid 为 None 时此参数作为用户 ID）
        :param uid: [str] 用户 ID (默认: None)
        :return: dict 用户画像，含 message_count/avg_length/peak_hours/top_emoji/top_vocab 等
        """
        if uid is not None:
            scope = scope_or_uid
        else:
            scope = None
            uid = scope_or_uid

        timing = await self.storage.aget(f"sonar:profile:{uid}:timing", {})
        emoji = await self.storage.aget(f"sonar:profile:{uid}:emoji", {})
        vocab = await self.storage.aget(f"sonar:profile:{uid}:vocab", {})
        length = await self.storage.aget(f"sonar:profile:{uid}:length", {"total": 0, "count": 0})

        active_hours = sorted(timing.items(), key=lambda x: x[1], reverse=True)
        peak_hours = [h for h, _ in active_hours[:3]] if active_hours else []

        top_emoji = sorted(emoji.items(), key=lambda x: x[1], reverse=True)[:5]
        top_vocab = sorted(vocab.items(), key=lambda x: x[1], reverse=True)[:5]

        avg_len = 0
        if length.get("count", 0) > 0:
            avg_len = round(length["total"] / length["count"], 1)

        result = {
            "message_count": length.get("count", 0),
            "avg_length": avg_len,
            "peak_hours": peak_hours,
            "top_emoji": top_emoji,
            "top_vocab": top_vocab,
        }

        if scope:
            interact = await self.storage.aget(f"{scope}:interact:{uid}", {})
            result["interact_count"] = sum(interact.values())
            result["interact_targets"] = len(interact)
            result["presence"] = await self._get_presence(scope, uid)
        else:
            groups = await self.storage.aget(f"sonar:profile:{uid}:groups", [])
            total_interact_count = 0
            total_interact_targets = set()
            for g_scope in groups:
                interact = await self.storage.aget(f"{g_scope}:interact:{uid}", {})
                total_interact_count += sum(interact.values())
                total_interact_targets.update(interact.keys())
            result["interact_count"] = total_interact_count
            result["interact_targets"] = len(total_interact_targets)
            result["presence"] = length.get("count", 0)
            result["groups_count"] = len(groups)

        return result

    async def get_interact_detail(self, scope, uid_a, uid_b):
        """
        返回两个用户的 @ 互动明细与共同活跃时段。

        :param scope: 数据范围标识
        :param uid_a: 用户 A ID
        :param uid_b: 用户 B ID
        :return: dict，含 a_to_b/b_to_a/reply_total/shared_hours
        """
        ia = await self.storage.aget(f"{scope}:interact:{uid_a}", {})
        ib = await self.storage.aget(f"{scope}:interact:{uid_b}", {})
        a_to_b = ia.get(uid_b, 0)
        b_to_a = ib.get(uid_a, 0)

        timing_a = await self.storage.aget(f"sonar:profile:{uid_a}:timing", {})
        timing_b = await self.storage.aget(f"sonar:profile:{uid_b}:timing", {})
        overlap = [h for h in timing_a if h in timing_b and timing_a[h] > 0 and timing_b[h] > 0]
        overlap.sort()

        return {
            "a_to_b": a_to_b,
            "b_to_a": b_to_a,
            "reply_total": a_to_b + b_to_a,
            "shared_hours": overlap,
        }

    async def get_cooccur_count(self, scope, uid_a, uid_b):
        """
        返回两个用户的共现次数。

        :param scope: 数据范围标识
        :param uid_a: 用户 A ID
        :param uid_b: 用户 B ID
        :return: int 共现次数
        """
        cooccur = await self.storage.aget(f"{scope}:cooccur", {})
        return cooccur.get(f"{uid_a}|{uid_b}", 0)

    async def get_user_groups(self, uid):
        """
        返回用户出现过的全部 scope 列表。

        :param uid: 用户 ID
        :return: list[str] scope 列表
        """
        return await self.storage.aget(f"sonar:profile:{uid}:groups", [])
