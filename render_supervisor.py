import os
import time
import logging
import subprocess
import database
from datetime import datetime, timezone

logger = logging.getLogger("render_supervisor")

class RenderSupervisor:
    def __init__(self, timeout_minutes=30):
        self.timeout_minutes = timeout_minutes

    def cleanup_stuck_jobs(self):
        """ Detects and resets jobs that are stuck in 'DOWNLOADING' or 'RENDERING' for too long. """
        with database.get_connection() as conn:
            cursor = conn.cursor()
            # Find jobs updated more than timeout_minutes ago that are not DONE or FAILED
            cursor.execute("""
                SELECT job_id, video_id, status, updated_at 
                FROM render_jobs 
                WHERE status IN ('DOWNLOADING', 'CUTTING', 'RENDERING')
                AND datetime(updated_at) < datetime('now', ?)
            """, (f"-{self.timeout_minutes} minutes",))
            
            stuck_jobs = cursor.fetchall()
            for job in stuck_jobs:
                jid, vid, status, updated = job
                logger.warning(f"🚨 Job {jid} ({vid}) stuck in {status} since {updated}. Resetting to PENDING.")
                database.update_job_status(jid, "PENDING", error_log=f"Supervisor: Stuck in {status} for > {self.timeout_minutes}m")
                database.log_operational_metric("stuck_job_reset", 1, {"job_id": jid, "status": status})

    def cleanup_zombie_ffmpeg(self):
        """ Kills ffmpeg processes that have no parent or are orphaned (basic implementation). """
        # On Linux, we can check for ffmpeg processes and their start time
        try:
            # This is a dangerous operation, let's just log for now in the prototype
            # res = subprocess.run(["pgrep", "ffmpeg"], capture_output=True, text=True)
            # if res.stdout:
            #     logger.info(f"Checking {len(res.stdout.split())} ffmpeg processes...")
            pass
        except Exception as e:
            logger.error(f"Error checking zombies: {e}")

    def expire_jobs(self):
        """ Explicitly marks expired jobs as CANCELLED. """
        with database.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE render_jobs 
                SET status = 'CANCELLED', updated_at = datetime('now')
                WHERE status = 'PENDING' AND expires_at < datetime('now')
            """)
            if cursor.rowcount > 0:
                logger.info(f"⏳ Expired {cursor.rowcount} pending jobs.")
                database.log_operational_metric("expired_jobs", cursor.rowcount)
            conn.commit()

    def run_cycle(self):
        logger.info("🛡️ Render Supervisor: Starting health check cycle...")
        self.cleanup_stuck_jobs()
        self.expire_jobs()
        self.cleanup_zombie_ffmpeg()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    supervisor = RenderSupervisor()
    while True:
        supervisor.run_cycle()
        time.sleep(300) # Every 5 minutes
