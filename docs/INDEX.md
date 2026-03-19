# Documentation Index

Priority-layered system. Only P0 is auto-loaded every session.

## P0 — Always Loaded
- `../CLAUDE.md` — Project context, architecture, commands, constraints

## P1 — Load When Working on CV/Detection
- `P1-cv-guide.md` — Event detection pipeline, CLIP classifier, per-game setup

## P2 — Load When Working on Backend↔Frontend Communication
- `P2-sse-protocol.md` — SSE message format, REST endpoints, message flow

## P3 — Load When Working on Overlay UI or Anti-Cheat
- `P3-overlay-patterns.md` — Character avatar system, speech bubble, shortcuts, anti-cheat

## Update Rules
- After any session that changes architecture → update CLAUDE.md
- After adding a game or changing detection → update P1
- After changing SSE protocol → update P2
- After changing overlay behavior → update P3
- Keep CLAUDE.md under 150 lines
- Date-stamp significant changes in commit messages
