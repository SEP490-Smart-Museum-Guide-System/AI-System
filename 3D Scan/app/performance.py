"""Explicit CPU quality budgets and candidate pairs for ordered capture loops."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Quality:
    resolution_level: int
    min_resolution: int
    refine: bool
    texture_size: int


PRESETS = {
    'detailed': Quality(0, 640, True, 4096),
    'balanced': Quality(1, 320, True, 4096),
    'preview': Quality(2, 256, False, 2048),
}
CAPTURE_ORDERS = {'unordered', 'ordered'}


def settings(quality='detailed', capture_order='unordered'):
    # Missing options in an already persisted job keep its original quality.
    if quality not in PRESETS or capture_order not in CAPTURE_ORDERS:
        raise ValueError('Invalid scan quality or capture order')
    return {**asdict(PRESETS[quality]), 'quality': quality, 'capture_order': capture_order}


def ordered_pairs(names, overlap=8, anchor_count=12):
    """Nearby views, loop closure and global anchors across multiple capture rings.

    The caller must supply capture order, not arbitrary filesystem order. Every
    photograph is retained. Geometric matching still verifies each candidate.
    """
    if len(names) != len(set(names)) or any(any(c.isspace() for c in n) for n in names):
        raise ValueError('Pair names must be unique and contain no whitespace')
    count = len(names)
    if count < 2:
        return []
    pairs = set()
    anchors = {i * count // min(anchor_count, count) for i in range(min(anchor_count, count))}
    for i in range(count):
        candidates = {(i + step) % count for step in range(1, min(overlap, count-1) + 1)} | anchors
        for j in candidates:
            if i != j:
                pairs.add(tuple(sorted((i, j))))
    return [(names[i], names[j]) for i, j in sorted(pairs)]
