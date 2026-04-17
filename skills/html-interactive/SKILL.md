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
  - replace_workspace_text
  - run_workspace_code
metadata:
  default-output: html
  preferred-runtime: python
---

# HTML Interactive Skill

Use this skill to create a runnable teaching interaction artifact such as:

- a mini game
- an interactive experiment
- a simple quiz or drag-and-drop activity
- a simulation page for classroom demonstration

The generated page should help students learn through:
- visualization
- interaction
- guided exploration
- animation
- step-by-step experiments
- instant feedback
- concept reinforcement

## Core Rules

- The final deliverable must be a single `.html` file.
- The file must run directly in a browser or iframe without a local build step.
- Prefer inline CSS and JavaScript.
- If you use external assets, they must be browser-loadable URLs such as public CDNs.
- Do not use `shell` to run npm, pnpm, yarn, vite, webpack, or other build tools.
- Use workspace tools only, and write the final artifact into `AGENT_OUTPUT_DIR`.
- Write a single `.html` file generator script or write the final `.html` file directly.

## Recommended workflow

### Step 1: Understand the teaching intent
Before writing code, identify:
- what students are supposed to learn
- what is hard to understand
- what would benefit from interaction
- what kind of experiment or animation would make the concept intuitive

## Revising Existing HTML Artifacts

- When the task is to revise an existing HTML artifact, first read `source_artifact.html` and `source_summary.json` from the workspace.
- Prefer `replace_workspace_text` for localized copy, style, selector, or logic edits instead of rewriting the whole file.
- Write the revised final HTML file into `AGENT_OUTPUT_DIR`, for example `revised-activity.html`.

## Quality Bar
Summarize internally:
- concept target
- learner level
- best interactive strategy
- likely misconceptions

### Step 2: Transform content into learning interactions
Convert raw teaching content into modules such as:
- concept overview
- guided exploration
- interactive experiment
- animation demonstration
- parameter manipulation
- observation and conclusion
- checkpoint quiz
- summary and reinforcement

Do not merely copy the lesson plan into HTML.

### Step 3: Design page structure
Prefer a structure like this:

1. Header / lesson identity  
2. Learning objectives  
3. Prior knowledge activation  
4. Core concept visualization  
5. Interactive experiment or simulation  
6. Step-by-step guided explanation  
7. Student interaction tasks  
8. Instant feedback / correctness hints  
9. Summary and key takeaways  
10. Practice / reflection prompts  

### Step 4: Choose the right interaction model
Select interaction types based on the subject matter:

#### For science / physics / chemistry / biology
Prefer:
- state-change animations
- process diagrams
- parameter sliders
- simulated experiments
- cause-effect control panels
- before/after comparisons
- observation logs

#### For mathematics
Prefer:
- dynamic graphs
- formula-to-visual mapping
- draggable geometry
- step-by-step derivation reveal
- variable sliders
- error diagnosis interactions

#### For computer science / programming
Prefer:
- algorithm step simulation
- data flow visualization
- code execution state demo
- interactive input/output changes
- stack/queue/tree animation
- tracing exercises

#### For language / humanities
Prefer:
- annotation interactions
- timeline exploration
- branching questions
- reading comprehension checkpoints
- compare-and-contrast panels
- discourse structure maps

### Step 5: Generate the HTML
Produce clean, maintainable HTML with:
- semantic structure
- readable CSS
- clear comments
- accessible labels and buttons
- responsive layout when practical

### Step 6: Verify educational quality
Check that:
- Keep the layout clear on desktop screens and the page is understandable to the target learners
- interaction is not decorative noise
- students can get feedback
- the page can actually be used in teaching

## Revising Existing HTML Artifacts

- When the task is to revise an existing HTML artifact, first read `source_artifact.html` and `source_summary.json` from the workspace.
- Prefer `replace_workspace_text` for localized copy, style, selector, or logic edits instead of rewriting the whole file.
- Write the revised final HTML file into `AGENT_OUTPUT_DIR`, for example `revised-activity.html`.

## Failure Handling

- If the requested interaction depends on unavailable runtime capabilities, explain that clearly.
- If the request is underspecified, produce a sensible teaching-friendly default instead of blocking.
