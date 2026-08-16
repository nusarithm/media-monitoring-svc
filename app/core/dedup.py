"""Group syndicated re-runs of the same story.

One Antara or Reuters piece reappears across several portals with a near
identical headline, which inflates volume counts and fills a page with the
same story.

Token Jaccard, not SimHash: headlines are ~8 useful tokens, and at that
length one extra word ("Menkeu Purbaya: ..." vs "Purbaya: ...") flips enough
SimHash bits to miss the match, while a looser bit threshold starts merging
unrelated stories. Jaccard degrades predictably and the threshold means
something you can read off ("share 55% of their words").
"""
import re
from typing import Dict, List, Set

SIMILARITY_THRESHOLD = 0.55

_TOKEN = re.compile(r"[a-z0-9]+")

# Portal boilerplate that appears in headlines regardless of the story.
STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "pada", "ini", "itu",
    "akan", "jadi", "the", "a", "an", "of", "in", "to", "for", "on",
}


def tokens(title: str) -> Set[str]:
    return {t for t in _TOKEN.findall((title or "").lower()) if t not in STOPWORDS and len(t) > 2}


def similarity(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster(items: List[dict], key: str = "title") -> Dict[int, List[int]]:
    """Map each cluster leader's index to the indexes folded into it.

    Linear scan against existing leaders: a page holds tens of articles, so
    the O(n x leaders) cost is invisible and LSH would be machinery for
    nothing. An item with no usable title is always its own cluster - empty
    titles must never collapse into one another.
    """
    leaders: List[tuple] = []  # (index, token set)
    assignment: Dict[int, List[int]] = {}

    for idx, item in enumerate(items):
        item_tokens = tokens(item.get(key) or "")

        if item_tokens:
            best_leader, best_score = None, 0.0
            for leader_idx, leader_tokens in leaders:
                score = similarity(item_tokens, leader_tokens)
                if score > best_score:
                    best_leader, best_score = leader_idx, score
            if best_leader is not None and best_score >= SIMILARITY_THRESHOLD:
                assignment[best_leader].append(idx)
                continue

        assignment[idx] = []
        leaders.append((idx, item_tokens))

    return assignment
