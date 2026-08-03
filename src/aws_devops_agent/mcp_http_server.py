# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""HTTP entry point for AgentCore Runtime (MCP / streamable-http on port 8000)."""

import os

os.environ.setdefault("MCP_TRANSPORT", "http")

from aws_devops_agent.mcp_server import main

if __name__ == "__main__":
    main()
