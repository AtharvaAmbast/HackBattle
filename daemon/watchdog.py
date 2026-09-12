import os
import sys
import json
import psutil
import subprocess
import asyncio
import warnings
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from ctypes import Structure, windll, c_uint, sizeof, byref

warnings.filterwarnings("ignore")

# --- Pythonw Crash Prevention ---
# Redirects output to a black hole if running without a console
if sys.executable.endswith("pythonw.exe"):
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

CONFIG_FILE = "watchdog_settings.json"

# --- Default Configuration ---
config = {
    "enabled": True,
    "timeout_minutes": 10,
    "cpu_threshold": 10,
    "memory_threshold": 60,
    "disk_io_threshold": 100
}

# Load saved settings if they exist
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config.update(json.load(f))

# --- Global Telemetry State ---
telemetry = {
    "idle_minutes": 0,
    "cpu_percent": 0,
    "memory_percent": 0,
    "disk_io_mb": 0,
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

# --- Web Server Setup ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(watchdog_daemon())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

class SettingsUpdate(BaseModel):
    enabled: bool
    timeout_minutes: float
    cpu_threshold: float
    memory_threshold: float
    disk_io_threshold: float

@app.get("/api/data")
def get_data():
    """Returns both live telemetry and current configuration."""
    return {"telemetry": telemetry, "config": config}

@app.post("/api/settings")
def update_settings(new_settings: SettingsUpdate):
    """Receives new settings from the UI and saves them to disk."""
    global config
    config.update(new_settings.model_dump())
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)
    return {"status": "success"}

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
        <h1 class="text-3xl font-bold mb-6">Watchdog Control Center</h1>
        
        <div class="grid grid-cols-2 gap-6 mb-8">
            <!-- Left Column: Live Data -->
            <div class="bg-gray-800 p-6 rounded-lg flex flex-col justify-between">
                <div>
                    <h2 class="text-xl mb-4 font-semibold text-blue-400">Live Resource Metrics</h2>
                    <canvas id="resourceChart" width="400" height="200"></canvas>
                </div>
                <div class="mt-6">
                    <h2 class="text-xl mb-4 font-semibold text-blue-400">Shutdown Conditions</h2>
                    <ul class="space-y-3 font-mono text-sm" id="conditions-list">
                        <!-- Populated by JS -->
                    </ul>
                    <div id="shutdown-status" class="mt-6 p-4 rounded text-center font-bold text-xl transition-colors"></div>
                </div>
            </div>
            
            <!-- Right Column: Interactive Settings -->
            <div class="bg-gray-800 p-6 rounded-lg">
                <h2 class="text-xl mb-4 font-semibold text-green-400">Adjust Thresholds</h2>
                <form id="settingsForm" class="space-y-4">
                    
                    <div class="flex items-center justify-between bg-gray-700 p-3 rounded">
                        <label class="font-bold">Master Watchdog Switch</label>
                        <input type="checkbox" id="set-enabled" class="w-6 h-6">
                    </div>

                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Idle Timeout (Minutes)</label>
                        <input type="number" id="set-timeout" class="w-full p-2 bg-gray-700 rounded border border-gray-600 text-white">
                    </div>

                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Max CPU Load (%)</label>
                        <input type="number" id="set-cpu" class="w-full p-2 bg-gray-700 rounded border border-gray-600 text-white">
                    </div>

                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Max Memory Load (%)</label>
                        <input type="number" id="set-memory" class="w-full p-2 bg-gray-700 rounded border border-gray-600 text-white">
                    </div>

                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Max Disk I/O (MB per 5s)</label>
                        <input type="number" id="set-disk" class="w-full p-2 bg-gray-700 rounded border border-gray-600 text-white">
                    </div>

                    <button type="button" onclick="saveSettings()" class="w-full bg-green-600 hover:bg-green-500 text-white font-bold py-3 rounded mt-4 transition-colors">
                        Save & Apply Changes
                    </button>
                    <p id="save-alert" class="text-green-400 text-center text-sm hidden mt-2">Settings applied instantly!</p>
                </form>
            </div>
        </div>

        <script>
            // Initialize Chart
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

            let isFirstLoad = true;

            function updateDashboard() {
                fetch('/api/data').then(r => r.json()).then(data => {
                    const t = data.telemetry;
                    const c = data.config;

                    // Populate form inputs on first load so user sees current state
                    if (isFirstLoad) {
                        document.getElementById('set-enabled').checked = c.enabled;
                        document.getElementById('set-timeout').value = c.timeout_minutes;
                        document.getElementById('set-cpu').value = c.cpu_threshold;
                        document.getElementById('set-memory').value = c.memory_threshold;
                        document.getElementById('set-disk').value = c.disk_io_threshold;
                        isFirstLoad = false;
                    }

                    // Update Chart
                    const now = new Date().toLocaleTimeString();
                    chart.data.labels.push(now);
                    chart.data.datasets[0].data.push(t.cpu_percent);
                    chart.data.datasets[1].data.push(t.memory_percent);
                    if(chart.data.labels.length > 20) {
                        chart.data.labels.shift();
                        chart.data.datasets.forEach(d => d.data.shift());
                    }
                    chart.update();

                    // Update Conditions Display
                    const getIcon = (pass) => pass ? '✅' : '❌';
                    document.getElementById('conditions-list').innerHTML = `
                        <li>${getIcon(c.enabled)} Watchdog Enabled</li>
                        <li>${getIcon(t.idle_minutes >= c.timeout_minutes)} Idle Time: ${t.idle_minutes.toFixed(1)} / ${c.timeout_minutes} min</li>
                        <li>${getIcon(t.cpu_percent <= c.cpu_threshold)} CPU Load ≤ ${c.cpu_threshold}% (Current: ${t.cpu_percent}%)</li>
                        <li>${getIcon(t.memory_percent <= c.memory_threshold)} Memory Load ≤ ${c.memory_threshold}% (Current: ${t.memory_percent}%)</li>
                        <li>${getIcon(t.disk_io_mb <= c.disk_io_threshold)} Disk I/O ≤ ${c.disk_io_threshold}MB (Current: ${t.disk_io_mb.toFixed(1)}MB)</li>
                    `;

                    // Update Status Banner
                    const statusDiv = document.getElementById('shutdown-status');
                    if(t.will_shutdown_next_cycle) {
                        statusDiv.className = "mt-6 p-4 rounded text-center font-bold text-xl bg-red-600 animate-pulse";
                        statusDiv.innerText = "SHUTDOWN IMMINENT";
                    } else {
                        statusDiv.className = "mt-6 p-4 rounded text-center font-bold text-xl bg-gray-700 text-green-400";
                        statusDiv.innerText = "SERVER SAFE (Conditions Not Met)";
                    }
                });
            }

            function saveSettings() {
                const payload = {
                    enabled: document.getElementById('set-enabled').checked,
                    timeout_minutes: parseFloat(document.getElementById('set-timeout').value),
                    cpu_threshold: parseFloat(document.getElementById('set-cpu').value),
                    memory_threshold: parseFloat(document.getElementById('set-memory').value),
                    disk_io_threshold: parseFloat(document.getElementById('set-disk').value)
                };

                fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                }).then(() => {
                    const alert = document.getElementById('save-alert');
                    alert.classList.remove('hidden');
                    setTimeout(() => alert.classList.add('hidden'), 3000);
                    updateDashboard(); // Force immediate refresh
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
    
    while True:
        # Fetch Hardware Data
        telemetry["idle_minutes"] = get_idle_time_minutes()
        telemetry["cpu_percent"] = psutil.cpu_percent(interval=None)
        telemetry["memory_percent"] = psutil.virtual_memory().percent
        
        current_disk = psutil.disk_io_counters()
        read_diff = current_disk.read_bytes - last_disk_io.read_bytes
        write_diff = current_disk.write_bytes - last_disk_io.write_bytes
        telemetry["disk_io_mb"] = (read_diff + write_diff) / 1000000.0
        last_disk_io = current_disk

        # Check Shutdown Logic against the live config
        all_conditions_met = (
            config["enabled"] and
            telemetry["idle_minutes"] >= config["timeout_minutes"] and
            telemetry["cpu_percent"] <= config["cpu_threshold"] and
            telemetry["memory_percent"] <= config["memory_threshold"] and
            telemetry["disk_io_mb"] <= config["disk_io_threshold"]
        )
        
        telemetry["will_shutdown_next_cycle"] = all_conditions_met

        if all_conditions_met:
            subprocess.run(["shutdown", "/s", "/t", "0"])
            
        await asyncio.sleep(5)



if __name__ == "__main__":
    if sys.executable.endswith("pythonw.exe"):
        # Silent mode for background Task Scheduler
        uvicorn.run("watchdog:app", host="0.0.0.0", port=80, reload=False, log_config=None)
    else:
        # Verbose mode for visible terminal debugging
        uvicorn.run("watchdog:app", host="0.0.0.0", port=80, reload=False)