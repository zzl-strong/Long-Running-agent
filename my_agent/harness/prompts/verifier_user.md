## Tier-2 Verification Task

Perform an independent code-quality and contract review of this feature's implementation.

**IMPORTANT**: Tier-1 already executed the automated acceptance test. You do NOT need to re-run it.
Your job is to find issues that automated testing misses.

### Feature
- ID: {feature_id}
- Description: {feature_desc}
- Dependencies: {dependencies}

### Tier-1 Result
{tier1_result}

### What to Check (distinct from Tier-1)
1. **API Contract**: Do the exported names, class signatures, and method parameters match what the feature description requires?
2. **Edge Cases**: Read the test files — do they cover empty inputs, None, missing keys, invalid types? Does the source code handle these correctly?
3. **Code Quality**: Look for logic errors, missing error handling, or inconsistency with the rest of the codebase.
4. **Constraint Compliance**: Check .agent/memory/decisions.md — does the code violate any documented decisions?

### Process
1. Read ONLY the source files and test files relevant to THIS feature — do not explore unrelated code
2. Check .agent/memory/decisions.md for any constraints
3. Perform the above checks
4. Deliver your verdict — do not get stuck in endless analysis

{spec_section}
Focus exclusively on feature {feature_id}. Other features are verified separately. End with VERDICT: pass|fail and specific EVIDENCE (cite file:line).
