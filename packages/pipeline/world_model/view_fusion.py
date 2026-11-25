"""Fusing the observations of a surface_atlas: one colour per texel from many photos.

    fuse           weighted median over the photos, or the best view where only a few saw the texel
    exposure_gains one brightness gain per photo, from what the photos agree on
    view_agreement / view_clusters   which photos show the same version of the street (eras of signs)
    smooth_labels / fuse_by_face     one photo per patch, neighbours agreeing
    TopK           the k heaviest observations per texel, for a mosaic too large to stack

Split from surface_atlas.py, which re-exports these names."""
import numpy as np
def fuse(colours, weights, few=3):
    """One colour per texel from (views, n, 3) and (views, n): the median where `few` or more views saw the
    texel, the sharpest view otherwise. Also returns how many views saw each texel."""
    seen = weights > 0
    count = seen.sum(axis=0)
    out = np.full(colours.shape[1:], np.nan, np.float32)
    idx = np.flatnonzero(count > 0)                         # most of an atlas is empty: work on what was seen
    if len(idx) == 0:
        return out, count
    col, w, n = colours[:, idx], weights[:, idx], count[idx]
    best = np.take_along_axis(col, w.argmax(axis=0)[None, :, None], axis=0)[0]
    stack = np.sort(np.where((w > 0)[..., None], col, np.nan), axis=0)       # NaN sorts last
    lo, hi = ((n - 1) // 2)[None, :, None], (n // 2)[None, :, None]
    median = (np.take_along_axis(stack, lo, axis=0)[0] + np.take_along_axis(stack, hi, axis=0)[0]) / 2
    out[idx] = np.where((n >= few)[:, None], median, best)
    return out, count


def exposure_gains(colours, weights, views, few=3, limit=(0.6, 1.6)):
    """One brightness gain per view, bringing each photo to what the photos agree on.

    The gain is the median, over the texels `few` or more photos saw, of (median luminance / this photo's
    luminance), clipped to `limit`: enough to even out exposure and haze between photos of the same kind of
    light, not enough to turn a night photo into a day one. Views nobody can be compared with keep 1.0.
    """
    lum = np.array([0.2126, 0.7152, 0.0722], np.float32)
    median, count = fuse(colours, weights, few=few)
    ref = median @ lum
    gains = np.ones(int(views.max()) + 1 if views.size else 0)
    ratios = [[] for _ in gains]
    for k in range(len(weights)):
        mine = colours[k] @ lum
        ok = (weights[k] > 0) & (count >= few) & (mine > 8) & (ref > 8)
        order = np.argsort(views[k][ok], kind="stable")
        v, r = views[k][ok][order], (ref[ok] / mine[ok])[order]
        cuts = np.flatnonzero(np.diff(v)) + 1
        for part_v, part_r in zip(np.split(v, cuts), np.split(r, cuts)):
            if len(part_v):
                ratios[int(part_v[0])].append(part_r)
    for i, parts in enumerate(ratios):
        if parts:
            gains[i] = float(np.clip(np.median(np.concatenate(parts)), *limit))
    return gains


def view_agreement(colours, weights, views, close=25.0, sample=200000, seed=0):
    """How alike each pair of photos is where both saw the same texel.

    Returns (share, pairs): share[i, j] is the fraction of the texels both kept where their colours are within
    `close` (mean absolute difference, 0..255), pairs[i, j] how many texels that was. A fraction rather than a
    mean distance: a video screen or one replaced billboard should not make two photos of the same year look
    like strangers.
    """
    n_views = int(views.max()) + 1
    cols = np.arange(weights.shape[1])
    if len(cols) > sample:
        cols = np.random.default_rng(seed).choice(len(cols), sample, replace=False)
    c, w, v = colours[:, cols], weights[:, cols], views[:, cols]
    near, pairs = np.zeros((n_views, n_views)), np.zeros((n_views, n_views))
    for a in range(len(w)):
        for b in range(a + 1, len(w)):
            both = (w[a] > 0) & (w[b] > 0)
            ok = np.abs(c[a][both] - c[b][both]).mean(axis=1) < close
            for i, j in ((v[a][both], v[b][both]), (v[b][both], v[a][both])):
                np.add.at(near, (i, j), ok)
                np.add.at(pairs, (i, j), 1)
    return near / np.maximum(pairs, 1), pairs


def view_clusters(share, pairs, k=2, enough=300):
    """Photos grouped into k sets that look alike (average linkage on 1 - share): the eras of a facade.

    Pairs that share fewer than `enough` texels say nothing and take the mean of the rest. Returns a label per
    view, 0 for the largest set.
    """
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import squareform
    known = pairs >= enough
    np.fill_diagonal(known, False)
    d = np.where(known, 1 - share, (1 - share)[known].mean() if known.any() else 0.5)
    np.fill_diagonal(d, 0)
    d = (d + d.T) / 2
    if len(d) <= k:
        return np.zeros(len(d), int)
    raw = fcluster(linkage(squareform(d, checks=False), "average"), k, "maxclust")
    order = np.argsort(-np.bincount(raw))
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    return rank[raw]


def smooth_labels(score, pairs, strength=0.7, rounds=6):
    """One view per group, preferring the view the neighbouring groups took.

    score (groups, views) >= 0; pairs (m, 2) are neighbouring groups. Each group starts on its best view and is
    then revisited: a view's worth is log(score / the group's best) + strength x (neighbours on that view), so at
    0.7 a view half as good wins when one more neighbour uses it. Fewer seams, and a sign or a video screen that
    changed between photos comes from one photo instead of a mosaic of several. Views with no score are never taken.
    """
    top = score.max(axis=1, keepdims=True)
    worth = np.where(score > 0, np.log(np.maximum(score, 1e-30) / np.maximum(top, 1e-30)), -np.inf)
    label = worth.argmax(axis=1)
    pairs = np.asarray(pairs, int).reshape(-1, 2)
    if len(pairs) == 0:
        return label
    both = np.concatenate([pairs, pairs[:, ::-1]])
    pull = np.broadcast_to(np.asarray(strength, float), (len(pairs),))   # one strength, or one per pair
    pull = np.concatenate([pull, pull])
    half = np.arange(len(score)) % 2 == 0
    still = 0
    for r in range(2 * rounds):
        votes = np.zeros_like(score, dtype=float)
        np.add.at(votes, (both[:, 0], label[both[:, 1]]), pull)
        # half of the groups move at a time: when all move at once, two neighbours swap views for ever
        turn = half if r % 2 == 0 else ~half
        new = np.where(turn, (worth + votes).argmax(axis=1), label)
        still = still + 1 if (new == label).all() else 0
        label = new
        if still == 2:
            break
    return label


def fuse_by_face(colours, weights, views, face_of, cap=400.0, agree=None, few=3, pairs=None, strength=0.7,
                 changing=None, hold=8.0):
    """One colour per texel, taking each face (or patch of one: `face_of` is any grouping) from as few photos
    as possible.

    A median over photos of different years and standing points blurs what does not sit exactly on the model's
    plane (signs, sashes, anything the coarse model flattens). Here each group ranks the photos by how much of it
    they saw (the sum of their weights, each capped at `cap` pixels per square metre: detail finer than the atlas
    earns nothing), and every texel takes the best-ranked photo among those kept for it.

    `agree` (a colour distance, 0..255) makes the rank also depend on the other photos: a photo's score on a
    group is multiplied by exp(-d / agree), d being its mean distance from the per-texel median where `few` or
    more photos saw the texel. The median is blurred but it is what most photos agree on, so the photo with a
    passer-by, a bus, a different season's sign or a wrong pose on that patch loses to one without.
    `pairs` (neighbouring groups) smooths the choice across groups, see smooth_labels.
    `changing` (a colour distance; needs `agree`) marks the groups whose photos disagree with each other by more
    than that on average: a video screen, a billboard that was replaced. There the median means nothing, so
    agreement is not asked of the photos, and neighbouring changing groups hold on to the same photo `hold` times
    harder: the screen shows one moment instead of a mosaic of several.
    Returns (colours (n, 3), NaN where unseen; the view taken (n), -1 where unseen)."""
    n_views, n_faces = int(views.max()) + 1, int(face_of.max()) + 1
    score = np.zeros((n_faces, max(n_views, 1)))
    seen = weights > 0
    for k in range(len(weights)):
        np.add.at(score, (face_of[seen[k]], views[k][seen[k]]), np.minimum(weights[k][seen[k]], cap))
    if agree:
        median, count = fuse(colours, weights, few=few)
        judged = count >= few
        dist, hits = np.zeros_like(score), np.zeros_like(score)
        for k in range(len(weights)):
            m = seen[k] & judged
            d = np.abs(colours[k][m] - median[m]).mean(axis=1)
            np.add.at(dist, (face_of[m], views[k][m]), d)
            np.add.at(hits, (face_of[m], views[k][m]), 1)
        # a photo nobody can vouch for on this group is treated as an average disagreement, not as perfect
        mean = np.where(hits > 0, dist / np.maximum(hits, 1), float(agree))
        factor = np.exp(-mean / float(agree))
        moving = np.zeros(n_faces, bool)
        if changing:
            moving = dist.sum(axis=1) / np.maximum(hits.sum(axis=1), 1) > float(changing)
            factor[moving] = 1.0
            if pairs is not None and len(pairs):
                pairs = np.asarray(pairs, int).reshape(-1, 2)
                strength = np.where(moving[pairs[:, 0]] & moving[pairs[:, 1]], strength * hold, strength)
        score = score * factor
    if pairs is not None and len(pairs):
        # the smoothed choice wins wherever that photo saw the texel; elsewhere the plain ranking still applies
        label = smooth_labels(score, pairs, strength)
        score = score.copy()
        score[np.arange(n_faces), label] = score.max() * 2 + 1
    rank = np.where(seen, score[face_of[None, :], np.maximum(views, 0)], -1.0)
    pick = rank.argmax(axis=0)
    cols = np.arange(weights.shape[1])
    out = colours[pick, cols].astype(np.float32)
    chosen = views[pick, cols].astype(np.int32)
    none = ~seen.any(axis=0)
    out[none], chosen[none] = np.nan, -1
    return out, chosen


class TopK:
    """The k heaviest observations of each of n texels, taken one view at a time (a full stack of a few hundred
    photos does not fit in memory). `count` is how many views saw each texel at all."""

    def __init__(self, n, k=6):
        self.colours = np.zeros((k, n, 3), np.float32)
        self.weights = np.zeros((k, n), np.float32)
        self.views = np.full((k, n), -1, np.int16)
        self.count = np.zeros(n, np.int32)

    def add(self, colours, weights, view=0):
        weights = np.asarray(weights, np.float32)
        self.count += weights > 0
        slot = self.weights.argmin(axis=0)
        cols = np.arange(len(slot))
        better = weights > self.weights[slot, cols]
        self.weights[slot[better], cols[better]] = weights[better]
        self.colours[slot[better], cols[better]] = np.asarray(colours, np.float32)[better]
        self.views[slot[better], cols[better]] = view

    def arrays(self, views=False):
        return (self.colours, self.weights, self.views) if views else (self.colours, self.weights)
