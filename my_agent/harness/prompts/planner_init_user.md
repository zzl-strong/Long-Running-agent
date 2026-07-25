Please decompose the following task description into a structured feature list and output a task state file in JSON format.

Task ID: {task_id}

Task Description:
{spec_content}

Please directly output the complete task_state.json content (JSON format), including milestones and features. Each feature must include an executable acceptance command.

Important: Ensure that JSON strings do not contain unescaped newlines. In command strings, use && and || to separate multiple commands; do not use multiple lines. Try to merge related small tasks into a single feature to avoid over-splitting.
