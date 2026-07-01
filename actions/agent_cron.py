import threading
import time

def agent_cron(parameters: dict, player=None, on_text_command=None) -> str:
    """
    Schedules the AI to perform a task periodically or after a delay.
    It simulates a user command being typed into the UI.
    """
    task = parameters.get("task", "").strip()
    if not task:
        return "No task provided."
        
    minutes = parameters.get("interval_minutes", 0)
    repeat = parameters.get("repeat", False)
    
    if minutes <= 0:
        return "Interval must be greater than 0 minutes."
        
    delay_seconds = minutes * 60
    
    def cron_job():
        while True:
            time.sleep(delay_seconds)
            if on_text_command:
                                                                       
                on_text_command(f"[CRON AUTOTASK] {task}")
            else:
                print(f"[CRON] Failed to execute {task} - no callback")
            
            if not repeat:
                break

    t = threading.Thread(target=cron_job, daemon=True)
    t.start()
    
    msg = f"Scheduled background task every {minutes} minutes." if repeat else f"Scheduled background task in {minutes} minutes."
    return msg
