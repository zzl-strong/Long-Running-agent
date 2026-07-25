## Continue Working: Next Feature

You have completed the previous feature. Now start working on:

**Feature ID**: {feature_id}
**Description**: {feature_desc}
**Acceptance Command**: `{acceptance_command}`
**Expected exit_code**: {expect_exit_code}

Work Steps:
1. Implement this feature
2. Run the acceptance command to confirm it passes
3. Run ALL tests to catch regressions: `cd workspace && python -m pytest tests/ -q`
4. Update the status of {feature_id} in task_state.json — also increment `attempts` by 1
5. Then continue reading task_state.json to find the next pending feature

**Keep working, don't stop. The context window is not yet full — make full use of it.**
