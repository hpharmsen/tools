# tools

instructions for creating single file tools

## System Context: Single-File HTML Tool Construction

**Goal:** Create self-contained, serverless, single-file HTML utilities that are easy to host, distribute, and maintain.

### 1. Core Architecture Guidelines
#### Tool structure
* Each folder in the root of the project contains it's own tool. So for each tool we need a new folder.
* **The Single-File objective: ** Try to create the tool in it's folder in a single `index.html` file.
* CSS must be inline within `<style>` tags.
* JavaScript must be inline within `<script>` tags.
* **Rationale:** Ensures ease of hosting (GitHub Pages), portability (copy-pasting), and eliminates deployment friction.


#### No Build Steps
* **STRICTLY FORBIDDEN:** React, JSX, TypeScript, Webpack, Vite, npm install, or node_modules.
* **Rationale:** Build steps break the "copy-paste" workflow and make self-hosting difficult.
* **Vanilla JS & DOM:** Use modern Vanilla JavaScript (ES6+). 
* Direct DOM manipulation is preferred over framework abstractions for these specific tools.

### 2. Dependency Management
* **CDN Only:** If libraries are required (e.g., PDF.js, Tesseract.js, Pyodide), load them directly via `<script src="...">` tags pointing to reliable CDNs.
* *Preferred Sources:* cdnjs, jsDelivr, unpkg.
* *Versioning:* Always pin to a specific version number in the URL to ensure stability.


### 3. State Management Patterns* **Shareable State (URL):**
* Store application state (configurations, active tabs, small inputs) in the URL Query Parameters or URL Hash.
* **Goal:** Allow users to bookmark or share a specific state of the tool.

* **Persistent/Secret State (localStorage):**
* Store large data blobs, user preferences, or **API Keys** in `localStorage`.
* Ask the user for API keys where they are not available or no longer valid
* **Never** send API keys to a server. They must remain client-side.
* *Pattern:* Check `localStorage` for a key; if missing, prompt the user via `window.prompt` or a UI modal, then save it.


### 4. Input/Output Patterns* 
#### The "Clipboard" Pattern
* **Input:** Allow users to paste content directly into the window or a textarea. Handle `paste` events to capture rich text or binary data.
* **Output:** Provide large, clear "Copy to Clipboard" buttons for the result.

#### File Handling (Local)
* Use `<input type="file">`.
* Process files entirely in the browser using `FileReader`, `URL.createObjectURL`, or `ArrayBuffers`.
* **Do not upload files to a server.**
* **Downloads:** Generate files (JSON, CSV, Images) client-side using `Blob` objects and trigger downloads dynamically via a hidden `<a>` tag.


### 5. Advanced Capabilities (Client-Side)* **CORS APIs:**
* Fetch data directly from CORS-enabled public APIs (e.g., GitHub, PyPI, iNaturalist).
* Connect to LLM providers (OpenAI, Anthropic, Gemini) directly from the browser using user-provided keys.


#### Python in Browser
* Use **Pyodide** via CDN to run Python code (Pandas, NumPy, etc.) if the logic is too complex for JavaScript or requires specific Python libraries.


#### WebAssembly (Wasm)
* Utilize Wasm libraries (via CDN) for heavy computing tasks like OCR (Tesseract), Video processing (FFmpeg), or Image compression.



### 6. Design & UX
* **Mobile Friendly:** Ensure buttons are touch-friendly.
* **Visual Feedback:** Provide loading states, error messages, and immediate visual feedback for actions (e.g., "Copied!" toast notifications).
* **Debug Mode:** When applicable, visualize invisible data (JSON structure, EXIF data, raw clipboard contents) to help the user understand the underlying data.

---

## Example Prompt for Tool Generation
When asking the agent to build a tool, use this format:

> "Build a single-file HTML tool that [functionality]. No React. Use [Library Name] from a CDN. Ensure it allows users to [Input Method] and [Output Method]. Save the API key in localStorage."
