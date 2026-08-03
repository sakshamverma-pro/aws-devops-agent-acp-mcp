FROM python:3.12-slim

WORKDIR /app

COPY . .

# RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir -e ".[mcp]"

ENV MCP_TRANSPORT=http
ENV DEVOPS_AGENT_REGION=us-east-1

EXPOSE 8000

CMD ["python", "-m", "aws_devops_agent.mcp_server"]
