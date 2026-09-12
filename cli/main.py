import os
import subprocess
import typer
import boto3
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
app = typer.Typer()
console = Console()

INSTANCE_ID = os.getenv("i-0d13a749f2a1f5fec")
REGION = os.getenv("us-east-1c")

@app.command()
def wake():
    console.print(f"Starting instance: [cyan]{INSTANCE_ID}[/cyan]...")
    
    # Boto3 automatically parses credentials from your local .env file
    ec2 = boto3.resource('ec2', region_name=REGION)
    instance = ec2.Instance(INSTANCE_ID)
    
    instance.start()
    console.print("Waiting for boot sequence to complete...")
    
    # Polling loop that pauses execution until the AWS instance is fully awake
    instance.wait_until_running()
    instance.reload()
    
    ip = instance.public_ip_address
    console.print(f"[green]Server is running![/green] Public IP: {ip}")
    
    # Automatically spawn the native Windows RDP client
    subprocess.run(["mstsc", "/v:" + ip])

if __name__ == "__main__":
    app()