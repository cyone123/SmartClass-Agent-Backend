---
name: html-interactive
description: Generate a single runnable HTML interactive activity, mini game, or teaching experiment page that can be opened directly in a browser or iframe.
compatibility: |
  Requires only the host browser and either Python or Node.js for simple file generation.
  Do not use local frontend build tools or install dependencies at runtime. Prefer a single
  self-contained `.html` file with inline CSS and JavaScript, or CDN-only assets when necessary.
allowed-tools:
  - list_workspace_files
  - read_workspace_file
  - write_workspace_file
  - run_workspace_code
metadata:
  default-output: html
  preferred-runtime: python
---

# HTML Interactive Skill

Use this skill when the workflow needs a runnable teaching interaction artifact such as:

- a mini game
- an interactive experiment
- a simple quiz or drag-and-drop activity
- a simulation page for classroom demonstration

## Core Rules

- The final deliverable must be a single `.html` file.
- The file must run directly in a browser or iframe without a local build step.
- Prefer inline CSS and JavaScript.
- If you use external assets, they must be browser-loadable URLs such as public CDNs.
- Do not use `shell` to run npm, pnpm, yarn, vite, webpack, or other build tools.
- Use workspace tools only, and write the final artifact into `AGENT_OUTPUT_DIR`.

## Recommended Flow

1. Read the user goal, teaching design plan, and any attachment summary.
2. Decide the interaction type and the minimum viable interaction loop.
3. Write a single `.html` file generator script or write the final `.html` file directly.
4. If you generate via script, run it with `run_workspace_code`.
5. Verify the final `.html` file exists under `AGENT_OUTPUT_DIR`.

## Quality Bar

- The page should be immediately usable by a teacher or student.
- Keep the layout clear on desktop screens.
- Avoid external dependencies unless they materially improve the result.
- The interaction should explain itself with concise labels or instructions.

## Failure Handling

- If the requested interaction depends on unavailable runtime capabilities, explain that clearly.
- If the request is underspecified, produce a sensible teaching-friendly default instead of blocking.
