# How to Run This Project on Your Mac

**What you need:** Mac · VS Code or Cursor · Claude Code subscription

---

## 1. Install the tools (one-time)

**VS Code** → https://code.visualstudio.com  
**or Cursor** → https://cursor.com

**Python 3.11+** → https://www.python.org/downloads  
*(Click the big yellow "Download Python" button)*

---

## 2. Install Claude Code in VS Code / Cursor

1. Open VS Code or Cursor
2. Click the **Extensions** icon in the left sidebar (looks like 4 squares)
3. Search for **`Claude Code`**
4. Click **Install**
5. Sign in with your Anthropic account when prompted

---

## 3. Get the project

1. Open VS Code / Cursor
2. Press **`Cmd + Shift + P`** → type **Clone** → select **"Git: Clone Repository"**
3. Paste this URL:
   ```
   https://github.com/techteampeer/lead-gen.git
   ```
4. Choose where to save it on your Mac → click **Open**

---

## 4. Open Claude Code and let it set up everything

1. In VS Code / Cursor, open the **Claude Code** panel
2. Type this message:

   > *Set up this project — create a virtual environment, install all dependencies, and install Playwright*

3. Claude Code will run all the setup commands automatically. Just approve when asked.

---

## 5. Run the pipeline

In the Claude Code panel, type:

> *Run the lead gen pipeline*

Claude Code runs the scraper across all job sources (Dice, Greenhouse, Lever, Ashby, Wellfound) and saves the results. This takes about **10–15 minutes**.

---

## 6. Launch the dashboard

In the Claude Code panel, type:

> *Launch the dashboard*

Claude Code starts a local server and opens the dashboard in your browser at:

```
http://localhost:8765/dashboard.html
```

You'll see all the scored and ranked leads ready to review.

---

## That's it!

Every time you want fresh leads, just open the project and tell Claude Code:

> *Run the pipeline and launch the dashboard*

---

## Useful things to ask Claude Code

> *"Show me all companies with a score above 70"*  
> *"Which companies are HIGH urgency?"*  
> *"Add this job board as a new source: [paste URL]"*  
> *"Why did this company get a low score?"*  
> *"What happened in the last pipeline run?"*
