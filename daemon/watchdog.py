import os, json, psutil, subprocess, urllib.request, asyncio
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn
from ctypes import Structure, windll, c_uint, sizeof, byref

# --- Global Telemetry State ---
telemetry = {
    "idle_minutes": 0,
    "cpu_percent": 0,
    "memory_percent": 0,
    "disk_io_mb": 0,
    "important_process_active": False,
    "remote_enabled": True,
    "timeout_minutes": 10,
    "will_shutdown_next_cycle": False
}

# --- Windows API ---
class LASTINPUTINFO(Structure):
    _fields_ = [('cbSize', c_uint), ('dwTime', c_uint)]

def get_idle_time_minutes():
    lastInputInfo = LASTINPUTINFO()
    lastInputInfo.cbSize = sizeof(lastInputInfo)
    if windll.user32.GetLastInputInfo(byref(lastInputInfo)):
        millis = windll.kernel32.GetTickCount() - lastInputInfo.dwTime
        return millis / 60000.0
    return 0

# --- Remote Config ---
def get_config():
    try:
        # REPLACE WITH YOUR ACTUAL GIST URL
        url = "https://gist.githubusercontent.com/YOUR_USERNAME/.../raw/config.json"
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode())
    except:
        return {"timeout_minutes": 10, "enabled": True}

# --- Web Server Setup ---
app = FastAPI()

@app.get("/api/telemetry")
def get_telemetry():
    return telemetry

@app.get("/")
def serve_dashboard():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Server Telemetry</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body class="bg-gray-900 text-white p-8">
        <h1 class="text-3xl font-bold mb-6">Watchdog Telemetry Dashboard</h1>
        
        <div class="grid grid-cols-2 gap-6 mb-8">
            <div class="bg-gray-800 p-6 rounded-lg">
                <h2 class="text-xl mb-4 font-semibold">Live Resource Metrics</h2>
                <canvas id="resourceChart" width="400" height="200"></canvas>
            </div>
            
            <div class="bg-gray-800 p-6 rounded-lg">
                <h2 class="text-xl mb-4 font-semibold">Shutdown Conditions</h2>
                <ul class="space-y-3" id="conditions-list">
                    <!-- Populated by JS -->
                </ul>
                <div id="shutdown-status" class="mt-6 p-4 rounded text-center font-bold text-xl"></div>
            </div>
        </div>

        <script>
            const ctx = document.getElementById('resourceChart').getContext('2d');
            const chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'CPU %', borderColor: '#3b82f6', data: [], tension: 0.4 },
                        { label: 'Memory %', borderColor: '#10b981', data: [], tension: 0.4 }
                    ]
                },
                options: { animation: false, scales: { y: { min: 0, max: 100 } } }
            });

            function updateDashboard() {
                fetch('/api/telemetry').then(r => r.json()).then(data => {
                    // Update Chart
                    const now = new Date().toLocaleTimeString();
                    chart.data.labels.push(now);
                    chart.data.datasets[0].data.push(data.cpu_percent);
                    chart.data.datasets[1].data.push(data.memory_percent);
                    if(chart.data.labels.length > 20) {
                        chart.data.labels.shift();
                        chart.data.datasets.forEach(d => d.data.shift());
                    }
                    chart.update();

                    // Update Conditions
                    const getIcon = (pass) => pass ? '✅' : '❌';
                    const html = `
                        <li>${getIcon(data.remote_enabled)} Remote Master Switch Enabled</li>
                        <li>${getIcon(data.idle_minutes >= data.timeout_minutes)} Idle Time: ${data.idle_minutes.toFixed(1)} / ${data.timeout_minutes} min</li>
                        <li>${getIcon(data.cpu_percent <= 10)} CPU Load ≤ 10% (Current: ${data.cpu_percent}%)</li>
                        <li>${getIcon(data.memory_percent <= 60)} Memory Load ≤ 60% (Current: ${data.memory_percent}%)</li>
                        <li>${getIcon(data.disk_io_mb <= 100)} Disk I/O ≤ 100MB (Current: ${data.disk_io_mb.toFixed(1)}MB)</li>
                        <li>${getIcon(!data.important_process_active)} No Important Processes Active</li>
                    `;
                    document.getElementById('conditions-list').innerHTML = html;

                    // Update Status Banner
                    const statusDiv = document.getElementById('shutdown-status');
                    if(data.will_shutdown_next_cycle) {
                        statusDiv.className = "mt-6 p-4 rounded text-center font-bold text-xl bg-red-600";
                        statusDiv.innerText = "SHUTDOWN IMMINENT";
                    } else {
                        statusDiv.className = "mt-6 p-4 rounded text-center font-bold text-xl bg-green-600";
                        statusDiv.innerText = "SERVER SAFE";
                    }
                });
            }
            setInterval(updateDashboard, 2000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --- Background Watchdog Loop ---
async def watchdog_daemon():
    last_disk_io = psutil.disk_io_counters()
    important_processes = ['code.exe', 'python.exe', 'node.exe', 'docker.exe']
    
    while True:
        config = get_config()
        telemetry["remote_enabled"] = config.get("enabled", True)
        telemetry["timeout_minutes"] = config.get("timeout_minutes", 10)
        
        # Fetch Hardware Data
        telemetry["idle_minutes"] = get_idle_time_minutes()
        telemetry["cpu_percent"] = psutil.cpu_percent(interval=None)
        telemetry["memory_percent"] = psutil.virtual_memory().percent
        
        current_disk = psutil.disk_io_counters()
        read_diff = current_disk.read_bytes - last_disk_io.read_bytes
        write_diff = current_disk.write_bytes - last_disk_io.write_bytes
        telemetry["disk_io_mb"] = (read_diff + write_diff) / 1000000.0
        last_disk_io = current_disk

        # Check Processes
        process_active = False
        for proc in psutil.process_iter(['name', 'cpu_percent']):
            try:
                if proc.info['name'] and proc.info['cpu_percent']:
                    if proc.info['name'].lower() in important_processes and proc.info['cpu_percent'] > 0.1:
                        process_active = True
                        break
            except:
                pass
        telemetry["important_process_active"] = process_active

        # Check Shutdown Logic
        all_conditions_met = (
            telemetry["remote_enabled"] and
            telemetry["idle_minutes"] >= telemetry["timeout_minutes"] and
            telemetry["cpu_percent"] <= 10 and
            telemetry["memory_percent"] <= 60 and
            telemetry["disk_io_mb"] <= 100 and
            not telemetry["important_process_active"]
        )
        
        telemetry["will_shutdown_next_cycle"] = all_conditions_met

        if all_conditions_met:
            subprocess.run(["shutdown", "/s", "/t", "0"])
            
        await asyncio.sleep(5) # Poll every 5 seconds for responsive frontend

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(watchdog_daemon())

if __name__ == "__main__":
    uvicorn.run("watchdog:app", host="0.0.0.0", port=80, reload=False)