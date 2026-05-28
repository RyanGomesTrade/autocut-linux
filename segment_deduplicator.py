import logging
import database

logger = logging.getLogger("deduplicator")

def deduplicate_segments(video_id, new_segments, overlap_threshold=5.0):
    """
    Deduplicates segments for a specific video based on temporal overlap.
    If two segments overlap more than threshold, they are merged.
    """
    if not new_segments:
        return []

    # 1. Get existing segments from DB to avoid re-rendering
    existing = database.get_video_segments(video_id)
    
    # 2. Sort by start time
    all_segs = sorted(new_segments + existing, key=lambda x: x['start'])
    
    if not all_segs:
        return []

    merged = []
    current = all_segs[0]

    for i in range(1, len(all_segs)):
        next_seg = all_segs[i]
        
        # Check for overlap
        # If next starts before current ends (with small threshold)
        if next_seg['start'] <= (current['end'] + overlap_threshold):
            # Merge: take the earliest start and latest end
            new_end = max(current['end'], next_seg['end'])
            # Update current segment
            current['end'] = new_end
            current['total_score'] = max(current.get('total_score', 0), next_seg.get('total_score', 0))
            logger.info(f"🔗 Merged segments for {video_id}: {current['start']}-{current['end']}")
        else:
            merged.append(current)
            current = next_seg
            
    merged.append(current)
    
    # Return only segments that are NOT already in the database (newly merged or purely new)
    # This is a simplified check for the prototype
    final_new_segments = []
    for m in merged:
        is_duplicate = False
        for e in existing:
            if abs(m['start'] - e['start']) < 1.0 and abs(m['end'] - e['end']) < 1.0:
                is_duplicate = True
                break
        if not is_duplicate:
            final_new_segments.append(m)
            
    if len(new_segments) != len(final_new_segments):
        logger.info(f"✂️ Deduplication: {len(new_segments)} -> {len(final_new_segments)} segments for {video_id}")
        database.log_operational_metric("deduplication_savings", len(new_segments) - len(final_new_segments), {"video_id": video_id})

    return final_new_segments
