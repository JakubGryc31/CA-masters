FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts

# default command (can be overridden in workflow)
CMD ["python", "-m", "scripts.run_demo"]
