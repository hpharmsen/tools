# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A collection of single-file HTML web tools hosted on GitHub Pages. Each tool is self-contained, serverless, and runs entirely in the browser.

## Architecture

- **Root `index.html`**: Landing page that dynamically loads tools from subdirectories via GitHub API
- **Tool structure**: Each tool lives in its own folder with:
  - `index.html` - The complete tool (HTML + inline CSS + inline JS)
  - `meta.json` - Metadata for the landing page (`name`, `description`, `icon`)
- **Hosting**: GitHub Pages at the domain specified in `CNAME`

## Creating a New Tool

1. Create a new folder in the project root (folder name becomes the URL path)
2. Create `index.html` with all CSS in `<style>` tags and all JS in `<script>` tags
3. Create `meta.json` with: `{"name": "...", "description": "...", "icon": "..."}`

## Core Constraints

- **Single-file only**: No external CSS/JS files, no build steps
- **No frameworks**: React, Vue, TypeScript, Webpack, npm are forbidden
- **CDN dependencies**: Use versioned URLs from cdnjs, jsDelivr, or unpkg
- **Client-side only**: Never upload files or send data to servers

## Git Workflow

- **Work in main branch**: Always work directly in main. No feature branches or pull requests.
- **Commit and push immediately**: After completing changes, commit and push to main so they go live on GitHub Pages.
- **Commit message style**: Use short, descriptive messages (e.g., "Add calculator tool", "Fix paste handling in clipboard-viewer").

## State Management

- **URL params/hash**: For shareable state (configurations, small inputs)
- **localStorage**: For API keys and user preferences (prompt user if missing)

## Common Patterns

- **Input**: File picker (`<input type="file">`), paste events, drag-and-drop
- **Output**: Copy to clipboard buttons, client-side file downloads via Blob
- **Files**: Process with FileReader/URL.createObjectURL, never upload
- **Heavy compute**: Use Pyodide (Python) or Wasm libraries via CDN
