# Documentation Index

Priority-layered system. Only P0 is auto-loaded every session.

## P0 — Always Loaded
- `../CLAUDE.md` — Project context, architecture, commands, constraints

## P1 — Load When Working on CV/Detection
- `P1-cv-guide.md` — CV techniques, ROI definitions, per-game detection methods

## P2 — Load When Working on Backend↔Frontend Communication
- `P2-ws-protocol.md` — WebSocket message format, flow, examples

## P3 — Load When Working on Overlay UI or Anti-Cheat
- `P3-overlay-patterns.md` — Widget patterns, rendering strategy, anti-cheat rules

## Update Rules
- After any session that changes architecture → update CLAUDE.md
- After adding a game or changing detection → update P1
- After changing WS protocol → update P2
- After changing overlay behavior → update P3
- Keep CLAUDE.md under 150 lines
- Date-stamp significant changes in commit messages
