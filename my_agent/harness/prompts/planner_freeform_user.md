Please decompose the following task description into a structured feature list and output a task state file in JSON format.

Task ID: {task_id}

Task Description:
{goal}

Notes:
1. If the description is vague, make reasonable assumptions and record them in the notes field (tagged [Assumption])
2. Decompose the task into concrete, verifiable features, each with an acceptance command
3. Favor a minimal viable implementation (MVP); do not over-engineer
4. Each milestone should contain 3-8 features, ordered by implementation sequence
5. If the description is too vague to decompose, output a clarification feature

Please directly output the complete JSON (including milestones and features), ensuring JSON strings contain no unescaped newlines.
