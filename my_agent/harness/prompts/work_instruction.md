## Work Queue

Start with these features (ordered by priority). Details are in task_state.json which you already read:
{work_queue_items}

### Workflow
Complete workflow for each feature:
1. Read tests first to understand expected behavior, then implement
2. Run the acceptance command to confirm it passes
3. **Run ALL tests** to catch regressions: `cd workspace && python -m pytest tests/ -q`
4. Update the feature's status in `.agent/memory/task_state.json` — also increment `attempts` by 1 (never decrease)
5. Read task_state.json to find the next pending feature and continue

**Context window is large — work continuously on multiple features per session.** The system will auto-end the session when context is nearly full.
