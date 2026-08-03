import math
import time
from collections import defaultdict


class Analyzer:
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

    def _get_users(self, scope):
        return list(self.storage.get(f"{scope}:users", {}).keys())

    def _get_global_count(self, uid):
        length_data = self.storage.get(f"sonar:profile:{uid}:length", {"count": 0})
        return length_data.get("count", 0)

    def _get_presence(self, scope, uid):
        return self.storage.get(f"{scope}:presence:{uid}", 0)

    def _eligible_users(self, scope):
        users = self._get_users(scope)
        min_msg = self._min_messages()
        return [u for u in users if self._get_global_count(u) >= min_msg]

    def _get_profile_cached(self, uid, cache=None):
        if cache is not None and uid in cache:
            return cache[uid]
        prof = {
            "timing": self.storage.get(f"sonar:profile:{uid}:timing", {}),
            "emoji": self.storage.get(f"sonar:profile:{uid}:emoji", {}),
            "vocab": self.storage.get(f"sonar:profile:{uid}:vocab", {}),
            "length": self.storage.get(f"sonar:profile:{uid}:length", {"total": 0, "count": 0}),
        }
        if cache is not None:
            cache[uid] = prof
        return prof

    def _load_scope_snapshot(self, scope, profile_cache=None):
        users = list(self.storage.get(f"{scope}:users", {}).keys())
        profiles = {}
        interact = {}
        presence = {}
        for uid in users:
            profiles[uid] = self._get_profile_cached(uid, profile_cache)
            interact[uid] = self.storage.get(f"{scope}:interact:{uid}", {})
            presence[uid] = self.storage.get(f"{scope}:presence:{uid}", 0)
        cooccur = self.storage.get(f"{scope}:cooccur", {}) if users else {}
        return {
            "users": users,
            "profiles": profiles,
            "interact": interact,
            "presence": presence,
            "cooccur": cooccur,
        }

    def get_snapshot(self, scope):
        return self._load_scope_snapshot(scope)

    def _all_scopes(self):
        scopes = set()
        for k in self.storage.keys():
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
        if not dict_a or not dict_b:
            return 0.0
        all_keys = set(dict_a.keys()) | set(dict_b.keys())
        dot = sum(dict_a.get(k, 0) * dict_b.get(k, 0) for k in all_keys)
        norm_a = math.sqrt(sum(v ** 2 for v in dict_a.values()))
        norm_b = math.sqrt(sum(v ** 2 for v in dict_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def timing_similarity(self, scope_or_uid_a, uid_b, scope=None):
        if scope is not None:
            uid_a = scope_or_uid_a
        else:
            uid_a = scope_or_uid_a
        ta = self.storage.get(f"sonar:profile:{uid_a}:timing", {})
        tb = self.storage.get(f"sonar:profile:{uid_b}:timing", {})
        if not ta and not tb:
            return 0.5
        all_hours = set(range(24))
        vec_a = {h: ta.get(str(h), 0) for h in all_hours}
        vec_b = {h: tb.get(str(h), 0) for h in all_hours}
        return self.cosine_sim(vec_a, vec_b)

    def emoji_similarity(self, scope_or_uid_a, uid_b, scope=None):
        uid_a = scope_or_uid_a
        ea = self.storage.get(f"sonar:profile:{uid_a}:emoji", {})
        eb = self.storage.get(f"sonar:profile:{uid_b}:emoji", {})
        if not ea and not eb:
            return 0.5
        return self.cosine_sim(ea, eb)

    def vocab_similarity(self, scope_or_uid_a, uid_b, scope=None):
        uid_a = scope_or_uid_a
        va = self.storage.get(f"sonar:profile:{uid_a}:vocab", {})
        vb = self.storage.get(f"sonar:profile:{uid_b}:vocab", {})
        if not va and not vb:
            return 0.5
        return self.cosine_sim(va, vb)

    def interaction_score(self, scope, uid_a, uid_b, max_interact=100.0):
        ia = self.storage.get(f"{scope}:interact:{uid_a}", {})
        ib = self.storage.get(f"{scope}:interact:{uid_b}", {})
        a_to_b = ia.get(uid_b, 0)
        b_to_a = ib.get(uid_a, 0)
        total = a_to_b + b_to_a
        if total == 0:
            return 0.0
        return min(total / max_interact, 1.0)

    def cooccurrence_score(self, scope, uid_a, uid_b, max_cooccur=50.0):
        cooccur = self.storage.get(f"{scope}:cooccur", {})
        pair = f"{uid_a}|{uid_b}"
        val = cooccur.get(pair, 0)
        if val == 0:
            return 0.0
        return min(val / max_cooccur, 1.0)

    def _compute_max_interact(self, scope, users):
        max_val = 0
        for uid in users:
            interact = self.storage.get(f"{scope}:interact:{uid}", {})
            for count in interact.values():
                max_val = max(max_val, count)
        return max(max_val, 1.0)

    def _compute_max_cooccur(self, scope, users):
        cooccur = self.storage.get(f"{scope}:cooccur", {})
        max_val = 0
        for count in cooccur.values():
            max_val = max(max_val, count)
        return max(max_val, 1.0)

    def compute_pair_distance(self, scope, uid_a, uid_b, weights=None, max_interact=100.0, max_cooccur=50.0):
        if weights is None:
            weights = self._default_weights()

        scores = {
            "timing": self.timing_similarity(uid_a, uid_b),
            "emoji": self.emoji_similarity(uid_a, uid_b),
            "vocab": self.vocab_similarity(uid_a, uid_b),
            "interaction": self.interaction_score(scope, uid_a, uid_b, max_interact),
            "cooccurrence": self.cooccurrence_score(scope, uid_a, uid_b, max_cooccur),
        }

        total_w = sum(weights.values())
        distance = 0.0
        for dim, w in weights.items():
            nw = w / total_w if total_w > 0 else 0
            distance += nw * (1.0 - scores.get(dim, 0))

        return distance, scores

    def compute_distance_matrix(self, scope, force=False):
        cache_key = f"{scope}:cache"
        if not force:
            cached = self.storage.get(cache_key)
            if cached:
                interval = self.config.get("update_interval", 3600)
                if time.time() - cached.get("timestamp", 0) < interval:
                    return cached

        snap = self._load_scope_snapshot(scope)
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
        self.storage.set(cache_key, result)
        return result

    def detect_islands(self, scope, data=None, threshold=None):
        if threshold is None:
            threshold = self._distance_threshold()
        if data is None:
            data = self.compute_distance_matrix(scope)
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

    def find_parallel_universe(self, scope, user_id):
        profile_cache = {}
        local = None
        if scope:
            local = self._find_parallel_in_scope(scope, user_id, profile_cache)

        cross = []
        for other_scope in self._all_scopes():
            if other_scope == scope:
                continue
            match = self._find_parallel_in_scope(other_scope, user_id, profile_cache)
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

    def _find_parallel_in_scope(self, scope, user_id, profile_cache=None):
        snap = self._load_scope_snapshot(scope, profile_cache)
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

    def get_user_distances(self, scope, user_id):
        data = self.compute_distance_matrix(scope)
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

    def get_user_detail(self, scope_or_uid, uid=None):
        if uid is not None:
            scope = scope_or_uid
        else:
            scope = None
            uid = scope_or_uid

        timing = self.storage.get(f"sonar:profile:{uid}:timing", {})
        emoji = self.storage.get(f"sonar:profile:{uid}:emoji", {})
        vocab = self.storage.get(f"sonar:profile:{uid}:vocab", {})
        length = self.storage.get(f"sonar:profile:{uid}:length", {"total": 0, "count": 0})

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
            interact = self.storage.get(f"{scope}:interact:{uid}", {})
            result["interact_count"] = sum(interact.values())
            result["interact_targets"] = len(interact)
            result["presence"] = self._get_presence(scope, uid)
        else:
            groups = self.storage.get(f"sonar:profile:{uid}:groups", [])
            total_interact_count = 0
            total_interact_targets = set()
            for g_scope in groups:
                interact = self.storage.get(f"{g_scope}:interact:{uid}", {})
                total_interact_count += sum(interact.values())
                total_interact_targets.update(interact.keys())
            result["interact_count"] = total_interact_count
            result["interact_targets"] = len(total_interact_targets)
            result["presence"] = length.get("count", 0)
            result["groups_count"] = len(groups)

        return result

    def get_interact_detail(self, scope, uid_a, uid_b):
        ia = self.storage.get(f"{scope}:interact:{uid_a}", {})
        ib = self.storage.get(f"{scope}:interact:{uid_b}", {})
        a_to_b = ia.get(uid_b, 0)
        b_to_a = ib.get(uid_a, 0)

        timing_a = self.storage.get(f"sonar:profile:{uid_a}:timing", {})
        timing_b = self.storage.get(f"sonar:profile:{uid_b}:timing", {})
        overlap = [h for h in timing_a if h in timing_b and timing_a[h] > 0 and timing_b[h] > 0]
        overlap.sort()

        return {
            "a_to_b": a_to_b,
            "b_to_a": b_to_a,
            "reply_total": a_to_b + b_to_a,
            "shared_hours": overlap,
        }

    def get_cooccur_count(self, scope, uid_a, uid_b):
        cooccur = self.storage.get(f"{scope}:cooccur", {})
        return cooccur.get(f"{uid_a}|{uid_b}", 0)

    def get_user_groups(self, uid):
        return self.storage.get(f"sonar:profile:{uid}:groups", [])
