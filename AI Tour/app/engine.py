"""Content-based TF-IDF recommender; never invents artifacts, facts or coordinates."""
import math
import re
import unicodedata
from collections import Counter
from .schemas import Candidate, PlanRequest, PlanResult, Stop

STOP_WORDS = set("va la cua nhung mot cac cho toi muon xem ve tai voi trong duoc co tu theo nay nhu de nao cai di tim hieu".split())
ALIASES = {
    "gom su": "gom su dat nung hoa nau men gom", "nghe thuat": "dieu khac hoa van tuong trang tri",
    "lich su": "lich su dong son trieu thoi co vat", "van hoa": "van hoa tin nguong nghi le am nhac",
    "khoa hoc": "ky thuat che tac duc may cong nghe",
    "do dong": "dong thau trong dong thap dong den dong tuong dong",
}
HEADER_CONCEPTS = {
    "gom su": ("gom", "dat nung", "hoa nau", "men gom", "bat men"),
    "do dong": ("dong thau", "trong dong", "thap dong", "den dong", "tuong dong", "chuong dong"),
    "nghe thuat": ("dieu khac", "tuong", "cham khac", "hoa van", "nghe thuat"),
    "lich su": ("lich su", "thoi", "trieu", "van hoa"),
    "van hoa": ("van hoa", "tin nguong", "le hoi", "nhac cu", "nghi le"),
    "khoa hoc": ("ky thuat", "cong nghe", "may", "che tac"),
}


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower().replace("đ", "d")) if unicodedata.category(c) != "Mn")


def tokens(text: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", normalize(text)) if w not in STOP_WORDS]
    return words + [a + "_" + b for a, b in zip(words, words[1:])]


def walk_minutes(previous: Candidate | None, current: Candidate) -> float:
    if previous is None:
        return 2.0  # Orientation allowance, not measured indoor travel time.
    if previous.gallery_id is not None and previous.gallery_id == current.gallery_id:
        return 0.5
    if previous.floor_id is not None and current.floor_id is not None and previous.floor_id != current.floor_id:
        return 4.0
    return 2.0


def recommend(request: PlanRequest) -> PlanResult:
    candidates = sorted(request.candidates, key=lambda c: c.artifact_id)
    # Titles and curated topics carry more weight than long narrative descriptions.
    documents = [Counter(tokens(" ".join([c.name] * 3 + [c.title] * 2 + c.topics * 4 + [c.description]))) for c in candidates]
    headings = [Counter(tokens(" ".join([c.name, c.title, *c.topics]))) for c in candidates]
    df = Counter(t for doc in documents for t in doc)
    idf = {t: math.log((1 + len(documents)) / (1 + count)) + 1 for t, count in df.items()}

    def vector(doc):
        v = {t: (1 + math.log(n)) * idf.get(t, math.log(1 + len(documents)) + 1) for t, n in doc.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1
        return {t: x / norm for t, x in v.items()}

    vectors = [vector(doc) for doc in documents]
    heading_vectors = [vector(doc) for doc in headings]
    query_vectors = []
    query_evidence = []
    for interest in request.interests:
        expanded = normalize(interest)
        expanded += " " + " ".join(v for k, v in ALIASES.items() if k in expanded)
        query_vectors.append(vector(Counter(tokens(expanded))))
        query_evidence.append((set(t for t in tokens(interest) if "_" not in t), any(k in normalize(interest) for k in ALIASES)))
    ranked = []
    for c, v, heading, document in zip(candidates, vectors, heading_vectors, documents):
        heading_text = " " + " ".join(re.findall(r"[a-z0-9]+", normalize(" ".join([c.name, c.title, *c.topics])))) + " "
        matches = []
        scores = []
        for interest, query, (original, known_alias) in zip(request.interests, query_vectors, query_evidence):
            score = sum(weight * (0.8 * heading.get(t, 0) + 0.2 * v.get(t, 0)) for t, weight in query.items())
            exact_topic = any(normalize(interest) in normalize(topic) or normalize(topic) in normalize(interest) for topic in c.topics)
            concept_match = any(label in normalize(interest) and any(" " + phrase + " " in heading_text for phrase in phrases)
                                for label, phrases in HEADER_CONCEPTS.items())
            score += 0.5 if concept_match else 0.0
            score += 1.0 if exact_topic else 0.0
            evidence = exact_topic or known_alias or len(original.intersection(document)) >= min(2, len(original))
            if score >= 0.08 and evidence:
                matches.append(interest)
            scores.append(score)
        ranked.append((c, max(scores, default=0), matches))
    fallback = not any(matches for _, _, matches in ranked)
    remaining = [r for r in ranked if fallback or r[2]]
    selected = []
    elapsed = 0.0
    previous = None
    while remaining and len(selected) < request.max_stops:
        feasible = [r for r in remaining if elapsed + r[0].visit_minutes + walk_minutes(previous, r[0]) <= request.available_minutes]
        if not feasible:
            break
        # Greedy relevance / time selection favors staying in the same room/floor.
        choice = max(feasible, key=lambda r: ((1 + r[1]) / (r[0].visit_minutes + walk_minutes(previous, r[0])), r[1], -r[0].artifact_id))
        c, score, matches = choice
        walking = walk_minutes(previous, c)
        reason = ("Phù hợp sở thích: " + ", ".join(matches) + ".") if matches else "Điểm khám phá thay thế vì chưa tìm thấy nội dung khớp sở thích."
        if previous is not None and c.gallery_id is not None and c.gallery_id == previous.gallery_id:
            reason += " Cùng phòng với điểm trước để hạn chế đi vòng."
        selected.append(Stop(artifact_id=c.artifact_id, content_version_id=c.content_version_id,
                             visit_minutes=c.visit_minutes, walk_minutes=walking, score=round(score, 5),
                             matched_interests=matches, reason=reason))
        elapsed += c.visit_minutes + walking
        previous = c
        remaining.remove(choice)
    notice = "Thời gian gồm tham quan và di chuyển ước tính theo phòng/tầng; chưa phải thời gian dẫn đường đo thực tế."
    if fallback:
        notice = "Chưa có nội dung khớp sở thích; đây là hành trình thay thế. " + notice
    if not selected:
        notice = "Thời gian hiện tại chưa đủ cho một điểm dừng. Hãy tăng thời gian hoặc đổi bảo tàng."
    return PlanResult(estimated_minutes=round(elapsed, 2), used_fallback=fallback, notice=notice, stops=selected)
