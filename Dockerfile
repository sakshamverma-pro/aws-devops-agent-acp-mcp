FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY setup.py setup.cfg README.md LICENSE.txt ./
COPY src/ ./src/

RUN pip install --no-cache-dir ".[mcp]"

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8000
ENV DEVOPS_AGENT_REGION=us-east-1

EXPOSE 8000

CMD ["python", "-m", "aws_devops_agent.mcp_http_server"]
