### 9\. The Asynchronous Task API (RESTful)

Certain operations, such as processing a large file, running a complex data analysis, or training a machine learning model, cannot be completed within the timeout of a standard synchronous HTTP request. Attempting to do so would lead to client timeouts, a poor user experience, and an architecture that is not resilient to long-running jobs.[1] The Asynchronous Task API is specifically designed to solve this problem by decoupling the task initiation from its completion.

#### Design Philosophy

The philosophy is to provide a **non-blocking, responsive interface for long-running operations**. The system should never force a client to maintain an open connection while waiting for a task to finish. Instead, we implement the well-established **Asynchronous Request-Reply pattern**.[2] The core idea is to immediately acknowledge the client's request and provide them with a "ticket" (a task ID and a status URL) that they can use to check on the progress of their job at their convenience. This approach makes the system more scalable, as it frees up server resources to handle new incoming requests, and more robust, as it gracefully handles tasks that may take minutes or even hours to complete.[3, 4]

#### Technical Implementation & Features

The API is built on RESTful principles and leverages standard HTTP mechanisms to manage the asynchronous workflow.

  * **Immediate Acknowledgment:** When a client submits a long-running task, the server validates the request and, if valid, immediately responds with an `HTTP 202 Accepted` status code. This code explicitly tells the client: "I have received and accepted your request for processing, but the work is not yet complete".[2, 3]
  * **Status Resource Location:** The `202 Accepted` response **MUST** include a `Location` HTTP header. This header contains a unique URL that points to the "status resource" for the newly created task. This is the endpoint the client will use to poll for updates.[1, 3]
  * **Polling Mechanism:** The client periodically sends `GET` requests to the status URL provided in the `Location` header to check the progress of the task.
  * **Standardized Status Payloads:** The status endpoint returns a JSON object with a consistent structure, indicating the current state of the task (e.g., `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`).
  * **Result Delivery:** Once the task is complete, a final `GET` request to the status endpoint will return a `COMPLETED` status and include the final result of the operation in the response body. If the task failed, it will return a `FAILED` status along with detailed error information.[2]
  * **Rate Limiting Guidance:** To prevent clients from polling too aggressively, the server can optionally include a `Retry-After` header in its responses, suggesting how many seconds the client should wait before making the next status request.[1]

#### Interaction Flow: Step-by-Step

1.  **Initiation:** The client sends a `POST` request to a resource-specific action endpoint (e.g., `POST /v1/bots/{bot_id}/actions/analyze-document`) with the necessary parameters for the task.
2.  **Acceptance:** The Orchestrator validates the request, creates a unique `task_id`, enqueues the job for a background worker, and immediately responds with `HTTP 202 Accepted`. The `Location` header in the response is set to `/v1/tasks/{task_id}`.
3.  **Polling:** The client begins polling the status endpoint by sending `GET /v1/tasks/{task_id}`.
4.  **In-Progress Response:** While the task is running, the server responds to the poll with `HTTP 200 OK` and a body indicating the status is `RUNNING`.
5.  **Completion:** Once the background worker finishes the task, it updates the task's status. The next time the client polls the status endpoint, the server responds with `HTTP 200 OK` and a body indicating the status is `COMPLETED`, along with the final result.

-----

### Real-Life Code Examples

#### 1\. cURL Command-Line Walkthrough

This sequence demonstrates the entire flow using cURL.

**Step 1: Initiate the long-running task.**

```bash
# The -i flag includes the HTTP headers in the output.
curl -i -X POST "https://api.orchestrator.example.com/v1/bots/bot-abc-123/actions/analyze-document" \
     -H "Authorization: Bearer <admin_api_key>" \
     -H "Content-Type: application/json" \
     -d '{"document_url": "https://example.com/large-report.pdf"}'

# --- SERVER RESPONSE ---
# Note the 202 Accepted status and the Location header.
# HTTP/1.1 202 Accepted
# Location: /v1/tasks/task-f4b5c6d7-e8f9-1234-5678-90abcdef1234
# Content-Type: application/json
#
# {
#   "task_id": "task-f4b5c6d7-e8f9-1234-5678-90abcdef1234",
#   "status": "PENDING"
# }
```

**Step 2: Poll the status endpoint while the task is in progress.**

```bash
curl "https://api.orchestrator.example.com/v1/tasks/task-f4b5c6d7-e8f9-1234-5678-90abcdef1234" \
     -H "Authorization: Bearer <admin_api_key>"

# --- SERVER RESPONSE ---
# HTTP/1.1 200 OK
# Content-Type: application/json
#
# {
#   "task_id": "task-f4b5c6d7-e8f9-1234-5678-90abcdef1234",
#   "status": "RUNNING",
#   "progress_percent": 45
# }
```

**Step 3: Poll the status endpoint after the task is complete.**

```bash
curl "https://api.orchestrator.example.com/v1/tasks/task-f4b5c6d7-e8f9-1234-5678-90abcdef1234" \
     -H "Authorization: Bearer <admin_api_key>"

# --- SERVER RESPONSE ---
# HTTP/1.1 200 OK
# Content-Type: application/json
#
# {
#   "task_id": "task-f4b5c6d7-e8f9-1234-5678-90abcdef1234",
#   "status": "COMPLETED",
#   "completed_at": "2025-09-16T02:30:00Z",
#   "result": {
#     "summary": "The document discusses market trends...",
#     "sentiment": "POSITIVE",
#     "entities": ["market", "growth", "revenue"]
#   }
# }
```

#### 2\. Python Client with Polling Logic

This script automates the process of initiating a task and polling for its result.

```python
import requests
import time
import os

API_BASE_URL = os.getenv("ORCHESTRATOR_API_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("ADMIN_API_KEY", "secret-key")

def run_async_task(bot_id: str, document_url: str):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    initiate_url = f"{API_BASE_URL}/v1/bots/{bot_id}/actions/analyze-document"
    payload = {"document_url": document_url}

    # 1. Initiate the task
    print(f"Submitting task to analyze: {document_url}")
    response = requests.post(initiate_url, headers=headers, json=payload)

    if response.status_code!= 202:
        print(f"Error initiating task: {response.status_code} - {response.text}")
        return

    status_url = API_BASE_URL + response.headers["Location"]
    print(f"Task accepted. Polling status at: {status_url}")

    # 2. Poll for the result
    while True:
        try:
            status_response = requests.get(status_url, headers=headers)
            status_data = status_response.json()
            current_status = status_data.get("status")

            print(f"  Current status: {current_status}")

            if current_status in:
                print("\n--- Task Finished ---")
                print(status_data)
                break
            
            # Wait before polling again
            time.sleep(5)

        except requests.RequestException as e:
            print(f"Error polling status: {e}")
            break

if __name__ == "__main__":
    run_async_task("bot-abc-123", "https://example.com/large-report.pdf")
```

This robust pattern ensures that the UBP framework can handle complex, time-intensive operations without compromising the responsiveness or stability of its core APIs.
