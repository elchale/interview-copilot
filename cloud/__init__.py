"""Cloud backend for Interview Copilot — hosted dashboard + local capture agent.

The local app (``src/``) becomes a capture agent that streams audio here; this
package hosts the website (landing/download, Google login, per-user live feed),
holds each user's encrypted BYO API keys, and runs the STT+gate+LLM pipeline.
"""
