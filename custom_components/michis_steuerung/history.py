"""Bounded 24-hour history with min/max-preserving chart reduction."""
import time
PERIODS = (900, 3600, 21600, 86400)

def chart_history(history, seconds=3600, now=None):
    if seconds not in PERIODS:
        raise ValueError('Unbekannter Diagrammzeitraum')
    now = time.time() if now is None else now
    points = [p for p in history if now-seconds <= p['t'] <= now]
    if len(points) <= 720:
        return points
    # Keep temporal order and extrema, plus a gap marker per bucket.
    size = (len(points)+99)//100
    result = []
    for start in range(0, len(points), size):
        bucket = points[start:start+size]
        indices = {0, len(bucket)-1}
        valid = [i for i,p in enumerate(bucket) if p['temperature'] is not None]
        if valid:
            indices.update((min(valid,key=lambda i:bucket[i]['temperature']), max(valid,key=lambda i:bucket[i]['temperature'])))
        gaps = [i for i,p in enumerate(bucket) if p['temperature'] is None]
        if gaps:
            indices.add(gaps[0])
        indices.update((min(range(len(bucket)),key=lambda i:bucket[i]['output']), max(range(len(bucket)),key=lambda i:bucket[i]['output'])))
        result.extend(bucket[i] for i in sorted(indices))
    return result
