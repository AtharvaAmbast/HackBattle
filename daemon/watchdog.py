import os
import time
import json
import psutil
import subprocess
import urllib.request
from ctypes import Structure, windll, c_uint, sizeof, byref

# --- Windows Idle Time API ---
class LASTINPUTINFO(Structure):
    _fields_ = [
        ('cbSize', c_uint),
        ('dwTime', c_uint),
    ]

def get_idle_time_minutes():
    lastInputInfo = LASTINPUTINFO()
    lastInputInfo.cbSize = sizeof(lastInputInfo)
    if windll.user32.GetLastInputInfo(byref(lastInputInfo)):
        millis_since_last_input = windll.kernel32.GetTickCount() - lastInputInfo.dwTime
        return millis_since_last_input / 60000.0
    return 0

# --- Remote Configuration ---
def get_config():
    try:
        # REPLACE THIS WITH YOUR ACTUAL GIST RAW URL
        url = "https://gist.githubusercontent.com/YOUR_USERNAME/.../raw/config.json"
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode())
    except Exception:
        # Safe fallback
        return {"timeout_minutes": 10, "enabled": True}

# --- Smart Hardware Monitor ---
class ServerMonitor:
    def __init__(self):
        self.cpu_threshold = 10.0
        self.memory_threshold = 60.0  # Increased for normal Windows idle usage
        self.disk_io_threshold = 100 * 1000000  # 100MB
        
        try:
            self.last_disk_io = psutil.disk_io_counters()
        except:
            self.last_disk_io = None

        self.important_processes = [
            'code.exe', 'devenv.exe', 'python.exe', 'pycharm.exe', 
            'node.exe', 'mysqld.exe', 'mongod.exe', 'redis-server.exe', 
            'postgres.exe', 'docker.exe', 'vlc.exe', 'ffmpeg.exe'
        ]

    def is_system_busy(self):
        """Returns True if the system is doing important work, False if safe to shutdown."""
        # 1. Check CPU
        try:
            if psutil.cpu_percent(interval=1) > self.cpu_threshold:
                return True
        except:
            pass

        # 2. Check Memory
        try:
            if psutil.virtual_memory().percent > self.memory_threshold:
                return True
        except:
            pass

        # 3. Check Disk I/O
        try:
            if self.last_disk_io:
                current_disk = psutil.disk_io_counters()
                read_diff = current_disk.read_bytes - self.last_disk_io.read_bytes
                write_diff = current_disk.write_bytes - self.last_disk_io.write_bytes
                self.last_disk_io = current_disk
                
                if (read_diff + write_diff) > self.disk_io_threshold:
                    return True
        except:
            pass

        # 4. Check Important Processes
        try:
            for proc in psutil.process_iter(['name', 'cpu_percent']):
                proc_name = proc.info['name'].lower() if proc.info['name'] else ""
                cpu = proc.info['cpu_percent'] or 0
                
                for important in self.important_processes:
                    # Only block shutdown if the important process is actively computing
                    if important in proc_name and cpu > 0.1:
                        return True
        except:
            pass

        return False

# --- Main Daemon Loop ---
def main():
    CHECK_INTERVAL_SECONDS = 60
    monitor = ServerMonitor()
    
    while True:
        config = get_config()
        
        # 1. Check if the watchdog is enabled remotely
        if config.get("enabled", True):
            idle_minutes = get_idle_time_minutes()
            
            # 2. Check if the user's RDP session has been idle long enough
            if idle_minutes >= config.get("timeout_minutes", 10):
                
                # 3. Final safety check: ensure the hardware isn't processing a background task
                if not monitor.is_system_busy():
                    subprocess.run(["shutdown", "/s", "/t", "0"])
                    break
                    
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()