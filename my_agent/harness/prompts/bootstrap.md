## Session Bootstrap (fixed opening sequence)

You are now a brand new session. Follow these steps to understand the project from scratch:

### Step 1: Verify Environment
Run: `bash: git log --oneline -15 2>/dev/null || echo '(not a git repository)'`
Verify working directory and recent commit history.

### Step 2: Read Recent Progress
Run: `read: {rel_memory}/progress.md` (read last 50 lines only)
Understand what recent sessions have done.

### Step 3: Read Task Status
Run: `read: {rel_state}`
Understand current status and next steps for all features.
{handoff_step}
{spec_step}
**IMPORTANT**: The spec is the authoritative source. It contains exact API signatures (parameter names, attribute names, return types). Follow the spec literally — do not substitute your own naming conventions. If the spec says `self.repository`, use `repository`, not `_repository`.
### Step {step_skills}: Read Skills Index
Run: `read: {rel_skills}/INDEX.md`
Learn about reusable skills and experience (index only; read full text as needed).

### Step {step_decisions}: Read Architecture Decisions
Run: `read: {rel_memory}/decisions.md` (read last 50 lines only)
Understand architectural constraints and decisions made in previous sessions.

### Step {step_facts}: Read Recent Facts
Run: `read: {rel_memory}/facts.md` (read last 50 lines only)
Learn from discoveries and contract deviations recorded by previous sessions.

### Step {step_env}: Verify Environment
Run: `bash: cd workspace && python -c "print('env ok')"` (or other smoke test)
Ensure the environment is not affected by leftover issues from the previous session.

### Step {step_start}: Start Working
After completing the above steps, begin implementing features from the work queue below.
