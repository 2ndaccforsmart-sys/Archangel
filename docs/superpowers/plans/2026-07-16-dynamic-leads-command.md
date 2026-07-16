# Dynamic Leads and Scrapling Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement dynamic `leads` parameter filters and refine Scrapling fallback logic.

---

### Task 1: Update scraper.py

**Files:**
- Modify: `archangel/agents/scraper.py`

- [ ] **Step 1: Rewrite scraper.py**
  Replace `scraper.py` with version using `"__FALLBACK__"` token fallback checks.

- [ ] **Step 2: Commit scraper.py changes**
  ```bash
  git add archangel/agents/scraper.py
  git commit -m "refactor: use clear fallback tokens for SmartScraper routing"
  ```

---

### Task 2: Update Leads command and Help text in bot.py

**Files:**
- Modify: `archangel/plugins/telegram_bridge/bot.py`

- [ ] **Step 1: Update leads_handler and help text**
  - Implement `SITE_SHORTCUTS` and `_parse_site_filter` helper.
  - Replace `leads_handler` to parse site filters, construct context-aware LLM prompts, and cache results.
  - Update `start_handler` leads description to `leads <query> [site:<platform>] - Find leads on any platform`.

- [ ] **Step 2: Commit bot.py changes**
  ```bash
  git add archangel/plugins/telegram_bridge/bot.py
  git commit -m "feat: make leads command dynamic with site filter parameter"
  ```
