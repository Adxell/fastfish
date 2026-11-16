# fastfish agent image: Claude Code + git + gh + tmux, with the fastfish plugin at /opt/fastfish.
# Build from the repository root:
#   docker build -f fleet/image/Dockerfile -t fastfish-agent:latest .
FROM node:22-bookworm-slim

ARG CLAUDE_CODE_VERSION=latest

RUN apt-get update \
 && apt-get install -y --no-install-recommends git gh tmux python3 ca-certificates curl openssh-client jq ripgrep \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" && npm cache clean --force

# The plugin, loaded per session with --plugin-dir (no install step, no network at build time).
COPY .claude-plugin /opt/fastfish/.claude-plugin
COPY agents /opt/fastfish/agents
COPY skills /opt/fastfish/skills
COPY scripts /opt/fastfish/scripts
COPY fleet/image/agent-run.sh /usr/local/bin/agent-run
RUN chmod 0755 /usr/local/bin/agent-run && mkdir -p /work && chown node:node /work

# "node" is uid 1000, matching runAsUser in the Job manifest.
USER node
ENV HOME=/home/node DISABLE_AUTOUPDATER=1 TERM=xterm-256color
# Skip first-run onboarding and the folder-trust prompt for the checkout path.
RUN printf '{"hasCompletedOnboarding":true,"projects":{"/work/repo":{"hasTrustDialogAccepted":true}}}\n' > /home/node/.claude.json

WORKDIR /work
ENTRYPOINT ["agent-run"]
