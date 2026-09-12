import time
import subprocess
from ctypes import Structure, windll, c_uint, sizeof, byref

class LASTINPUTINFO(Structure):
    _fields_ = [
        ('cbSize', c_uint),
        ('dwTime', c_uint),
    ]

def get_idle_time_minutes():
    """Calculates the time elapsed since the last keyboard or mouse input."""
    lastInputInfo = LASTINPUTINFO()
    lastInputInfo.cbSize = sizeof(lastInputInfo)
    
    # Retrieve the time of the last input event from Windows
    if windll.user32.GetLastInputInfo(byref(lastInputInfo)):
        # GetTickCount returns milliseconds since system boot
        millis_since_last_input = windll.kernel32.GetTickCount() - lastInputInfo.dwTime
        return millis_since_last_input / 60000.0 # Convert to minutes
    return 0

def main():
    IDLE_THRESHOLD_MINUTES = 1
    CHECK_INTERVAL_SECONDS = 5 # Poll every 5 seconds
    
    while True:
        idle_minutes = get_idle_time_minutes()
        print(f"Current idle time: {idle_minutes:.2f} minutes")
        
        if idle_minutes >= IDLE_THRESHOLD_MINUTES:
            # Native OS shutdown. AWS detects this and stops compute billing.
            subprocess.run(["shutdown", "/s", "/t", "0"])
            break
            
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()