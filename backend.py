from fastapi import FastAP
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import requests
import uvicorn
import csv

app = FastAPI()

class ECGSample(BaseModel):
    timestamp: int
    value: int

buffer = []
last_analysis = "Waiting for analysis..."
analysis_history = []


@app.post("/ecg")
async def receive_ecg(sample: ECGSample):
    buffer.append(sample.dict())
    print(f"Received ECG: {sample.value}")

    if len(buffer) >= 50:
        segment = buffer.copy()
        buffer.clear()

        #prompt = f"Analyze this ECG data: {segment}. Identify any abnormalities or health concerns."
        prompt = """
        You are a medical assistant AI analyzing raw ECG data. Review the following ECG segment and provide a concise summary of findings.
        Data: {segment}
        Instructions:
        Identify any irregular patterns such as arrhythmia, tachycardia, bradycardia, or skipped beats.
        Comment on heart rate trends and waveform consistency.
        Point out if the signal appears noisy or unreliable.
        Keep the output under 80 words. Use clear, non-technical language suitable for general users.
        Output format:
        Summary of rhythm
        Any abnormalities detected
        Signal quality
        Only include relevant observations. If the signal appears normal, say "ECG appears normal with no detectable abnormalities."
        """


        try:
            response = requests.post(
                "http://localhost:1234/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "tinyllama-1.1b-chat-v1.0",
                    "messages": [
                        {"role": "system", "content": "You are a medical assistant analyzing ECG data."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
            )
            if response.ok:
                analysis = response.json()["choices"][0]["message"]["content"]
                global last_analysis
                last_analysis = analysis
                analysis_history.append(analysis)
                print("Analysis complete:", analysis)
            else:
                print("LLMStudio error:", response.text)
        except Exception as e:
            print("LLMStudio exception:", e)

    return {"status": "received"}

@app.get("/latest")
def get_latest():
    return JSONResponse(content=buffer[-1] if buffer else {})

@app.get("/analysis/history")
def get_analysis_history():
    return {"history": analysis_history[-5:]}

@app.get("/")
def serve_frontend():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>ECG Monitor</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {
                background-color: #f8f9fa;
                padding-top: 2rem;
            }
            canvas {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 0.5rem;
            }
            .card {
                margin-bottom: 1.5rem;
            }
            .status-dot {
                height: 10px;
                width: 10px;
                border-radius: 50%;
                display: inline-block;
                margin-right: 6px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="text-center mb-4">📈 Live ECG Monitor</h1>

            <div class="card shadow-sm">
                <div class="card-header">
                    Real-Time ECG Signal
                </div>
                <div class="card-body">
                    <canvas id="chart" width="800" height="200"></canvas>
                    <p class="mt-3 mb-0">Status: <span class="status-dot bg-secondary" id="status-dot"></span><span id="status">Waiting for data...</span></p>
                </div>
            </div>

            <div class="card shadow-sm">
                <div class="card-header">
                    🧠 LLM Analysis (Latest 5 Results)
                </div>
                <div class="card-body">
                    <ul class="list-group" id="analysis">
                        <li class="list-group-item">Waiting for analysis...</li>
                    </ul>
                </div>
            </div>
        </div>

        <script>
            const ctx = document.getElementById("chart").getContext("2d");
            const chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'ECG Value',
                        data: [],
                        borderColor: '#0d6efd',
                        backgroundColor: 'rgba(13, 110, 253, 0.1)',
                        tension: 0.3
                    }]
                },
                options: {
                    animation: false,
                    scales: {
                        x: { display: false },
                        y: {
                            min: 0,
                            max: 1024,
                            ticks: {
                                stepSize: 256
                            }
                        }
                    }
                }
            });

            async function updateChart() {
                const res = await fetch("/latest");
                const data = await res.json();
                if (data && data.value !== undefined) {
                    chart.data.labels.push('');
                    chart.data.datasets[0].data.push(data.value);
                    if (chart.data.labels.length > 100) {
                        chart.data.labels.shift();
                        chart.data.datasets[0].data.shift();
                    }
                    chart.update();
                    document.getElementById("status").innerText = "Receiving ECG...";
                    document.getElementById("status-dot").className = "status-dot bg-success";
                } else {
                    document.getElementById("status").innerText = "No data";
                    document.getElementById("status-dot").className = "status-dot bg-danger";
                }
            }

            async function updateAnalysis() {
                const res = await fetch("/analysis/history");
                const data = await res.json();
                const list = document.getElementById("analysis");
                list.innerHTML = "";

                if (data.history.length === 0) {
                    const li = document.createElement("li");
                    li.className = "list-group-item";
                    li.innerText = "No analysis yet.";
                    list.appendChild(li);
                    return;
                }

                data.history.slice(-5).reverse().forEach(item => {
                    const li = document.createElement("li");
                    li.className = "list-group-item";
                    li.innerText = item;
                    list.appendChild(li);
                });
            }

            setInterval(updateChart, 1000);
            setInterval(updateAnalysis, 5000);
        </script>
    </body>
    </html>
    """

    return HTMLResponse(html)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
